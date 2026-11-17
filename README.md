# ThermaLite

**Where could data center waste heat go?** ThermaLite pairs data centers (heat
sources) with nearby heat users (district energy, hospitals, greenhouses, pools,
multifamily housing). It scores each pair on the three constraints that decide
whether heat reuse works:

1. **Distance**: pipe cost per km vs. the value of the heat delivered → a break-even pipe length per pair.
2. **Temperature lift**: data center heat (~30–60 °C) is usually too cold. A heat pump lifts it, and the lift sets the COP and so the electricity bill. Steam systems (>~90 °C) are out of reach.
3. **Seasonality**: data centers make heat 8,760 h/yr, while buildings mostly need it in winter. Year-round sinks (greenhouses, pools) use more of the supply.

Model built on the Odense precedent: Meta's Tietgenbyen data center supplies
Fjernvarme Fyn's district heating via heat pumps at 70–75 °C, ~215,000 MWh/yr,
>12,000 homes (Ramboll).

## Run it

Core matching needs only the Python standard library. Earth Engine features need
`earthengine-api` and a noncommercial Earth Engine Cloud project (ours: `thermalite`).

```bash
/usr/local/bin/python3.12 -m venv .venv && .venv/bin/pip install earthengine-api
earthengine authenticate          # once; CLI may live in ~/Library/Python/3.9/bin

PY=.venv/bin/python
$PY -m thermalite                                   # example data (SYNTHETIC)
$PY -m thermalite sources --state NJ                # data centers  <- IM3 atlas
$PY -m thermalite sinks --state NJ                  # heat users    <- OpenStreetMap
$PY -m thermalite match --sources data/nj/sources.csv --sinks data/nj/sinks.csv --out out/nj --climate
$PY -m thermalite sensitivity --sources data/nj/sources.csv --sinks data/nj/sinks.csv --out out/nj --climate
$PY -m thermalite greenhouses --state NJ [--bbox W,S,E,N]   # NAIP detector (Earth Engine)
$PY -m unittest discover -s tests -t .
```

Outputs in `out/nj/`: `matches.csv`, `map.html`, `sensitivity.html` (+ CSVs).

## New Jersey results so far (2026-11-17)

Model outputs under placeholder cost assumptions. **Screening, not investment-grade.**

- **Inputs:** 57 data centers (IM3 atlas; 2 implausible footprints set aside in
  `data/nj/sources_review.csv`), 1,230 heat users from OSM (94 hospitals,
  42 greenhouse operations, 152 indoor pools, 942 large apartment buildings),
  ERA5-Land heating degree days per site.
- **Baseline (gas $35/MWh, electricity $120/MWh, no incentive):** 0 viable pairings.
  Pipe cost and the gas/electricity price ratio make every pairing uneconomic.
- **With a recovered-heat incentive:** $10/MWh -> 1 pairing; $30/MWh -> 12 pairings,
  ~246,000 MWh/yr (~13,700 homes-equivalent, ~27,000 t CO2/yr), mostly hospitals and
  apartments, plus greenhouses; $100/MWh -> 29 pairings, ~800,000 MWh/yr.
- **Greenhouse detector:** trains and validates (2023 NAIP, block-held-out pixel accuracy
  ~87%) but object-level recall on a test area is only 3/26 OSM greenhouses. **Not yet
  usable for results**; see Next steps.

Outputs in `out/`: `matches.csv` (every pair, with the reason any pair was rejected) and
`map.html` (open in a browser).

## Input format

`sources.csv`: `id,name,lat,lon,it_load_mw,cooling[,source_temp_c,recoverable_fraction]`
with `cooling` one of `liquid | chilled_water | air` (blank optional columns use defaults).

`sinks.csv`: `id,name,type,lat,lon,annual_heat_mwh,supply_temp_c[,profile]`
with `type` such as `district_energy, university, hospital, greenhouse, pool, multifamily, aquaculture, industrial`.

**`data/example/` is made up.** Never present those numbers as findings.

## Assumptions

All numbers live in [thermalite/assumptions.py](thermalite/assumptions.py), each tagged
`[SOURCED]`, `[ENGINEERING]` or `[PLACEHOLDER]`. Before presenting results, replace the placeholders:

| Assumption | Replace with |
|---|---|
| Pipe cost per metre | Kavvadias & Quoilin (2018), *Applied Energy*, long-distance heat transmission model |
| Heat pump capex | Published large heat pump cost data (e.g. Danish Energy Agency technology catalogue) |
| Gas & electricity prices | EIA commercial prices for the state |
| Grid CO2 factor | Regional marginal factor (WattTime / EPA eGRID, PJM for NJ) |
| Space-heating profile | Done with `--climate`: ERA5-Land monthly heating degree days (2015–2024, 18 °C base) via Earth Engine project `thermalite` |
| Heat loss per km | Same transmission literature |

## Next steps

- [x] Real sources: IM3 atlas (capacity estimated from footprint)
- [x] Real sinks: OSM hospitals, greenhouses, indoor pools, large apartments
- [x] Price / incentive sensitivity
- [ ] **Replace the pipe cost placeholder** (Kavvadias & Quoilin 2018). It dominates every result.
- [ ] **Greenhouse detector v2:** inspect errors on the review GeoJSON, add hard negatives
      (bright warehouse roofs), larger-scale texture (GLCM), handle small hoop houses; report object-level precision/recall.
- [ ] **Public housing sinks** (HUD open data) for the equity angle
- [ ] **District energy sinks** entered by hand (IDEA maps); check Rutgers' plant (steam or hot water?)
- [ ] **Better capacity data** for the largest data centers (operator disclosures, utility filings)

## Sources

- Ramboll, *Meta surplus heat to district heating* (Tietgenbyen Energy Center, Odense)
- Meta Engineering, *Odense data center* (2018)
- DTU Compute, *Five answers about integrating waste heat from data centres* (Cool-Data, 2022)
- Kavvadias & Quoilin, *Exploiting waste heat potential by long distance heat transmission*, Applied Energy (2018)
- EPA, emission factor for natural gas: 53.06 kg CO2/MMBtu
- Mongird et al., IM3 Open Source Data Center Atlas, OSTI 2550666, doi:10.57931/2550666 (ODbL)
- OpenStreetMap contributors (ODbL), via Overpass API
- ECMWF ERA5-Land daily aggregates; USDA NAIP; via Google Earth Engine
