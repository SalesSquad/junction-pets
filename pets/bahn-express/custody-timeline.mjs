/**
 * Deterministic, fictional/redacted custody-record rehearsal. No I/O, identity
 * verification, signatures, provider access, booking or real-world completion.
 * Ordinary JSON-like data only; Proxies are outside this contract. See
 * CAPABILITY_PROOF.md for the schema, evidence boundary and finite limits.
 */

export class CustodyInputError extends TypeError {
  constructor(code, path) {
    super(`Invalid custody input (${code}) at ${path}`);
    this.name = 'CustodyInputError';
    this.code = code;
    this.path = path;
  }
}

const reject = (code, path) => { throw new CustodyInputError(code, path); };
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const KINDS = new Set(['pickup-planned', 'picked-up', 'handover-planned', 'handed-over']);
const ROLES = new Set(['origin', 'carrier', 'recipient']);
const PROOF_REFERENCES = ['conditionRecordId', 'releasingPartyRecordId', 'receivingPartyRecordId'];

// Inspect own data descriptors, never getters, toJSON, coercion or iterators.
// Reflection can invoke Proxy traps: callers must not pass Proxies or treat this
// function as a sandbox for arbitrary JavaScript objects.
function snapshotJson(value, path = '$', seen = new Set(), depth = 0, budget = { nodes: 0 }) {
  if (++budget.nodes > 4096 || depth > 6) reject('input-limit', path);
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    if (value.length > 2048) reject('string-limit', path);
    return value;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) reject('non-finite-number', path);
    return value;
  }
  if (typeof value !== 'object') reject('non-json-value', path);
  if (seen.has(value)) reject('cycle-or-alias', path);
  seen.add(value);
  const array = Array.isArray(value);
  const prototype = Object.getPrototypeOf(value);
  if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
    reject('non-ordinary-prototype', path);
  }
  const keys = Reflect.ownKeys(value);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (keys.some(key => typeof key !== 'string')) reject('symbol-key', path);
  if (array) {
    const length = descriptors.length.value;
    if (length > 100 || keys.length !== length + 1) reject('array-shape-or-limit', path);
    const copy = [];
    for (let index = 0; index < length; index++) {
      const descriptor = descriptors[index];
      if (!descriptor || !Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) reject('array-data-required', `${path}[${index}]`);
      copy.push(snapshotJson(descriptor.value, `${path}[${index}]`, seen, depth + 1, budget));
    }
    return copy;
  }
  if (keys.length > 16) reject('object-key-limit', path);
  const copy = Object.create(null);
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) reject('own-enumerable-data-required', path);
    // The path omits caller-controlled key names and never prints input values.
    copy[key] = snapshotJson(descriptor.value, `${path}.*`, seen, depth + 1, budget);
  }
  return copy;
}

function record(value, path, required, optional = []) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) reject('record-required', path);
  for (const key of required) if (!Object.hasOwn(value, key)) reject('missing-field', `${path}.${key}`);
  for (const key of Object.keys(value)) if (!required.includes(key) && !optional.includes(key)) reject('unknown-field', path);
}

function identifier(value, path) {
  if (typeof value !== 'string' || !IDENTIFIER.test(value)) reject('redacted-reference-required', path);
}

function timestamp(value, path) {
  if (typeof value !== 'string' || !TIMESTAMP.test(value)) reject('canonical-utc-required', path);
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString() !== value) reject('invalid-calendar-time', path);
  return milliseconds;
}

function validate(input) {
  record(input, '$', ['schemaVersion', 'scenario', 'asOf', 'freshnessWindowMinutes', 'events']);
  if (input.schemaVersion !== 1) reject('unsupported-schema', '$.schemaVersion');
  if (input.scenario !== 'fictional-redacted') reject('fictional-scenario-required', '$.scenario');
  const asOf = timestamp(input.asOf, '$.asOf');
  if (!Number.isInteger(input.freshnessWindowMinutes) || input.freshnessWindowMinutes < 1 || input.freshnessWindowMinutes > 1440) {
    reject('minutes-in-range-1-to-1440-required', '$.freshnessWindowMinutes');
  }
  if (!Array.isArray(input.events)) reject('events-array-required', '$.events');
  const times = [];
  for (let index = 0; index < input.events.length; index++) {
    const event = input.events[index];
    const path = `$.events[${index}]`;
    record(event, path, ['eventId', 'kind', 'observedAt'], ['custodyProof']);
    identifier(event.eventId, `${path}.eventId`);
    if (typeof event.kind !== 'string' || !KINDS.has(event.kind)) reject('unsupported-kind', `${path}.kind`);
    times.push(timestamp(event.observedAt, `${path}.observedAt`));
    if (Object.hasOwn(event, 'custodyProof')) {
      if (event.kind.endsWith('-planned')) reject('plan-cannot-have-custody-proof', path);
      const proof = event.custodyProof;
      record(proof, `${path}.custodyProof`, ['fromRole', 'toRole', 'observedAt', ...PROOF_REFERENCES]);
      for (const field of ['fromRole', 'toRole']) if (typeof proof[field] !== 'string' || !ROLES.has(proof[field])) reject('unsupported-role', `${path}.custodyProof.${field}`);
      timestamp(proof.observedAt, `${path}.custodyProof.observedAt`);
      for (const field of PROOF_REFERENCES) identifier(proof[field], `${path}.custodyProof.${field}`);
    }
  }
  return { asOf, times };
}

