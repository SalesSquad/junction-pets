// Pure, bounded SIMULATED rules. Actor IDs are fixture selectors, never identity.
import { proposeMeeting, sharedEventSlots, transitionMeeting } from '../event-meetings.mjs';
import { immutable } from '../demo-validation.mjs';

export const MODES = Object.freeze(['in-person', 'online', 'hybrid']);
export const PEOPLE = immutable([
  { id: 'pilot-mira', name: 'Mira', context: 'Fictional participant exploring a repair-service idea' },
  { id: 'pilot-rowan', name: 'Rowan', context: 'Fictional host exploring a repair-service need' },
]);
export const OPTIONS = immutable({
  takeaway: {
    'shared-topic': 'I found a topic worth exploring together',
    'open-question': 'I still have a question about the need',
    'different-direction': 'I see a different direction for myself',
  },
  nextStep: {
    'small-exercise': 'Explore a small fictional exercise',
    'another-conversation': 'Consider another fictional conversation',
    'pause': 'Pause here; no next step',
  },
  support: {
    'example': 'A concrete example would help me',
    'thinking-time': 'I would like time to think',
    'nothing': 'Nothing else to add',
  },
});
const reject = message => { throw new TypeError(message); };
function shape(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
      Reflect.ownKeys(value).length !== keys.length ||
      keys.some(key => !Object.hasOwn(value, key) || !('value' in Object.getOwnPropertyDescriptor(value, key)))) {
    reject('Use exactly the documented payload fields.');
  }
}
function reflection(value) {
  shape(value, Object.keys(OPTIONS));
  for (const key of Object.keys(OPTIONS)) {
    if (typeof value[key] !== 'string' || !Object.hasOwn(OPTIONS[key], value[key])) reject('Choose a listed reflection; free text and scores are not accepted.');
  }
}

// Reuse W2's proposal, shared-slot and separate acceptance rules; no second scheduler.
const availability = [{ start: '2026-11-15T09:00:00Z', end: '2026-11-15T09:15:00Z' }];
const role = { id: 'pilot-repair', employerId: 'pilot-rowan', availability };
const candidate = { id: 'pilot-mira', availability };
const proposed = proposeMeeting({ role, candidate, records: [], slot: sharedEventSlots(role, candidate)[0], actor: { kind: 'employer', id: role.employerId } });
const accepted = transitionMeeting({ records: proposed.records, meetingId: proposed.meeting.id, action: 'accept', actor: { kind: 'candidate', id: candidate.id } }).meeting;

export function createScenario(mode = 'in-person') {
  if (!MODES.includes(mode)) reject('Choose a listed event format.');
  return immutable({ simulation: 'SIMULATED', version: 0, mode, phase: 'accepted', meeting: accepted,
    participants: PEOPLE.map(({ id }) => ({ id, acknowledged: false, consent: 'pending', reflection: null })) });
}

function validate(state) {
  shape(state, ['simulation', 'version', 'mode', 'phase', 'meeting', 'participants']);
  if (state.simulation !== 'SIMULATED' || !Number.isSafeInteger(state.version) || state.version < 0 || state.version > 128 || !MODES.includes(state.mode)) reject('Invalid simulated session.');
  if (state.phase === 'deleted') {
    if (state.meeting !== null || !Array.isArray(state.participants) || state.participants.length !== 0 || Reflect.ownKeys(state.participants).length !== 1) reject('Deleted sessions must contain no records.');
    return;
  }
  if (!['accepted', 'ended'].includes(state.phase)) reject('Invalid conversation phase.');
  shape(state.meeting, Object.keys(accepted));
  shape(state.meeting.slot, ['start', 'end']);
  if (Object.keys(accepted).some(key => key === 'slot'
    ? state.meeting.slot.start !== accepted.slot.start || state.meeting.slot.end !== accepted.slot.end
    : state.meeting[key] !== accepted[key])) reject('Use the fixed, accepted fictional meeting.');
  if (!Array.isArray(state.participants) || state.participants.length !== 2 ||
      !Object.hasOwn(state.participants, 0) || !Object.hasOwn(state.participants, 1) ||
      Reflect.ownKeys(state.participants).length !== 3) reject('Keep both fictional participants.');
  state.participants.forEach((person, index) => {
    shape(person, ['id', 'acknowledged', 'consent', 'reflection']);
    if (person.id !== PEOPLE[index].id || typeof person.acknowledged !== 'boolean' || !['pending', 'accepted', 'declined', 'revoked'].includes(person.consent)) reject('Unknown actor or invalid participant state.');
    if (state.phase === 'accepted' && (person.acknowledged || person.consent !== 'pending' || person.reflection !== null)) reject('Post-meeting evidence cannot precede the simulated end.');
    if (person.reflection !== null) {
      reflection(person.reflection);
      if (person.consent !== 'accepted') reject('Reflection sharing needs explicit simulated acceptance.');
    }
    if (person.consent !== 'pending' && !state.participants.every(p => p.acknowledged === true)) reject('Both acknowledgements must precede reflection choices.');
  });
}

