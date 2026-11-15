import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { simulate, stress, createDay, scheduledAction, CASES, ASSUMPTIONS } from '../engine.mjs';
import { evaluate, initialState, POLICY } from '../../core.mjs';

const winter = simulate({ scenario: 'winter', trace: true });
const fault = simulate({ scenario: 'fault', trace: true });

test('deterministic day replay, including full trace; different seeds change the environment', () => {
  assert.deepEqual(simulate({ scenario: 'winter', trace: true }), winter);
  assert.notEqual(simulate({ seed: 2 }).disturbanceDigest, winter.disturbanceDigest);
  assert.equal(winter.trace.length, 8640);
  assert.equal(winter.stepSeconds * 1000 <= POLICY.maxGapMs, true);
});

test('one matched exogenous day: baseline is fixed timer; M1 receives only the sensor sample', () => {
  const day = createDay();
  let state = initialState(), baselineWs = 0;
  day.forEach((d, i) => {
    const t = winter.trace[i];
    assert.deepEqual(t.hiddenScoringTruth, d.truth);
    assert.deepEqual(t.sensorSample, d.sample);
    assert.deepEqual(t.baseline, scheduledAction(d.second, 'winter'));
    const evaluated = evaluate(d.sample, state, { now: ASSUMPTIONS.epochMs + d.second * 1000, optIn: true, override: 'auto' });
    state = evaluated.state;
    assert.deepEqual(t.action, evaluated.action);
    assert.equal(t.reason, evaluated.reason);
    baselineWs += (Number(t.baseline.fan) * 40 + Number(t.baseline.light) * 20) * 10;
  });
  assert.equal(winter.baselineWs, baselineWs);
  // A changed noisy sensor cannot secretly change the baseline or hidden truth.
  const biased = createDay({ sensorBias: -2 });
  assert.deepEqual(biased.map(d => d.truth), day.map(d => d.truth));
  assert.equal(simulate({ sensorBias: -2 }).baselineWs, winter.baselineWs);
});

test('exact 24h accounting and device linearity; signed losses are never clamped', () => {
  const zero = simulate({ overheadWatts: 0 });
  const high = simulate({ overheadWatts: 30 });
  assert.equal(high.disturbanceDigest, zero.disturbanceDigest);
  assert.equal(high.baselineWs, zero.baselineWs);
  assert.equal(high.edgeLoadWs, zero.edgeLoadWs);
  assert.equal(high.deviceWs, 30 * 86400);
  assert.equal(zero.netWs - high.netWs, 30 * 86400);
  assert.equal(high.netWs < 0, true);
  assert.equal(high.recommendation, 'NOT_RECOMMENDED');
  assert.ok(high.recommendationReasons.includes('NON_POSITIVE_NET'));
  assert.equal(simulate({ overheadWatts: 0.001 }).deviceWs, 86.4);
  assert.equal(winter.breakEvenDeviceWatts, winter.grossWs / 86400);
  assert.equal(simulate({ overheadWatts: 0.125 }).netWs, zero.netWs - 10800);
  assert.equal(winter.trace.reduce((sum, t) => sum + t.baselineWs, 0), winter.baselineWs);
  assert.equal(winter.trace.reduce((sum, t) => sum + t.edgeLoadWs, 0), winter.edgeLoadWs);
});

test('HOLD remains null; hypothetical schedule fallback can be ON, never a physical command', () => {
  const held = fault.trace.filter(t => t.action === null);
  assert.ok(held.length > 0);
  assert.equal(held.length, fault.coverage.fallbackSlots);
  assert.ok(held.some(t => t.baseline.fan && t.accounted.fan && t.edgeLoadWs >= 400));
  for (const t of held) {
    assert.equal(t.decision, 'HOLD');
    assert.equal(t.accountingSource, 'HYPOTHETICAL_SCHEDULE_FALLBACK');
    assert.deepEqual(t.accounted, t.baseline);
    assert.equal(t.action, null);
    assert.equal(t.physicalExecution, false);
  }
});

test('debounce and recovery actually run: first fresh slot holds; next can simulate', () => {
  assert.equal(winter.trace[0].action, null);
  assert.equal(winter.trace[0].pendingCount, 1);
  assert.equal(winter.trace[1].decision, 'SIMULATE');
  assert.equal(winter.trace[1].pendingCount, 2);
  const recovery = fault.trace.findIndex(t => t.reason.startsWith('Watchdog gap'));
  assert.ok(recovery > 0);
  assert.equal(fault.trace[recovery].action, null);
  assert.equal(fault.trace[recovery + 1].decision, 'SIMULATE');
});

