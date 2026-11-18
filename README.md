# ThermaLite

**Where should the next data center go so its waste heat gets used?**

ThermaLite cuts a state into 2 km squares and scores each one as a site for a new
50 MW data center. It weighs five factors: heat it could sell to buildings nearby,
how clean the grid is, local water stress, how hot the climate is, and distance to
the power grid. For every square it also plans who would buy the heat: which
hospitals, greenhouses, indoor pools or apartment blocks, how much, and over how
much pipe.

It covers the three states that benefit most: **Virginia, Texas and North Carolina**.

**Team:** Faith Nyambane, Jude Shorbaji, Deena Kojimen, Jesse Osei-Asante · Rutgers University, Electrical and Computer Engineering · AI-Impact-Athon, NSBE Region 1 Fall Regional

The model follows the Odense precedent: Meta's Tietgenbyen data center supplies the
city's district heating through heat pumps, about 215,000 MWh a year for more than
12,000 homes (Ramboll).

**Live site:** https://faithnyambane.github.io/ThermaLite/ 

## Results

| State | Heat reused at 10 independent sites (MWh/yr) | Homes' worth | CO₂ avoided (t/yr) |
|---|---|---|---|
| Virginia | 780,000 | 43,600 | 109,000 |
| Texas | 640,000 | 35,700 | 90,000 |
| North Carolina | 410,000 | 22,900 | 57,000 |

"Independent" means no two sites share a heat buyer, so nothing is counted twice.
These are screening results: pipe and heat pump costs are still placeholders.

## How it works

| Stage | What it does | Code |
|---|---|---|
| 1. Ingest | Heat buyers and substations from OpenStreetMap; prices from EIA; grid carbon from EPA eGRID | `osm.py`, `national.py`, `atlas.py`, `data.py` |
| 2. Climate | Heating and cooling degree days from ERA5-Land (Earth Engine) | `climate.py` |
| 3. Pricing a heat deal | Heat pump efficiency, seasonal demand, gas saved vs electricity and pipe cost | `assumptions.py`, `physics.py`, `seasonal.py`, `matcher.py` |
| 4. Siting grid | 2 km squares with water stress, flood, protected land, water/wetland, grid distance | `siting.py` |
| 5. Heat allocation | Who buys a new data center's heat in each square | `siting.py` (`allocate`) |
| 6. Rank states | 50-state price screen, then heat at independent sites | `national.py`, `rank_states.py` |
| 7. Website | Compact data files; the browser scores every square live | `siting_ui.py`, `site/index.html` |

Start reading the code at [thermalite/__init__.py](thermalite/__init__.py), which holds
a full code map. Every module says which stage it belongs to.

## Run it

The core model needs only the Python standard library. The Earth Engine steps need
`earthengine-api` and a noncommercial Earth Engine Cloud project (ours: `thermalite`).

```bash
python3 -m venv .venv && .venv/bin/pip install earthengine-api openpyxl xlrd
earthengine authenticate          # once

PY=.venv/bin/python
$PY -m thermalite sources --state VA     # existing data centers (shown on the map)
$PY -m thermalite sinks   --state VA     # heat buyers from OpenStreetMap
$PY -m thermalite site    --state VA     # siting grid + heat allocation -> out/siting/va.json
# pack for the website with thermalite.siting_ui.pack -> site/data-va.json
```

Open the website locally:

```bash
cd site && python3 -m http.server 8000   # then open http://localhost:8000
```

## Tests

```bash
$PY -m unittest discover -s tests -t .   # 30 tests: physics, seasons, allocation, ranking
node tests/check_ui_data.js site         # website data files add up
node tests/ui_e2e.js site                # 83 checks in a simulated browser (needs jsdom)
```

## Assumptions

Every number lives in [thermalite/assumptions.py](thermalite/assumptions.py), tagged
`[SOURCED]`, `[ENGINEERING]` or `[PLACEHOLDER]`. The two that matter most:

| Assumption | Now | Replace with |
|---|---|---|
| Pipe cost | $1,500/m + $50/m per MW (placeholder) | Kavvadias & Quoilin (2018) transmission model |
| Heat pump cost | $1M per MW thermal (placeholder) | Danish Energy Agency technology catalogue |

## Data sources

- OpenStreetMap contributors (ODbL), via the Overpass API
- ECMWF ERA5-Land; WRI Aqueduct 4.0; JRC GLOFAS v2.1; WDPA; MODIS MCD12Q1, via Google Earth Engine
- US EIA state commercial gas and electricity prices; EPA eGRID 2023
- Mongird et al., IM3 Open Source Data Center Atlas, OSTI 2550666 (ODbL)
- Ramboll, *Meta surplus heat to district heating* (Odense)
- Kavvadias & Quoilin, *Exploiting waste heat potential by long distance heat transmission*, Applied Energy (2018)

`data/example/` is made up for testing; never present those numbers as findings.
