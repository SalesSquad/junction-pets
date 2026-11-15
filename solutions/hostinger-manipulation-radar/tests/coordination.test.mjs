import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeCoordination, POLICY_V2} from '../public/coordination.mjs';
import {evaluateV2} from '../evaluation-v2.mjs';

const epoch = Date.parse('2026-11-15T10:00:00Z');
const copy = 'The local demonstration opens tomorrow with the same public timetable';
const make = (n = 4, options = {}) => Array.from({length: n}, (_, i) => ({
  id: 'e' + i, account: 'person-' + i, time: new Date(epoch + i * 1000).toISOString(),
  text: copy, url: 'https://example.test/item?id=1', amplifies: '', ...options
}));
const flagged = events => analyzeCoordination(events).findings.filter(f => f.review);

test('four distinct accounts with pairwise text, resource and timing evidence trigger coordination, never intent', () => {
  const input = make(), before = JSON.stringify(input), result = analyzeCoordination(input);
  assert.equal(result.policy.version, 'coordination-v2');
  assert.equal(POLICY_V2.threshold, 80);
  assert.equal(result.findings.length, 1);
  const f = result.findings[0];
  assert.equal(f.review, true); assert.equal(f.intent, 'UNKNOWN');
  assert.equal(f.pairCount, 6); assert.equal(f.links.length, 6);
  assert.equal(f.evidenceClass, 'OBSERVABLE_COMPLETE_LINK_COACTION');
  assert.equal(JSON.stringify(input), before);
  assert.deepEqual(result, analyzeCoordination([...input].reverse()));
  const ids = new Set(input.map(e => e.id));
  assert.ok(f.signals.every(s => s.eventIds.every(id => ids.has(id))));
  assert.ok(f.links.every(l => ids.has(l.a) && ids.has(l.b)));
});
test('single-account repetition, sparse cohorts and text-only or URL-only overlap cannot trigger', () => {
  assert.equal(flagged(make(9).map(e => ({...e, account: 'one'}))).length, 0);
  assert.equal(flagged(make(3)).length, 0);
  assert.equal(flagged(make().map(e => ({...e, url: ''}))).length, 0);
  assert.equal(flagged(make().map((e, i) => ({...e, text: ['One independent observation about birds', 'Another different account of weather', 'Unique engineering notes regarding steel', 'Personal travel comments around Europe'][i]}))).length, 0);
});
test('URL-only bridge cannot join separate supported cohorts; complete-link groups retain pair evidence', () => {
  const a = make(4).map(e => ({...e, id: 'a' + e.id, account: 'a' + e.account}));
  const b = make(4).map(e => ({...e, id: 'b' + e.id, account: 'b' + e.account, text: 'Seven different words describe an unrelated astronomy observation'}));
  const findings = flagged([...a, ...b]);
  assert.equal(findings.length, 2);
  assert.deepEqual(findings.map(f => f.accountCount), [4, 4]);
  assert.ok(findings.every(f => f.links.length === 6));
});
test('strong single-edge bridge does not transitively union pairwise-incompatible text cohorts', () => {
  const common = 'base0 base1 base2 base3 base4 base5 base6 base7';
  const a = make().map(e => ({...e, id: 'a' + e.id, account: 'a' + e.account, text: common + ' x1 x2'}));
  const c = make().map(e => ({...e, id: 'c' + e.id, account: 'c' + e.account, text: common + ' y1 y2'}));
  const bridge = {...make()[0], id: 'bridge', account: 'bridge', text: common + ' x2 y1'};
  const groups = flagged([...a, ...c, bridge]);
  assert.equal(groups.length, 2);
  assert.ok(groups.every(f => !(f.events.some(e => e.id.startsWith('a')) && f.events.some(e => e.id.startsWith('c')))));
});
test('semantic query fields distinguish resources; tracking fields do not; query values stay private', () => {
  const semantic = make().map((e, i) => ({...e, url: 'https://example.test/item?id=' + i}));
  assert.equal(flagged(semantic).length, 0);
  assert.equal(flagged(make().map((e, i) => ({...e, url: 'https://example.test/item?sort=' + (i % 2 ? 'a&sort=b' : 'b&sort=a')}))).length, 0);
  assert.equal(flagged(make().map((e, i) => ({...e, url: 'https://example.test/item?id=' + 'x'.repeat(2100) + i}))).length, 0);

  assert.equal(flagged(make().map((e, i) => ({...e, url: 'https://example.test/item?ref=chapter-' + i}))).length, 0);
  const tracked = make().map((e, i) => ({...e, url: 'https://example.test/item?id=1&utm_source=private-' + i + '&fbclid=private-' + i,
    text: copy + ' https://example.test/read?private=secret-' + i}));
  assert.equal(flagged(tracked).length, 1);
  const json = JSON.stringify(analyzeCoordination(tracked));
  for (const secret of ['?id=', '?private=', 'secret-', 'private-']) assert.equal(json.includes(secret), false, secret);
});
test('60-second boundary included; 61-second span does not produce a four-account cohort', () => {
  const boundary = make().map((e, i) => ({...e, time: new Date(epoch + [0, 20000, 40000, 60000][i]).toISOString()}));
  assert.equal(flagged(boundary).length, 1);
  boundary[3].time = new Date(epoch + 61000).toISOString();
  assert.equal(flagged(boundary).length, 0);
});
test('repeated rounds show persistence without a false between-round timing claim', () => {
  const first = make(), second = make().map(e => ({...e, id: 'second-' + e.id, time: new Date(Date.parse(e.time) + 600000).toISOString(), url: 'https://example.test/item?id=2'}));
  const findings = flagged([...first, ...second]);
  assert.equal(findings.length, 1); assert.equal(findings[0].roundCount, 2);
  assert.equal(findings[0].pairCount, 12); assert.equal(findings[0].score, 100);
  assert.equal(findings[0].intent, 'UNKNOWN'); assert.equal(findings[0].peak.length, 4);
});
test('same observations with opposite hidden labels remain identical; metadata never invents or erases intent', () => {
  const a = make().map(e => ({...e, truth: 'benign', label: 'volunteer', accountAgeDays: 1}));
  const b = make().map(e => ({...e, truth: 'harmful', label: 'paid', accountAgeDays: 1}));
  assert.deepEqual(analyzeCoordination(a), analyzeCoordination(b));
  for (const options of [{accountAgeDays: 900, attribution: 'Trusted source'}, {accountAgeDays: null}, {accountAgeDays: 1}]) {
    const f = flagged(make(4, options))[0]; assert.equal(f.review, true); assert.equal(f.intent, 'UNKNOWN');
  }
});
test('ablation removes actual coaction requirements; stronger content support is still required', () => {
  for (const omit of [['text'], ['timing'], ['url']]) assert.equal(analyzeCoordination(make(), {omit}).findings.some(f => f.review), false);
  assert.equal(analyzeCoordination(make(4, {url: '', amplifies: 'shared-post'})).findings.some(f => f.review), true);
});
test('joint trace ablation removes destination and amplification support, including when both exist', () => {
  for (const input of [make(), make(4, {url: '', amplifies: 'shared-post'}), make(4, {amplifies: 'shared-post'})]) {
    assert.equal(analyzeCoordination(input).findings.some(f => f.review), true);
    const withoutJoint = analyzeCoordination(input, {omit: ['joint']});
    assert.equal(withoutJoint.findings.some(f => f.review), false);
    assert.ok(withoutJoint.findings.every(f => f.links.length === 0 && f.score === 0));
  }
  // Individual source ablation still keeps the alternative source when available.
  assert.equal(analyzeCoordination(make(4, {amplifies: 'shared-post'}), {omit: ['url']}).findings.some(f => f.review), true);
  assert.equal(analyzeCoordination(make(4, {amplifies: 'shared-post'}), {omit: ['amplification']}).findings.some(f => f.review), true);
});
test('input validation bounds and empty input are inherited; maximum input completes deterministically', () => {
  assert.deepEqual(analyzeCoordination([]).findings, []);
  assert.throws(() => analyzeCoordination(make(401)), /400/);
  assert.throws(() => analyzeCoordination([make()[0], make()[0]]), /duplicate/);
  assert.equal(analyzeCoordination(make(400)).eventCount, 400);
});
test('fresh mechanistic evaluation discloses exact denominators, purpose and intent abstention', () => {
  const result = evaluateV2();
  assert.equal(result.mode, 'SYNTHETIC_CONTRACT_VALIDATION');
  assert.equal(result.cases, 20);
  assert.equal(result.coordination.fp, 0); assert.equal(result.coordination.fn, 0);
  assert.equal(result.coordination.precision.denominator, 10);
  assert.equal(result.coordination.recall.denominator, 10);
  assert.equal(result.intentAbstention.numerator, 20);
  assert.match(result.limitations, /not comparable/);
});
