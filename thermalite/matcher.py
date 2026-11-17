"""Score every source-sink pair on distance, temperature lift and seasonality."""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import physics, seasonal
from .assumptions import DEFAULT, Assumptions
from .data import Sink, Source, haversine_km


@dataclass(frozen=True)
class Match:
    source: Source
    sink: Sink
    route_km: float
    lift_k: float  # 0 when direct exchange works
    cop: float  # inf when direct exchange works
    heat_used_mwh: float
    utilization: float  # share of the sink's annual demand met
    peak_mw: float
    electricity_mwh: float
    gas_displaced_mwh: float  # boiler fuel avoided
    co2_avoided_t: float
    homes_equivalent: float
    annual_value_usd: float  # gas saved minus heat pump electricity
    annual_cost_usd: float  # annualized heat pump + pipe capital
    net_annual_usd: float
    breakeven_route_km: float
    feasible: bool
    reason: str  # why infeasible, or "ok"


def _crf(r: float, n: int) -> float:
    """Capital recovery factor: converts an up-front cost to an annual payment."""
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


def score(source: Source, sink: Sink, a: Assumptions = DEFAULT) -> Match:
    route_km = haversine_km(source.lat, source.lon, sink.lat, sink.lon) * a.route_factor
    needs_hp = physics.needs_heat_pump(source.temp_c, sink.supply_temp_c, a)
    lift = physics.temperature_lift_k(source.temp_c, sink.supply_temp_c, a) if needs_hp else 0.0

    def infeasible(reason: str) -> Match:
        return Match(source, sink, route_km, lift, math.nan, 0, 0, 0, 0, 0, 0, 0,
                     0, 0, 0, 0, False, reason)

    if needs_hp and sink.supply_temp_c + a.approach_k > a.max_hp_output_c:
        return infeasible(f"sink needs {sink.supply_temp_c:.0f} C; heat pumps top out near "
                          f"{a.max_hp_output_c:.0f} C (steam system?)")
    cop = physics.heat_pump_cop(source.temp_c, sink.supply_temp_c, a)
    if cop <= 1.0:
        return infeasible(f"lift of {lift:.0f} K too large (COP {cop:.2f})")

    available = physics.delivered_from_source(source.annual_heat_mwh, cop)
    available *= max(0.0, 1 - a.heat_loss_per_km * route_km)
    profile = seasonal.profile_for(sink.type, sink.profile, sink.hdd_shape)
    used, peak_mw = seasonal.utilized(available, sink.annual_heat_mwh, profile)

    electricity = physics.electricity_for(used, cop)
    gas = used / a.boiler_efficiency
    co2 = gas * a.gas_co2_t_per_mwh - electricity * a.grid_co2_t_per_mwh
    value = gas * a.gas_price_per_mwh - electricity * a.electricity_price_per_mwh

    crf = _crf(a.discount_rate, a.lifetime_years)
    hp_annual = a.hp_capex_per_mw * peak_mw * crf if needs_hp else 0.0
    pipe_annual_per_km = (a.pipe_cost_base_per_m + a.pipe_cost_per_m_per_mw * peak_mw) * 1000 * crf
    cost = hp_annual + pipe_annual_per_km * route_km
    net = value - cost
    breakeven = max(0.0, (value - hp_annual) / pipe_annual_per_km)

    if used <= 0:
        reason, ok = "no usable demand", False
    elif net <= 0:
        reason, ok = f"uneconomic: breaks even at {breakeven:.1f} km of pipe, needs {route_km:.1f}", False
    else:
        reason, ok = "ok", True

    return Match(
        source=source, sink=sink, route_km=route_km, lift_k=lift, cop=cop,
        heat_used_mwh=used, utilization=used / sink.annual_heat_mwh if sink.annual_heat_mwh else 0.0,
        peak_mw=peak_mw, electricity_mwh=electricity, gas_displaced_mwh=gas,
        co2_avoided_t=co2, homes_equivalent=used / a.home_heat_mwh_per_year,
        annual_value_usd=value, annual_cost_usd=cost, net_annual_usd=net,
        breakeven_route_km=breakeven, feasible=ok, reason=reason,
    )


def match_all(sources: list[Source], sinks: list[Sink], a: Assumptions = DEFAULT) -> list[Match]:
    """Score all pairs within the search radius, best net value first."""
    matches = [
        score(src, snk, a)
        for src in sources for snk in sinks
        if haversine_km(src.lat, src.lon, snk.lat, snk.lon) <= a.max_search_km
    ]
    return sorted(matches, key=lambda m: (m.feasible, m.net_annual_usd), reverse=True)


def assign(matches: list[Match]) -> list[Match]:
    """Greedy one-to-one pairing (each source and sink used once) so the
    headline totals don't count the same heat twice."""
    used_src, used_snk, chosen = set(), set(), []
    for m in matches:
        if m.feasible and m.source.id not in used_src and m.sink.id not in used_snk:
            chosen.append(m)
            used_src.add(m.source.id)
            used_snk.add(m.sink.id)
    return chosen


def summarize(sources: list[Source], chosen: list[Match]) -> dict:
    return {
        "sources_examined": len(sources),
        "sources_with_viable_sink": len(chosen),
        "recoverable_heat_available_mwh": sum(s.annual_heat_mwh for s in sources),
        "heat_reused_mwh": sum(m.heat_used_mwh for m in chosen),
        "homes_equivalent": sum(m.homes_equivalent for m in chosen),
        "gas_displaced_mwh": sum(m.gas_displaced_mwh for m in chosen),
        "co2_avoided_t": sum(m.co2_avoided_t for m in chosen),
        "net_annual_usd": sum(m.net_annual_usd for m in chosen),
    }
