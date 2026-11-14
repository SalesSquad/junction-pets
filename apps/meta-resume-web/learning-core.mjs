/**
 * Portable SYNTHETIC learning reference. Real authorization and encrypted
 * personal memory belong to the private Chibi host, not this browser module.
 */
const clone = (value) => structuredClone(value);
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value) &&
  [Object.prototype, null].includes(Object.getPrototypeOf(value));
const exact = (value, keys) => object(value) && Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key));
const id = (value) => typeof value === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/.test(value);
const natural = (value) => Number.isSafeInteger(value) && value >= 0;
const style = (value) => ['one_step', 'detailed', 'quiet'].includes(value);
const scopeKeys = ['tenantId', 'ownerId', 'contextId'];
const validScope = (value) => exact(value, scopeKeys) && scopeKeys.every((key) => id(value[key]));
const sameScope = (a, b) => validScope(a) && validScope(b) && scopeKeys.every((key) => a[key] === b[key]);
const same = (a, b) => canonical(a) === canonical(b);
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().map((key) => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
async function fingerprint(value) {
  const bytes = new TextEncoder().encode(canonical(value));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, '0')).join('');
}
const payloadKeys = Object.freeze({
  setConsent: ['enabled'], setGoal: ['goal'], startEpisode: ['episodeId', 'templateId'],
  proposeMemory: ['memoryId', 'style'], confirmMemory: ['memoryId'],
  correctMemory: ['memoryId', 'style'], forgetMemory: ['memoryId'], forgetAll: [],
  checkpoint: ['taskId', 'taskRevision', 'nextStepId'],
  recordOutcome: ['stepId', 'correct', 'hints'], recordFeedback: ['proposalId', 'value'],
  setReminder: ['reminderId', 'stepId'], ackReminder: ['reminderId'],
});
export function validateLearningCommand(command) {
  if (!exact(command, ['schema', 'commandId', 'expectedRevision', 'operation', 'payload']) ||
      command.schema !== 'lens.learning-command/v1' || !id(command.commandId) ||
      !natural(command.expectedRevision) || !Object.hasOwn(payloadKeys, command.operation) ||
      !exact(command.payload, payloadKeys[command.operation])) return false;
  const p = command.payload;
  for (const key of ['memoryId', 'episodeId', 'templateId', 'taskId', 'stepId', 'reminderId', 'proposalId']) {
    if (Object.hasOwn(p, key) && !id(p[key])) return false;
  }
  if (Object.hasOwn(p, 'nextStepId') && p.nextStepId !== null && !id(p.nextStepId)) return false;
  if (Object.hasOwn(p, 'taskRevision') && !natural(p.taskRevision)) return false;
  if (Object.hasOwn(p, 'enabled') && typeof p.enabled !== 'boolean') return false;
  if (Object.hasOwn(p, 'goal') && !['finish', 'learn'].includes(p.goal)) return false;
  if (Object.hasOwn(p, 'style') && !style(p.style)) return false;
  if (Object.hasOwn(p, 'correct') && typeof p.correct !== 'boolean') return false;
  if (Object.hasOwn(p, 'hints') && (!natural(p.hints) || p.hints > 20)) return false;
  if (Object.hasOwn(p, 'value') && !['useful', 'distracting'].includes(p.value)) return false;
  return true;
}
function validTask(task) {
  return exact(task, ['taskId', 'revision', 'status', 'nextStepId']) && id(task.taskId) &&
    natural(task.revision) && ['active', 'interrupted', 'completed'].includes(task.status) &&
    (task.nextStepId === null || id(task.nextStepId)) &&
    (task.status !== 'completed' || task.nextStepId === null);
}
const stateKeys = ['schema', 'evidenceMode', 'scope', 'revision', 'memoryEpoch', 'consent', 'goal',
  'episode', 'memories', 'outcomes', 'feedback', 'reminders', 'checkpoint', 'audit', 'ledger'];
