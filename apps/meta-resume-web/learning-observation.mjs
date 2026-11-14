import { canonical } from './learning-core.mjs';
import { observationRequest, parseObservationBundle, validateObservationResponse } from './observation-client.mjs';

const clone = (value) => structuredClone(value);
const record = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
const exact = (x, keys) => record(x) && Object.keys(x).length === keys.length && keys.every((key) => Object.hasOwn(x, key));
const id = (x) => typeof x === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(x);
const natural = (x) => Number.isSafeInteger(x) && x >= 0;
const scopeKeys = ['tenantId', 'ownerId', 'contextId'];
const failure = (code) => ({ ok: false, error: { code } });
const same = (a, b) => canonical(a) === canonical(b);

/** Ephemeral composition only: no storage, learning commands or task authority. */
export function createLearningObservationBridge({ read, now = Date.now } = {}) {
  if (typeof read !== 'function' || typeof now !== 'function') throw new TypeError('INVALID_BRIDGE_PORT');
  let active = null, pending = null, version = 0;

  function readCurrent() {
    const value = read(), time = now();
    if (!record(value) || !natural(time)) throw new Error('INVALID_BRIDGE_CONTEXT');
    const { state, policy, learning } = value;
    if (!record(state) || !id(state.taskId) || !natural(state.revision) ||
        !['active', 'interrupted'].includes(state.status) || !id(state.nextUnconfirmedStep)) {
      throw new Error('TASK_NOT_ACTIVE');
    }
    if (!record(policy) || policy.captureEnabled !== true || !id(policy.sessionId) || !natural(policy.captureGeneration)) {
      throw new Error('CAPTURE_NOT_ACTIVE');
    }
    if (!record(learning) || learning.schema !== 'lens.learning-state/v1' || learning.evidenceMode !== 'SYNTHETIC' ||
        !exact(learning.scope, scopeKeys) || !scopeKeys.every((key) => id(learning.scope[key])) ||
        !natural(learning.revision) || !natural(learning.memoryEpoch) ||
        !record(learning.consent) || learning.consent.enabled !== true || !natural(learning.consent.generation) ||
        !record(learning.episode) || !id(learning.episode.id) || !Array.isArray(learning.memories)) {
      throw new Error('LEARNING_NOT_ACTIVE');
    }
    const binding = {
      scope: clone(learning.scope), episodeId: learning.episode.id,
      revision: learning.revision, memoryEpoch: learning.memoryEpoch,
      consentGeneration: learning.consent.generation, taskId: state.taskId,
      taskRevision: state.revision, taskStatus: state.status, nextStepId: state.nextUnconfirmedStep,
      sessionId: policy.sessionId, captureGeneration: policy.captureGeneration,
    };
    return { state: clone(state), policy: clone(policy), learning: clone(learning), time, binding };
  }

  function clear() { version++; active = null; pending = null; }

  function requestKey(request) {
    return canonical({ schemaVersion: request.schemaVersion, task: request.task,
      observation: request.observation,
      image: { kind: request.image.kind, sha256: request.image.sha256, trackId: request.image.trackId } });
  }

  /** Capture learning and task state BEFORE the observation service is awaited. */
  function begin(request) {
    clear();
    try {
      if (!exact(request, ['schemaVersion', 'task', 'observation', 'image']) || request.schemaVersion !== 1) return null;
      const current = readCurrent();
      const expected = observationRequest({ observation: request.observation, image: request.image }, current.state, current.policy);
      if (!same(request.task, expected.task)) return null;
      const capturedAt = Date.parse(request.observation.frame.capturedAt);
      if (!natural(capturedAt) || capturedAt > current.time || current.time - capturedAt >= 30_000) return null;
      // Object identity is local-only and unforgeable through JSON. It carries
      // no pixels, grant, tenant data or request contents to another component.
      const ticket = Object.freeze({});
      pending = { ticket, version, binding: current.binding, key: requestKey(request),
        startedAt: current.time, expiresAt: capturedAt + 30_000 };
      return ticket;
    } catch { return null; }
  }

  async function accept(input) {
    if (!exact(input, ['request', 'result', 'ticket']) || !pending || input.ticket !== pending.ticket) {
      return failure('STALE_OBSERVATION');
    }
    const issued = pending, ticket = issued.version;
    pending = null; active = null;
    let initial, request, result;
    try {
      if (!exact(input.request, ['schemaVersion', 'task', 'observation', 'image']) || input.request.schemaVersion !== 1) {
        return failure('INVALID_OBSERVATION_INPUT');
      }
      initial = readCurrent();
      request = clone(input.request);
      if (!same(issued.binding, initial.binding) || issued.key !== requestKey(request) ||
          initial.time < issued.startedAt || initial.time >= issued.expiresAt) return failure('STALE_OBSERVATION');
      const expected = observationRequest({ observation: request.observation, image: request.image }, initial.state, initial.policy);
      if (!same(request.task, expected.task)) return failure('OBSERVATION_TASK_MISMATCH');
      const response = input.result;
      if (!record(response)) return failure('INVALID_OBSERVATION_INPUT');
      result = validateObservationResponse(clone({ status: response.status, binding: response.binding, proposal: response.proposal }),
        request, initial.state, initial.policy);
      if (result.status !== 'proposed' || !result.proposal) return failure('NO_OBSERVATION_PROPOSAL');
      const capturedAt = Date.parse(request.observation.frame.capturedAt);
      if (!natural(capturedAt) || capturedAt > initial.time || initial.time - capturedAt >= 30_000) {
        return failure('OBSERVATION_EXPIRED');
      }
      // Reuse actual bundle byte validation; no raw pixels are retained in active.
      await parseObservationBundle(JSON.stringify({ observation: request.observation, image: request.image }));
      const material = { observation: request.observation, binding: result.binding, proposal: result.proposal };
      const bytes = new TextEncoder().encode(canonical(material));
      const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
      const current = readCurrent(), expiresAt = capturedAt + 30_000;
      if (ticket !== version || !same(initial.binding, current.binding) || current.time < initial.time || current.time >= expiresAt) {
        return failure('STALE_OBSERVATION');
      }
      const observationSha256 = [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, '0')).join('');
      active = { observationSha256, binding: current.binding, source: clone(result.binding),
        evidenceMode: request.observation.evidenceMode, acceptedAt: current.time, expiresAt,
        proposal: clone(result.proposal) };
      return { ok: true, observationSha256, expiresAt };
    } catch {
      return failure(ticket === version ? 'OBSERVATION_NOT_ADMITTED' : 'STALE_OBSERVATION');
    }
  }

  function context(recommendation) {
    if (!active) return null;
    try {
      const current = readCurrent(), r = recommendation, b = r?.binding;
      if (!same(active.binding, current.binding) || current.time < active.acceptedAt || current.time >= active.expiresAt) {
        clear(); return null;
      }
      const expectedBinding = { scope: current.binding.scope, episodeId: current.binding.episodeId,
        revision: current.binding.revision, memoryEpoch: current.binding.memoryEpoch,
        consentGeneration: current.binding.consentGeneration, taskId: current.binding.taskId,
        taskRevision: current.binding.taskRevision, expiresAt: b?.expiresAt };
      if (!record(r) || r.schema !== 'lens.learning-recommendation/v1' || r.evidenceMode !== 'SYNTHETIC' ||
          r.authority !== 'advisory_only' || r.taskCompletionAuthorized !== false ||
          !['one_step', 'explain', 'ask_one_question', 'stay_silent'].includes(r.action) ||
          r.nextStepId !== current.binding.nextStepId || !same(b, expectedBinding) ||
          !natural(b?.expiresAt) || b.expiresAt <= current.time || b.expiresAt > current.time + 30_000 ||
          !Array.isArray(r.reasonCodes) || r.reasonCodes.length > 8 || !r.reasonCodes.every((x) => id(x))) return null;
      const memory = current.learning.memories.find((x) => x.status === 'active');
      if (r.appliedMemoryId !== (memory?.id ?? null)) return null;
      const quiet = r.action === 'stay_silent', p = active.proposal;
      return {
        schema: 'lens.learning-observation-context/v1', evidenceMode: active.evidenceMode,
        learningEvidenceMode: 'SYNTHETIC', authority: 'advisory_only',
        observationSha256: active.observationSha256,
        binding: { ...clone(active.binding), observation: clone(active.source), expiresAt: Math.min(active.expiresAt, b.expiresAt) },
        summary: quiet ? null : p.summary, observations: quiet ? [] : clone(p.observations),
        uncertainties: quiet ? [] : clone(p.uncertainties), nextQuestion: quiet ? null : p.nextQuestion,
        nextStepProposal: quiet ? null : clone(p.nextStepProposal),
        assistance: { action: r.action, reasonCodes: [...r.reasonCodes], appliedMemoryId: r.appliedMemoryId },
        physicalIdentityVerified: false, taskCompletionAuthorized: false, memoryMutationAuthorized: false,
      };
    } catch { clear(); return null; }
  }

  return { begin, accept, context, clear };
}
