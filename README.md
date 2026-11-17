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

Python 3.9+, standard library only.

```bash
python3 -m thermalite                       # runs on data/example (SYNTHETIC)
python3 -m thermalite --sources my_dcs.csv --sinks my_sinks.csv --out out/
python3 -m thermalite --climate             # real heating degree days per sink (Earth Engine)
python3 -m unittest discover -s tests -t .
```

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

- [ ] **Real sources:** PNNL / IM3 Open Source Data Center Atlas (OSTI) → `sources.csv`
- [ ] **Real sinks:** IDEA district energy system maps, hospitals (CMS / HIFLD), universities (IPEDS)
- [ ] **Greenhouse detector:** computer vision on aerial imagery to build the greenhouse layer that has no national database
- [ ] **Local hook:** check whether Rutgers runs a district heating / cogeneration plant (steam or hot water?)
- [ ] **Policy lever:** sensitivity on gas/electricity prices. Denmark's 2022 surplus-heat tax repeal changed the business case; show what US price or incentive would flip pairs to viable.

## Sources

- Ramboll, *Meta surplus heat to district heating* (Tietgenbyen Energy Center, Odense)
- Meta Engineering, *Odense data center* (2018)
- DTU Compute, *Five answers about integrating waste heat from data centres* (Cool-Data, 2022)
- Kavvadias & Quoilin, *Exploiting waste heat potential by long distance heat transmission*, Applied Energy (2018)
- EPA, emission factor for natural gas: 53.06 kg CO2/MMBtu
