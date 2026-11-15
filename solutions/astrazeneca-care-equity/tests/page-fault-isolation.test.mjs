// Fault isolation on the page: every renderer called from init() and selectRegion() runs through guard(), so one throw
// shows "This section could not be shown" in its own container and the panels after it still render.
// app.mjs needs a browser (absolute /src imports, document), so this checks the wiring in the source and runs the
// guard() function itself against a stub.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const text = (p) => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8');

test('init() and selectRegion() call each renderer through guard() with its own container', () => {
  const js = text('web/app.mjs'), index = text('web/index.html');
  const sel = js.slice(js.indexOf('function selectRegion'), js.indexOf('function mount'));
  for (const [id, fn] of [['map', 'renderGeography'], ['county-summary', 'renderCounty'], ['brief-content', 'renderBrief']]) assert.ok(sel.includes(`guard('${id}',${fn})`), `selectRegion guards ${fn}`);
  assert.ok(js.includes("function renderPlanner(){guard('planner-content',renderPlannerPanel);}"), 'renderPlanner is guarded');
  const init = js.slice(js.indexOf('async function init'));
  for (const [id, fn] of [['provenance', 'header'], ['assumptions', 'controls'], ['scoreboard', 'scoreboard'], ['portfolio', 'renderPortfolio'], ['scenarios', 'scenarios'], ['evidence-list', 'evidence']]) assert.ok(init.includes(`guard('${id}',${fn})`), `init guards ${fn}`);
  for (const id of ['decision-content', 'future-context', 'map', 'county-summary', 'brief-content', 'planner-content', 'provenance', 'assumptions', 'scoreboard', 'portfolio', 'scenarios', 'evidence-list']) assert.ok(index.includes(`id="${id}"`), `container #${id} exists`);
});

test('guard(): a throw shows the message in its panel, logs, and later panels still run', () => {
  const js = text('web/app.mjs');
  const start = js.indexOf('function guard'), src = js.slice(start, js.indexOf('\n', start));
  const shown = {}, errors = [];
  const guard = new Function('esc', 'mount', 'console', `${src}; return guard;`)((v) => String(v), (id, html) => { shown[id] = html; }, { error: (...a) => errors.push(a) });
  const ran = [];
  guard('a', () => { throw new Error('boom'); });
  guard('b', () => ran.push('b'));
  assert.equal(shown.a, '<p class="missing-label">This section could not be shown: boom</p>');
  assert.deepEqual(ran, ['b']);
  assert.equal(shown.b, undefined, 'a panel that does not throw is left alone');
  assert.equal(errors.length, 1);
});
