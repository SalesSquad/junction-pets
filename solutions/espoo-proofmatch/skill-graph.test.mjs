import test from 'node:test';
import assert from 'node:assert/strict';
import { roles, candidates, asOf } from './data.mjs';
import { createSkillGraph, alignSkills, conversation, renderEvidence, EVIDENCE_CODES } from './skill-graph.mjs';
const [role] = roles;
const [mira, devon, , ren, ari] = candidates;
const req = (id, required = true, weight = required ? 1 : 0.6) => ({ id, required, weight });
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };

test('symmetric normalized graph keeps strongest duplicate relation and has no transitive inference', () => {
  const graph = createSkillGraph([['TypeScript', 'JavaScript', 0.7], ['javascript', 'typescript', 0.85], ['javascript', 'testing', 0.8]]);
  assert.equal(graph.edgeCount, 2);
  assert.equal(graph.relatedness('typescript', 'JAVASCRIPT'), 0.85);
  assert.equal(graph.relatedness('JavaScript', 'TypeScript'), 0.85);
  assert.equal(graph.relatedness('typescript', 'typescript'), 1);
  assert.equal(graph.relatedness('typescript', 'testing'), 0);
});
test('related credit is partial and names the direct transfer path; exact takes precedence', () => {
  const related = alignSkills([req('javascript')], ['typescript']);
  assert.equal(related.rows[0].status, 'related');
  assert.equal(related.rows[0].via, 'typescript');
  assert.equal(related.requiredCoverage, 0.6 * 0.85);
  const exact = alignSkills([req('javascript')], ['typescript', 'JAVASCRIPT', 'javascript']);
  assert.equal(exact.rows[0].status, 'exact'); assert.equal(exact.requiredCoverage, 1);
});
test('strongest direct relation wins; equal weights break ties independent of owned order', () => {
  const graph = createSkillGraph([['js', 'aaa', 0.7], ['js', 'bbb', 0.7], ['js', 'ccc', 0.4]]);
  assert.equal(alignSkills([req('js')], ['bbb', 'aaa'], graph).rows[0].via, 'aaa');
  assert.deepEqual(alignSkills([req('js')], ['aaa', 'bbb'], graph), alignSkills([req('js')], ['bbb', 'aaa'], graph));
  assert.equal(alignSkills([req('js')], ['ccc'], graph).rows[0].status, 'unknown');
});
test('required count coverage and weighted preferred coverage remain separate', () => {
  const result = alignSkills([req('javascript'), req('testing'), req('documentation', false, 0.6), req('sql', false, 0.3)], ['typescript', 'documentation']);
  assert.equal(result.requiredCoverage, 0.51 / 2);
  assert.ok(Math.abs(result.preferredCoverage - 2 / 3) < 1e-12);
  assert.equal(result.rows.find(r => r.id === 'sql').required, false);
  assert.equal(alignSkills([], []).requiredCoverage, null);
  assert.equal(alignSkills([], []).preferredCoverage, null);
});
test('device example keeps C++ and C# separate and preserves required versus preferred', () => {
  const device = roles.find(item => item.id === 'device');
  const cpp = conversation(device, mira, asOf);
  const csharp = conversation(device, ari, asOf);
  const pair = result => result.alignment.rows.map(({ id, required, status }) => ({ id, required, status }));
  assert.deepEqual(pair(cpp), [
    { id: 'c-plus-plus', required: true, status: 'exact' },
    { id: 'c-sharp', required: false, status: 'unknown' },
  ]);
  assert.deepEqual(pair(csharp), [
    { id: 'c-plus-plus', required: true, status: 'unknown' },
    { id: 'c-sharp', required: false, status: 'exact' },
  ]);
  assert.deepEqual(cpp.alignment.rows[0].evidence.args.sources, [{ id: 'M-10', sourceType: 'artifact' }]);
  assert.deepEqual(csharp.alignment.rows[1].evidence.args.sources, [{ id: 'A-10', sourceType: 'artifact' }]);
  const labels = new Map([...device.requiredSkills, ...device.preferredSkills].map(item => [item.id, item.label]));
  const display = id => labels.get(id) ?? id;
  assert.match(renderEvidence(cpp.alignment.rows[0].evidence, display), /^C\+\+:/);
  assert.match(renderEvidence(csharp.alignment.rows[1].evidence, display), /^C#:/);
  assert.equal(cpp.alignment.rows[0].evidence.args.skill, 'c-plus-plus');
});
test('Ari fixture exercises TypeScript → JavaScript with stable code and self-provided sources', () => {
  const result = conversation(role, ari, asOf);
  const related = result.reasons.find(r => r.code === 'related_skill_match');
  assert.equal(related.args.via, 'typescript'); assert.equal(related.args.skill, 'javascript');
  assert.equal(related.args.credit, 0.51); assert.equal(related.args.required, true);
  assert.deepEqual(related.args.sources, [{ id: 'A-01', sourceType: 'artifact' }]);
  assert.equal(result.externalVerification, false); assert.equal(result.interest, 'interested');
  assert.match(renderEvidence(related), /not an exact match/);
});
test('no portfolio and absent, null or empty preference remain visible and unknown', () => {
  for (const interests of [undefined, null, []]) {
    const result = conversation(role, { ...ren, interests }, asOf);
    assert.equal(result.interest, 'unknown'); assert.equal(result.candidateId, ren.id);
    assert.ok(result.alignment.rows.every(s => s.status === 'unknown'));
    assert.ok(result.cautions.some(e => e.code === 'portfolio_unknown'));
  }
  assert.equal(candidates.map(c => conversation(role, c, asOf)).length, candidates.length);
  const other = conversation(roles[1], mira, asOf);
  assert.equal(other.interest, 'other'); assert.equal(other.candidateId, mira.id);
});
test('declared labels and statements never imply external verification or ability', () => {
  const result = conversation(role, devon, asOf);
  assert.equal(result.alignment.rows[0].status, 'exact');
  assert.equal(result.alignment.rows[0].evidence.args.sources[0].sourceType, 'statement');
  assert.match(renderEvidence(result.alignment.rows[0].evidence), /Proficiency is unverified/);
  const changed = { ...ari, bio: 'javascript '.repeat(100), age: 99, nationality: 'ignored', gender: 'ignored' };
  assert.deepEqual(conversation(role, ari, asOf), conversation(role, changed, asOf));
});
test('future evidence is excluded and codes are structured and renderable', () => {
  const future = structuredClone(ari); future.evidence[0].observedDate = '2026-11-16';
  assert.equal(conversation(role, future, asOf).alignment.rows[0].status, 'unknown');
  for (const r of roles) for (const c of candidates) {
    const result = conversation(r, c, asOf);
    for (const item of [...result.reasons, ...result.cautions]) {
      assert.ok(EVIDENCE_CODES.includes(item.code)); assert.equal(typeof item.args, 'object');
      assert.ok(renderEvidence(item).length > 0);
    }
  }
  assert.match(renderEvidence({ code: 'future_code', args: {} }), /Unrecognized/);
});
test('malformed, nonfinite, oversized and adversarial graph/alignment inputs fail', () => {
  for (const pairs of [null, {}, new Array(2), Array(129).fill(['a', 'b', 0.8]), [['a', 'a', 1]], [['a', 'b', NaN]], [['a', 'b', Infinity]], [['a', 'b', -1]], [['a', 'b', 1.1]], [['a', 'b', '0.5']], [['<script>', 'b', 0.5]], [['a', 'b']], [['x'.repeat(65), 'b', 1]]]) assert.throws(() => createSkillGraph(pairs), TypeError);
  for (const requirements of [null, new Array(2), [{ id: 'a', required: 'true' }], [req('a'), req('A')], [req('a', true, NaN)], [req('a', false, 0)], [req('a', false, 2)]]) assert.throws(() => alignSkills(requirements, []), TypeError);
  assert.throws(() => alignSkills([], Array(65).fill('a')), TypeError);
  assert.throws(() => alignSkills([req('a')], ['b'], { relatedness: () => NaN }), TypeError);
});
test('malformed evidence, preferences, role weights, dates and false verification fail', () => {
  for (const interests of ['repair', [null], new Array(1), Array(17).fill('repair')]) assert.throws(() => conversation(role, { ...ari, interests }, asOf));
  for (const evidence of [null, new Array(1), Array(33).fill(ari.evidence[0]), [{ ...ari.evidence[0], externalVerification: true }]]) assert.throws(() => conversation(role, { ...ari, evidence }, asOf));
  for (const date of ['today', '2026-02-30', null]) assert.throws(() => conversation(role, ari, date));
  assert.throws(() => conversation({ ...role, requiredSkills: [req('a', true, NaN)] }, ari, asOf));
  assert.throws(() => conversation({ ...role, preferredSkills: [req('javascript', false)] }, ari, asOf));
});
test('frozen inputs stay unchanged; graph and conversation outputs cannot be mutated', () => {
  const pairs = freeze([['typescript', 'javascript', 0.85]]), graph = createSkillGraph(pairs);
  const c = freeze(structuredClone(ari)), r = freeze(structuredClone(role));
  const before = JSON.stringify({ c, r, pairs });
  const result = conversation(r, c, asOf, graph);
  assert.equal(JSON.stringify({ c, r, pairs }), before);
  assert.throws(() => { result.reasons[0].args.sources[0].id = 'fake'; }, TypeError);
  assert.throws(() => { graph.edgeCount = 999; }, TypeError);
  const mutablePairs = [['typescript', 'javascript', 0.8]], independent = createSkillGraph(mutablePairs);
  mutablePairs[0][2] = 0; assert.equal(independent.relatedness('typescript', 'javascript'), 0.8);
});
