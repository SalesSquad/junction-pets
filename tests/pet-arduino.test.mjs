import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewCompatibility} from '../pets/arduino/compatibility.mjs';

const fixture = () => JSON.parse(readFileSync(new URL('../pets/arduino/example.json', import.meta.url), 'utf8'));
const splitFixture = () => {
  const x = fixture();
  x.schemaVersion = 2;
  for (const part of [x.board, ...x.sensors]) {
    part.supplyVoltageMv = part.voltageMv;
    part.logicVoltageMv = 1800;
    delete part.voltageMv;
  }
  return x;
};
const rejected = x => {
  const r = reviewCompatibility(x);
  assert.equal(r.status, 'invalid');
  assert.deepEqual(r.issues, ['malformed-or-unsupported-input']);
  assert.equal(r.totals, null);
  assert.equal(r.budgets, null);
  assert.equal(r.inputSchema, null);
  assert.ok(r.diagnostics.length >= 1);
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
};
const needsReview = (x, issues, totals = {supplyMa: 14, signalMa: 3}) => {
  const r = reviewCompatibility(x);
  assert.equal(r.status, 'needs-review');
  assert.deepEqual(r.issues, issues);
  assert.deepEqual(r.totals, totals);
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
};

test('fictional worked arithmetic and review boundary', () => {
  const x = fixture(), before = structuredClone(x), r = reviewCompatibility(x);
  assert.equal(r.status, 'consistent');
  assert.deepEqual(r.totals, {supplyMa: 14, signalMa: 3});
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
  assert.ok(r.unknowns.length >= 3);
  assert.deepEqual(x, before);
  assert.deepEqual(reviewCompatibility(x), r);
});

test('split supply and logic voltages are independent and legacy remains explicit', () => {
  const legacy = reviewCompatibility(fixture());
  assert.equal(legacy.inputSchema, 'legacy-single-voltage');
  assert.deepEqual(legacy.diagnostics, []);
  const x = splitFixture(), r = reviewCompatibility(x);
  assert.equal(r.status, 'consistent');
  assert.equal(r.inputSchema, 'split-voltage-v2');
  assert.deepEqual(r.issues, []);
  assert.deepEqual(r.diagnostics, []);
  assert.deepEqual(r.totals, {supplyMa: 14, signalMa: 3});
  assert.equal(x.board.supplyVoltageMv, 3000);
  assert.equal(x.board.logicVoltageMv, 1800);
});

test('documented split-voltage JSON example matches the published arithmetic', () => {
  const x = JSON.parse(readFileSync(new URL('../pets/arduino/example-v2.json', import.meta.url), 'utf8'));
  const r = reviewCompatibility(x);
  assert.equal(r.status, 'consistent');
  assert.equal(r.inputSchema, 'split-voltage-v2');
  assert.equal(x.board.supplyVoltageMv, 5000);
  assert.equal(x.board.logicVoltageMv, 3000);
  assert.deepEqual(r.issues, []);
  assert.deepEqual(r.diagnostics, []);
  assert.deepEqual(r.totals, {supplyMa: 14, signalMa: 3});
  assert.deepEqual(r.budgets, {
    total: {demandMa: 17, limitMa: 30, headroomMa: 13},
    signal: {demandMa: 3, limitMa: 6, headroomMa: 3},
    pins: [
      {pin: 'P0', demandMa: 1, limitMa: 4, headroomMa: 3},
      {pin: 'P1', demandMa: 2, limitMa: 4, headroomMa: 2},
    ],
  });
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
});

test('supply voltage regression reports the exact field and declared mismatch', () => {
  const x = splitFixture(); x.sensors[0].supplyVoltageMv = 3300;
  needsReview(x, ['voltage-mismatch:sensor-a']);
  const [d] = reviewCompatibility(x).diagnostics;
  assert.equal(d.code, 'voltage-mismatch:sensor-a');
  assert.equal(d.path, 'sensors[0].supplyVoltageMv');
  assert.equal(d.actual, 3300);
  assert.ok(d.expected !== undefined);
  assert.equal(typeof d.correction, 'string');
  assert.ok(d.correction.length > 0);
});

