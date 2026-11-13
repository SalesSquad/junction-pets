import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { assessCustodyTimeline, CustodyInputError } from '../pets/bahn-express/custody-timeline.mjs';

const raw = await readFile(new URL('../pets/bahn-express/examples/custody-timeline.json', import.meta.url), 'utf8');
const fixture = () => JSON.parse(raw);
const codes = value => assessCustodyTimeline(value).issues.map(issue => issue.code);
const invalid = value => assert.throws(() => assessCustodyTimeline(value), CustodyInputError);
const freeze = value => {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
};

test('Bahn: valid fictional pickup and handover records remain explicitly unverified', () => {
  const card = assessCustodyTimeline(fixture());
  assert.equal(card.assessment, 'consistent');
  assert.equal(card.syntheticState, 'handover-recorded');
  assert.equal(card.reportedCustodianRole, 'recipient');
  assert.equal(card.pendingIntent, null);
  assert.equal(card.currentEvidenceEventId, 'fictional-handover-record');
  assert.equal(card.evidenceAgeMinutes, 15);
  assert.deepEqual(card.issues, []);
  assert.equal(card.mode, 'synthetic-unverified');
  assert.equal(card.realWorldStatus, 'not-verified');
  assert.equal(card.completionVerified, false);
  assert.equal(card.evidenceStatus, 'unverified-reference-strings');
});

test('Bahn: pickup planning alone cannot transfer custody or establish completion', () => {
  const input = fixture(); input.events = input.events.slice(0, 1);
  const card = assessCustodyTimeline(input);
  assert.equal(card.assessment, 'consistent');
  assert.equal(card.syntheticState, 'not-started');
  assert.equal(card.pendingIntent, 'pickup-planned');
  assert.equal(card.reportedCustodianRole, null);
  assert.equal(card.completionVerified, false);
});

test('Bahn: a handover intent preserves the supplied pickup state and carrier role', () => {
  const input = fixture(); input.events = input.events.slice(0, 3);
  const card = assessCustodyTimeline(input);
  assert.equal(card.syntheticState, 'pickup-recorded');
  assert.equal(card.pendingIntent, 'handover-planned');
  assert.equal(card.reportedCustodianRole, 'carrier');
  assert.equal(card.currentEvidenceEventId, 'fictional-pickup-record');
  assert.equal(card.evidenceAgeMinutes, 35);
  assert.equal(card.completionVerified, false);
});

test('Bahn: no events is a valid no-observation control, never a completed move', () => {
  const input = fixture(); input.events = [];
  const card = assessCustodyTimeline(input);
  assert.equal(card.assessment, 'consistent');
  assert.equal(card.syntheticState, 'not-started');
  assert.equal(card.evidenceAgeMinutes, null);
  assert.equal(card.reportedCustodianRole, null);
  assert.equal(card.completionVerified, false);
});

test('Bahn: factual records need not invent preceding planning events', () => {
  const input = fixture(); input.events = input.events.filter(event => event.custodyProof);
  assert.equal(assessCustodyTimeline(input).syntheticState, 'handover-recorded');
});

test('Bahn: freshness uses the latest custody record, not older legitimate history', () => {
  const input = fixture(); input.freshnessWindowMinutes = 15;
  assert.equal(assessCustodyTimeline(input).assessment, 'consistent');
  input.freshnessWindowMinutes = 14;
  const card = assessCustodyTimeline(input);
  assert.equal(card.assessment, 'unresolved');
  assert.equal(card.syntheticState, 'unresolved');
  assert.equal(card.reportedCustodianRole, null);
  assert.ok(card.issues.some(issue => issue.code === 'stale-state'));
});

test('Bahn: a fresh handover intent cannot refresh a stale custody record', () => {
  const input = fixture(); input.events = input.events.slice(0, 3);
  input.events[2].observedAt = input.asOf;
  input.freshnessWindowMinutes = 30;
  assert.ok(codes(input).includes('stale-state'));
  assert.equal(assessCustodyTimeline(input).reportedCustodianRole, null);
});

