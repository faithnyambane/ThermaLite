"""Pack siting results into compact, columnar JSON files for the web UI."""
from __future__ import annotations

import csv
import json
from pathlib import Path

STATE_NAMES = {"NJ": "New Jersey", "WA": "Washington", "OR": "Oregon", "TX": "Texas",
               "VA": "Virginia", "NC": "North Carolina", "PA": "Pennsylvania"}

# Reference labels for the map (city centre coordinates).
CITIES = {
    "NJ": [("Newark", 40.7357, -74.1724), ("Jersey City", 40.7178, -74.0431), ("Paterson", 40.9168, -74.1718),
           ("New Brunswick", 40.4862, -74.4518), ("Trenton", 40.2206, -74.7597), ("Camden", 39.9259, -75.1196),
           ("Vineland", 39.4864, -75.0260), ("Atlantic City", 39.3643, -74.4229),
           ("Newton", 41.0582, -74.7527), ("Morristown", 40.7968, -74.4815), ("Toms River", 39.9537, -74.1979)],
    "WA": [("Seattle", 47.6062, -122.3321), ("Tacoma", 47.2529, -122.4443), ("Bellingham", 48.7519, -122.4787),
           ("Vancouver", 45.6387, -122.6615), ("Wenatchee", 47.4235, -120.3103), ("Quincy", 47.2343, -119.8526),
           ("Yakima", 46.6021, -120.5059), ("Tri-Cities", 46.2112, -119.1372), ("Spokane", 47.6588, -117.4260),
           ("Everett", 47.9790, -122.2021), ("Arlington", 48.1987, -122.1251), ("Olympia", 47.0379, -122.9007),
           ("Mount Vernon", 48.4212, -122.3341)],
    "OR": [("Portland", 45.5152, -122.6784), ("Hillsboro", 45.5229, -122.9898), ("Salem", 44.9429, -123.0351),
           ("Eugene", 44.0521, -123.0868), ("Bend", 44.0582, -121.3153), ("Prineville", 44.2999, -120.8345),
           ("The Dalles", 45.5946, -121.1787), ("Medford", 42.3265, -122.8756), ("Boardman", 45.8399, -119.7006)],
    "TX": [("Dallas", 32.7767, -96.7970), ("Fort Worth", 32.7555, -97.3308), ("Houston", 29.7604, -95.3698),
           ("San Antonio", 29.4241, -98.4936), ("Austin", 30.2672, -97.7431), ("El Paso", 31.7619, -106.4850),
           ("Abilene", 32.4487, -99.7331), ("Amarillo", 35.2220, -101.8313), ("Lubbock", 33.5779, -101.8552)],
    "VA": [("Ashburn", 39.0438, -77.4874), ("Manassas", 38.7509, -77.4753), ("Arlington", 38.8816, -77.0910),
           ("Richmond", 37.5407, -77.4360), ("Norfolk", 36.8508, -76.2859), ("Charlottesville", 38.0293, -78.4767),
           ("Roanoke", 37.2710, -79.9414)],
    "NC": [("Charlotte", 35.2271, -80.8431), ("Raleigh", 35.7796, -78.6382), ("Durham", 35.9940, -78.8986),
           ("Greensboro", 36.0726, -79.7920), ("Asheville", 35.5951, -82.5515), ("Wilmington", 34.2104, -77.8868),
           ("Maiden", 35.5757, -81.2118), ("Lenoir", 35.9140, -81.5390)],
    "PA": [("Philadelphia", 39.9526, -75.1652), ("Pittsburgh", 40.4406, -79.9959), ("Harrisburg", 40.2732, -76.8867),
           ("Allentown", 40.6023, -75.4714), ("Scranton", 41.4090, -75.6624), ("Erie", 42.1292, -80.0851),
           ("State College", 40.7934, -77.8600)],
}


def pack(state: str, siting_json: Path, sources_csv: Path, out: Path) -> dict:
    d = json.loads(siting_json.read_text())
    cells = d["cells"]
    sink_ids = list(d["sinks"])
    sink_pos = {sid: i for i, sid in enumerate(sink_ids)}
    cols = {k: [] for k in ("lat", "lon", "heat", "co2t", "bws", "cdd", "sub", "flood", "prot", "water")}
    alloc = {}
    for i, c in enumerate(cells):
        for k in cols:
            cols[k].append(c[k])
        if c["alloc"]:
            alloc[i] = [[sink_pos[a["sink"]], a["mwh"], a["km"], a["co2"]] for a in c["alloc"]]
    sinks = [[d["sinks"][s]["name"], d["sinks"][s]["type"], round(d["sinks"][s]["lat"], 5),
              round(d["sinks"][s]["lon"], 5), d["sinks"][s]["demand"]] for s in sink_ids]
    dcs = []
    with open(sources_csv, newline="") as f:
        for r in csv.DictReader(f):
            dcs.append([r["name"], round(float(r["lat"]), 5), round(float(r["lon"]), 5), float(r["it_load_mw"])])
    st = state.upper()
    payload = {
        "state": st, "name": STATE_NAMES.get(st, st), "dlat": d["dlat"], "dlon": d["dlon"],
        "cellKm": d["cell_km"], "refMW": d["ref_it_mw"], "gridCO2": d["grid_co2"], "prices": d["prices"],
        "cols": cols, "alloc": alloc, "sinks": sinks, "dcs": dcs,
        "cities": [[n, la, lo] for n, la, lo in CITIES.get(st, [])],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")))
    return {"cells": len(cells), "with_heat": len(alloc), "bytes": out.stat().st_size}
