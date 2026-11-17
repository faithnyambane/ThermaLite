"""Every numeric assumption in ThermaLite lives here.

Each value is tagged:
  [SOURCED]      taken from a cited source (see README "Sources")
  [ENGINEERING]  typical textbook/industry range; defensible but check it
  [PLACEHOLDER]  stand-in so the pipeline runs; REPLACE before quoting results

Change values by constructing Assumptions(...) with overrides, or with
dataclasses.replace(DEFAULT, field=value).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Assumptions:
    # --- Heat pump -----------------------------------------------------------
    # Real large heat pumps reach roughly 40-60% of the ideal Carnot COP.  [ENGINEERING]
    carnot_efficiency: float = 0.5
    max_cop: float = 8.0  # cap for very small lifts  [ENGINEERING]
    # Highest supply temperature a large heat pump can deliver. Odense delivers
    # 70-75 C (Ramboll); ~90 C is the practical upper end today.  [ENGINEERING]
    max_hp_output_c: float = 90.0
    # Temperature difference needed across each heat exchanger.  [ENGINEERING]
    approach_k: float = 5.0

    # --- Transmission --------------------------------------------------------
    route_factor: float = 1.3  # pipe route / straight-line distance  [ENGINEERING]
    max_search_km: float = 50.0  # straight-line radius to consider at all
    # Installed pipe cost, USD per metre = base + per_mw * peak capacity.
    # Replace with the Kavvadias & Quoilin (2018) transmission cost model.  [PLACEHOLDER]
    pipe_cost_base_per_m: float = 1500.0
    pipe_cost_per_m_per_mw: float = 50.0
    heat_loss_per_km: float = 0.005  # fraction of delivered heat lost per route km  [PLACEHOLDER]

    # --- Capital -------------------------------------------------------------
    hp_capex_per_mw: float = 1_000_000.0  # USD per MW thermal output  [PLACEHOLDER]
    discount_rate: float = 0.06  # [ENGINEERING]
    lifetime_years: int = 25  # [ENGINEERING]

    # --- Energy prices -------------------------------------------------------
    gas_price_per_mwh: float = 35.0  # ~ $10/MMBtu commercial  [PLACEHOLDER: use EIA state price]
    electricity_price_per_mwh: float = 120.0  # [PLACEHOLDER: use EIA state price]
    boiler_efficiency: float = 0.85  # gas boiler being displaced  [ENGINEERING]

    # --- Emissions -----------------------------------------------------------
    # EPA: 53.06 kg CO2 per MMBtu natural gas = 0.181 t/MWh fuel.  [SOURCED]
    gas_co2_t_per_mwh: float = 0.181
    # Grid emissions for heat pump electricity. Use a regional MARGINAL factor
    # (e.g. WattTime / eGRID for PJM).  [PLACEHOLDER]
    grid_co2_t_per_mwh: float = 0.40

    # --- Reporting -----------------------------------------------------------
    # Odense: 215,000 MWh heats >12,000 homes (Ramboll) -> ~17.9 MWh/home/yr.
    # Danish homes; swap for a US figure (EIA RECS) if presenting US homes.  [SOURCED]
    home_heat_mwh_per_year: float = 215_000 / 12_000


DEFAULT = Assumptions()

# Default supply temperature (C) and recoverable fraction of IT load by cooling type.
# Newer liquid-cooled facilities return ~140 F / 60 C water (Resource Innovation
# Institute, quoted in plan doc); air-cooled exhaust is low-grade.  [ENGINEERING]
COOLING_DEFAULTS = {
    "liquid": (55.0, 0.8),
    "chilled_water": (30.0, 0.7),
    "air": (30.0, 0.4),
}
