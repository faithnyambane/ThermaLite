"""What would it take? Sweep energy prices and a heat-recovery incentive and
count how many source-sink pairings become viable.

Denmark's heat reuse took off partly after a 2022 tax change (Ramboll), so the
policy question is: which US price ratio, or what incentive per MWh, flips
pairings from uneconomic to viable?
"""
from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from .assumptions import DEFAULT, Assumptions
from .data import Sink, Source
from .matcher import assign, match_all

GAS_PRICES = [20, 30, 35, 45, 60, 80, 100]  # USD/MWh fuel (~$6-29/MMBtu)
ELEC_PRICES = [60, 80, 100, 120, 150, 180]  # USD/MWh
INCENTIVES = [0, 5, 10, 20, 30, 40, 50, 75, 100]  # USD per MWh recovered heat


def _run(sources, sinks, a: Assumptions) -> dict:
    chosen = assign(match_all(sources, sinks, a))
    return {
        "viable_pairs": len(chosen),
        "heat_reused_mwh": round(sum(m.heat_used_mwh for m in chosen)),
        "homes_equivalent": round(sum(m.homes_equivalent for m in chosen)),
        "co2_avoided_t": round(sum(m.co2_avoided_t for m in chosen)),
        "net_annual_usd": round(sum(m.net_annual_usd for m in chosen)),
    }


def price_grid(sources: list[Source], sinks: list[Sink], a: Assumptions = DEFAULT,
               gas=GAS_PRICES, elec=ELEC_PRICES) -> list[dict]:
    return [
        {"gas_price_per_mwh": g, "electricity_price_per_mwh": e,
         **_run(sources, sinks, replace(a, gas_price_per_mwh=g, electricity_price_per_mwh=e))}
        for g in gas for e in elec
    ]


def incentive_curve(sources: list[Source], sinks: list[Sink], a: Assumptions = DEFAULT,
                    incentives=INCENTIVES) -> list[dict]:
    return [{"incentive_per_mwh": i, **_run(sources, sinks, replace(a, heat_incentive_per_mwh=i))}
            for i in incentives]


def write(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