test('stale, dropout and valid-but-wrong occupancy are visible and counted', () => {
  assert.equal(fault.coverage.faultSlots, 540); // one hour dropout + half-hour stale
  assert.equal(fault.coverage.reasons['Sensor disconnected'], 360);
  assert.equal(fault.coverage.reasons['Missing, future or stale measurement'], 180);
  assert.ok(fault.trace.some(t => t.fault === 'false-empty' && t.sensorSample.occupancy === 0 && t.hiddenScoringTruth.occupancy > 0 && t.action?.fan === false));
  assert.equal(fault.coverage.actionSlots + fault.coverage.fallbackSlots, 8640);
  assert.ok(fault.coverage.fallbackEvents > 2);
  assert.ok(fault.recommendationReasons.includes('EXCESSIVE_FALLBACK'));
});

test('lower load is refused when service degrades; ground truth, not noisy readings, scores demand', () => {
  assert.ok(fault.grossWs > 0);
  assert.ok(fault.netWs > 0);
  assert.ok(fault.service.edgeOnlyUnmet.fanSeconds > 0);
  assert.equal(fault.service.baselineUnmet.fanSeconds, 0);
  assert.equal(fault.recommendation, 'NOT_RECOMMENDED');
  assert.ok(fault.recommendationReasons.includes('SERVICE_DEGRADATION_VS_BASELINE'));
  const missed = fault.trace.filter(t => t.required.fan && t.baseline.fan && !t.accounted.fan).length * 10;
  assert.equal(fault.service.edgeOnlyUnmet.fanSeconds, missed);
});

test('candidate is explicitly model-only; crossing break-even refuses', () => {
  assert.equal(winter.recommendation, 'MODEL_ONLY_CANDIDATE');
  assert.equal(winter.eligibilityScope, 'SIMULATION_ONLY');
  // Find a valid milli-watt overhead at/above break-even.
  const threshold = Math.ceil(winter.breakEvenDeviceWatts * 1000) / 1000;
  assert.equal(simulate({ overheadWatts: threshold }).recommendation, 'NOT_RECOMMENDED');
  for (const r of [winter, fault]) {
    assert.equal(r.evidence, 'SYNTHETIC');
    assert.equal(r.accounting, 'HYPOTHETICAL');
    assert.equal(r.measured, false);
    assert.equal(r.modelInference, false);
    assert.equal(r.physicalExecution, false);
    assert.equal(/verified|carbon|emissions|co2/i.test(JSON.stringify(Object.keys(r))), false);
  }
});