function validSaved(saved, scope) {
  if (!exact(saved, stateKeys) || saved.schema !== 'lens.learning-state/v1' ||
      saved.evidenceMode !== 'SYNTHETIC' || !sameScope(saved.scope, scope) ||
      !natural(saved.revision) || !natural(saved.memoryEpoch) || saved.memoryEpoch > saved.revision ||
      !exact(saved.consent, ['enabled', 'generation']) || typeof saved.consent.enabled !== 'boolean' ||
      !natural(saved.consent.generation) || saved.consent.generation > saved.revision ||
      !['finish', 'learn'].includes(saved.goal)) return false;
  if (saved.episode !== null && (!exact(saved.episode, ['id', 'templateId']) ||
      !id(saved.episode.id) || !id(saved.episode.templateId))) return false;
  const specs = [
    ['memories', 16, (x) => exact(x, ['id', 'style', 'status', 'sourceEpisodeId', 'version']) &&
      id(x.id) && style(x.style) && ['proposed', 'active'].includes(x.status) &&
      id(x.sourceEpisodeId) && natural(x.version) && x.version > 0],
    ['outcomes', 128, (x) => exact(x, ['episodeId', 'templateId', 'stepId', 'correct', 'hints']) &&
      id(x.episodeId) && id(x.templateId) && id(x.stepId) && typeof x.correct === 'boolean' &&
      natural(x.hints) && x.hints <= 20],
    ['feedback', 64, (x) => exact(x, ['proposalId', 'value']) && id(x.proposalId) &&
      ['useful', 'distracting'].includes(x.value)],
    ['reminders', 16, (x) => exact(x, ['id', 'stepId', 'acknowledged']) &&
      id(x.id) && id(x.stepId) && typeof x.acknowledged === 'boolean'],
    ['audit', 128, (x) => exact(x, ['revision', 'operation', 'commandId']) &&
      natural(x.revision) && x.revision > 0 && x.revision <= saved.revision &&
      Object.hasOwn(payloadKeys, x.operation) && id(x.commandId)],
    ['ledger', 256, (x) => exact(x, ['commandId', 'fingerprint', 'appliedRevision']) &&
      id(x.commandId) && typeof x.fingerprint === 'string' && /^[a-f0-9]{64}$/.test(x.fingerprint) &&
      natural(x.appliedRevision) && x.appliedRevision > 0 && x.appliedRevision <= saved.revision],
  ];
  for (const [name, max, check] of specs) if (!Array.isArray(saved[name]) ||
    saved[name].length > max || !saved[name].every(check)) return false;
  if (new Set(saved.memories.map((x) => x.id)).size !== saved.memories.length ||
      saved.memories.filter((x) => x.status === 'active').length > 1 ||
      new Set(saved.reminders.map((x) => x.id)).size !== saved.reminders.length ||
      new Set(saved.ledger.map((x) => x.commandId)).size !== saved.ledger.length ||
      new Set(saved.outcomes.map((x) => JSON.stringify([x.episodeId, x.stepId]))).size !== saved.outcomes.length ||
      new Set(saved.feedback.map((x) => x.proposalId)).size !== saved.feedback.length) return false;
  if (saved.checkpoint !== null && (!exact(saved.checkpoint, ['taskId', 'taskRevision', 'nextStepId']) ||
      !id(saved.checkpoint.taskId) || !natural(saved.checkpoint.taskRevision) ||
      saved.checkpoint.nextStepId !== null && !id(saved.checkpoint.nextStepId))) return false;
  return true;
}

export function createLearningSession({ scope, now = Date.now } = {}) {
  if (!validScope(scope) || typeof now !== 'function') throw new Error('INVALID_SCOPE');
  return sessionFromState({
    schema: 'lens.learning-state/v1', evidenceMode: 'SYNTHETIC', scope: clone(scope),
    revision: 0, memoryEpoch: 0, consent: { enabled: false, generation: 0 },
    goal: 'finish', episode: null, memories: [], outcomes: [], feedback: [],
    reminders: [], checkpoint: null, audit: [], ledger: [],
  }, now);
}

export function restoreLearningSession(saved, { scope, now = Date.now } = {}) {
  if (!validScope(scope) || !validSaved(saved, scope) || typeof now !== 'function') {
    throw new Error('INVALID_OR_WRONG_SCOPE_SAVE');
  }
  return sessionFromState(clone(saved), now);
}

