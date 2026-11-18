"""Rank states by how much a NEW data center's heat could be reused there.

Neighbouring grid cells often sell heat to the same building, so counting
viable cells double-counts. Instead, greedily pick up to `k` sites with the
most heat that share no heat buyer with an already-picked site, and sum them.
"""
from __future__ import annotations

import json
from pathlib import Path

HOME_MWH = 215_000 / 12_000  # Odense ratio, as elsewhere


def summarize(siting_json: Path, k: int = 10) -> dict:
    d = json.loads(siting_json.read_text())
    viable = sorted((c for c in d["cells"] if c["heat"] > 0), key=lambda c: -c["heat"])
    used, picked = set(), []
    for c in viable:
        buyers = {a["sink"] for a in c["alloc"]}
        if buyers & used:
            continue
        picked.append(c)
        used |= buyers
        if len(picked) == k:
            break
    heat = sum(c["heat"] for c in picked)
    return {
        "state": d["state"], "cells": len(d["cells"]), "viable_cells": len(viable),
        "distinct_buyers": len({a["sink"] for c in viable for a in c["alloc"]}),
        "independent_sites": len(picked), "heat_mwh": heat, "homes": round(heat / HOME_MWH),
        "co2_t": sum(c["co2t"] for c in picked), "grid_co2": d["grid_co2"],
        "prices": d["prices"],
    }