test('aggregate-only synthetic samples; no identity or external runtime dependencies', () => {
  for (const t of fault.trace) {
    assert.deepEqual(Object.keys(t.sensorSample).sort(), ['at', 'connected', 'humidity', 'lux', 'occupancy', 'temperature']);
    assert.deepEqual(Object.keys(t.hiddenScoringTruth).sort(), ['humidity', 'lux', 'occupancy', 'temperature']);
  }
  const engine = readFileSync(new URL('../engine.mjs', import.meta.url), 'utf8');
  const view = readFileSync(new URL('../view.mjs', import.meta.url), 'utf8');
  assert.equal(/\b(fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage)\s*[.(]|https?:\/\//.test(engine + view), false);
  assert.equal(/innerHTML/.test(view), false);
});

test('bounded shifted cohort covers seasons, late occupancy, faults, bias and service risk', () => {
  const cohort = stress({ seeds: 12, overheadWatts: 30 });
  const replay = stress({ seeds: 12, overheadWatts: 30 });
  assert.deepEqual(cohort, replay);
  assert.deepEqual([...new Set(cohort.cases.map(c => c.scenario))].sort(), [...CASES].sort());
  assert.equal(new Set(cohort.cases.map(c => c.shiftHours)).size, 4);
  for (const scenario of CASES) {
    assert.equal(new Set(cohort.cases.filter(c => c.scenario === scenario).map(c => c.shiftHours)).size, 3);
  }
  assert.ok(new Set(cohort.cases.map(c => c.sensorBias)).size > 1);
  const sorted = cohort.cases.map(c => c.netWs).sort((a, b) => a - b);
  assert.equal(cohort.worstNetWs, sorted[0]);
  assert.equal(cohort.medianNetWs, (sorted[5] + sorted[6]) / 2);
  assert.equal(cohort.meanNetWs, sorted.reduce((a, b) => a + b) / 12);
  assert.equal(cohort.negativeCases, sorted.filter(n => n < 0).length);
  assert.ok(cohort.negativeCases > 0);
  assert.ok(cohort.degradedCases > 0);
  assert.equal(cohort.recommendation, 'NOT_RECOMMENDED');
});

test('malformed or unbounded inputs refuse rather than producing NaN or runaway work', () => {
  for (const overheadWatts of [-1, 31, Infinity, NaN, '4', 0.0001]) assert.throws(() => simulate({ overheadWatts }));
  for (const seed of [-1, 0x100000000, 1.5, NaN]) assert.throws(() => simulate({ seed }));
  for (const seeds of [0, 1, 3, 33, Infinity, 4.5]) assert.throws(() => stress({ seeds }));
  assert.throws(() => simulate({ scenario: 'unknown' }));
  assert.throws(() => simulate({ shiftHours: 3 }));
  assert.throws(() => simulate({ sensorBias: NaN }));
  assert.throws(() => simulate({ trace: 'yes' }));
});

test('CLI emits deterministic JSON, includes cohort statistics, refuses excessive input', () => {
  const cli = new URL('../cli.mjs', import.meta.url);
  const run = args => spawnSync(process.execPath, [cli.pathname, ...args], { encoding: 'utf8', timeout: 15000 });
  const a = run(['winter', '4']);
  assert.equal(a.status, 0, a.stderr);
  assert.equal(a.stdout, run(['winter', '4']).stdout);
  assert.equal(JSON.parse(a.stdout).evidence, 'SYNTHETIC');
  const cohort = run(['summer', '30', '--seeds=4', '--seed=2']);
  assert.equal(cohort.status, 0, cohort.stderr);
  assert.equal(JSON.parse(cohort.stdout).cases.length, 4);
  const bad = run(['fault', 'NaN', '--seeds=1000000']);
  assert.equal(bad.status, 1);
  assert.equal(bad.stdout, '');
  assert.equal(JSON.parse(bad.stderr).evidence, 'SYNTHETIC');
  assert.equal(run(['winter', '4', '--seed=1', '--seed=2']).status, 1);
});

test('browser view handlers wire real HTML IDs, single/stress runs, changed and invalid controls', async () => {
  // Dependency-free DOM harness, not a browser rendering/accessibility verdict.
  const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');
  class Element {
    constructor() { this.textContent = ''; this.children = []; this.listeners = {}; this.hidden = false; this.value = ''; }
    append(child) { this.children.push(child); }
    replaceChildren(...children) { this.children = children; }
    addEventListener(event, handler) { this.listeners[event] = handler; }
    fire(event) { this.listeners[event](); }
  }
  const elements = new Map([...html.matchAll(/id="(twin-[^"]+)"/g)].map(m => [m[1], new Element()]));
  assert.equal(elements.size, [...html.matchAll(/id="(twin-[^"]+)"/g)].length);
  const get = suffix => {
    const element = elements.get(`twin-${suffix}`);
    assert.ok(element, `HTML must supply twin-${suffix}`);
    return element;
  };
  const previous = globalThis.document;
  globalThis.document = { getElementById: id => elements.get(id), createElement: () => new Element() };
  try {
    await import('../view.mjs');
    get('case').value = 'winter'; get('overhead').value = '4';
    get('single').fire('click');
    assert.match(get('status').textContent, /MODEL_ONLY_CANDIDATE/);
    assert.equal(get('results').hidden, false);
    assert.equal(get('hours').children.length, 24);
    assert.equal(get('services').children.length, 2);
    assert.equal(JSON.parse(get('diagnostic').textContent).action, null);
    get('slot').value = '1'; get('slot').fire('input');
    assert.equal(JSON.parse(get('diagnostic').textContent).decision, 'SIMULATE');
    get('overhead').value = '30'; get('overhead').fire('input');
    assert.equal(get('results').hidden, true);
    get('stress').fire('click');
    assert.match(get('status').textContent, /NOT_RECOMMENDED/);
    assert.equal(get('cases').children.length, 12);
    assert.equal(get('inspector').hidden, true);
    assert.match(get('cohort-summary').textContent, /worst .* median .* mean/);
    get('case').value = 'fault'; get('overhead').value = '4';
    get('single').fire('click');
    assert.match(get('risk').textContent, /misses required service/);
    get('overhead').value = '';
    get('single').fire('click');
    assert.match(get('status').textContent, /Run refused/);
    assert.equal(get('results').hidden, true);
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});
