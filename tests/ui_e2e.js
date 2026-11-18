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

const canvasCalls = { fillRect: 0, arc: 0, lineTo: 0 };
const ctxStub = new Proxy({}, { get: (t, k) => {
  if (k in canvasCalls) return () => { canvasCalls[k]++; };
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

(async () => {
  await sleep(1500);
  const TL = win.ThermaLite;
  check(!!TL, 'page script ran and exposed its test handle');

  console.log('Navigation');
  check(!$('view-map').hidden && $('view-tutorial').hidden && $('view-about').hidden, 'map view shows first');
  for (const v of ['tutorial', 'about', 'map']) {
    win.location.hash = v; await sleep(50);
    check(!$('view-' + v).hidden, `#${v} shows its page`);
    check($('nav-' + v).getAttribute('aria-current') === 'page', `nav marks ${v} as current`);
  }

  console.log('States');
  const targets = [...doc.querySelectorAll('#targets button')].map(b => b.textContent);
  check(targets.join(',') === 'Virginia,Texas,North Carolina', `three state buttons (${targets})`);
  for (const st of ['VA', 'TX', 'NC']) {
    await TL.switchState(st); await sleep(50);
    const n = TL.S.data[st].cols.lat.length;
    check($('loading').hidden, `${st} loaded`);
    check(TL.S.score.length === n, `${st} scored all ${n} squares`);
    check(doc.querySelectorAll('#top li').length === 10, `${st} top 10 listed`);
    check(/of [\d,]+/.test($('verdict').textContent), `${st} verdict shows a count`);
    check(Number($('lg-hi').textContent) > Number($('lg-lo').textContent), `${st} legend range`);
    check(canvasCalls.fillRect > 1000, `${st} map drew squares`);
    canvasCalls.fillRect = 0;
  }

  console.log('Presets and sliders');
  for (const p of ['heat', 'water', 'clean', 'balanced']) {
    const btn = doc.querySelector(`.plist button[data-p="${p}"]`); const before = $('top').innerHTML;
    btn.click(); await sleep(20);
    check(btn.getAttribute('aria-pressed') === 'true', `preset ${p} highlights`);
    if (p !== 'balanced') check($('top').innerHTML !== before || p === 'heat', `preset ${p} re-ranks`);
  }
  const slider = $('w-water'); slider.value = '5'; slider.dispatchEvent(new win.Event('input'));
  check($('o-water').textContent === '5', 'slider output updates');
  check([...doc.querySelectorAll('.plist button')].every(b => b.getAttribute('aria-pressed') === 'false'), 'custom weights clear preset highlight');

  console.log('Site report and heat plan');
  doc.querySelector('.plist button[data-p="heat"]').click(); await TL.switchState('TX'); await sleep(50);
  doc.querySelector('#top button').click(); await sleep(20);
  check(/Site report/.test($('reportSec').textContent) && /Heat reuse/.test($('reportSec').textContent), 'report opens with factor bars');
  check(/Heat delivery plan/.test($('reportSec').textContent), 'report has heat delivery plan section');
  check(/Altman Plants/.test($('reportSec').textContent), 'Texas #1 heat-first site sells to Altman Plants');
  check(doc.querySelectorAll('#reportSec table tr').length >= 2, 'heat plan table has buyer rows');
  const noHeat = TL.S.data.TX.cols.heat.findIndex(h => h === 0);
  TL.select(noHeat, false); await sleep(10);
  check(/would be vented/.test($('reportSec').textContent), 'no-buyer site explains its heat would be vented');

  console.log('Map interaction');
  const cv = $('map');
  const ev = (type, x, y) => cv.dispatchEvent(new win.MouseEvent(type, { clientX: x, clientY: y, bubbles: true }));
  ev('pointermove', 450, 300); await sleep(20);
  check(/LAT .* LON/.test($('hud').textContent), `hover readout shows coordinates (${$('hud').textContent.slice(0, 60)})`);
  ev('pointerdown', 450, 300); ev('pointerup', 450, 300); await sleep(10);
  check(TL.S.sel >= -1, 'click on map selects a square or nothing without error');
  const s0 = TL.S.view.s; $('z-in').click(); check(TL.S.view.s > s0, 'zoom in'); $('z-out').click(); $('z-fit').click();
  check(TL.S.view.s > 0, 'fit restores a view');
  $('c-excl').click(); await sleep(10); check(TL.S.ex.every(x => x === 0), 'turning off exclusions un-greys all squares'); $('c-excl').click();
  $('c-dc').click(); check(TL.S.showDC === false, 'hide existing data centers'); $('c-dc').click();

  console.log('Guided tour');
  TL.startTour(); await sleep(20);
  for (let step = 1; step <= 6; step++) {
    const tip = doc.querySelector('.tour-tip');
    check(tip && tip.textContent.includes(`Step ${step} of 6`), `tour step ${step} shows`);
    $('tourNext').click(); await sleep(20);
  }
  check(!doc.querySelector('.tour-tip') && !doc.querySelector('.tour-ring'), 'tour closes after Finish');
  win.location.hash = 'tutorial'; await sleep(30);
  $('tourFromTutorial').click(); await sleep(150);
  check(!$('view-map').hidden && doc.querySelector('.tour-tip'), 'tutorial button opens map and starts tour');
  doc.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape' })); await sleep(10);
  check(!doc.querySelector('.tour-tip'), 'Escape closes the tour');

  console.log('Content');
  const about = $('view-about').textContent, tut = $('view-tutorial').textContent;
  check(/40 independent sites/.test(about) && /Data sources/.test(about) && /Limits/.test(about), 'about page has findings, sources, limits');
  check((tut.match(/Choose a mission target|Pick a mission profile|Read the map|Hover and zoom|Open a site report|Fine-tune and compare/g) || []).length === 6, 'tutorial has 6 steps');
  check(/What every output means/.test(tut), 'tutorial explains every output');
  check(!/NASA/i.test(html), 'page does not use the NASA name');
  check(errors.length === 0, `no script errors (${errors.join(' | ')})`);

  console.log(`${passes} passed, ${failures} failed`);
  console.log(failures ? 'UI E2E FAILED' : 'UI E2E PASSED');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log('CRASH', e.stack); process.exit(1); });
