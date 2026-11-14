import test from 'node:test';
import assert from 'node:assert/strict';
import { roles, candidates, asOf } from './data.mjs';
import { match, rank, keywordRank, sharedSlots, createDraft } from './matcher.mjs';
import { benchmark } from './benchmark.mjs';
const copy = value => structuredClone(value);
const [role, host] = roles;
const [mira, devon, jules, ren] = candidates;
const proposal = (extra = {}) => ({ role, candidate: mira, slot: sharedSlots(role, mira)[0], employerConsent: true, candidateConsent: true, records: [], ...extra });
const freeze = value => { Object.freeze(value); for (const child of Object.values(value)) if (child && typeof child === 'object' && !Object.isFrozen(child)) freeze(child); return value; };

test('fixed labelled benchmark: evidence 2/2 versus keyword 0/2', () => {
  const b = benchmark();
  assert.equal(b.evidenceCorrect, 2); assert.equal(b.keywordCorrect, 0);
  assert.deepEqual(b.cases.map(c => c.evidenceTop), ['mira', 'jules']);
  assert.deepEqual(b.cases.map(c => c.keywordTop), ['devon', 'devon']);
  console.log('BENCHMARK', JSON.stringify(b));
});
test('keyword stuffing changes baseline, never evidence score or order', () => {
  const stuffed = { ...ren, bio: 'javascript accessibility testing '.repeat(1000) };
  assert.equal(match(role, stuffed, asOf).score, 0);
  assert.equal(keywordRank(role, [mira, stuffed])[0].candidateId, 'ren');
  assert.equal(rank(role, [mira, stuffed], asOf)[0].candidateId, 'mira');
});
test('absent evidence is UNKNOWN and remains in ranked results', () => {
  const result = match(role, ren, asOf);
  assert.equal(result.unknown.length, 3);
  assert.ok(result.skills.every(s => s.status === 'UNKNOWN'));
  assert.ok(rank(role, candidates, asOf).some(c => c.candidateId === ren.id));
});
test('self statements are claim-only, not verified', () => {
  assert.ok(match(role, devon, asOf).skills.every(s => s.status === 'CLAIM_ONLY' && s.support === 0.2));
});
test('score is deterministic, auditable and role-specific', () => {
  assert.equal(match(role, mira, asOf).score, 94);
  assert.equal(match(host, jules, asOf).score, 96);
  assert.deepEqual(match(role, mira, asOf), match(copy(role), copy(mira), asOf));
  assert.equal(match(host, mira, asOf).unknown.length, 2);
});
test('name, protected attributes and irrelevant fields do not affect scores', () => {
  const changed = { ...mira, name: 'Another fictional name', age: 99, gender: 'ignored', nationality: 'ignored', disability: 'ignored', bio: '' };
  assert.deepEqual(match(role, changed, asOf), match(role, mira, asOf));
});
test('stable ID tie-break is independent of array order', () => {
  const a = { ...ren, id: 'alpha' }, b = { ...ren, id: 'beta' };
  assert.deepEqual(rank(role, [b, a], asOf).map(c => c.candidateId), ['alpha', 'beta']);
});
test('duplicate cards never stack; duplicate IDs and unknown source types fail', () => {
  const doubled = copy(mira); doubled.evidence.push({ ...copy(mira.evidence[0]), id: 'M-03' });
  assert.equal(match(role, doubled, asOf).score, match(role, mira, asOf).score);
  doubled.evidence[2].id = 'M-01'; assert.throws(() => match(role, doubled, asOf));
  const bad = copy(mira); bad.evidence[0].sourceType = 'verified'; assert.throws(() => match(role, bad, asOf));
});
test('future evidence is unknown and old evidence is explicitly discounted', () => {
  const future = copy(mira); future.evidence.forEach(e => { e.observedDate = '2026-11-16'; });
  assert.equal(match(role, future, asOf).unknown.length, 3);
  const old = copy(mira); old.evidence.forEach(e => { e.observedDate = '2025-01-01'; });
  assert.equal(match(role, old, asOf).score, 75.2);
});
test('invalid roles, provenance, dates, arrays and numeric input fail closed', () => {
  for (const bad of [null, {}, { ...role, requiredSkills: [] }, { ...role, requiredSkills: [{ id: 'testing', label: 'Testing', weight: NaN }] }, { ...role, requiredSkills: [role.requiredSkills[0], role.requiredSkills[0]] }]) assert.throws(() => match(bad, mira, asOf));
  for (const bad of [null, {}, { ...mira, availability: [{ start: '2026-02-30T09:00:00Z', end: '2026-03-01T10:00:00Z' }] }, { ...mira, evidence: [{ ...mira.evidence[0], externalVerification: true }] }, { ...mira, evidence: [{ ...mira.evidence[0], observedDate: '2026-02-30' }] }]) assert.throws(() => match(role, bad, asOf));
  assert.throws(() => match(role, mira, 'today'));
  assert.throws(() => rank(role, [mira, mira], asOf));
  assert.throws(() => rank(role, null, asOf));
});
test('empty candidates yields an empty result', () => assert.deepEqual(rank(role, [], asOf), []));
test('availability intersects in canonical 20-minute UTC slots', () => {
  const slots = sharedSlots(role, mira);
  assert.equal(slots.length, 3);
  assert.deepEqual(slots[0], { start: '2026-11-15T09:00:00Z', end: '2026-11-15T09:20:00Z' });
  const overlapping = { ...mira, availability: [...mira.availability, ...mira.availability] };
  assert.deepEqual(sharedSlots(role, overlapping), slots);
  assert.deepEqual(sharedSlots(role, ren), []);
  assert.deepEqual(sharedSlots({ ...role, availability: [] }, mira), []);
});
test('partial overlapping windows only produce complete grid-aligned slots', () => {
  const r = { ...role, availability: [{ start: '2026-11-15T09:05:00Z', end: '2026-11-15T09:55:00Z' }] };
  assert.deepEqual(sharedSlots(r, mira), [{ start: '2026-11-15T09:20:00Z', end: '2026-11-15T09:40:00Z' }]);
});
test('both consent booleans must be exactly true', () => {
  for (const [employerConsent, candidateConsent] of [[false, true], [true, false], [false, false], ['true', true], [true, 1], [undefined, true]]) assert.throws(() => createDraft(proposal({ employerConsent, candidateConsent })), /Both demo consent/);
});
test('draft is local only, duplicate pair across another slot is blocked', () => {
  const { draft, records } = createDraft(proposal());
  assert.equal(draft.status, 'DRAFT'); assert.equal(draft.candidateConsent, true);
  assert.throws(() => createDraft(proposal({ records, slot: sharedSlots(role, mira)[1] })), /already exists/);
});
test('candidate conflict across employers and employer conflict across roles blocked', () => {
  const { records } = createDraft(proposal({ slot: sharedSlots(role, mira)[2] }));
  assert.ok(!sharedSlots(host, mira, records).some(s => s.start === records[0].slot.start));
  const sibling = { ...role, id: 'repair-two' };
  assert.throws(() => createDraft(proposal({ role: sibling, candidate: devon, records, slot: records[0].slot })), /unavailable/);
  const next = sharedSlots(role, devon, records)[0];
  assert.equal(next.start, '2026-11-15T09:20:00Z'); // adjacent boundaries do not conflict
});
test('invented, stale, short, reversed and malformed slots cannot create a draft', () => {
  for (const slot of [null, {}, { start: '2026-11-15T09:00:00Z', end: '2026-11-15T09:10:00Z' }, { start: '2026-11-15T10:00:00Z', end: '2026-11-15T09:00:00Z' }, { start: '2026-11-15T12:00:00Z', end: '2026-11-15T12:20:00Z' }]) assert.throws(() => createDraft(proposal({ slot })));
  const { records } = createDraft(proposal());
  assert.throws(() => createDraft(proposal({ candidate: { ...devon, availability: mira.availability }, slot: records[0].slot, records })), /conflicts/);
  assert.throws(() => sharedSlots(role, mira, [{}]));
});
test('frozen inputs remain untouched through matching, baseline, scheduling and drafts', () => {
  const r = freeze(copy(role)), c = freeze(copy(mira)), list = freeze(copy(candidates)), records = freeze([]);
  const before = JSON.stringify({ r, c, list, records });
  match(r, c, asOf); rank(r, list, asOf); keywordRank(r, list); sharedSlots(r, c, records);
  const result = createDraft({ role: r, candidate: c, slot: freeze(sharedSlots(r, c)[0]), employerConsent: true, candidateConsent: true, records });
  assert.equal(result.records.length, 1); assert.equal(records.length, 0);
  assert.equal(JSON.stringify({ r, c, list, records }), before);
});