test('Bahn: planning-only timestamps also expire', () => {
  const input = fixture(); input.events = input.events.slice(0, 1); input.freshnessWindowMinutes = 30;
  assert.ok(codes(input).includes('stale-state'));
});

test('Bahn: exact as-of time is age zero and valid (not missing evidence)', () => {
  const input = fixture(); input.asOf = input.events.at(-1).observedAt;
  assert.equal(assessCustodyTimeline(input).evidenceAgeMinutes, 0);
  assert.equal(assessCustodyTimeline(input).assessment, 'consistent');
});

test('Bahn: leap-day timestamps are validated against a real calendar', () => {
  const input = fixture(); input.events = input.events.slice(0, 1);
  input.events[0].observedAt = '2024-02-29T10:00:00.000Z'; input.asOf = '2024-02-29T10:45:00.000Z';
  assert.equal(assessCustodyTimeline(input).assessment, 'consistent');
  input.events[0].observedAt = '2023-02-29T10:00:00.000Z'; invalid(input);
});

test('Bahn: deterministic assessment never mutates or retains input objects', () => {
  const input = freeze(fixture());
  const before = JSON.stringify(input);
  assert.deepEqual(assessCustodyTimeline(input), assessCustodyTimeline(input));
  assert.equal(JSON.stringify(input), before);
  const mutable = fixture(); const card = assessCustodyTimeline(mutable);
  mutable.events.at(-1).eventId = 'changed-after-assessment';
  assert.equal(card.currentEvidenceEventId, 'fictional-handover-record');
});

test('Bahn: ordinary null-prototype records are supported', () => {
  const input = Object.assign(Object.create(null), fixture());
  assert.equal(assessCustodyTimeline(input).assessment, 'consistent');
});

test('Bahn: missing custody proof never inherits support from the earlier transfer', () => {
  for (const index of [1, 3]) {
    const input = fixture(); delete input.events[index].custodyProof;
    const card = assessCustodyTimeline(input);
    assert.ok(card.issues.some(issue => issue.code === 'missing-custody-proof'));
    assert.equal(card.syntheticState, 'unresolved');
    assert.equal(card.reportedCustodianRole, null);
    assert.equal(card.currentEvidenceEventId, null);
    assert.equal(card.completionVerified, false);
  }
});

test('Bahn: duplicate event identifiers are replay even at different times', () => {
  const input = fixture(); input.events[3].eventId = input.events[1].eventId;
  assert.ok(codes(input).includes('duplicate-event-id'));
});

test('Bahn: reusing any custody evidence reference is replay', () => {
  for (const key of ['conditionRecordId', 'releasingPartyRecordId', 'receivingPartyRecordId']) {
    const input = fixture(); input.events[3].custodyProof[key] = input.events[1].custodyProof[key];
    assert.ok(codes(input).includes('reused-proof-reference'));
  }
  const input = fixture(); input.events[1].custodyProof.receivingPartyRecordId = input.events[1].custodyProof.releasingPartyRecordId;
  assert.ok(codes(input).includes('reused-proof-reference'));
});

test('Bahn: equal and decreasing event timestamps are not silently sorted', () => {
  for (const timestamp of ['2026-11-13T10:10:00.000Z', '2026-11-13T10:09:59.999Z']) {
    const input = fixture(); input.events[2].observedAt = timestamp;
    assert.ok(codes(input).includes('out-of-order'));
  }
  const input = fixture(); [input.events[1], input.events[2]] = [input.events[2], input.events[1]];
  assert.ok(codes(input).includes('out-of-order'));
});

test('Bahn: future observations and mismatched proof timestamps fail closed', () => {
  const future = fixture(); future.asOf = '2026-11-13T10:29:59.999Z';
  assert.ok(codes(future).includes('future-event'));
  const mismatch = fixture(); mismatch.events[3].custodyProof.observedAt = '2026-11-13T10:29:00.000Z';
  assert.ok(codes(mismatch).includes('proof-time-mismatch'));
});

