"""National screen: where in the US can recovered data center heat pay at all?

For each state, the margin per MWh of heat delivered (before pipe and capital):

    margin = gas_price / boiler_efficiency - electricity_price / COP

using EIA commercial prices for that state, and the model's own heat pump COP
for a typical case (30 C chilled-water data center heat -> 70 C building loop).
A state with a thin or negative margin cannot pay for pipe at any distance;
a fat margin is necessary (not sufficient) for viable pairings.

Prices (EIA, downloaded to data/raw/eia/):
  electricity: Electric Power Monthly Table 5.6.B, commercial, Jan-Aug 2026 YTD
  natural gas: Natural Gas Prices, commercial, annual 2025 ($/Mcf)
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from . import physics
from .assumptions import DEFAULT, Assumptions

MCF_TO_MWH = 1.036 * 0.293071  # EIA average heat content 1,036 Btu/cf; 1 MMBtu = 0.293071 MWh

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def electricity_prices(path: Path) -> dict[str, float]:
    """State -> commercial $/MWh from EIA EPM Table 5.6.B (first data column = latest YTD)."""
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    out = {}
    for row in ws.iter_rows(min_row=5, values_only=True):
        name = (row[0] or "").strip()
        if name in STATE_ABBR and isinstance(row[3], (int, float)):
            out[STATE_ABBR[name]] = row[3] * 10  # cents/kWh -> $/MWh
    return out


def gas_prices(path: Path) -> tuple[dict[str, float], dict[str, int]]:
    """State -> commercial $/MWh of fuel, from each state's latest reported year
    in EIA's annual series (a few states lag a year). Also returns the year used."""
    import xlrd

    s = xlrd.open_workbook(str(path)).sheet_by_index(1)
    header = s.row_values(2)
    out, years = {}, {}
    for col, title in enumerate(header[1:], start=1):
        name = title.split(" Price of Natural Gas")[0]
        if name not in STATE_ABBR:
            continue
        for r in range(s.nrows - 1, 2, -1):
            v = s.row_values(r)[col]
            if isinstance(v, float):
                out[STATE_ABBR[name]] = v / MCF_TO_MWH
                years[STATE_ABBR[name]] = xlrd.xldate_as_datetime(s.row_values(r)[0], 0).year
                break
    return out, years


def data_centers_by_state(atlas_geojson: Path) -> Counter:
    feats = json.loads(atlas_geojson.read_text())["features"]
    return Counter(f["properties"].get("state_abb") for f in feats)


def screen(elec: dict, gas: dict, dcs: Counter, a: Assumptions = DEFAULT,
           source_c: float = 30.0, sink_c: float = 70.0, gas_years: dict | None = None) -> list[dict]:
    cop = physics.heat_pump_cop(source_c, sink_c, a)
    rows = []
    for st in sorted(set(elec) & set(gas)):
        g, e = gas[st], elec[st]
        gas_value = g / a.boiler_efficiency
        margin = gas_value - e / cop
        rows.append({
            "state": st, "data_centers": dcs.get(st, 0),
            "gas_usd_per_mwh": round(g, 1), "gas_year": (gas_years or {}).get(st, ""),
            "elec_usd_per_mwh": round(e, 1),
            "elec_to_gas_ratio": round(e / g, 2),
            "heat_pump_margin_usd_per_mwh": round(margin, 1),
            "direct_use_margin_usd_per_mwh": round(gas_value, 1),
            # Pipe one km of $1,500/m (annualized) can pay for, at this margin:
            "mwh_per_km_to_break_even": round(_pipe_annual_per_km(a) / margin) if margin > 0 else None,
        })
    rows.sort(key=lambda r: -r["heat_pump_margin_usd_per_mwh"])
    return rows, cop


def _pipe_annual_per_km(a: Assumptions) -> float:
    r, n = a.discount_rate, a.lifetime_years
    crf = r * (1 + r) ** n / ((1 + r) ** n - 1)
    return a.pipe_cost_base_per_m * 1000 * crf


def write(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
