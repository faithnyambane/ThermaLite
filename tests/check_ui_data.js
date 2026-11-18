// Checks the siting UI's data files against what web/siting.html expects, and
// runs the page's scoring formulas on every cell. Run: node tests/check_ui_data.js out/siting/ui
const fs = require('fs');
const path = require('path');
const dir = process.argv[2] || 'out/siting/ui';
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
const states = [...html.matchAll(/\['([A-Z]{2})', '[^']+'(?:, '[^']+')?\]/g)].map(m => m[1]);
let failures = 0;
const check = (ok, msg) => { if (!ok) { failures++; console.log('  FAIL', msg); } };

// same formulas as the page
const KEYS = ['heat', 'carbon', 'water', 'cooling', 'grid'];
const f = (d, i) => { const c = d.cols, b = c.bws[i], cd = c.cdd[i]; return {
  heat: Math.sqrt(Math.min(c.heat[i], 60000) / 60000), carbon: Math.max(0, 1 - d.gridCO2 / 1400),
  water: b == null ? 0.5 : Math.max(0, 1 - b / 5), cooling: cd == null ? 0.5 : Math.max(0, 1 - cd / 1200),
  grid: Math.max(0, 1 - c.sub[i] / 15) }; };
const PRESETS = { balanced: [2, 2, 2, 2, 2], heat: [5, 1, 1, 1, 2], water: [1, 1, 5, 2, 2], clean: [1, 4, 2, 4, 1] };

console.log('states in page:', states.join(', '));
check(states.length === 3, 'page lists 3 states');
for (const st of states) {
  const file = path.join(dir, `data-${st.toLowerCase()}.json`);
  check(fs.existsSync(file), `${file} exists`);
  if (!fs.existsSync(file)) continue;
  const d = JSON.parse(fs.readFileSync(file));
  const n = d.cols.lat.length;
  for (const k of Object.keys(d.cols)) check(d.cols[k].length === n, `${st} column ${k} has ${n} rows`);
  for (const [i, al] of Object.entries(d.alloc)) {
    check(+i < n && d.cols.heat[+i] > 0, `${st} alloc ${i} points at a cell with heat`);
    for (const a of al) check(a[0] >= 0 && a[0] < d.sinks.length && a[1] > 0, `${st} alloc ${i} buyer index valid`);
    const sum = al.reduce((s, a) => s + a[1], 0);
    check(Math.abs(sum - d.cols.heat[+i]) <= al.length, `${st} cell ${i} heat equals sum of allocations`);
  }
  check(d.cities.length >= 5, `${st} has city labels`);
  check(d.dcs.length > 0, `${st} has existing data centers`);
  for (const [name, w] of Object.entries(PRESETS)) {
    const ws = w.reduce((a, b) => a + b, 0); let lo = 1, hi = 0, best = -1, bestS = -1, bad = 0;
    for (let i = 0; i < n; i++) {
      const F = f(d, i), s = KEYS.reduce((a, k, j) => a + w[j] * F[k], 0) / ws;
      if (!(s >= 0 && s <= 1)) bad++;
      const ex = d.cols.flood[i] > .5 || d.cols.prot[i] > .5 || d.cols.water[i] > .5;
      if (!ex) { lo = Math.min(lo, s); hi = Math.max(hi, s); if (s > bestS) { bestS = s; best = i; } }
    }
    check(bad === 0, `${st} ${name}: all scores within 0-1 (${bad} bad)`);
    check(hi > lo, `${st} ${name}: scores vary`);
    console.log(`  ${st} ${name.padEnd(8)} score range ${lo.toFixed(2)}-${hi.toFixed(2)}, best ${d.cols.lat[best]},${d.cols.lon[best]} heat=${d.cols.heat[best]}`);
  }
  console.log(`  ${st}: ${n} cells, ${Object.keys(d.alloc).length} with heat, ${d.sinks.length} buyers, ${(fs.statSync(file).size / 1e6).toFixed(1)} MB`);
}
console.log(failures ? `${failures} FAILURES` : 'ALL UI DATA CHECKS PASSED');
process.exit(failures ? 1 : 0);