test('logic voltage regression cannot be masked by matching supply voltage', () => {
  const x = splitFixture(); x.sensors[0].logicVoltageMv = 2500;
  needsReview(x, ['logic-voltage-mismatch:sensor-a']);
  const [d] = reviewCompatibility(x).diagnostics;
  assert.equal(d.code, 'logic-voltage-mismatch:sensor-a');
  assert.equal(d.path, 'sensors[0].logicVoltageMv');
  assert.equal(d.actual, 2500);
  assert.ok(d.expected !== undefined);
  assert.ok(d.correction.length > 0);
});

test('split voltage schema rejects mixed, omitted, unknown and malformed declarations', () => {
  for (const mutate of [
    x => x.schemaVersion = 1, x => x.schemaVersion = 3, x => x.schemaVersion = '2',
    x => x.schemaVersion = null, x => delete x.schemaVersion,
    x => x.board.voltageMv = 3000, x => x.sensors[0].voltageMv = 3000,
    x => delete x.board.supplyVoltageMv, x => delete x.sensors[0].logicVoltageMv,
    x => x.board.logicVoltageMv = null, x => x.sensors[0].supplyVoltageMv = 0,
    x => x.board.supplyVoltageMv = 3.3,
  ]) { const x = splitFixture(); mutate(x); rejected(x); }
  const legacy = fixture(); legacy.schemaVersion = 2; rejected(legacy);
});

test('review budgets expose exact demand, limits and remaining current', () => {
  const r = reviewCompatibility(splitFixture());
  assert.deepEqual(r.budgets, {
    total: {demandMa: 17, limitMa: 30, headroomMa: 13},
    signal: {demandMa: 3, limitMa: 6, headroomMa: 3},
    pins: [
      {pin: 'P0', demandMa: 1, limitMa: 4, headroomMa: 3},
      {pin: 'P1', demandMa: 2, limitMa: 4, headroomMa: 2},
    ],
  });
  const x = splitFixture();
  x.board.powerLimitMa = 16; x.board.totalPinLimitMa = 2; x.board.pinLimitMa = 1;
  const excess = reviewCompatibility(x);
  assert.deepEqual(excess.issues, ['pin-oversubscribed:P1', 'power-oversubscribed', 'signal-oversubscribed']);
  assert.equal(excess.budgets.total.headroomMa, -1);
  assert.equal(excess.budgets.signal.headroomMa, -1);
  assert.equal(excess.budgets.pins[1].headroomMa, -1);
  assert.equal(excess.budgets.pins[0].headroomMa, 0);
});

test('unknown budget limits remain null and zero limits stay known', () => {
  for (const key of ['powerLimitMa', 'pinLimitMa', 'totalPinLimitMa']) {
    const x = splitFixture(); x.board[key] = null;
    needsReview(x, [`unknown-${key}`]);
    const r = reviewCompatibility(x);
    const budgets = key === 'powerLimitMa' ? [r.budgets.total] : key === 'totalPinLimitMa' ? [r.budgets.signal] : r.budgets.pins;
    for (const b of budgets) {assert.equal(b.limitMa, null); assert.equal(b.headroomMa, null);}
    delete x.board[key]; rejected(x);
  }
  const x = splitFixture(); x.board.powerLimitMa = 0;
  assert.deepEqual(reviewCompatibility(x).budgets.total, {demandMa: 17, limitMa: 0, headroomMa: -17});
});

