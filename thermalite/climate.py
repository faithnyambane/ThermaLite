"""Real heating demand seasonality from ERA5-Land, via Google Earth Engine.

For each sink, computes average heating degree days (HDD) per calendar month:
    HDD_day = max(0, base_temp - daily mean 2 m air temperature)
summed by month and averaged over the chosen years. The 12 values replace the
illustrative space-heating curve in seasonal.py.

Dataset: ECMWF/ERA5_LAND/DAILY_AGGR (band temperature_2m, kelvin, ~11 km grid).

One reduceRegions call covers all sinks; results are cached in
data/cache/hdd.json keyed by rounded lat/lon, so repeat runs cost no quota.

Setup (once): `earthengine authenticate`, and a Cloud project registered for
noncommercial Earth Engine use.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .data import Sink

DATASET = "ECMWF/ERA5_LAND/DAILY_AGGR"
DEFAULT_CACHE = Path("data/cache/hdd.json")
DEFAULT_PROJECT = "thermalite"
MONTH_BANDS = [f"m{m:02d}" for m in range(1, 13)]


def _key(lat: float, lon: float, start_year: int, end_year: int, base_c: float) -> str:
    return f"{lat:.3f},{lon:.3f}|{start_year}-{end_year}|base{base_c:g}"


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def init(project: str = DEFAULT_PROJECT):
    import ee  # imported lazily so the rest of ThermaLite runs without it

    try:
        ee.Initialize(project=project)
    except Exception as e:  # noqa: BLE001 - surface a useful message
        raise SystemExit(
            f"Could not start Earth Engine for project {project!r}: {e}\n"
            "Run `earthengine authenticate`, and make sure the project is registered "
            "for noncommercial use at https://code.earthengine.google.com/register"
        ) from e
    return ee


def _monthly_hdd_image(ee, start_year: int, end_year: int, base_c: float):
    """12-band image: mean HDD per calendar month over the year range."""
    base_k = base_c + 273.15
    daily = (ee.ImageCollection(DATASET)
             .filterDate(f"{start_year}-01-01", f"{end_year + 1}-01-01")
             .select("temperature_2m")
             .map(lambda img: ee.Image(base_k).subtract(img).max(0)
                  .copyProperties(img, ["system:time_start"])))
    n_years = end_year - start_year + 1
    bands = [
        daily.filter(ee.Filter.calendarRange(m, m, "month")).sum().divide(n_years).rename(name)
        for m, name in zip(range(1, 13), MONTH_BANDS)
    ]
    return ee.Image.cat(bands)


def fetch_hdd(points: list[tuple[float, float]], project: str = DEFAULT_PROJECT,
              start_year: int = 2015, end_year: int = 2024, base_c: float = 18.0,
              cache_path: Path = DEFAULT_CACHE) -> dict[tuple[float, float], list[float]]:
    """Monthly HDD (12 values, degree-C-days) for each (lat, lon)."""
    cache = _load_cache(cache_path)
    missing = sorted({p for p in points if _key(*p, start_year, end_year, base_c) not in cache})

    if missing:
        ee = init(project)
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([lon, lat]), {"i": i}) for i, (lat, lon) in enumerate(missing)
        ])
        img = _monthly_hdd_image(ee, start_year, end_year, base_c)
        result = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=11132).getInfo()
        for feat in result["features"]:
            props = feat["properties"]
            values = [props.get(b) for b in MONTH_BANDS]
            if any(v is None for v in values):
                lat, lon = missing[props["i"]]
                raise ValueError(f"No ERA5-Land data at ({lat}, {lon}); is the point over open ocean?")
            cache[_key(*missing[props["i"]], start_year, end_year, base_c)] = values
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1))

    return {p: cache[_key(*p, start_year, end_year, base_c)] for p in points}


def apply_climate(sinks: list[Sink], **kwargs) -> list[Sink]:
    """Return sinks with hdd_shape filled from ERA5-Land."""
    hdd = fetch_hdd([(s.lat, s.lon) for s in sinks], **kwargs)
    return [replace(s, hdd_shape=tuple(hdd[(s.lat, s.lon)])) for s in sinks]
