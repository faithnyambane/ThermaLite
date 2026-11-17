"""Monthly demand profiles.

Data centers produce heat all year; most buildings only need it in winter.
Each profile is 12 monthly fractions of annual demand (normalized to sum to 1).

The built-in space-heating shape is ILLUSTRATIVE for a US Northeast climate.
Run with --climate to replace it with real heating degree days per sink
(ERA5-Land via Earth Engine; see thermalite/climate.py).
"""
from __future__ import annotations

DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

_FLAT = [d / 365 for d in DAYS_IN_MONTH]
_SPACE = [0.19, 0.16, 0.13, 0.07, 0.03, 0.01, 0.0, 0.0, 0.01, 0.05, 0.11, 0.17]


def _normalize(xs):
    s = sum(xs)
    return [x / s for x in xs]


def _mix(w_space: float, space_shape=None):
    space = _normalize(space_shape if space_shape is not None else _SPACE)
    return _normalize([w_space * s + (1 - w_space) * f for s, f in zip(space, _FLAT)])


# Share of each profile that follows outdoor temperature (the rest is flat,
# e.g. domestic hot water or process heat).
SPACE_WEIGHT = {
    "flat": 0.0,  # pools, aquaculture, industrial process heat
    "space_heating": 1.0,
    "space_and_water": 0.7,  # district energy, hospitals, multifamily
    "greenhouse": 0.5,  # heated year-round, winter peak
}

PROFILES = {name: _mix(w) for name, w in SPACE_WEIGHT.items()}

# Default profile by sink type.
TYPE_PROFILE = {
    "district_energy": "space_and_water",
    "hospital": "space_and_water",
    "university": "space_and_water",
    "multifamily": "space_and_water",
    "greenhouse": "greenhouse",
    "pool": "flat",
    "aquaculture": "flat",
    "industrial": "flat",
}


def profile_for(sink_type: str, override: str | None = None, hdd_shape=None) -> list[float]:
    """Monthly demand fractions for a sink. `hdd_shape` (12 monthly heating
    degree-day values for the site, e.g. from thermalite.climate) replaces the
    illustrative space-heating curve."""
    name = override or TYPE_PROFILE.get(sink_type, "space_and_water")
    if name not in PROFILES:
        raise KeyError(f"unknown profile {name!r}; choose from {sorted(PROFILES)}")
    if hdd_shape is None:
        return PROFILES[name]
    if SPACE_WEIGHT[name] == 0.0:
        return PROFILES[name]
    return _mix(SPACE_WEIGHT[name], list(hdd_shape))


def utilized(supply_annual: float, demand_annual: float, profile: list[float]) -> tuple[float, float]:
    """Heat actually used when a flat supply meets a seasonal demand.

    Returns (annual heat used, peak monthly-average power in MW), with energy in MWh."""
    used = 0.0
    peak_mw = 0.0
    for days, frac in zip(DAYS_IN_MONTH, profile):
        supply_m = supply_annual * days / 365
        use_m = min(supply_m, demand_annual * frac)
        used += use_m
        peak_mw = max(peak_mw, use_m / (days * 24))
    return used, peak_mw