test('duplicate pin regression reports conflict and aggregates its declared demand', () => {
  const x = splitFixture(); x.sensors[1].pins[0].pin = 'P0'; x.sensors[1].pins[0].mode = 'input';
  needsReview(x, ['duplicate-pin:P0']);
  const r = reviewCompatibility(x);
  assert.deepEqual(r.budgets.pins, [{pin: 'P0', demandMa: 3, limitMa: 4, headroomMa: 1}]);
  assert.ok(r.diagnostics.some(d => d.code === 'duplicate-pin:P0' && d.path === 'sensors[1].pins[0].pin'));
});

test('per-pin current regression reports demand and limit for that pin', () => {
  const x = splitFixture(); x.sensors[1].pins[0].currentMa = 5;
  needsReview(x, ['pin-oversubscribed:P1'], {supplyMa: 14, signalMa: 6});
  const d = reviewCompatibility(x).diagnostics.find(d => d.code === 'pin-oversubscribed:P1');
  assert.equal(d.path, 'sensors[1].pins[0].currentMa');
  assert.equal(d.actual, 5);
  assert.ok(d.expected !== undefined);
  assert.ok(d.correction.length > 0);
});

test('total current regression counts signal demand in the supply budget', () => {
  const x = splitFixture(); x.board.powerLimitMa = 16;
  needsReview(x, ['power-oversubscribed']);
  const r = reviewCompatibility(x);
  assert.equal(r.budgets.total.demandMa, 17);
  const d = r.diagnostics.find(d => d.code === 'power-oversubscribed');
  assert.equal(d.path, 'board.powerLimitMa');
  assert.equal(d.actual, 16);
  assert.equal(d.expected, 'at least 17 mA for declared demand');
});

test('aggregate signal current regression retains its independent budget', () => {
  const x = splitFixture(); x.board.totalPinLimitMa = 2;
  needsReview(x, ['signal-oversubscribed']);
  const r = reviewCompatibility(x);
  assert.deepEqual(r.budgets.signal, {demandMa: 3, limitMa: 2, headroomMa: -1});
  assert.equal(r.budgets.total.headroomMa, 13);
  const d = r.diagnostics.find(d => d.code === 'signal-oversubscribed');
  assert.equal(d.path, 'board.totalPinLimitMa');
  assert.equal(d.actual, 2);
  assert.equal(d.expected, 'at least 3 mA for declared demand');
});

test('malformed diagnostics identify missing, unknown, count and numeric fields safely', () => {
  for (const [mutate, code, path] of [
    [x => delete x.board.powerLimitMa, 'missing-field', 'board.powerLimitMa'],
    [x => x.board.unrecognized = 1, 'unknown-field', 'board.unrecognized'],
    [x => x.board.pinCount = 3, 'invalid-count', 'board.pinCount'],
    [x => x.sensors[0].currentMa = -1, 'invalid-number', 'sensors[0].currentMa'],
  ]) {
    const x = splitFixture(); mutate(x); rejected(x);
    const [d] = reviewCompatibility(x).diagnostics;
    assert.equal(d.code, code); assert.equal(d.path, path);
    assert.ok(d.expected !== undefined);
    assert.equal(typeof d.correction, 'string'); assert.ok(d.correction.length > 0);
    assert.ok(d.actual === null || ['string', 'number', 'boolean'].includes(typeof d.actual));
  }
});

test('v2 schema selection and diagnostics never invoke getters, hooks or proxy traps', () => {
  let calls = 0;
  for (const mutate of [
    x => Object.defineProperty(x, 'schemaVersion', {get() {calls++; throw Error('version getter');}}),
    x => Object.defineProperty(x.board, 'logicVoltageMv', {get() {calls++; throw Error('voltage getter');}}),
    x => x.board.logicVoltageMv = {toJSON() {calls++; throw Error('conversion hook');}},
    x => x.sensors[0].logicVoltageMv = new Proxy({}, {get() {calls++; throw Error('proxy');}}),
  ]) {
    const x = splitFixture(); mutate(x); rejected(x);
    const r = reviewCompatibility(x);
    assert.doesNotThrow(() => JSON.stringify(r));
  }
  assert.equal(calls, 0);
});

