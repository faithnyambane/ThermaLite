"""Write results: ranked CSV, summary text, and a standalone Leaflet map.

Output of the original matching tool (`thermalite match`), not the siting website.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from .data import Sink, Source
from .matcher import Match

CSV_FIELDS = [
    "source_id", "source_name", "sink_id", "sink_name", "sink_type", "feasible", "reason",
    "route_km", "breakeven_route_km", "source_temp_c", "sink_temp_c", "lift_k", "cop",
    "heat_used_mwh", "utilization", "peak_mw", "electricity_mwh", "gas_displaced_mwh",
    "co2_avoided_t", "homes_equivalent", "annual_value_usd", "annual_cost_usd", "net_annual_usd",
]


def _num(x: float, nd: int = 2):
    if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        return "direct" if math.isinf(x) else ""
    return round(x, nd)


def write_csv(matches: list[Match], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for m in matches:
            w.writerow({
                "source_id": m.source.id, "source_name": m.source.name,
                "sink_id": m.sink.id, "sink_name": m.sink.name, "sink_type": m.sink.type,
                "feasible": m.feasible, "reason": m.reason,
                "route_km": _num(m.route_km), "breakeven_route_km": _num(m.breakeven_route_km),
                "source_temp_c": m.source.temp_c, "sink_temp_c": m.sink.supply_temp_c,
                "lift_k": _num(m.lift_k, 1), "cop": _num(m.cop),
                "heat_used_mwh": _num(m.heat_used_mwh, 0), "utilization": _num(m.utilization, 3),
                "peak_mw": _num(m.peak_mw), "electricity_mwh": _num(m.electricity_mwh, 0),
                "gas_displaced_mwh": _num(m.gas_displaced_mwh, 0),
                "co2_avoided_t": _num(m.co2_avoided_t, 0), "homes_equivalent": _num(m.homes_equivalent, 0),
                "annual_value_usd": _num(m.annual_value_usd, 0), "annual_cost_usd": _num(m.annual_cost_usd, 0),
                "net_annual_usd": _num(m.net_annual_usd, 0),
            })


def summary_text(s: dict) -> str:
    return "\n".join([
        f"Of {s['sources_examined']} data centers examined, {s['sources_with_viable_sink']} "
        f"have an economically viable heat sink within reach.",
        f"  Recoverable heat at all sources : {s['recoverable_heat_available_mwh']:>14,.0f} MWh/yr",
        f"  Heat reused in viable pairings  : {s['heat_reused_mwh']:>14,.0f} MWh/yr",
        f"  Homes-equivalent heated         : {s['homes_equivalent']:>14,.0f}",
        f"  Natural gas displaced           : {s['gas_displaced_mwh']:>14,.0f} MWh/yr",
        f"  CO2 avoided (net of HP power)   : {s['co2_avoided_t']:>14,.0f} t/yr",
        f"  Net annual value                : ${s['net_annual_usd']:>13,.0f}",
    ])


_MAP_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ThermaLite Heat Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 html,body{margin:0;height:100%;font:14px system-ui,sans-serif;background:#fff}
 #map{position:absolute;inset:0}
 .panel{position:absolute;z-index:1000;top:10px;right:10px;max-width:340px;background:#fff;
   padding:12px 14px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.2);white-space:pre-wrap;font-size:12px}
 .panel h1{font-size:15px;margin:0 0 6px}
 .lg span{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
</style></head><body>
<div id="map"></div>
<div class="panel"><h1>ThermaLite: where could the heat go?</h1>__SUMMARY__
<div class="lg"><span style="background:#d6452b"></span>data center &nbsp;<span style="background:#2b7bd6"></span>heat sink &nbsp;green line = viable pairing</div></div>
<script>
const D = __DATA__;
const map = L.map('map');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'}).addTo(map);
const pts = [];
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
D.sources.forEach(s => { pts.push([s.lat, s.lon]);
  L.circleMarker([s.lat, s.lon], {radius: 6 + Math.sqrt(s.mw), color: '#d6452b', fillOpacity: .8})
   .bindPopup(`<b>${esc(s.name)}</b><br>${s.mw} MW IT, ${esc(s.cooling)} cooling, ${s.temp} C`).addTo(map); });
D.sinks.forEach(s => { pts.push([s.lat, s.lon]);
  L.circleMarker([s.lat, s.lon], {radius: 6, color: '#2b7bd6', fillOpacity: .8})
   .bindPopup(`<b>${esc(s.name)}</b><br>${esc(s.type)}, needs ${s.temp} C, ${s.mwh.toLocaleString()} MWh/yr`).addTo(map); });
D.links.forEach(l => {
  L.polyline([[l.a[0], l.a[1]], [l.b[0], l.b[1]]], {color: '#1f9d55', weight: 2 + Math.min(8, l.homes / 500), opacity: .8})
   .bindPopup(`<b>${esc(l.src)} &rarr; ${esc(l.snk)}</b><br>${l.km} km pipe, lift ${l.lift} K, COP ${l.cop}<br>`
     + `${l.mwh.toLocaleString()} MWh/yr reused &asymp; ${l.homes.toLocaleString()} homes<br>`
     + `${l.co2.toLocaleString()} t CO2/yr avoided, net $${l.net.toLocaleString()}/yr`).addTo(map); });
if (pts.length) map.fitBounds(pts, {padding: [40, 40]}); else map.setView([40.5, -74.4], 9);
</script></body></html>
"""


def write_map(sources: list[Source], sinks: list[Sink], chosen: list[Match], summary: str, path: Path) -> None:
    data = {
        "sources": [{"name": s.name, "lat": s.lat, "lon": s.lon, "mw": s.it_load_mw,
                     "cooling": s.cooling, "temp": s.temp_c} for s in sources],
        "sinks": [{"name": s.name, "type": s.type, "lat": s.lat, "lon": s.lon,
                   "temp": s.supply_temp_c, "mwh": round(s.annual_heat_mwh)} for s in sinks],
        "links": [{"src": m.source.name, "snk": m.sink.name,
                   "a": [m.source.lat, m.source.lon], "b": [m.sink.lat, m.sink.lon],
                   "km": round(m.route_km, 1), "lift": round(m.lift_k), "cop": _num(m.cop, 1),
                   "mwh": round(m.heat_used_mwh), "homes": round(m.homes_equivalent),
                   "co2": round(m.co2_avoided_t), "net": round(m.net_annual_usd)} for m in chosen],
    }
    payload = json.dumps(data).replace("</", "<\\/")
    html_summary = summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    path.write_text(_MAP_TEMPLATE.replace("__DATA__", payload).replace("__SUMMARY__", html_summary))
