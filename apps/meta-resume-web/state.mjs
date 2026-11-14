import { FIXTURE, OPERATIONS, TRANSPORT_KEYS } from './fixture.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const clone = (value) => structuredClone(value);
const record = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value, keys) => record(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
const isId = (value) => typeof value === 'string' && UUID.test(value);
const canonical = (value) => JSON.stringify(value, Object.keys(value).sort());

function validate(command) {
  if (!exact(command, TRANSPORT_KEYS) || command.schemaVersion !== 1 ||
      !isId(command.taskId) || !isId(command.commandId) ||
      !Number.isSafeInteger(command.expectedRevision) || command.expectedRevision < 0 || typeof command.operation !== 'string' ||
      !Object.hasOwn(OPERATIONS, command.operation) ||
      !exact(command.payload, OPERATIONS[command.operation])) return 'INVALID_COMMAND';
  const payload = command.payload;
  if (Object.hasOwn(payload, 'stepId') && !isId(payload.stepId)) return 'INVALID_COMMAND';
  if (Object.hasOwn(payload, 'evidenceId') && !isId(payload.evidenceId)) return 'INVALID_COMMAND';
  if (Object.hasOwn(payload, 'evidenceIds') && (!Array.isArray(payload.evidenceIds) ||
      payload.evidenceIds.length > 8 || !payload.evidenceIds.every(isId) ||
      new Set(payload.evidenceIds).size !== payload.evidenceIds.length)) return 'INVALID_COMMAND';
  return null;
}

/**
 * Local deterministic reference adapter, not the Chibi authority boundary.
 * Only the fixture map resolves observations. Commands cannot carry identity,
 * timestamps, capture grants or observation details.
 */
export function createSession() {
  const state = {
    taskId: FIXTURE.taskId, revision: 0, status: 'active',
    steps: FIXTURE.steps.map(({ stepId, label }) => ({ stepId, label, userConfirmed: false, observedEvidenceIds: [] })),
    evidence: [], proposal: null,
  };
  const policy = { captureEnabled: true, captureGeneration: FIXTURE.captureGeneration, sessionId: FIXTURE.sessionId };
  const ledger = new Map();
  const journal = [];
  const events = [];
  const source = new Map([...FIXTURE.observations, FIXTURE.archived].map((item) => [item.evidenceId, item]));
  const revoked = new Set();

  function validity(evidence) {
    if (revoked.has(evidence.evidenceId)) return 'revoked';
    if (!policy.captureEnabled) return 'captureDisabled';
    if (evidence.sessionId !== policy.sessionId) return 'staleSession';
    if (evidence.captureGeneration !== policy.captureGeneration) return 'staleGeneration';
    const age = Date.parse(FIXTURE.now) - Date.parse(evidence.capturedAt);
    if (!Number.isFinite(age) || age < 0 || age > FIXTURE.maxEvidenceAgeMs) return 'expired';
    return 'current';
  }

  function snapshot() {
    const result = clone(state);
    result.evidence = result.evidence.map((item) => ({ ...item, validity: validity(item) }));
    if (result.proposal?.evidenceIds.some((key) => !result.evidence.some((item) => item.evidenceId === key && item.validity === 'current'))) result.proposal = null;
    result.nextUnconfirmedStep = result.steps.find((step) => !step.userConfirmed)?.stepId ?? null;
    return result;
  }

  function failure(code) {
    const messages = {
      INVALID_COMMAND: 'This command does not match the local command contract.',
      WRONG_TASK: 'The command belongs to a different task.',
      REVISION_CONFLICT: 'The task changed. Read its current state before retrying.',
      COMMAND_COLLISION: 'That command ID was already used for different input.',
      AUTHORITY_REQUIRED: 'Only a visible user action can confirm or change this task.',
      UNKNOWN_STEP: 'That step is not in this task.',
      STEP_ORDER: 'Confirm the next unfinished step first.',
      WRONG_STATUS: 'Pause the task before asking to resume it.',
      UNKNOWN_EVIDENCE: 'No trusted local fixture exists for that evidence reference.',
      SUBJECT_MISMATCH: 'The similar charger is a different item. It cannot verify your charger.',
      EVIDENCE_UNAVAILABLE: 'That evidence is old, revoked or from a stopped capture generation.',
      NOT_OBSERVED: 'Only an admitted current observation may support this proposal.',
      JOURNAL_FULL: 'The bounded demo is full. Start a new local demo.',
    };
    return { error: true, code, message: messages[code], state: snapshot(), next_action: 'Explain the issue briefly; use the visible controls or read current state. Do not claim the step is complete.' };
  }

  function dispatch(command, { authority = 'ui' } = {}) {
    const invalid = validate(command);
    if (invalid) return failure(invalid);
    if (command.taskId !== state.taskId) return failure('WRONG_TASK');
    // Authority is supplied by the local caller, never accepted in transport.
    if (authority !== 'ui' && !(authority === 'webmcp' && command.operation === 'resume')) return failure('AUTHORITY_REQUIRED');
    const fingerprint = JSON.stringify([
      command.schemaVersion, command.taskId, command.commandId, command.expectedRevision,
      command.operation, canonical(command.payload),
    ]);
    const prior = ledger.get(command.commandId);
    if (prior) {
      if (prior.fingerprint !== fingerprint) return failure('COMMAND_COLLISION');
      return { ...snapshot(), commandId: command.commandId, appliedRevision: prior.appliedRevision, replayed: true };
    }
    if (command.expectedRevision !== state.revision) return failure('REVISION_CONFLICT');
    if (journal.length >= 100) return failure('JOURNAL_FULL');
    const { operation, payload } = command;
    const index = state.steps.findIndex((step) => step.stepId === payload.stepId);
    const nextIndex = state.steps.findIndex((step) => !step.userConfirmed);
    const before = state.revision;

    if (operation === 'confirmStep') {
      if (index < 0) return failure('UNKNOWN_STEP');
      if (state.status !== 'active' || index !== nextIndex) return failure('STEP_ORDER');
      state.steps[index].userConfirmed = true;
      state.proposal = null;
      state.status = state.steps.every((step) => step.userConfirmed) ? 'completed' : 'active';
    } else if (operation === 'correctStep') {
      if (index < 0) return failure('UNKNOWN_STEP');
      state.steps.slice(index).forEach((step) => { step.userConfirmed = false; });
      state.status = 'active';
      state.proposal = null;
    } else if (operation === 'interrupt') {
      if (state.status !== 'active') return failure('WRONG_STATUS');
      state.status = 'interrupted';
      state.proposal = null;
    } else if (operation === 'observe') {
      const fixture = source.get(payload.evidenceId);
      if (!fixture) return failure('UNKNOWN_EVIDENCE');
      if (validity(fixture) !== 'current') return failure('EVIDENCE_UNAVAILABLE');
      const target = FIXTURE.steps.find((step) => step.stepId === fixture.stepId);
      if (!target || target.subjectId !== fixture.subjectId) return failure('SUBJECT_MISMATCH');
      if (!state.evidence.some((item) => item.evidenceId === fixture.evidenceId)) {
        const { evidenceId, stepId, subjectId, sessionId, captureGeneration, capturedAt } = fixture;
        state.evidence.push({ evidenceId, stepId, subjectId, sessionId, captureGeneration, capturedAt });
        state.steps.find((step) => step.stepId === stepId).observedEvidenceIds.push(evidenceId);
      }
    } else if (operation === 'resume') {
      if (state.status !== 'interrupted') return failure('WRONG_STATUS');
      for (const key of payload.evidenceIds) {
        const evidence = state.evidence.find((item) => item.evidenceId === key);
        if (!evidence || evidence.stepId !== state.steps[nextIndex]?.stepId) return failure('NOT_OBSERVED');
        if (validity(evidence) !== 'current') return failure('EVIDENCE_UNAVAILABLE');
      }
      state.proposal = nextIndex < 0 ? null : { stepId: state.steps[nextIndex].stepId, evidenceIds: [...payload.evidenceIds], basedOnRevision: before };
      state.status = nextIndex < 0 ? 'completed' : 'active';
    } else if (operation === 'revokeEvidence') {
      if (!source.has(payload.evidenceId)) return failure('UNKNOWN_EVIDENCE');
      revoked.add(payload.evidenceId);
      if (state.proposal?.evidenceIds.includes(payload.evidenceId)) state.proposal = null;
    }
    state.revision += 1;
    const result = { ...snapshot(), commandId: command.commandId, appliedRevision: state.revision, replayed: false };
    ledger.set(command.commandId, { fingerprint, appliedRevision: state.revision });
    journal.push({ kind: 'command', command: clone(command), authority });
    events.push({ operation, revision: state.revision, stepId: payload.stepId ?? null, evidenceId: payload.evidenceId ?? null });
    return result;
  }

  function revokeCapture() {
    if (!policy.captureEnabled) return snapshot();
    policy.captureEnabled = false;
    policy.captureGeneration += 1;
    // Capture policy has its own generation; it is not a fabricated task command.
    state.proposal = null;
    journal.push({ kind: 'revokeCapture' });
    events.push({ operation: 'revokeCapture', revision: state.revision });
    return snapshot();
  }

  function exportJournal() { return clone({ fixture: FIXTURE.id, entries: journal }); }
  return { dispatch, snapshot, revokeCapture, exportJournal, getPolicy: () => clone(policy), getEvents: () => clone(events) };
}

export function restoreSession(saved) {
  if (!exact(saved, ['fixture', 'entries']) || saved.fixture !== FIXTURE.id || !Array.isArray(saved.entries) || saved.entries.length > 101) throw new Error('Invalid local demo journal');
  const session = createSession();
  for (const entry of saved.entries) {
    if (exact(entry, ['kind']) && entry.kind === 'revokeCapture') session.revokeCapture();
    else if (exact(entry, ['kind', 'command', 'authority']) && entry.kind === 'command' && ['ui', 'webmcp'].includes(entry.authority)) {
      if (session.dispatch(entry.command, { authority: entry.authority }).error) throw new Error('Local journal cannot be replayed');
    } else throw new Error('Invalid local journal entry');
  }
  return session;
}
