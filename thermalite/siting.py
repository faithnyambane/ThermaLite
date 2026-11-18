"""Siting: where should a NEW data center go so its heat gets used and its
environmental footprint stays low?

Every ~2 km grid cell in a state is a candidate site for a reference data
center (REF_IT_MW). Each cell gets raw factor values; the UI turns them into
0-1 scores and a weighted total, so weights can change live.

Factors (raw values per cell):
  heat_mwh     heat a data center here could deliver to nearby heat users,
               via a multi-building allocation using the existing physics and
               economics (thermalite.matcher.score), at the state's EIA prices
  grid_co2     state grid CO2 rate, lb/MWh (EPA eGRID2023, state output rate)
  bws          baseline water stress score 0-5 (WRI Aqueduct 4.0)
  cdd          cooling degree days per year, base 18 C (ERA5-Land, 2015-2024)
  sub_km       distance to nearest OSM power substation (km)
  excl_*       share of the cell that is 100-yr flood zone (GLOFAS v2.1),
               protected area (WDPA) or water/wetland (MODIS MCD12Q1)

Earth Engine computes the raster layers on the grid in one sampleRectangle
call per state; Python does substations and heat allocation.
"""
from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

from .assumptions import COOLING_DEFAULTS, DEFAULT, Assumptions
from .data import Sink, Source, haversine_km, load_sinks
from .matcher import score

CELL_KM = 2.0
REF_IT_MW = 50.0
SEARCH_KM = 3.0  # straight-line radius for heat users

# EPA eGRID2023 (rev2, June 2025), Table 3 state output emission rates, CO2 lb/MWh.
GRID_CO2_LB_PER_MWH = {"NJ": 468.3, "WA": 265.1}
EGRID_SOURCE = "EPA eGRID2023 summary tables rev2, Table 3 (state CO2 output emission rate)"


# --------------------------------------------------------------------------- EE

def ee_layers(state: str, project: str = "thermalite") -> dict:
    """Grid + raster factors for a state, as row-major lists."""
    from .climate import init
    ee = init(project)
    st = ee.FeatureCollection("TIGER/2018/States").filter(ee.Filter.eq("STUSPS", state))
    geom = st.geometry()
    (w, s), _, (e, n), _ = geom.bounds().coordinates().get(0).getInfo()[:4]
    lat_mid = (s + n) / 2
    dlat = CELL_KM / 111.32
    dlon = CELL_KM / (111.32 * math.cos(math.radians(lat_mid)))
    proj = ee.Projection("EPSG:4326", [dlon, 0, w, 0, -dlat, n])

    def frac(img, native_m):
        return (img.unmask(0).reproject(crs="EPSG:4326", scale=native_m)
                .reduceResolution(ee.Reducer.mean(), maxPixels=4096).reproject(proj))

    inside = ee.Image(1).clip(geom).unmask(0).reproject(proj).rename("inside")
    aq = (ee.FeatureCollection("WRI/Aqueduct_Water_Risk/V4/baseline_annual")
          .filterBounds(geom).filter(ee.Filter.gte("bws_score", 0)))
    bws = aq.reduceToImage(["bws_score"], ee.Reducer.mean()).reproject(proj).rename("bws")
    daily = (ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate("2015-01-01", "2025-01-01")
             .select("temperature_2m").map(lambda i: i.subtract(291.15).max(0)))
    cdd = daily.sum().divide(10).reproject(proj).rename("cdd")
    flood = frac(ee.ImageCollection("JRC/CEMS_GLOFAS/FloodHazard/v2_1").select("RP100_depth")
                 .mosaic().gt(0), 250).rename("excl_flood")
    wdpa = ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(geom)
    prot = frac(ee.Image(0).paint(wdpa, 1).selfMask(), 250).rename("excl_protected")
    lc = ee.ImageCollection("MODIS/061/MCD12Q1").filterDate("2023-01-01", "2024-01-01").first().select("LC_Type1")
    water = frac(lc.eq(11).Or(lc.eq(17)).selfMask(), 500).rename("excl_water")

    stack = ee.Image.cat([inside, bws, cdd, flood, prot, water]).toFloat().reproject(proj)
    rows = int(math.ceil((n - s) / dlat))
    cols = int(math.ceil((e - w) / dlon))
    region = ee.Geometry.Rectangle([w, n - rows * dlat, w + cols * dlon, n], proj="EPSG:4326", geodesic=False)
    arr = stack.sampleRectangle(region=region, defaultValue=-1).getInfo()["properties"]
    for band in ("bws", "cdd"):  # land-only datasets: fill coastal gaps from neighbours
        _fill_nearest(arr[band], arr["inside"])
    return {"west": w, "north": n, "dlon": dlon, "dlat": dlat, "bands": arr}


def _fill_nearest(grid: list[list], inside: list[list], max_steps: int = 6) -> None:
    """Replace missing (None or < 0) in-state values with the mean of the nearest
    valid ring of neighbours, up to max_steps cells away."""
    nr, nc = len(grid), len(grid[0])

    def ok(v):
        return v is not None and v >= 0

    for i in range(nr):
        for j in range(nc):
            if inside[i][j] != 1 or ok(grid[i][j]):
                continue
            for r in range(1, max_steps + 1):
                vals = [grid[a][b] for a in range(max(0, i - r), min(nr, i + r + 1))
                        for b in range(max(0, j - r), min(nc, j + r + 1)) if ok(grid[a][b])]
                if vals:
                    grid[i][j] = -2 - sum(vals) / len(vals)  # marked filled; decoded below
                    break
    for i in range(nr):
        for j in range(nc):
            v = grid[i][j]
            if v is not None and v <= -2:
                grid[i][j] = -(v + 2)