test('budgets and diagnostics are isolated from inputs and subsequent results', () => {
  const x = splitFixture(); x.sensors[0].logicVoltageMv = 2500;
  const before = structuredClone(x), first = reviewCompatibility(x), second = reviewCompatibility(x);
  first.budgets.total.demandMa = 999;
  first.budgets.pins[0].pin = 'changed';
  first.diagnostics[0].correction = 'changed';
  first.unknowns[0] = 'changed';
  assert.deepEqual(x, before);
  assert.deepEqual(reviewCompatibility(x), second);
});

test('power and pin limits: exact boundary, zero, unknown and missing differ', () => {
  const x = fixture(); x.board.powerLimitMa = 17; x.board.totalPinLimitMa = 3;
  assert.equal(reviewCompatibility(x).status, 'consistent');
  x.board.powerLimitMa = 16; needsReview(x, ['power-oversubscribed']);
  x.board.powerLimitMa = 0; assert.ok(reviewCompatibility(x).issues.includes('power-oversubscribed'));
  x.board.powerLimitMa = null; assert.ok(reviewCompatibility(x).issues.includes('unknown-powerLimitMa'));
  delete x.board.powerLimitMa; assert.equal(reviewCompatibility(x).status, 'invalid');
});

test('each mismatch and oversubscription fails closed independently', () => {
  for (const [change, issues, totals] of [
    [x => x.sensors[0].voltageMv++, ['voltage-mismatch:sensor-a']],
    [x => x.sensors[0].ground = false, ['missing-ground:sensor-a']],
    [x => x.sensors[0].pins[0].mode = 'output', ['mode-mismatch:P0']],
    [x => x.sensors[0].pins[0].pin = 'absent', ['unknown-pin:absent']],
    [x => {x.sensors[1].pins[0].pin = 'P0'; x.sensors[1].pins[0].mode = 'input';}, ['duplicate-pin:P0']],
    [x => x.board.pinLimitMa = 0, ['pin-oversubscribed:P0', 'pin-oversubscribed:P1']],
    [x => x.board.totalPinLimitMa = 2, ['signal-oversubscribed']],
    [x => x.sensors[0].currentMa = 100, ['power-oversubscribed'], {supplyMa: 106, signalMa: 3}],
  ]) { const x = fixture(); change(x); needsReview(x, issues, totals); }
  for (const change of [x => x.board.pins[1].id = 'P0', x => x.sensors[1].id = 'sensor-a']) {
    const x = fixture(); change(x); rejected(x);
  }
});

test('all limit fields distinguish missing, null, zero, boundary and excess', () => {
  for (const [key, boundary, excessIssues, zeroIssues] of [
    ['powerLimitMa', 17, ['power-oversubscribed'], ['power-oversubscribed']],
    ['pinLimitMa', 2, ['pin-oversubscribed:P1'], ['pin-oversubscribed:P0', 'pin-oversubscribed:P1']],
    ['totalPinLimitMa', 3, ['signal-oversubscribed'], ['signal-oversubscribed']],
  ]) {
    const x = fixture(); x.board[key] = boundary;
    assert.equal(reviewCompatibility(x).status, 'consistent');
    x.board[key]--; needsReview(x, excessIssues);
    x.board[key] = 0; needsReview(x, zeroIssues);
    x.board[key] = null; needsReview(x, [`unknown-${key}`]);
    delete x.board[key]; rejected(x);
  }
});