const fields = {
  'end-conversation': ['confirmed'],
  acknowledge: ['actorId', 'confirmed'],
  consent: ['actorId', 'decision', 'confirmed'],
  reflect: ['actorId', 'reflection'],
  revoke: ['actorId', 'confirmed'],
  delete: ['confirmed'],
};

export function applyCommand(state, command) {
  validate(state);
  if (!command || typeof command.type !== 'string' || !Object.hasOwn(fields, command.type)) reject('Unknown simulation action.');
  shape(command, ['type', 'expectedVersion', 'simulation', ...fields[command.type]]);
  if (command.simulation !== 'SIMULATED') reject('This action must be explicitly SIMULATED.');
  if (command.expectedVersion !== state.version) reject('State conflict: use the current session version.');
  if (state.phase === 'deleted') reject('This session was deleted. Start a new fictional scenario.');
  if (state.version >= 127 && command.type !== 'delete') reject('Simulation limit reached. Delete and start a new scenario.');
  if (fields[command.type].includes('confirmed') && command.confirmed !== true) reject('Explicit confirmation is required; truthy values are not consent.');
  const next = structuredClone(state);
  next.version++;
  if (command.type === 'delete') return immutable({ ...next, version: Math.min(next.version, 128), phase: 'deleted', meeting: null, participants: [] });
  const person = fields[command.type].includes('actorId') ? next.participants.find(p => p.id === command.actorId) : null;
  if (fields[command.type].includes('actorId') && !person) reject('Unknown fictional actor ID.');
  switch (command.type) {
    case 'end-conversation':
      if (next.phase !== 'accepted') reject('The simulated conversation has already ended.');
      next.phase = 'ended';
      break;
    case 'acknowledge':
      if (next.phase !== 'ended') reject('First simulate the end of the conversation.');
      if (person.acknowledged) reject('This participant already acknowledged; no duplicate evidence.');
      person.acknowledged = true;
      break;
    case 'consent':
      if (!next.participants.every(p => p.acknowledged)) reject('Both participants must acknowledge separately first.');
      if (person.consent !== 'pending') reject('This choice was already recorded; revoke accepted sharing to withdraw.');
      if (!['accepted', 'declined'].includes(command.decision)) reject('Explicitly accept or decline reflection sharing.');
      person.consent = command.decision;
      break;
    case 'reflect':
      if (person.consent !== 'accepted' || !next.participants.every(p => p.acknowledged)) reject('Reflection needs both acknowledgements and this participant’s accepted sharing choice.');
      if (person.reflection !== null) reject('A reflection already exists; revoke it to withdraw.');
      reflection(command.reflection);
      person.reflection = command.reflection;
      break;
    case 'revoke':
      if (person.consent !== 'accepted') reject('Only accepted reflection sharing can be revoked.');
      person.consent = 'revoked';
      person.reflection = null;
      break;
  }
  validate(next);
  return immutable(next);
}

export function reviewSession(state) {
  validate(state);
  const label = state.phase === 'deleted' ? 'deleted' : state.phase === 'accepted' ? 'accepted' :
    !state.participants.every(p => p.acknowledged) ? 'awaiting-acknowledgements' :
    state.participants.some(p => p.consent === 'revoked') ? 'sharing-withdrawn' :
    state.participants.some(p => p.consent === 'pending') ? 'awaiting-choices' :
    state.participants.some(p => p.consent === 'accepted' && p.reflection === null) ? 'awaiting-reflections' :
    state.participants.every(p => p.consent === 'accepted') ? 'ready-for-review' : 'closed-without-reciprocal-evidence';
  const shared = state.participants.filter(p => p.consent === 'accepted' && p.reflection !== null)
    .map(p => ({ actorId: p.id, reflection: p.reflection }));
  return immutable({ simulation: 'SIMULATED', label, shared,
    reciprocalEvidence: label === 'ready-for-review',
    nextSteps: label !== 'ready-for-review' ? 'unavailable' : shared[0].reflection.nextStep === shared[1].reflection.nextStep ? 'same-choice' : 'different-choices',
    realWorldOutcome: 'not-established' });
}