# ---------------------------------------------------------------- substations

def substations(path: Path) -> list[tuple[float, float]]:
    els = json.loads(path.read_text())["elements"]
    pts = []
    for e in els:
        if "lat" in e:
            pts.append((e["lat"], e["lon"]))
        elif "center" in e:
            pts.append((e["center"]["lat"], e["center"]["lon"]))
    return pts


class _Buckets:
    """Spatial hash for nearest / within-radius lookups."""

    def __init__(self, items, key, size_deg: float = 0.05):
        self.size, self.key, self.cells = size_deg, key, {}
        for it in items:
            lat, lon = key(it)
            self.cells.setdefault((int(lat // size_deg), int(lon // size_deg)), []).append(it)

    def near(self, lat, lon, rings: int):
        ci, cj = int(lat // self.size), int(lon // self.size)
        for di in range(-rings, rings + 1):
            for dj in range(-rings, rings + 1):
                yield from self.cells.get((ci + di, cj + dj), ())

    def nearest_km(self, lat, lon, max_rings: int = 12) -> float:
        for r in range(1, max_rings + 1):
            best = min((haversine_km(lat, lon, *self.key(p)) for p in self.near(lat, lon, r)), default=None)
            if best is not None and best <= r * self.size * 111 * 0.7:
                return best
        return float(max_rings * self.size * 111)


# --------------------------------------------------------------- heat allocation

def allocate(src: Source, sinks: list[Sink], a: Assumptions) -> list[dict]:
    """Greedy multi-building allocation: best net value per MWh first, each
    building getting what it can use until the data center's heat runs out.
    Each building gets its own pipe from the data center."""
    remaining = src.annual_heat_mwh
    candidates = []
    for k in sinks:
        m = score(src, k, a)
        if m.feasible and m.heat_used_mwh > 0:
            candidates.append((m.net_annual_usd / m.heat_used_mwh, k))
    out = []
    for _, k in sorted(candidates, key=lambda t: -t[0]):
        if remaining <= 0:
            break
        frac = remaining / src.annual_heat_mwh
        m = score(replace(src, recoverable_fraction=src.recoverable_fraction * frac), k, a)
        if not m.feasible or m.heat_used_mwh <= 0:
            continue
        source_heat_used = m.heat_used_mwh - m.electricity_mwh
        remaining -= source_heat_used
        out.append({"sink": k.id, "mwh": round(m.heat_used_mwh), "km": round(m.route_km, 2),
                    "net": round(m.net_annual_usd), "co2": round(m.co2_avoided_t)})
    return out


# ----------------------------------------------------------------------- build

def build(state: str, sinks_csv: Path, substations_json: Path, a: Assumptions,
          project: str = "thermalite", cooling: str = "chilled_water") -> dict:
    from .climate import apply_climate

    st = state.upper()
    lay = ee_layers(st, project)
    b = lay["bands"]
    sinks = apply_climate(load_sinks(sinks_csv), project=project)
    sink_idx = _Buckets(sinks, key=lambda k: (k.lat, k.lon), size_deg=0.03)
    subs = _Buckets(substations(substations_json), key=lambda p: p, size_deg=0.05)
    temp, frac = COOLING_DEFAULTS[cooling]

    cells, used_sinks = [], {}
    nrows, ncols = len(b["inside"]), len(b["inside"][0])
    for i in range(nrows):
        for j in range(ncols):
            if b["inside"][i][j] != 1:
                continue
            lat = lay["north"] - (i + 0.5) * lay["dlat"]
            lon = lay["west"] + (j + 0.5) * lay["dlon"]
            src = Source(f"cell{i}_{j}", "candidate", lat, lon, REF_IT_MW, cooling, temp, frac)
            near = [k for k in sink_idx.near(lat, lon, 2) if haversine_km(lat, lon, k.lat, k.lon) <= SEARCH_KM]
            alloc = allocate(src, near, a) if near else []
            for al in alloc:
                used_sinks[al["sink"]] = True
            bws, cdd = b["bws"][i][j], b["cdd"][i][j]
            cells.append({
                "lat": round(lat, 4), "lon": round(lon, 4),
                "heat": sum(al["mwh"] for al in alloc),
                "co2t": sum(al["co2"] for al in alloc),
                "bws": None if bws is None or bws < 0 else round(bws, 2),
                "cdd": None if cdd is None or cdd < 0 else round(cdd),
                "sub": round(subs.nearest_km(lat, lon), 1),
                "flood": round(max(b["excl_flood"][i][j], 0), 2),
                "prot": round(max(b["excl_protected"][i][j], 0), 2),
                "water": round(max(b["excl_water"][i][j], 0), 2),
                "alloc": alloc,
            })
    sink_info = {k.id: {"name": k.name, "type": k.type, "lat": k.lat, "lon": k.lon,
                        "demand": round(k.annual_heat_mwh)} for k in sinks if k.id in used_sinks}
    return {
        "state": st, "cell_km": CELL_KM, "ref_it_mw": REF_IT_MW, "cooling": cooling,
        "dlat": lay["dlat"], "dlon": lay["dlon"],
        "grid_co2": GRID_CO2_LB_PER_MWH[st],
        "prices": {"gas": round(a.gas_price_per_mwh, 1), "elec": round(a.electricity_price_per_mwh, 1)},
        "cells": cells, "sinks": sink_info,
    }
