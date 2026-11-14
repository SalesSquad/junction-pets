// Event-only SIMULATED proposals. Caller-selected actors are not authentication.
import { fail, identifier, list, isRecord, availability, utc, immutable } from './demo-validation.mjs';
export const EVENT_ID = 'proofmatch-2026-11-15';
export const SLOT_MINUTES = 15;
const duration = SLOT_MINUTES * 60_000;
const active = record => ['pending', 'accepted'].includes(record.status);
const overlaps = (a, b) => a.start < b.end && b.start < a.end;
const sameParty = (a, b) => [a.candidateId, a.employerId].some(id => [b.candidateId, b.employerId].includes(id));
const pair = (a, b) => a.roleId === b.roleId && a.candidateId === b.candidateId;
function validSlot(slot) {
  if (!isRecord(slot)) fail('Choose a shared event slot.');
  const start = utc(slot.start), end = utc(slot.end);
  if (end - start !== duration || start % duration !== 0) fail('Use one complete UTC-aligned 15-minute slot.');
}
function validateRecords(records) {
  const ids = new Set(), roles = new Map();
  list(records, 256);
  for (const r of records) {
    if (!isRecord(r) || r.eventId !== EVENT_ID || r.simulation !== 'SIMULATED' || !['pending', 'accepted', 'declined', 'cancelled'].includes(r.status)) fail('Invalid simulated event ledger.');
    for (const key of ['id', 'roleId', 'employerId', 'candidateId']) identifier(r[key]);
    if (r.employerId === r.candidateId || ids.has(r.id)) fail('Distinct parties and unique meeting IDs are required.');
    ids.add(r.id);
    if (roles.has(r.roleId) && roles.get(r.roleId) !== r.employerId) fail('A role cannot change employer in this ledger.');
    roles.set(r.roleId, r.employerId);
    validSlot(r.slot);
  }
  for (let i = 0; i < records.length; i++) for (let j = i + 1; j < records.length; j++) {
    const a = records[i], b = records[j];
    if (active(a) && active(b) && (pair(a, b) || (sameParty(a, b) && overlaps(a.slot, b.slot)))) fail('Conflicting active proposals in event ledger.');
  }
}
function participants(role, candidate, records) {
  if (!isRecord(role) || !isRecord(candidate)) fail('Choose an event role and candidate.');
  identifier(role.id); identifier(role.employerId); identifier(candidate.id);
  if (role.employerId === candidate.id) fail('Employer and candidate must be distinct demo actors.');
  availability(role.availability); availability(candidate.availability);
  if (records.some(r => r.roleId === role.id && r.employerId !== role.employerId)) fail('Role employer differs from the event ledger.');
}
function actorFor(actor, meeting) {
  if (!isRecord(actor) || !['employer', 'candidate'].includes(actor.kind)) fail('Choose a valid simulated actor.');
  identifier(actor.id);
  if (actor.id !== (actor.kind === 'employer' ? meeting.employerId : meeting.candidateId)) fail('Only the intended party may perform this action.');
}
const iso = milliseconds => new Date(milliseconds).toISOString().replace('.000', '');

export function sharedEventSlots(role, candidate, records = []) {
  validateRecords(records); participants(role, candidate, records);
  const context = { roleId: role.id, employerId: role.employerId, candidateId: candidate.id };
  if (records.some(r => active(r) && pair(r, context))) return immutable([]);
  const slots = new Map();
  for (const a of role.availability) for (const b of candidate.availability) {
    const end = Math.min(utc(a.end), utc(b.end));
    for (let start = Math.ceil(Math.max(utc(a.start), utc(b.start)) / duration) * duration; start + duration <= end; start += duration) {
      const slot = { start: iso(start), end: iso(start + duration) };
      if (!records.some(r => active(r) && sameParty(r, context) && overlaps(slot, r.slot))) slots.set(slot.start, slot);
    }
  }
  return immutable([...slots.values()].sort((a, b) => a.start < b.start ? -1 : 1));
}

export function proposeMeeting({ role, candidate, slot, actor, records = [] } = {}) {
  validateRecords(records); participants(role, candidate, records); validSlot(slot);
  const context = { roleId: role.id, employerId: role.employerId, candidateId: candidate.id };
  actorFor(actor, context);
  if (actor.kind !== 'employer') fail('Only the employer may propose a conversation.');
  if (records.length >= 256) fail('Demo ledger is full. Reset the simulation.');
  if (records.some(r => active(r) && pair(r, context))) fail('An active proposal already exists for this pair.');
  if (!sharedEventSlots(role, candidate, records).some(s => s.start === slot.start && s.end === slot.end)) fail('Slot is not shared or conflicts with an active proposal.');
  const meeting = { id: `meeting-${records.length + 1}`, eventId: EVENT_ID, ...context, slot: { start: slot.start, end: slot.end }, status: 'pending', simulation: 'SIMULATED' };
  // Sequential IDs are local only; explicitly avoid collision with caller data.
  let sequence = records.length + 1;
  while (records.some(r => r.id === meeting.id)) meeting.id = `meeting-${++sequence}`;
  return immutable({ meeting, records: [...records, meeting] });
}

export function transitionMeeting({ records, meetingId, action, actor } = {}) {
  validateRecords(records); identifier(meetingId);
  const meeting = records.find(r => r.id === meetingId);
  if (!meeting) fail('Meeting was not found in this simulation.');
  actorFor(actor, meeting);
  if (!['accept', 'decline', 'cancel'].includes(action)) fail('Choose accept, decline or cancel.');
  if (action === 'cancel') {
    if (!active(meeting)) fail('Only a pending or accepted proposal may be cancelled.');
  } else {
    if (actor.kind !== 'candidate') fail('Only the intended candidate may accept or decline.');
    if (meeting.status !== 'pending') fail('Only a pending proposal may be accepted or declined.');
  }
  const changed = { ...meeting, status: { accept: 'accepted', decline: 'declined', cancel: 'cancelled' }[action] };
  return immutable({ meeting: changed, records: records.map(r => r.id === meetingId ? changed : r) });
}