test('Bahn: custody roles must form origin to carrier to recipient', () => {
  for (const [index, key, role] of [[1, 'fromRole', 'recipient'], [1, 'toRole', 'origin'], [3, 'fromRole', 'origin'], [3, 'toRole', 'carrier']]) {
    const input = fixture(); input.events[index].custodyProof[key] = role;
    assert.ok(codes(input).includes('custody-role-mismatch'));
  }
});

test('Bahn: handover without pickup and repeated or backwards transitions are rejected', () => {
  const noPickup = fixture(); noPickup.events = noPickup.events.slice(2);
  assert.ok(codes(noPickup).includes('invalid-transition'));
  for (const kind of ['pickup-planned', 'picked-up', 'handover-planned', 'handed-over']) {
    const input = fixture();
    const event = structuredClone(input.events.find(item => item.kind === kind));
    event.eventId = 'fictional-late-repeat'; event.observedAt = '2026-11-13T10:40:00.000Z';
    if (event.custodyProof) {
      event.custodyProof.observedAt = event.observedAt;
      for (const key of ['conditionRecordId', 'releasingPartyRecordId', 'receivingPartyRecordId']) event.custodyProof[key] += '-new';
    }
    input.events.push(event); assert.ok(codes(input).includes('invalid-transition'));
  }
});

test('Bahn: a plan cannot smuggle a custody proof into a factual claim', () => {
  const input = fixture(); input.events[0].custodyProof = input.events[1].custodyProof;
  invalid(input);
});

test('Bahn: all top-level required fields distinguish absent, null and zero', () => {
  for (const key of ['schemaVersion', 'scenario', 'asOf', 'freshnessWindowMinutes', 'events']) {
    const missing = fixture(); delete missing[key]; invalid(missing);
    for (const value of [null, 0]) { const input = fixture(); input[key] = value; invalid(input); }
  }
  for (const value of [null, 0, false, 'fixture', [], undefined]) invalid(value);
});

test('Bahn: required event and custody fields reject missing, null, zero and blank values', () => {
  for (const index of [0, 1, 3]) {
    for (const key of ['eventId', 'kind', 'observedAt']) {
      const missing = fixture(); delete missing.events[index][key]; invalid(missing);
      for (const value of [null, 0, '']) { const input = fixture(); input.events[index][key] = value; invalid(input); }
    }
  }
  for (const key of Object.keys(fixture().events[1].custodyProof)) {
    const missing = fixture(); delete missing.events[1].custodyProof[key]; invalid(missing);
    for (const value of [null, 0, '']) { const input = fixture(); input.events[1].custodyProof[key] = value; invalid(input); }
  }
  for (const value of [null, 0, false, [], 'signed']) { const input = fixture(); input.events[3].custodyProof = value; invalid(input); }
});

test('Bahn: minute units are explicit and finite bounded integers, not coerced', () => {
  for (const value of [0, -1, 1.5, NaN, Infinity, -Infinity, '60', true, 1441, Number.MAX_SAFE_INTEGER]) {
    const input = fixture(); input.freshnessWindowMinutes = value; invalid(input);
  }
  for (const key of ['freshnessWindowSeconds', 'freshnessUnit', 'maxAge']) {
    const input = fixture(); input[key] = 'seconds'; invalid(input);
  }
  const input = fixture(); input.freshnessWindowMinutes = 1440;
  assert.equal(assessCustodyTimeline(input).assessment, 'consistent');
});

test('Bahn: timestamps require canonical millisecond UTC and actual dates', () => {
  for (const value of ['2026-02-30T10:00:00.000Z', '2026-11-13T25:00:00.000Z', '2026-11-13T10:00:00Z', '2026-11-13T10:00:00.000+00:00', '2026-11-13', 1794564000000, false, NaN]) {
    const input = fixture(); input.asOf = value; invalid(input);
  }
});

