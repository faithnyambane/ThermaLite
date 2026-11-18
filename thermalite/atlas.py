"""Heat sources from the IM3 Open Source Data Center Atlas (PNNL).

Dataset: Mongird et al., "IM3 Open Source Data Center Atlas", OSTI 2550666,
doi:10.57931/2550666. Locations derive from OpenStreetMap (ODbL). The file used
here is the footprint layer published with PNNL's web map
(github.com/IMMM-SFA/datacenter-atlas). It carries name, operator, state and
footprint square footage, but NOT power or cooling type, so IT load is an
estimate (see DC_WATTS_PER_SQFT in assumptions.py).

Pipeline stage 1 (ingest). `thermalite sources --state VA` -> data/va/sources.csv.
The siting tool uses these only to draw existing data centers on the map.
"""
from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path

from .assumptions import DC_DEFAULT_COOLING, DC_WATTS_PER_SQFT

URL = "https://raw.githubusercontent.com/IMMM-SFA/datacenter-atlas/main/static/im3_datacenter_footprints.geojson"
RAW = Path("data/raw/im3_datacenter_footprints.geojson")


def download(path: Path = RAW) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "thermalite-research/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path


def _rings(geom: dict):
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    return []


def centroid(geom: dict) -> tuple[float, float]:
    """(lat, lon). Vertex average of outer rings: fine at building scale."""
    if geom["type"] == "Point":
        lon, lat = geom["coordinates"][:2]
        return lat, lon
    pts = [p for ring in _rings(geom) for p in ring[:-1]]
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


# Footprints above this are almost certainly land parcels or whole campuses
# mis-measured as floor area (e.g. two Ocean County, NJ "campuses" at 2.9M and
# 8.6M sq ft). They go to a review file instead of inflating the totals.
MAX_PLAUSIBLE_SQFT = 1_000_000


def to_sources_csv(states: list[str], out: Path, raw: Path = RAW,
                   watts_per_sqft: float = DC_WATTS_PER_SQFT) -> dict:
    """Write a ThermaLite sources CSV for the given state abbreviations.
    Implausibly large footprints are written to <out>_review.csv instead."""
    feats = json.loads(download(raw).read_text())["features"]
    states_u = {s.upper() for s in states}
    rows, review, skipped = [], [], 0
    for i, f in enumerate(feats):
        p = f["properties"]
        if p.get("state_abb") not in states_u:
            continue
        if not p.get("sqft"):
            skipped += 1
            continue
        lat, lon = centroid(f["geometry"])
        name = p.get("name") or (f"{p['operator']} site" if p.get("operator") else f"Unnamed site ({p.get('county')})")
        (review if p["sqft"] > MAX_PLAUSIBLE_SQFT else rows).append({
            "id": f"DC{i}", "name": name, "lat": round(lat, 6), "lon": round(lon, 6),
            "it_load_mw": round(p["sqft"] * watts_per_sqft / 1e6, 2),
            "cooling": DC_DEFAULT_COOLING, "source_temp_c": "", "recoverable_fraction": "",
            "operator": p.get("operator") or "", "county": p.get("county") or "",
            "sqft": p["sqft"], "atlas_type": p.get("type"), "it_load_estimated": "yes",
        })
    out.parent.mkdir(parents=True, exist_ok=True)
    review_path = out.with_name(out.stem + "_review.csv")
    for path, data in ((out, rows), (review_path, review)):
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list((rows or review)[0].keys()) if (rows or review) else ["id"])
            w.writeheader()
            w.writerows(data)
    return {"written": len(rows), "needs_review": len(review), "skipped_no_sqft": skipped}