test('proxy inputs at every structural position are rejected without executing traps', () => {
  let calls = 0;
  const handler = Object.fromEntries(['get', 'getPrototypeOf', 'ownKeys', 'getOwnPropertyDescriptor'].map(k =>
    [k, () => {calls++; throw Error('input trap');}]));
  for (const replace of [
    (x, wrap) => wrap(x),
    (x, wrap) => {x.board = wrap(x.board); return x;},
    (x, wrap) => {x.sensors = wrap(x.sensors); return x;},
    (x, wrap) => {x.board.pins[0] = wrap(x.board.pins[0]); return x;},
    (x, wrap) => {x.board.pins[0].modes = wrap(x.board.pins[0].modes); return x;},
    (x, wrap) => {x.sensors[0].pins[0] = wrap(x.sensors[0].pins[0]); return x;},
  ]) rejected(replace(fixture(), value => new Proxy(value, handler)));
  const revoked = Proxy.revocable({}, handler); revoked.revoke();
  rejected(revoked.proxy);
  // A transparent proxy must not be accepted either.
  const x = fixture(); x.board = new Proxy(x.board, {}); rejected(x);
  assert.equal(calls, 0);
});

test('unknown keys rejected before inspecting child descriptors or values', () => {
  let calls = 0;
  const x = fixture();
  x.extra = new Proxy({}, {getPrototypeOf() {calls++; throw Error('must not traverse');}});
  rejected(x);
  assert.equal(calls, 0);
});

test('shared work budget bounds repeated schema-shaped input; ordinary aliases work', () => {
  const x = fixture();
  // Only a few allocated objects but 10,000 logical pin occurrences.
  x.sensors[0].pins = Array(100).fill(x.sensors[0].pins[0]);
  x.sensors[0].pinCount = 100;
  x.sensors = Array.from({length: 100}, (_, i) => ({...x.sensors[0], id: `sensor-${i}`}));
  rejected(x);
  const y = fixture(); y.board.pins[0].modes = y.board.pins[1].modes = ['input'];
  y.sensors[1].pins[0].mode = 'input';
  assert.equal(reviewCompatibility(y).status, 'consistent');
});

test('strict scalar/count/unit validation at nested levels', () => {
  for (const value of [undefined, null, NaN, Infinity, -1, 0.5, '14', true, {}, 1e20]) {
    const x = fixture(); x.sensors[0].currentMa = value; rejected(x);
  }
  for (const count of [0, -1, 1.5, 3, null, '2']) {const x = fixture(); x.board.pinCount = count; rejected(x);}
  for (const mutate of [x => x.units = 'A', x => x.sensors[0].unit = 'A',
    x => x.board.pins[0].extra = true, x => x.sensors[0].pins[0].mode = 'analog-ish',
    x => x.board.pins[0].modes.push('input'), x => x.sensors = []]) {
    const x = fixture(); mutate(x); rejected(x);
  }
});

test('zero demand is known and acceptable under zero current limits', () => {
  const x = fixture();
  for (const s of x.sensors) {s.currentMa = 0; for (const p of s.pins) p.currentMa = 0;}
  x.board.powerLimitMa = x.board.pinLimitMa = x.board.totalPinLimitMa = 0;
  assert.equal(reviewCompatibility(x).status, 'consistent');
});

test('getters, hooks and caller methods are never invoked', () => {
  let calls = 0;
  for (const mutate of [
    x => Object.defineProperty(x.board, 'voltageMv', {get() {calls++; throw Error('getter');}}),
    x => Object.defineProperty(x.sensors, '0', {get() {calls++; throw Error('array getter');}}),
    x => x.toJSON = () => {calls++; throw Error('hook');},
    x => x.sensors.map = () => {calls++; throw Error('method');},
    x => Object.defineProperty(x.board, 'hidden', {get() {calls++; throw Error('hidden');}}),
  ]) { const x = fixture(); mutate(x); rejected(x); }
  assert.equal(calls, 0);
});

