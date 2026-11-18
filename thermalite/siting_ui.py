"""Pack siting results into compact, columnar JSON files for the web UI."""
from __future__ import annotations

import csv
import json
from pathlib import Path

STATE_NAMES = {"NJ": "New Jersey", "WA": "Washington"}

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