test('Bahn: unknown keys, kinds, roles and unredacted-shaped identifiers are rejected', () => {
  for (const mutate of [
    input => { input.verified = true; },
    input => { input.events[0].vehicleRegistration = 'not-allowed'; },
    input => { input.events[1].custodyProof.signatureVerified = true; },
    input => { input.events[1].kind = 'delivered'; },
    input => { input.events[1].custodyProof.fromRole = 'driver'; },
    input => { input.events[0].eventId = 'person@example.invalid'; },
    input => { input.events[1].custodyProof.conditionRecordId = 'https://example.invalid/evidence'; },
    input => { input.scenario = 'production'; },
    input => { input.schemaVersion = 2; },
  ]) { const input = fixture(); mutate(input); invalid(input); }
  const input = fixture(); Object.defineProperty(input, '__proto__', { value: {}, enumerable: true }); invalid(input);
});

test('Bahn: getters are rejected without being invoked at any schema depth', () => {
  let calls = 0;
  for (const locate of [input => [input, 'asOf'], input => [input.events, '0'], input => [input.events[1], 'custodyProof'], input => [input.events[1].custodyProof, 'conditionRecordId']]) {
    const input = fixture(); const [object, key] = locate(input);
    Object.defineProperty(object, key, { get() { calls++; throw Error('must not run'); }, enumerable: true, configurable: true });
    invalid(input);
  }
  assert.equal(calls, 0);
});

test('Bahn: caller toJSON, coercion, iterator and function hooks are never invoked', () => {
  let calls = 0; const hook = () => { calls++; throw Error('must not run'); };
  for (const mutate of [
    input => { input.toJSON = hook; },
    input => { input.events[1].custodyProof.toJSON = hook; },
    input => { input.asOf = { toString: hook, valueOf: hook }; },
    input => { input.freshnessWindowMinutes = { [Symbol.toPrimitive]: hook }; },
    input => { input.events[Symbol.iterator] = hook; },
    input => { input.events[0].eventId = hook; },
  ]) { const input = fixture(); mutate(input); invalid(input); }
  assert.equal(calls, 0);
});

test('Bahn: custom prototypes and non-JSON built-ins are outside the contract', () => {
  for (const value of [new Date(), new Map(), new Set(), /pattern/, new Number(60), new Uint8Array(1), 1n]) {
    const input = fixture(); input.freshnessWindowMinutes = value; invalid(input);
  }
  const input = fixture(); Object.setPrototypeOf(input.events[0], { injected: true }); invalid(input);
});

test('Bahn: sparse, named-property, symbol and non-enumerable data are rejected', () => {
  for (const mutate of [
    input => { delete input.events[1]; },
    input => { input.events.extra = true; },
    input => { input.events[Symbol('extra')] = true; },
    input => { input[Symbol('extra')] = true; },
    input => { Object.defineProperty(input, 'hidden', { value: true }); },
    input => { Object.defineProperty(input.events, '0', { value: input.events[0], enumerable: false }); },
  ]) { const input = fixture(); mutate(input); invalid(input); }
});

test('Bahn: cycles, shared-object aliases, oversized collections and strings fail boundedly', () => {
  const cycle = fixture(); cycle.events[0].cycle = cycle; invalid(cycle);
  const alias = fixture(); alias.events[2] = alias.events[0]; invalid(alias);
  const many = fixture(); many.events = Array.from({ length: 101 }, (_, n) => ({ eventId: `event-${n}`, kind: 'pickup-planned', observedAt: many.asOf })); invalid(many);
  const large = fixture(); large.events[0].eventId = 'x'.repeat(2049); invalid(large);
  const deep = fixture(); let cursor = deep; for (let n = 0; n < 12; n++) { cursor.extra = {}; cursor = cursor.extra; } invalid(deep);
});

test('Bahn: errors do not stringify or echo supplied secret-like values', () => {
  const input = fixture(); input.events[0].eventId = 'do-not-echo private value';
  assert.throws(() => assessCustodyTimeline(input), error => error instanceof CustodyInputError && !error.message.includes('do-not-echo'));
});
