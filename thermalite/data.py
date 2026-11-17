"""Heat sources, heat sinks, and CSV loading."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from .assumptions import COOLING_DEFAULTS


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    lat: float
    lon: float
    it_load_mw: float
    cooling: str
    temp_c: float
    recoverable_fraction: float

    @property
    def annual_heat_mwh(self) -> float:
        """Recoverable heat per year. Nearly all IT electricity ends up as heat."""
        return self.it_load_mw * self.recoverable_fraction * 8760


@dataclass(frozen=True)
class Sink:
    id: str
    name: str
    type: str
    lat: float
    lon: float
    annual_heat_mwh: float
    supply_temp_c: float
    profile: str | None = None
    hdd_shape: tuple | None = None  # 12 monthly heating degree days, from climate.py


def _opt_float(row: dict, key: str) -> float | None:
    v = (row.get(key) or "").strip()
    return float(v) if v else None


def load_sources(path: str | Path) -> list[Source]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            cooling = row["cooling"].strip()
            if cooling not in COOLING_DEFAULTS:
                raise ValueError(f"{row['id']}: cooling must be one of {sorted(COOLING_DEFAULTS)}")
            d_temp, d_frac = COOLING_DEFAULTS[cooling]
            temp = _opt_float(row, "source_temp_c")
            frac = _opt_float(row, "recoverable_fraction")
            out.append(Source(
                id=row["id"], name=row["name"],
                lat=float(row["lat"]), lon=float(row["lon"]),
                it_load_mw=float(row["it_load_mw"]), cooling=cooling,
                temp_c=d_temp if temp is None else temp,
                recoverable_fraction=d_frac if frac is None else frac,
            ))
    return out


def load_sinks(path: str | Path) -> list[Sink]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append(Sink(
                id=row["id"], name=row["name"], type=row["type"].strip(),
                lat=float(row["lat"]), lon=float(row["lon"]),
                annual_heat_mwh=float(row["annual_heat_mwh"]),
                supply_temp_c=float(row["supply_temp_c"]),
                profile=(row.get("profile") or "").strip() or None,
            ))
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