test('sparse, extended and foreign-prototype data rejected', () => {
  for (const mutate of [
    x => delete x.sensors[0], x => x.sensors.extra = 1,
    x => x.sensors[Symbol('extra')] = 1,
    x => Object.setPrototypeOf(x.board, {inherited: 1}),
    x => Object.setPrototypeOf(x.sensors, null),
    x => x.board.pins = new Uint8Array([1, 2]),
    x => x.sensors[0].pins[0] = new Date(),
    x => x.board.self = x.board,
  ]) { const x = fixture(); mutate(x); rejected(x); }
  rejected(null); rejected([]); rejected(new Map());
});

const workspaceApi = () => import('../pets/arduino/app/workspace.mjs');
const evidenceRow = overrides => ({
  path: 'board.supplyVoltageMv', status: 'fictional', url: '', revision: '',
  excerpt: '', note: 'Invented test declaration.', ...overrides,
});

test('workspace report is deterministic, complete and isolated without authorizing hardware', async () => {
  const {buildWorkspace} = await workspaceApi();
  const input = {design: splitFixture(), evidence: [evidenceRow()]};
  const before = structuredClone(input), first = buildWorkspace(input), second = buildWorkspace(input);
  assert.deepEqual(first, second);
  assert.equal(typeof first.checkerVersion, 'string');
  assert.ok(first.checkerVersion.length > 0);
  assert.equal(first.review.status, 'consistent');
  assert.equal(first.report.schemaVersion, 1);
  assert.equal(first.report.checkerVersion, first.checkerVersion);
  // Returned data may use null prototypes; exported JSON must retain the design.
  assert.deepEqual(JSON.parse(JSON.stringify(first.report.design)), input.design);
  assert.deepEqual(first.report.review, first.review);
  assert.deepEqual(first.report.evidence, first.evidence);
  assert.ok(first.report.limitations.length > 0);
  assert.equal(first.report.synthetic, true);
  assert.equal(first.report.authorization, false);
  assert.equal(first.report.safetyCertification, false);
  assert.equal(first.review.authorization, false);
  assert.equal(first.review.safetyCertification, false);
  assert.equal(typeof first.reportText, 'string');
  assert.ok(first.reportText.includes(first.checkerVersion));
  assert.doesNotThrow(() => JSON.parse(JSON.stringify(first.report)));
  first.report.design.board.supplyVoltageMv = 999;
  first.report.review.unknowns[0] = 'changed';
  first.report.evidence[0].note = 'changed';
  first.report.limitations[0] = 'changed';
  assert.deepEqual(input, before);
  assert.deepEqual(buildWorkspace(input), second);
});

test('evidence statuses remain explicit user assertions with no fetched verification', async () => {
  const {buildWorkspace} = await workspaceApi();
  for (const [status, attribution] of [
    ['fictional', 'FICTIONAL declaration'],
    ['supplied', 'USER-SUPPLIED unverified'],
    ['reviewed', 'USER-ASSERTED reviewed'],
  ]) {
    const row = evidenceRow({status, url: 'https://example.invalid/specification',
      revision: 'invented-revision-1', excerpt: 'Invented source excerpt.', note: 'Synthetic test only.'});
    const x = buildWorkspace({design: splitFixture(), evidence: [row]});
    assert.equal(x.evidence[0].status, status);
    assert.equal(x.evidence[0].attribution, attribution);
    assert.equal(x.evidence[0].path, row.path);
    assert.equal(x.evidence[0].url, row.url);
    assert.equal(x.evidence[0].revision, row.revision);
    assert.equal(x.evidence[0].excerpt, row.excerpt);
    assert.equal(x.evidence[0].note, row.note);
    assert.equal(x.report.authorization, false);
    assert.equal(x.report.safetyCertification, false);
  }
});

