// End-to-end test of the siting UI in a simulated browser (jsdom).
// Usage: NODE_PATH=<dir with jsdom> node tests/ui_e2e.js out/siting/ui
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const dir = process.argv[2] || 'out/siting/ui';
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
let failures = 0, passes = 0;
const check = (ok, msg) => { if (ok) passes++; else { failures++; console.log('  FAIL', msg); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const calls = { fillRect: 0, arc: 0, lineTo: 0, fillText: 0 };
const ctxStub = new Proxy({}, { get: (t, k) => {
  if (k in calls) return () => { calls[k]++; };
  if (k === 'measureText') return () => ({ width: 10 });
  return typeof k === 'string' && /^[a-z]/.test(k) ? (t[k] ?? (() => {})) : undefined;
}, set: (t, k, v) => { t[k] = v; return true; } });

const dom = new JSDOM(`<!doctype html><html><head></head><body>${html}</body></html>`, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://example.test/#map',
  beforeParse(win) {
    win.HTMLCanvasElement.prototype.getContext = () => ctxStub;
    Object.defineProperty(win.HTMLElement.prototype, 'clientWidth', { get() { return 900; } });
    Object.defineProperty(win.HTMLElement.prototype, 'clientHeight', { get() { return 600; } });
    win.HTMLElement.prototype.getBoundingClientRect = function () { return { left: 0, top: 0, right: 900, bottom: 600, width: 900, height: 600 }; };
    win.HTMLElement.prototype.scrollIntoView = () => {};
    win.HTMLElement.prototype.setPointerCapture = () => {};
    win.ResizeObserver = class { observe() {} };
    win.matchMedia = () => ({ matches: false, addEventListener() {} });
    win.requestAnimationFrame = cb => setTimeout(cb, 0);
    win.fetch = async url => {
      const p = path.join(dir, String(url));
      if (!fs.existsSync(p)) return { ok: false, status: 404 };
      return { ok: true, status: 200, json: async () => JSON.parse(fs.readFileSync(p, 'utf8')) };
    };
  },
});
const win = dom.window, doc = win.document, $ = id => doc.getElementById(id);
const errors = [];
win.addEventListener('error', e => errors.push(e.message));
const press = sel => doc.querySelector(sel).click();

(async () => {
  await sleep(1500);
  const TL = win.ThermaLite;
  check(!!TL, 'page script ran');

  console.log('Pages');
  check(!$('view-map').hidden && $('view-guide').hidden && $('view-about').hidden, 'map shows first');
  for (const v of ['guide', 'about', 'map']) {
    win.location.hash = v; await sleep(40);
    check(!$('view-' + v).hidden, `#${v} shows`);
    check($('nav-' + v).getAttribute('aria-current') === 'page', `nav marks ${v}`);
  }

  console.log('Theme and type');
  check(/family=Inter/.test(html), 'Inter font loaded');
  check(/--green:/.test(html) && /prefers-color-scheme: dark/.test(html) && /\[data-theme="dark"\]/.test(html), 'green theme with light and dark modes');
  check(TL.S.ramp.length === 7 && TL.S.ramp.every(c => /^#/.test(c)), 'map color ramp read from theme');
  check(!/NASA/i.test(html), 'no NASA branding');

  console.log('States');
  const names = [...doc.querySelectorAll('#states button')].map(b => b.textContent).join(',');
  check(names === 'Virginia,Texas,North Carolina', `state control (${names})`);
  for (const st of ['VA', 'TX', 'NC']) {
    press(`#states button[data-st="${st}"]`); await sleep(400);
    const d = TL.S.data[st], n = d && d.cols.lat.length;
    check(!!d && $('loading').hidden, `${st} loads`);
    check(TL.S.score && TL.S.score.length === n, `${st} scores ${n} squares`);
    check(doc.querySelectorAll('#top li').length === 10, `${st} top 10`);
    check($('sumTitle').textContent === d.name && doc.querySelectorAll('#kpis .kpi').length === 3, `${st} summary`);
    check(calls.fillRect > 1000, `${st} map drawn`); calls.fillRect = 0;
    check(doc.querySelector(`#states button[data-st="${st}"]`).getAttribute('aria-pressed') === 'true', `${st} marked selected`);
  }

  console.log('Priority and weights');
  for (const p of ['heat', 'water', 'clean', 'balanced']) {
    press(`#presets button[data-p="${p}"]`); await sleep(20);
    check(doc.querySelector(`#presets button[data-p="${p}"]`).getAttribute('aria-pressed') === 'true', `priority ${p} selected`);
    check($('caption').textContent.length > 20, `caption explains ${p}`);
  }
  check($('weights').hidden, 'weights hidden by default');
  press('#weightsBtn'); await sleep(10);
  check(!$('weights').hidden && $('weightsBtn').getAttribute('aria-expanded') === 'true', 'Adjust weights opens sliders');
  const before = $('top').innerHTML; const s = $('w-water'); s.value = '5'; s.dispatchEvent(new win.Event('input')); await sleep(10);
  check($('o-water').textContent === '5', 'slider value shows');
  check(/Custom weights/.test($('caption').textContent), 'caption switches to custom');
  check($('top').innerHTML !== before, 'slider re-ranks top 10');
  press('#weightsBtn'); check($('weights').hidden, 'weights close again');

  console.log('Site report');
  press('#presets button[data-p="heat"]'); press('#states button[data-st="TX"]'); await sleep(300);
  press('#top button'); await sleep(20);
  check($('overview').hidden && !$('report').hidden, 'report replaces the overview');
  check(/Score breakdown/.test($('report').textContent) && doc.querySelectorAll('#report .factor').length === 5, 'five factor rows');
  check(/Heat delivery plan/.test($('report').textContent) && /Altman Plants/.test($('report').textContent), 'Texas #1 sells heat to Altman Plants');
  check(/Heat would sell/.test($('report').textContent), 'status badge shows heat would sell');
  check(calls.lineTo > 0, 'heat lines drawn on map');
  press('#back'); await sleep(10);
  check(!$('overview').hidden && $('report').hidden, 'back returns to top 10');
  const noHeat = TL.S.data.TX.cols.heat.findIndex((h, i) => h === 0 && !TL.S.ex[i]);
  TL.select(noHeat, false); await sleep(10);
  check(/would be vented/.test($('report').textContent) && /Buildable/.test($('report').textContent), 'no-buyer site explains venting');
  const out = TL.S.ex.findIndex(x => x === 1);
  TL.select(out, false); await sleep(10);
  check(/Ruled out/.test($('report').textContent), 'ruled-out site says so');
  press('#back');

  console.log('Map');
  const cv = $('map'), ev = (t, x, y) => cv.dispatchEvent(new win.MouseEvent(t, { clientX: x, clientY: y, bubbles: true }));
  ev('pointermove', 450, 300); await sleep(30);
  check(!$('tip').hidden && /Score \d\.\d\d/.test($('tip').textContent), `hover tooltip (${$('tip').textContent.slice(0, 40)})`);
  ev('pointerleave', 0, 0); check($('tip').hidden, 'tooltip hides on leave');
  ev('pointerdown', 450, 300); ev('pointerup', 450, 300); await sleep(10);
  check(TL.S.sel >= 0 && !$('report').hidden, 'clicking a square opens its report');
  press('#back');
  const s0 = TL.S.view.s; press('#z-in'); check(TL.S.view.s > s0, 'zoom in'); press('#z-out'); press('#z-fit');
  $('c-excl').click(); await sleep(10); check(TL.S.ex.every(x => x === 0), 'exclusion toggle'); $('c-excl').click();
  $('c-dc').click(); check(TL.S.showDC === false, 'data center toggle'); $('c-dc').click();

  console.log('Tour');
  press('#tourBtn'); await sleep(20);
  for (let k = 1; k <= 6; k++) {
    const card = doc.querySelector('.tour-card');
    check(card && card.textContent.includes(`Step ${k} of 6`), `tour step ${k}`);
    if (k === 2) { press('#tourBack'); await sleep(10); check(doc.querySelector('.tour-card').textContent.includes('Step 1 of 6'), 'tour back'); press('#tourNext'); await sleep(10); }
    press('#tourNext'); await sleep(20);
  }
  check(!doc.querySelector('.tour-card') && !doc.querySelector('.tour-ring'), 'tour closes on Done');
  win.location.hash = 'guide'; await sleep(30); press('#guideTour'); await sleep(150);
  check(!$('view-map').hidden && !!doc.querySelector('.tour-card'), 'Guide button opens tour on the map');
  doc.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape' })); await sleep(10);
  check(!doc.querySelector('.tour-card'), 'Escape ends tour');

  console.log('Content');
  const guide = $('view-guide').textContent, about = $('view-about').textContent;
  check(doc.querySelectorAll('#view-guide ol.steps li').length === 6, 'guide has 6 steps');
  check(doc.querySelectorAll('#view-guide dl.defs dt').length === 9, 'guide defines 9 outputs');
  check(/40/.test(about) && /Limitations/.test(about) && /Data sources/.test(about), 'about has findings, limits, sources');
  check(errors.length === 0, `no script errors ${errors.join(' | ')}`);

  console.log(`${passes} passed, ${failures} failed`);
  console.log(failures ? 'UI E2E FAILED' : 'UI E2E PASSED');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log('CRASH', e.stack); process.exit(1); });
