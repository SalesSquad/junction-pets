import test from 'node:test';
import assert from 'node:assert/strict';
import { roles, candidates } from './data.mjs';
import { EVENT_ID, sharedEventSlots, proposeMeeting, transitionMeeting } from './event-meetings.mjs';
const [role, host] = roles;
const [mira, devon, , ren] = candidates;
const employer = { kind: 'employer', id: role.employerId }, candidate = { kind: 'candidate', id: mira.id };
const proposal = (extra = {}) => ({ role, candidate: mira, actor: employer, slot: sharedEventSlots(role, mira)[0], records: [], ...extra });
const change = (records, action, actor = candidate) => transitionMeeting({ records, meetingId: records[0].id, action, actor });
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };

test('shared times are complete, deduplicated 15-minute UTC slots with adjacent boundaries', () => {
  const slots = sharedEventSlots(role, mira);
  assert.equal(slots.length, 4);
  assert.deepEqual(slots[0], { start: '2026-11-15T09:00:00Z', end: '2026-11-15T09:15:00Z' });
  assert.deepEqual(sharedEventSlots(role, { ...mira, availability: [...mira.availability, ...mira.availability] }), slots);
  const clipped = { ...role, availability: [{ start: '2026-11-15T09:05:00Z', end: '2026-11-15T09:55:00Z' }] };
  assert.deepEqual(sharedEventSlots(clipped, mira).map(s => s.start), ['2026-11-15T09:15:00Z', '2026-11-15T09:30:00Z']);
  assert.deepEqual(sharedEventSlots(role, ren), []);
  assert.deepEqual(sharedEventSlots({ ...role, availability: [] }, mira), []);
});
test('only intended employer may propose; actors must be valid and distinct', () => {
  for (const actor of [null, {}, candidate, { kind: 'employer', id: 'outsider' }, { kind: 'candidate', id: role.employerId }, { kind: 'admin', id: role.employerId }]) assert.throws(() => proposeMeeting(proposal({ actor })));
  assert.throws(() => proposeMeeting(proposal({ candidate: { ...mira, id: role.employerId } })));
  const result = proposeMeeting(proposal());
  assert.equal(result.meeting.status, 'pending'); assert.equal(result.meeting.eventId, EVENT_ID);
  assert.equal(result.meeting.simulation, 'SIMULATED');
  assert.equal(Object.hasOwn(result.meeting, 'applicationId'), false);
});
test('intended candidate accepts separately; employer and other candidates cannot respond', () => {
  const { records } = proposeMeeting(proposal());
  for (const action of ['accept', 'decline']) for (const actor of [employer, { kind: 'candidate', id: devon.id }, { kind: 'employer', id: mira.id }, null]) assert.throws(() => change(records, action, actor));
  const accepted = change(records, 'accept'); assert.equal(accepted.meeting.status, 'accepted');
  for (const action of ['accept', 'decline']) assert.throws(() => change(accepted.records, action));
  assert.equal(records[0].status, 'pending');
});
test('pending and accepted hold time; duplicate active pair blocked even at another slot', () => {
  for (const status of ['pending', 'accepted']) {
    let { records } = proposeMeeting(proposal());
    if (status === 'accepted') records = change(records, 'accept').records;
    assert.deepEqual(sharedEventSlots(role, mira, records), []);
    assert.throws(() => proposeMeeting(proposal({ records, slot: sharedEventSlots(role, mira)[1] })), /active proposal/);
    const sibling = { ...role, id: 'other-repair' };
    assert.ok(!sharedEventSlots(sibling, mira, records).some(s => s.start === records[0].slot.start));
    assert.ok(sharedEventSlots(sibling, mira, records).some(s => s.start === records[0].slot.end));
  }
});
test('cross-role candidate and employer conflicts are enforced across all records', () => {
  const slot = sharedEventSlots(role, mira)[3]; // 09:45
  const { records } = proposeMeeting(proposal({ slot }));
  assert.throws(() => proposeMeeting(proposal({ role: host, actor: { kind: 'employer', id: host.employerId }, slot, records })), /conflicts/);
  assert.throws(() => proposeMeeting(proposal({ role: { ...role, id: 'sibling' }, candidate: devon, slot, records })), /conflicts/);
  const unrelated = { ...host, id: 'independent' };
  assert.equal(proposeMeeting(proposal({ role: unrelated, candidate: devon, actor: { kind: 'employer', id: host.employerId }, slot, records })).records.length, 2);
});
test('candidate decline frees times and permits a fresh uniquely identified proposal', () => {
  const pending = proposeMeeting(proposal());
  const declined = change(pending.records, 'decline');
  assert.equal(declined.meeting.status, 'declined');
  assert.deepEqual(sharedEventSlots(role, mira, declined.records), sharedEventSlots(role, mira));
  const again = proposeMeeting(proposal({ records: declined.records }));
  assert.notEqual(again.meeting.id, pending.meeting.id); assert.equal(again.records.length, 2);
  assert.throws(() => change(declined.records, 'accept'));
  assert.throws(() => change(declined.records, 'cancel'));
});
test('either intended party can cancel pending or accepted; terminal states cannot transition', () => {
  for (const actor of [employer, candidate]) for (const state of ['pending', 'accepted']) {
    let { records } = proposeMeeting(proposal());
    if (state === 'accepted') records = change(records, 'accept').records;
    assert.throws(() => change(records, 'cancel', { kind: 'employer', id: 'outsider' }));
    const cancelled = change(records, 'cancel', actor);
    assert.equal(cancelled.meeting.status, 'cancelled');
    assert.deepEqual(sharedEventSlots(role, mira, cancelled.records), sharedEventSlots(role, mira));
    for (const action of ['accept', 'decline', 'cancel']) assert.throws(() => change(cancelled.records, action, actor));
  }
});
test('malformed timestamps, wrong date, non-grid and non-shared slots fail', () => {
  const end = '2026-11-15T09:15:00Z';
  for (const slot of [null, {}, { start: '2026-11-15T09:00:00Z', end: '2026-11-15T09:20:00Z' }, { start: '2026-11-15T09:01:00Z', end: '2026-11-15T09:16:00Z' }, { start: end, end: '2026-11-15T09:00:00Z' }, { start: '2026-11-14T09:00:00Z', end: '2026-11-14T09:15:00Z' }, { start: '2026-11-15T09:00:00+00:00', end }, { start: '2026-11-15T09:00:01Z', end }, { start: '2026-11-15T25:00:00Z', end }, { start: '2026-11-15T12:00:00Z', end: '2026-11-15T12:15:00Z' }]) assert.throws(() => proposeMeeting(proposal({ slot })));
  for (const availability of [null, new Array(1), Array(25).fill(mira.availability[0]), [{ start: '2026-02-30T09:00:00Z', end }], [{ start: end, end }]]) assert.throws(() => sharedEventSlots(role, { ...mira, availability }));
});
test('ledger validation rejects duplicate IDs, impossible statuses, active overlaps and pair duplication', () => {
  const { meeting } = proposeMeeting(proposal());
  const corrupt = [null, {}, new Array(1), [{}], [{ ...meeting, eventId: 'other-event' }], [{ ...meeting, simulation: true }], [{ ...meeting, status: 'DRAFT' }], [{ ...meeting, candidateId: meeting.employerId }], [meeting, meeting], [meeting, { ...meeting, id: 'different', roleId: 'sibling', candidateId: devon.id }], [meeting, { ...meeting, id: 'different', slot: sharedEventSlots(role, mira)[1] }], Array(257).fill(meeting)];
  for (const records of corrupt) assert.throws(() => sharedEventSlots(role, mira, records));
  assert.throws(() => sharedEventSlots({ ...role, employerId: 'swapped' }, mira, [meeting]));
  assert.throws(() => transitionMeeting({ records: [meeting], meetingId: 'absent', action: 'accept', actor: candidate }));
  for (const action of ['', 'ACCEPT', 'reschedule', null]) assert.throws(() => change([meeting], action));
});
test('frozen fixtures and records remain unchanged; result records and slots cannot be mutated', () => {
  const input = freeze(structuredClone(proposal()));
  const before = JSON.stringify(input);
  const proposed = proposeMeeting(input);
  const accepted = change(proposed.records, 'accept');
  change(accepted.records, 'cancel', employer);
  assert.equal(JSON.stringify(input), before); assert.equal(proposed.records[0].status, 'pending');
  assert.throws(() => { proposed.records[0].slot.start = 'fake'; }, TypeError);
  assert.throws(() => { accepted.records.push(proposed.meeting); }, TypeError);
  const mutable = structuredClone(proposed.records);
  const changed = change(mutable, 'decline'); mutable[0].slot.start = 'fake';
  assert.equal(changed.records[0].slot.start, input.slot.start);
});
