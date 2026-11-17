"""Standalone HTML page for the sensitivity analysis (inline SVG, no libraries)."""
from __future__ import annotations

import json
from pathlib import Path

_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ThermaLite Sensitivity</title>
<style>
:root{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
 --bar:#2a78d6;--ring:rgba(11,11,11,.10);
 --s1:#cde2fb;--s2:#9ec5f4;--s3:#6da7ec;--s4:#3987e5;--s5:#256abf;--s6:#184f95;--s7:#0d366b}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;
 --grid:#2c2c2a;--axis:#383835;--bar:#3987e5;--ring:rgba(255,255,255,.10);
 --s1:#0d366b;--s2:#104281;--s3:#184f95;--s4:#256abf;--s5:#3987e5;--s6:#6da7ec;--s7:#9ec5f4}}
:root[data-theme="dark"]{--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--bar:#3987e5;
 --ring:rgba(255,255,255,.10);--s1:#0d366b;--s2:#104281;--s3:#184f95;--s4:#256abf;--s5:#3987e5;--s6:#6da7ec;--s7:#9ec5f4}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,sans-serif}
main{max-width:880px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:16px;margin:0 0 4px} p{color:var(--ink2);margin:0 0 12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:16px 0}
svg{width:100%;height:auto;display:block;overflow:visible}
svg text{fill:var(--muted);font-size:11px} svg .val{fill:var(--ink2)}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);
 border-radius:6px;padding:6px 8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9}