const MESSAGES = Object.freeze({
  'duplicate-event-id': 'Event identifier repeated; replay cannot establish a new event.',
  'reused-proof-reference': 'Each transfer requires three distinct evidence references not reused by another transfer.',
  'out-of-order': 'Events must be supplied in strictly increasing observation-time order; none are silently sorted.',
  'future-event': 'An observation is later than the explicit assessment time.',
  'invalid-transition': 'The fictional sequence must progress from optional pickup intent to pickup record, then optional handover intent to handover record.',
  'missing-custody-proof': 'A reported transfer lacks condition, releasing-party or receiving-party evidence references.',
  'custody-role-mismatch': 'Pickup must report origin to carrier; handover must report carrier to recipient.',
  'proof-time-mismatch': 'Custody evidence must explicitly refer to the same observation time as its event.',
  'stale-state': 'The latest custody record (or intent when no custody record exists) is older than the explicit freshness window.',
});

/**
 * Return a source-only consistency card. Structural/non-JSON input throws
 * CustodyInputError; coherent-shaped but unsupported event claims yield an
 * unresolved card. Even a consistent card never verifies a real handover.
 */
export function assessCustodyTimeline(value) {
  const input = snapshotJson(value);
  const { asOf, times } = validate(input);
  const issues = [];
  const add = (code, path) => issues.push({ code, path, message: MESSAGES[code] });
  const eventIds = new Set();
  const proofReferences = new Set();
  let phase = 0;
  let syntheticState = 'not-started';
  let reportedCustodianRole = null;
  let pendingIntent = null;
  let currentEvidenceEventId = null;
  let evidenceIndex = null;

  for (let index = 0; index < input.events.length; index++) {
    const event = input.events[index];
    const path = `$.events[${index}]`;
    if (eventIds.has(event.eventId)) add('duplicate-event-id', `${path}.eventId`);
    eventIds.add(event.eventId);
    if (index > 0 && times[index] <= times[index - 1]) add('out-of-order', `${path}.observedAt`);
    if (times[index] > asOf) add('future-event', `${path}.observedAt`);
    const allowed = event.kind === 'pickup-planned' ? phase === 0
      : event.kind === 'picked-up' ? phase <= 1
      : event.kind === 'handover-planned' ? phase === 2
      : phase === 2 || phase === 3;
    if (!allowed) add('invalid-transition', `${path}.kind`);

    if (event.kind.endsWith('-planned')) {
      if (allowed) {
        phase = event.kind === 'pickup-planned' ? 1 : 3;
        pendingIntent = event.kind;
      }
      continue;
    }
    if (!Object.hasOwn(event, 'custodyProof')) {
      add('missing-custody-proof', `${path}.custodyProof`);
      continue;
    }
    const proof = event.custodyProof;
    for (const field of PROOF_REFERENCES) {
      if (proofReferences.has(proof[field])) add('reused-proof-reference', `${path}.custodyProof.${field}`);
      proofReferences.add(proof[field]);
    }
    const pickup = event.kind === 'picked-up';
    if (proof.fromRole !== (pickup ? 'origin' : 'carrier') || proof.toRole !== (pickup ? 'carrier' : 'recipient')) {
      add('custody-role-mismatch', `${path}.custodyProof`);
    }
    if (proof.observedAt !== event.observedAt) add('proof-time-mismatch', `${path}.custodyProof.observedAt`);
    if (allowed) {
      phase = pickup ? 2 : 4;
      syntheticState = pickup ? 'pickup-recorded' : 'handover-recorded';
      reportedCustodianRole = pickup ? 'carrier' : 'recipient';
      pendingIntent = null;
      currentEvidenceEventId = event.eventId;
      evidenceIndex = index;
    }
  }

  // A later intent does not make old custody evidence fresh. Historical pickup
  // records may be old when a subsequent handover record is itself recent.
  const freshnessIndex = evidenceIndex ?? (input.events.length ? input.events.length - 1 : null);
  const ageMinutes = freshnessIndex === null ? null : (asOf - times[freshnessIndex]) / 60_000;
  if (ageMinutes !== null && ageMinutes > input.freshnessWindowMinutes) add('stale-state', `$.events[${freshnessIndex}].observedAt`);
  const unresolved = issues.length > 0;
  return {
    schemaVersion: 1,
    mode: 'synthetic-unverified',
    assessment: unresolved ? 'unresolved' : 'consistent',
    syntheticState: unresolved ? 'unresolved' : syntheticState,
    reportedCustodianRole: unresolved ? null : reportedCustodianRole,
    pendingIntent: unresolved ? null : pendingIntent,
    currentEvidenceEventId: unresolved ? null : currentEvidenceEventId,
    evidenceAgeMinutes: unresolved ? null : ageMinutes,
    evidenceStatus: 'unverified-reference-strings',
    realWorldStatus: 'not-verified',
    completionVerified: false,
    issues,
  };
}
