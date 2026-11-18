"""Heat sinks from OpenStreetMap via the Overpass API.

Pulls hospitals, greenhouses, indoor pools and large apartment buildings for a
US state, and estimates annual heat demand from footprint area:

    annual_heat_mwh = footprint_m2 * floors * heat_intensity_kwh_per_m2 / 1000

OSM coverage is incomplete (which is exactly why the greenhouse detector exists),
and the intensities below are placeholders. Data (c) OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import csv
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# type: (supply temp C, heat kWh per m2 of floor per year, default floors, min footprint m2)
# Supply temps [ENGINEERING]; intensities [PLACEHOLDER: replace with CBECS / RECS
# end-use intensities for space + water heating by building type].
SINK_TYPES = {
    "hospital": (80.0, 250.0, 4, 5000),
    "greenhouse": (50.0, 300.0, 1, 1000),
    "pool": (40.0, 400.0, 1, 0),
    "multifamily": (65.0, 90.0, 3, 1500),
}

# One small query per tag: public Overpass servers time out on one big statewide
# query. Each part is cached separately, so a failure only re-runs that part.
PARTS = {
    "hospital": ['way["amenity"="hospital"]', 'way["building"="hospital"]'],
    "greenhouse": ['way["building"="greenhouse"]', 'way["landuse"="greenhouse_horticulture"]'],
    "pool": ['way["leisure"="sports_centre"]["sport"="swimming"]', 'way["leisure"="swimming_pool"]["indoor"="yes"]'],
    "multifamily": ['way["building"="apartments"]'],
}
QUERY = '[out:json][timeout:180];area["ISO3166-2"="US-{state}"]->.s;({body});out tags geom;'


def _overpass(query: str, retries: int = 2) -> bytes:
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(retries):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": "thermalite-research/0.1"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    raw = r.read()
                json.loads(raw)  # validate
                return raw
            except Exception as e:  # noqa: BLE001 - try the next mirror
                last = e
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"All Overpass mirrors failed; last error: {last}")


def fetch(state: str, cache: Path, parts=PARTS) -> list[dict]:
    """Raw Overpass elements for a state. Parts that still fail are skipped with
    a warning; the combined result is cached to `cache`."""
    if cache.exists():
        return json.loads(cache.read_text())["elements"]
    elements, failed = [], []
    for name, filters in parts.items():
        part_cache = cache.with_name(f"{cache.stem}_{name}.json")
        if not part_cache.exists():
            q = QUERY.format(state=state.upper(), body="".join(f"{f}(area.s);" for f in filters))
            try:
                raw = _overpass(q)
            except RuntimeError as e:
                print(f"  warning: OSM part {name!r} failed ({e}); continuing without it")
                failed.append(name)
                continue
            part_cache.parent.mkdir(parents=True, exist_ok=True)
            part_cache.write_bytes(raw)
        part = json.loads(part_cache.read_text())["elements"]
        print(f"  OSM {name}: {len(part)} features")
        elements.extend(part)
    if not failed:  # only write the combined cache once complete
        cache.write_text(json.dumps({"elements": elements}))
    return elements


# Share of a hospital campus polygon that is building footprint, used only when
# OSM has no hospital buildings mapped inside it.  [PLACEHOLDER]
HOSPITAL_SITE_COVERAGE = 0.25
# Indoor pools use ~200-800 MWh/yr (research notes: direct_low_temperature_uses.md);
# cap to stop a large footprint from implying an implausible demand.
POOL_MAX_MWH = 1500
# Upper bound for one hospital: a ~2M sq ft academic medical centre at ~250 kWh/m2
# is roughly 45,000 MWh/yr. Rural campuses with no mapped buildings otherwise
# come out at 100,000-300,000 MWh/yr.  [PLACEHOLDER: replace with CBECS-based sizing]
HOSPITAL_MAX_MWH = 60000
CAPS = {"pool": POOL_MAX_MWH, "hospital": HOSPITAL_MAX_MWH}


def classify(tags: dict) -> str | None:
    if tags.get("amenity") == "hospital" or tags.get("building") == "hospital":
        return "hospital"
    if tags.get("building") == "greenhouse" or tags.get("landuse") == "greenhouse_horticulture":
        return "greenhouse"
    if tags.get("sport") == "swimming" or tags.get("leisure") == "swimming_pool":
        # Private (residential/hotel) and outdoor (summer-only) pools are not
        # year-round community heat users. Most OSM swim "sports centres" are
        # outdoor swim clubs, so require evidence of a building or indoor pool.
        if tags.get("access") in ("private", "customers") or tags.get("indoor") == "no" or tags.get("covered") == "no":
            return None
        if tags.get("indoor") != "yes" and not tags.get("building"):
            return None
        return "pool"
    if tags.get("building") == "apartments":
        return "multifamily"
    return None


def polygon_area_m2(geom: list[dict]) -> float:
    """Shoelace area on a local equirectangular projection (fine below ~10 km)."""
    if len(geom) < 3:
        return 0.0
    lat0 = math.radians(sum(p["lat"] for p in geom) / len(geom))
    k = 111_320.0
    xs = [p["lon"] * k * math.cos(lat0) for p in geom]
    ys = [p["lat"] * k for p in geom]
    return abs(sum(xs[i] * ys[i - 1] - xs[i - 1] * ys[i] for i in range(len(xs)))) / 2


def _centroid(geom):
    return sum(p["lat"] for p in geom) / len(geom), sum(p["lon"] for p in geom) / len(geom)


def _floors(tags: dict, default: int) -> float:
    try:
        return max(1.0, float(tags.get("building:levels", "").split(";")[0]))
    except ValueError:
        return float(default)


def to_features(elements: list[dict]) -> list[dict]:
    feats = []
    for e in elements:
        t = classify(e.get("tags", {}))
        if not t or not e.get("geometry"):
            continue
        lat, lon = _centroid(e["geometry"])
        feats.append({"osm_id": e["id"], "type": t, "lat": lat, "lon": lon,
                      "area_m2": polygon_area_m2(e["geometry"]), "tags": e.get("tags", {})})
    return feats


def cluster(feats: list[dict], radius_m: float) -> list[list[dict]]:
    """Greedy single-link clustering: nearby greenhouse houses form one operation."""
    from .data import haversine_km

    if radius_m <= 0:  # no grouping: avoid the O(n^2) scan (21k+ apartment buildings in WA)
        return [[f] for f in feats]
    clusters: list[list[dict]] = []
    for f in sorted(feats, key=lambda f: -f["area_m2"]):
        for c in clusters:
            if haversine_km(f["lat"], f["lon"], c[0]["lat"], c[0]["lon"]) * 1000 <= radius_m:
                c.append(f)
                break
        else:
            clusters.append([f])
    return clusters


def to_sinks_csv(state: str, out: Path, cache: Path | None = None) -> dict:
    cache = cache or Path(f"data/raw/osm_{state.lower()}.json")
    feats = to_features(fetch(state, cache))
    rows, counts = [], {}
    by_type: dict[str, list] = {}
    for f in feats:
        by_type.setdefault(f["type"], []).append(f)

    for t, items in by_type.items():
        temp, kwh_m2, default_floors, min_fp = SINK_TYPES[t]
        # Greenhouse buildings often sit inside a greenhouse landuse polygon, and
        # hospital buildings inside a hospital campus: cluster to avoid double counting.
        groups = cluster(items, 300 if t in ("greenhouse", "hospital") else 0)
        for g in groups:
            lead = g[0]
            bldg = sum(x["area_m2"] for x in g if x["tags"].get("building"))
            if t == "greenhouse":
                # A greenhouse landuse polygon is mostly glass; buildings inside it would
                # double count, so take the larger of the two, never the sum.
                footprint, floors = max(bldg, max(x["area_m2"] for x in g)), 1.0
            elif t == "hospital":
                # Hospital campus polygons include lawns and parking. Use mapped
                # buildings when present; otherwise assume a share of the campus is built.
                if bldg > 0:
                    footprint = bldg
                else:
                    footprint = max(x["area_m2"] for x in g) * HOSPITAL_SITE_COVERAGE
                floors = _floors(next((x["tags"] for x in g if x["tags"].get("building:levels")), lead["tags"]),
                                 default_floors)
            else:
                footprint, floors = lead["area_m2"], _floors(lead["tags"], default_floors)
            if footprint < min_fp:
                continue
            name = next((x["tags"].get("name") for x in g if x["tags"].get("name")), None)
            rows.append({
                "id": f"{t[:2].upper()}{lead['osm_id']}",
                "name": name or f"Unnamed {t} (OSM {lead['osm_id']})",
                "type": t, "lat": round(lead["lat"], 6), "lon": round(lead["lon"], 6),
                "annual_heat_mwh": round(min(footprint * floors * kwh_m2 / 1000, CAPS.get(t, float("inf")))),
                "supply_temp_c": temp, "profile": "",
                "footprint_m2": round(footprint), "floors": floors,
                "osm_features": len(g), "demand_estimated": "yes",
            })
            counts[t] = counts.get(t, 0) + 1

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return counts
