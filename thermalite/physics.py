"""Heat pump and heat-flow physics.

Pipeline stage 3 (physics). Pure functions, no I/O; matcher.score() calls them.
Data center heat is ~30 C but buildings want 40-80 C, so a heat pump "lifts" it.
The bigger the lift, the more electricity each MWh of heat costs (lower COP).
"""
from __future__ import annotations

import math

from .assumptions import Assumptions

C_TO_K = 273.15


def needs_heat_pump(source_c: float, sink_c: float, a: Assumptions) -> bool:
    """Direct heat exchange works only if the source is hotter than the sink
    by at least one exchanger approach temperature."""
    return source_c - sink_c < a.approach_k


def temperature_lift_k(source_c: float, sink_c: float, a: Assumptions) -> float:
    """Lift the heat pump must provide: from (source - approach) at the
    evaporator to (sink + approach) at the condenser."""
    return (sink_c + a.approach_k) - (source_c - a.approach_k)


def heat_pump_cop(source_c: float, sink_c: float, a: Assumptions) -> float:
    """Heating COP = carnot_efficiency * T_hot / (T_hot - T_cold), in kelvin.

    Returns math.inf when no heat pump is needed (direct exchange)."""
    if not needs_heat_pump(source_c, sink_c, a):
        return math.inf
    t_hot = sink_c + a.approach_k + C_TO_K
    lift = temperature_lift_k(source_c, sink_c, a)
    cop = a.carnot_efficiency * t_hot / lift
    return min(cop, a.max_cop)


def delivered_from_source(source_heat: float, cop: float) -> float:
    """Heat delivered to the sink when `source_heat` is upgraded by a heat pump.

    Energy balance: delivered = source + compressor work, and work = delivered / COP,
    so delivered = source * COP / (COP - 1)."""
    if math.isinf(cop):
        return source_heat
    if cop <= 1.0:
        raise ValueError(f"COP {cop:.2f} <= 1: heat pump cannot upgrade this source")
    return source_heat * cop / (cop - 1.0)


def electricity_for(delivered_heat: float, cop: float) -> float:
    """Compressor electricity needed to deliver `delivered_heat`."""
    return 0.0 if math.isinf(cop) else delivered_heat / cop