function sessionFromState(initial, now) {
  let state = initial;
  const proposals = new Map();
  const instanceId = globalThis.crypto.randomUUID();
  let proposalSequence = 0;
  let latestTask = null;
  function invalidateProposals() {
    proposals.clear();
    latestTask = null;
  }
  const snapshot = () => clone(state);
  const failure = (code) => ({ ok: false, error: { code }, state: snapshot() });
  function current(binding, task) {
    const time = now();
    return validTask(task) && natural(time) && exact(binding, ['scope', 'episodeId', 'revision',
      'memoryEpoch', 'consentGeneration', 'taskId', 'taskRevision', 'expiresAt']) &&
      sameScope(binding.scope, state.scope) && binding.episodeId === (state.episode?.id ?? null) &&
      binding.revision === state.revision && binding.memoryEpoch === state.memoryEpoch &&
      binding.consentGeneration === state.consent.generation && state.consent.enabled &&
      binding.taskId === task.taskId && binding.taskRevision === task.revision &&
      natural(binding.expiresAt) && binding.expiresAt > time && binding.expiresAt <= time + 30_000;
  }
  async function dispatch(input, { actor = 'user' } = {}) {
    if (!validateLearningCommand(input)) return failure('INVALID_COMMAND');
    const command = clone(input);
    if (actor !== 'user' && !(actor === 'model' && command.operation === 'proposeMemory')) {
      return failure('USER_ACTION_REQUIRED');
    }
    // Snapshot before the await; compare revision again afterwards. No untrusted
    // command can mutate while hashing or bypass the serialized commit point.
    const digest = await fingerprint(command);
    const prior = state.ledger.find((x) => x.commandId === command.commandId);
    if (prior) return prior.fingerprint === digest
      ? { ok: true, state: snapshot(), appliedRevision: prior.appliedRevision, replayed: true }
      : failure('COMMAND_COLLISION');
    if (command.expectedRevision !== state.revision) return failure('REVISION_CONFLICT');
    if (state.ledger.length >= 256) return failure('JOURNAL_FULL');
    if (!state.consent.enabled && !['setConsent', 'forgetAll', 'forgetMemory'].includes(command.operation)) {
      return failure('LEARNING_CONSENT_REQUIRED');
    }
    const next = clone(state), p = command.payload, operation = command.operation;
    const findMemory = () => next.memories.find((x) => x.id === p.memoryId);
    switch (operation) {
      case 'setConsent':
        next.consent = { enabled: p.enabled, generation: next.consent.generation + 1 };
        next.memoryEpoch++;
        if (!p.enabled) next.memories = next.memories.filter((x) => x.status === 'active');
        break;
      case 'setGoal':
        next.goal = p.goal;
        // Feedback learned for one goal must not silently penalize another.
        next.feedback = [];
        break;
      case 'startEpisode':
        if (next.episode?.id === p.episodeId || next.outcomes.some((x) => x.episodeId === p.episodeId)) {
          return failure('EPISODE_REUSED');
        }
        next.episode = { id: p.episodeId, templateId: p.templateId };
        next.checkpoint = null;
        break;
      case 'proposeMemory':
        if (!next.episode) return failure('EPISODE_REQUIRED');
        if (findMemory()) return failure('MEMORY_ID_REUSED');
        if (next.memories.length >= 16) return failure('MEMORY_LIMIT');
        next.memories.push({ id: p.memoryId, style: p.style, status: 'proposed',
          sourceEpisodeId: next.episode.id, version: 1 });
        break;
      case 'confirmMemory': {
        const memory = findMemory();
        if (!memory || memory.status !== 'proposed') return failure('PROPOSED_MEMORY_REQUIRED');
        next.memories = next.memories.filter((x) => x.status !== 'active');
        next.memories.find((x) => x.id === p.memoryId).status = 'active';
        next.memoryEpoch++;
        next.feedback = [];
        break;
      }
      case 'correctMemory': {
        const memory = findMemory();
        if (!memory || memory.status !== 'active') return failure('ACTIVE_MEMORY_REQUIRED');
        memory.style = p.style;
        memory.version++;
        next.memoryEpoch++;
        next.feedback = [];
        break;
      }
      case 'forgetMemory':
        if (!findMemory()) return failure('UNKNOWN_MEMORY');
        next.memories = next.memories.filter((x) => x.id !== p.memoryId);
        // Conservative invalidation: no derived reminder/feedback survives.
        next.reminders = [];
        next.feedback = [];
        next.memoryEpoch++;
        break;
      case 'forgetAll':
        next.memories = []; next.outcomes = []; next.feedback = [];
        next.reminders = []; next.checkpoint = null; next.episode = null;
        next.goal = 'finish'; next.memoryEpoch++;
        break;
      case 'checkpoint':
        if (!next.episode) return failure('EPISODE_REQUIRED');
        next.checkpoint = clone(p);
        break;
      case 'recordOutcome':
        if (!next.episode) return failure('EPISODE_REQUIRED');
        if (next.outcomes.some((x) => x.episodeId === next.episode.id && x.stepId === p.stepId)) {
          return failure('OUTCOME_ALREADY_RECORDED');
        }
        if (next.outcomes.length >= 128) return failure('OUTCOME_LIMIT');
        next.outcomes.push({ episodeId: next.episode.id, templateId: next.episode.templateId,
          stepId: p.stepId, correct: p.correct, hints: p.hints });
        break;
      case 'recordFeedback': {
        const proposal = proposals.get(p.proposalId);
        if (!proposal || !current(proposal.binding, latestTask)) return failure('STALE_PROPOSAL');
        if (next.feedback.some((x) => x.proposalId === p.proposalId)) return failure('FEEDBACK_ALREADY_RECORDED');
        if (next.feedback.length >= 64) next.feedback.shift();
        next.feedback.push({ proposalId: p.proposalId, value: p.value });
        break;
      }
      case 'setReminder':
        if (next.reminders.some((x) => x.id === p.reminderId)) return failure('REMINDER_ID_REUSED');
        if (next.reminders.length >= 16) return failure('REMINDER_LIMIT');
        next.reminders.push({ id: p.reminderId, stepId: p.stepId, acknowledged: false });
        break;
      case 'ackReminder': {
        const reminder = next.reminders.find((x) => x.id === p.reminderId);
        if (!reminder) return failure('UNKNOWN_REMINDER');
        reminder.acknowledged = true;
        break;
      }
      default: return failure('INVALID_COMMAND');
    }
    next.revision++;
    next.ledger.push({ commandId: command.commandId, fingerprint: digest, appliedRevision: next.revision });
    next.audit.push({ revision: next.revision, operation, commandId: command.commandId });
    if (next.audit.length > 128) next.audit.shift();
    state = next;
    proposals.clear();
    return { ok: true, state: snapshot(), appliedRevision: state.revision, replayed: false };
  }

  function recommend(task, { requested = false } = {}) {
    if (!validTask(task) || typeof requested !== 'boolean') throw new Error('INVALID_TASK');
    if (!same(latestTask, task)) proposals.clear();
    latestTask = clone(task);
    const time = now();
    if (!natural(time) || !natural(time + 30_000)) throw new Error('INVALID_TIME');
    const enabled = state.consent.enabled;
    const memory = enabled ? state.memories.find((x) => x.status === 'active') : null;
    const outcomes = enabled ? state.outcomes.filter((x) => x.stepId === task.nextStepId) : [];
    const independentTemplates = new Set(outcomes.filter((x) => x.correct && x.hints === 0).map((x) => x.templateId)).size;
    const assistedAttempts = outcomes.filter((x) => x.hints > 0).length;
    const reminder = enabled ? state.reminders.find((x) => !x.acknowledged && x.stepId === task.nextStepId) : null;
    const distracts = state.feedback.filter((x) => x.value === 'distracting').length;
    let action = 'one_step', reason = 'next_unconfirmed_step';
    if (!enabled) { action = 'stay_silent'; reason = 'learning_disabled'; }
    else if (task.status === 'completed') { action = 'stay_silent'; reason = 'task_already_confirmed'; }
    else if (!state.episode) { action = 'ask_one_question'; reason = 'episode_required'; }
    else if (task.nextStepId === null) { action = 'ask_one_question'; reason = 'next_step_unknown'; }
    else if (reminder) { action = 'one_step'; reason = 'user_requested_context_reminder'; }
    else if (!requested && (memory?.style === 'quiet' || distracts >= 2)) {
      action = 'stay_silent'; reason = memory?.style === 'quiet' ? 'confirmed_quiet_preference' : 'explicit_distraction_feedback';
    } else if (state.goal === 'learn' && (independentTemplates < 3 ||
        outcomes.length > 0 && (!outcomes.at(-1).correct || outcomes.at(-1).hints > 0))) {
      action = 'explain'; reason = 'learning_goal_needs_practice';
    } else if (memory?.style === 'detailed') { action = 'explain'; reason = 'confirmed_detailed_preference'; }
    else if (state.goal === 'learn') { reason = 'diverse_self_attested_practice'; }
    else if (memory) { reason = 'confirmed_preference'; }
    const proposalId = 'p-' + instanceId + '-' + (++proposalSequence);
    const proposal = {
      schema: 'lens.learning-recommendation/v1', evidenceMode: 'SYNTHETIC',
      authority: 'advisory_only', taskCompletionAuthorized: false,
      proposalId, action, reasonCodes: [reason], nextStepId: task.nextStepId,
      appliedMemoryId: memory?.id ?? null, reminderId: reminder?.id ?? null,
      learning: { independentTemplates, assistedAttempts, masteryVerified: false },
      binding: { scope: clone(state.scope), episodeId: state.episode?.id ?? null,
        revision: state.revision, memoryEpoch: state.memoryEpoch,
        consentGeneration: state.consent.generation, taskId: task.taskId,
        taskRevision: task.revision, expiresAt: time + 30_000 },
    };
    proposals.set(proposalId, { ...clone(proposal), task: clone(task) });
    if (proposals.size > 32) proposals.delete(proposals.keys().next().value);
    return proposal;
  }

  function admitDecision(decision, task) {
    if (!exact(decision, ['schema', 'proposalId', 'action', 'binding', 'evidenceMode', 'authority']) ||
        decision.schema !== 'lens.learning-decision/v1' || decision.evidenceMode !== 'SYNTHETIC' ||
        decision.authority !== 'advisory_only' || !['one_step', 'explain', 'ask_one_question', 'stay_silent'].includes(decision.action)) {
      return { ok: false, error: { code: 'INVALID_DECISION' } };
    }
    const original = proposals.get(decision.proposalId);
    if (!original || !same(original.binding, decision.binding) || !current(decision.binding, task)) {
      return { ok: false, error: { code: 'STALE_DECISION' } };
    }
    // Model output may reduce certainty or attention, never override silence,
    // an explicit goal, a changed task, or grant completion/learning authority.
    if (decision.action !== original.action && !['ask_one_question', 'stay_silent'].includes(decision.action) ||
        original.action === 'stay_silent' && decision.action !== 'stay_silent') {
      return { ok: false, error: { code: 'POLICY_REJECTED' } };
    }
    return { ok: true, recommendation: { ...clone(original), action: decision.action,
      reasonCodes: [...original.reasonCodes, 'advisory_model_selection'] },
      stateChanged: false, taskCompletionAuthorized: false };
  }

  function handoff(recipient, task) {
    if (!['taimi', 'meta', 'nvidia'].includes(recipient) || !validTask(task)) throw new Error('INVALID_HANDOFF');
    if (!state.consent.enabled || !state.episode) throw new Error('LEARNING_CONSENT_REQUIRED');
    return { schema: 'lens.learning-handoff/v1', evidenceMode: 'SYNTHETIC',
      authority: 'advisory_only', recipient, goal: state.goal, nextStepId: task.nextStepId,
      context: { taskId: task.taskId, taskRevision: task.revision },
      executionAuthorized: false };
  }
  return { dispatch, snapshot, recommend, admitDecision, handoff, invalidateProposals, exportState: snapshot };
}