table{border-collapse:collapse;font-size:12px;width:100%} td,th{padding:3px 6px;text-align:right;border-bottom:1px solid var(--grid)}
details{margin-top:10px;color:var(--ink2)} .note{font-size:12px;color:var(--muted)}
</style></head><body><main>
<h1>What would it take to reuse the heat?</h1>
<p>__SUBTITLE__</p>
<div class="card"><h2>Heat reused vs. a recovery incentive</h2>
<p>MWh/yr of data center heat reused across viable pairings, if each MWh delivered earned the incentive shown (at baseline prices).</p>
<svg id="inc" viewBox="0 0 800 300" role="img" aria-label="Bar chart of heat reused by incentive level"></svg>
<details><summary>Table</summary><table id="inc-t"></table></details></div>
<div class="card"><h2>Viable pairings by energy price</h2>
<p>Each cell counts viable source-sink pairings at that gas and electricity price (no incentive). Cheaper electricity and dearer gas favor heat pumps.</p>
<svg id="grid" viewBox="0 0 800 360" role="img" aria-label="Heatmap of viable pairings by gas and electricity price"></svg>
<details><summary>Table</summary><table id="grid-t"></table></details></div>
<p class="note">Model outputs, not measurements. Capacities and heat demands are estimated from public footprints; several cost inputs are placeholders (see thermalite/assumptions.py).</p>
</main><div id="tip"></div>
<script>
const D = __DATA__;
const NS = 'http://www.w3.org/2000/svg', tip = document.getElementById('tip');
const el = (n, a, p) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); p && p.appendChild(e); return e; };
const fmt = n => Math.round(n).toLocaleString();
const show = (ev, html) => { tip.innerHTML = html; tip.style.display = 'block';
  tip.style.left = Math.min(ev.clientX + 12, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (ev.clientY + 12) + 'px'; };
const hide = () => tip.style.display = 'none';
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

// Incentive bars
(() => {
  const s = document.getElementById('inc'), R = D.incentive, L = 70, B = 260, T = 20, W = 800 - L - 10;
  const max = Math.max(1, ...R.map(r => r.heat_reused_mwh)), bw = W / R.length;
  for (let i = 0; i <= 4; i++) { const y = B - (B - T) * i / 4;
    el('line', {x1: L, x2: 800 - 10, y1: y, y2: y, stroke: 'var(--grid)'}, s);
    el('text', {x: L - 6, y: y + 4, 'text-anchor': 'end'}, s).textContent = fmt(max * i / 4); }
  el('line', {x1: L, x2: 800 - 10, y1: B, y2: B, stroke: 'var(--axis)'}, s);
  R.forEach((r, i) => {
    const h = (B - T) * r.heat_reused_mwh / max, x = L + i * bw + 2, w = bw - 4;
    if (h > 0) el('path', {d: `M${x},${B}V${B - h + 4}q0,-4 4,-4h${w - 8}q4,0 4,4V${B}Z`, fill: 'var(--bar)'}, s);
    el('text', {x: x + w / 2, y: B + 16, 'text-anchor': 'middle'}, s).textContent = '$' + r.incentive_per_mwh;
    if (i === R.length - 1 || i === 0) el('text', {x: x + w / 2, y: B - h - 6, 'text-anchor': 'middle', class: 'val'}, s).textContent = fmt(r.heat_reused_mwh);
    const hit = el('rect', {x: L + i * bw, y: T, width: bw, height: B - T, fill: 'transparent'}, s);
    hit.addEventListener('mousemove', ev => show(ev, `<b>$${r.incentive_per_mwh}/MWh incentive</b><br>${r.viable_pairs} viable pairings<br>${fmt(r.heat_reused_mwh)} MWh/yr reused<br>≈ ${fmt(r.homes_equivalent)} homes<br>${fmt(r.co2_avoided_t)} t CO₂/yr avoided`));
    hit.addEventListener('mouseleave', hide);
  });
  el('text', {x: L + W / 2, y: 292, 'text-anchor': 'middle'}, s).textContent = 'Incentive per MWh of recovered heat delivered';
  const t = document.getElementById('inc-t');
  t.innerHTML = '<tr><th>$/MWh</th><th>Viable pairs</th><th>MWh/yr reused</th><th>Homes eq.</th><th>t CO₂/yr</th></tr>' +
    R.map(r => `<tr><td>${r.incentive_per_mwh}</td><td>${r.viable_pairs}</td><td>${fmt(r.heat_reused_mwh)}</td><td>${fmt(r.homes_equivalent)}</td><td>${fmt(r.co2_avoided_t)}</td></tr>`).join('');
})();

// Price heatmap
(() => {
  const s = document.getElementById('grid'), R = D.prices;
  const gas = [...new Set(R.map(r => r.gas_price_per_mwh))], el_ = [...new Set(R.map(r => r.electricity_price_per_mwh))];
  const L = 90, T = 10, W = 800 - L - 10, H = 290, cw = W / gas.length, ch = H / el_.length;
  const max = Math.max(1, ...R.map(r => r.viable_pairs)), steps = ['--s1','--s2','--s3','--s4','--s5','--s6','--s7'];
  R.forEach(r => {
    const i = gas.indexOf(r.gas_price_per_mwh), j = el_.length - 1 - el_.indexOf(r.electricity_price_per_mwh);
    const k = r.viable_pairs === 0 ? -1 : Math.min(6, Math.floor(r.viable_pairs / max * 6.999));
    const x = L + i * cw, y = T + j * ch;
    const c = el('rect', {x: x + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3,
      fill: k < 0 ? 'var(--grid)' : `var(${steps[k]})`}, s);
    const dark = k >= 4;
    el('text', {x: x + cw / 2, y: y + ch / 2 + 4, 'text-anchor': 'middle',
      style: `fill:${dark ? '#ffffff' : 'var(--ink)'};font-size:12px`}, s).textContent = r.viable_pairs;
    c.addEventListener('mousemove', ev => show(ev, `<b>Gas $${r.gas_price_per_mwh}/MWh · Electricity $${r.electricity_price_per_mwh}/MWh</b><br>${r.viable_pairs} viable pairings<br>${fmt(r.heat_reused_mwh)} MWh/yr reused<br>≈ ${fmt(r.homes_equivalent)} homes`));
    c.addEventListener('mouseleave', hide);
  });
  gas.forEach((g, i) => el('text', {x: L + i * cw + cw / 2, y: T + H + 16, 'text-anchor': 'middle'}, s).textContent = '$' + g);
  el_.forEach((e, j) => el('text', {x: L - 8, y: T + (el_.length - 1 - j) * ch + ch / 2 + 4, 'text-anchor': 'end'}, s).textContent = '$' + e);
  el('text', {x: L + W / 2, y: T + H + 36, 'text-anchor': 'middle'}, s).textContent = 'Natural gas price, $/MWh of fuel';
  el('text', {x: 14, y: T + H / 2, 'text-anchor': 'middle', transform: `rotate(-90 14 ${T + H / 2})`}, s).textContent = 'Electricity, $/MWh';
  const t = document.getElementById('grid-t');
  t.innerHTML = '<tr><th>Elec \\ Gas</th>' + gas.map(g => `<th>$${g}</th>`).join('') + '</tr>' +
    el_.slice().reverse().map(e => `<tr><th>$${e}</th>` + gas.map(g => `<td>${R.find(r => r.gas_price_per_mwh === g && r.electricity_price_per_mwh === e).viable_pairs}</td>`).join('') + '</tr>').join('');
})();
</script></body></html>
"""


def write_html(price_rows: list[dict], incentive_rows: list[dict], subtitle: str, path: Path) -> None:
    payload = json.dumps({"prices": price_rows, "incentive": incentive_rows}).replace("</", "<\\/")
    safe = subtitle.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    path.write_text(_PAGE.replace("__DATA__", payload).replace("__SUBTITLE__", safe))
