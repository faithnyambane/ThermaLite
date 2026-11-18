"""ThermaLite: decide where to build the next data center so its waste heat gets used.

CODE MAP (the pipeline runs top to bottom; each stage writes files the next reads)

  Stage 1  Ingest public data
           atlas.py      existing data centers (PNNL IM3 atlas) -> data/<st>/sources.csv
           osm.py        heat users + substations (OpenStreetMap) -> data/<st>/sinks.csv
           national.py   EIA gas and electricity prices by state
           data.py       Source / Sink records and CSV loaders, used by every stage

  Stage 2  Climate
           climate.py    heating degree days per month (ERA5-Land, Earth Engine), cached

  Stage 3  Physics and economics of ONE data center -> building pair
           assumptions.py  every number the model uses, tagged SOURCED / ENGINEERING / PLACEHOLDER
           physics.py      heat pump COP and energy balance
           seasonal.py     flat supply vs seasonal demand -> heat actually used
           matcher.py      score(): lift + season + money -> feasible? net $/yr? why not?

  Stage 4  Siting grid        siting.py  ee_layers(), build()   2 km squares + every map layer
  Stage 5  Heat allocation    siting.py  allocate()             who buys a new data center's heat
  Stage 6  Rank states        national.py screen() (price screen), rank_states.py (heat at independent sites)
  Stage 7  Website            siting_ui.py pack() -> site/data-<st>.json; the page is site/index.html

  Command line: __main__.py  (python -m thermalite <match|sources|sinks|sensitivity|greenhouses|site>)
  Earlier tools kept for the record: report.py (match map/CSV), sensitivity*.py (price sweeps),
  greenhouse.py (satellite greenhouse detector; not used in results).
"""