test('evidence rejects unknown paths, fields, statuses and unsafe or credentialed URLs', async () => {
  const {buildWorkspace} = await workspaceApi();
  for (const override of [
    {path: 'board.notAField'}, {path: 'board'}, {path: 'sensors[99].id'},
    {path: '__proto__.polluted'}, {status: 'verified'}, {unexpected: true},
    {url: 'http://example.invalid/specification'},
    {url: 'https://user:secret@example.invalid/specification'},
    {url: 'javascript:alert(1)'}, {url: 'file:///tmp/specification'},
  ]) assert.throws(() => buildWorkspace({design: splitFixture(), evidence: [evidenceRow(override)]}));
  for (const key of ['url', 'revision', 'excerpt', 'note']) {
    const row = evidenceRow({status: 'reviewed', url: 'https://example.invalid/specification',
      revision: 'invented-revision-1', excerpt: 'Invented excerpt.', note: 'Synthetic only.'});
    row[key] = '';
    assert.throws(() => buildWorkspace({design: splitFixture(), evidence: [row]}));
  }
  assert.throws(() => buildWorkspace({design: splitFixture(), evidence: Array.from({length: 101}, () => evidenceRow())}));
});

test('workspace validation rejects executable evidence without invoking caller code', async () => {
  const {buildWorkspace} = await workspaceApi();
  let calls = 0;
  const getter = evidenceRow();
  Object.defineProperty(getter, 'note', {get() {calls++; throw Error('evidence getter');}});
  const proxy = new Proxy(evidenceRow(), {
    getPrototypeOf() {calls++; throw Error('evidence proxy');},
    ownKeys() {calls++; throw Error('evidence proxy');},
  });
  const hook = evidenceRow({note: {toJSON() {calls++; throw Error('evidence conversion');}}});
  for (const row of [getter, proxy, hook]) {
    assert.throws(() => buildWorkspace({design: splitFixture(), evidence: [row]}));
  }
  const sparse = [evidenceRow()]; delete sparse[0];
  assert.throws(() => buildWorkspace({design: splitFixture(), evidence: sparse}));
  const extra = [evidenceRow()]; extra.extra = true;
  assert.throws(() => buildWorkspace({design: splitFixture(), evidence: extra}));
  assert.equal(calls, 0);
});

test('design comparison reports issue changes and known headroom deltas without mutation', async () => {
  const {compareDesigns} = await workspaceApi();
  const baseline = splitFixture(), candidate = splitFixture();
  baseline.sensors[0].ground = false;
  candidate.sensors[0].logicVoltageMv = 2500;
  candidate.board.powerLimitMa = 40;
  const before = structuredClone({baseline, candidate});
  const result = compareDesigns({baseline, candidate});
  assert.deepEqual(result.resolvedIssues, ['missing-ground:sensor-a']);
  assert.deepEqual(result.addedIssues, ['logic-voltage-mismatch:sensor-a']);
  assert.deepEqual(result.budgetChanges.total, {
    baselineHeadroomMa: 13, candidateHeadroomMa: 23, deltaHeadroomMa: 10,
  });
  assert.deepEqual(result.budgetChanges.signal, {
    baselineHeadroomMa: 3, candidateHeadroomMa: 3, deltaHeadroomMa: 0,
  });
  assert.equal(result.baseline.authorization, false);
  assert.equal(result.candidate.authorization, false);
  assert.ok(result.limitations.length > 0);
  assert.deepEqual({baseline, candidate}, before);
});

test('comparison preserves unknown versus zero headroom instead of inventing a delta', async () => {
  const {compareDesigns} = await workspaceApi();
  const baseline = splitFixture(), candidate = splitFixture();
  baseline.board.powerLimitMa = null;
  candidate.board.powerLimitMa = 0;
  const r = compareDesigns({baseline, candidate});
  assert.deepEqual(r.resolvedIssues, ['unknown-powerLimitMa']);
  assert.deepEqual(r.addedIssues, ['power-oversubscribed']);
  assert.deepEqual(r.budgetChanges.total, {
    baselineHeadroomMa: null, candidateHeadroomMa: -17, deltaHeadroomMa: null,
  });
  assert.equal(r.budgetChanges.signal.deltaHeadroomMa, 0);
});
