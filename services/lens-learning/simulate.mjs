import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import {
  createLearningSession, restoreLearningSession, canonical,
} from '../../apps/meta-resume-web/learning-core.mjs';
import { createSession } from '../../apps/meta-resume-web/state.mjs';
import { FIXTURE } from '../../apps/meta-resume-web/fixture.mjs';

const BASE = '9e1915827fabff9836dac217ab69727e514acc49';
const scope = Object.freeze({ tenantId: 'demo-tenant', ownerId: 'demo-owner', contextId: 'camera-packing' });
const NOW = 1_794_655_200_000;
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const task = Object.freeze({ taskId: 'demo-packing', revision: 2, status: 'active', nextStepId: 'check-batteries' });
const decisions = {
  memory_route: {
    instructions: 'Choose how the supplied memory may be used NOW. A visual guess is episode-only. An explicit confirmed preference may guide help. A revoke disables use even when the record is retained. An explicit forget must erase learned and derived state. Never infer a permanent trait from a picture.',
    choices: [
      { value: 'retain_episode', description: 'Only an episode or unconfirmed candidate exists; do not apply a permanent preference.' },
      { value: 'apply_confirmed_preference', description: 'An active user-confirmed preference exists and current learning consent allows use.' },
      { value: 'forget_derived_state', description: 'The user explicitly requested forgetting; learned preferences and their dependent state must be removed.' },
      { value: 'do_not_use', description: 'Learning consent is revoked or the context is unauthorized; do not use personal memory.' },
    ],
  },
  assistance: {
    instructions: 'Choose the next advisory help action. Disabled learning or a confirmed quiet preference without an explicit help request means stay_silent. An unknown episode/next step means ask_one_question. In learning mode, fewer than 3 diverse independently correct templates OR the latest assisted/incorrect result means explain. An active detailed preference means explain. Otherwise offer one_step. Never mark the task completed.',
    choices: [
      { value: 'one_step', description: 'Offer one next unfinished step without completing it.' },
      { value: 'explain', description: 'Explain the current step because of the learning goal or confirmed detailed preference.' },
      { value: 'ask_one_question', description: 'Ask one bounded clarification before assuming the current episode or step.' },
      { value: 'stay_silent', description: 'Do not proactively interrupt or use revoked learning context.' },
    ],
  },
  skill_evidence: {
    instructions: 'Classify the available permitted outcome evidence, not physical mastery. No outcomes or disabled consent means unverified. A latest successful attempt with hints is assisted. Diverse user-attested correct attempts without hints count as independent practice but never verified mastery. Seeing an object alone proves no successful performance.',
    choices: [
      { value: 'independent', description: 'Permitted user-attested successful practice without hints is present; this is not verified mastery.' },
      { value: 'assisted', description: 'The supplied practice required hints; do not credit independent mastery.' },
      { value: 'unverified', description: 'There is no permitted explicit performance evidence.' },
    ],
  },
};
function command(session, operation, payload, commandId) {
  return { schema: 'lens.learning-command/v1', commandId: commandId ?? 'c-' + (session.snapshot().revision + 1),
    expectedRevision: session.snapshot().revision, operation, payload };
}
async function apply(session, operation, payload = {}, actor = 'user') {
  const result = await session.dispatch(command(session, operation, payload), { actor });
  assert.equal(result.ok, true, operation + ': ' + result.error?.code);
  return result;
}
async function fresh() {
  const s = createLearningSession({ scope, now: () => NOW });
  await apply(s, 'setConsent', { enabled: true });
  await apply(s, 'startEpisode', { episodeId: 'episode-1', templateId: 'desk-kit' });
  return s;
}
async function memory(s, value) {
  await apply(s, 'proposeMemory', { memoryId: 'help-style', style: value });
  await apply(s, 'confirmMemory', { memoryId: 'help-style' });
}
function modelDecision(p, action = p.action) {
  return { schema: 'lens.learning-decision/v1', proposalId: p.proposalId, action,
    binding: p.binding, evidenceMode: 'SYNTHETIC', authority: 'advisory_only' };
}

export async function runSimulations() {
  const checks = [], cases = [];
  async function check(name, action) { await action(); checks.push({ name, result: 'pass' }); }
  function addCase(id, session, note, expected, extra = {}) {
    const state = session.snapshot(), suggestion = session.recommend(task);
    assert.equal(suggestion.action, expected.assistance[0], id);
    assert.equal(suggestion.taskCompletionAuthorized, false);
    assert.equal(suggestion.learning.masteryVerified, false);
    const input = canonical({ evidenceMode: 'SYNTHETIC', scenario: note,
      learningConsent: state.consent.enabled, goal: state.goal, episode: state.episode,
      memories: state.memories, outcomes: state.outcomes, task, explicitHelpRequest: false, ...extra });
    const request = { schema: 'factory.decision-assist-request/v1', task_id: 'lens-' + id,
      source_sha256: hash(input), input,
      questions: Object.entries(decisions).map(([name, value]) => ({ name, ...structuredClone(value) })) };
    cases.push({ id, request, expected, domain: { action: suggestion.action,
      activeMemories: state.memories.filter((x) => x.status === 'active').length,
      independentTemplates: suggestion.learning.independentTemplates,
      assistedAttempts: suggestion.learning.assistedAttempts,
      masteryVerified: false, taskCompletionAuthorized: false } });
  }
  {
    const s = await fresh();
    await apply(s, 'proposeMemory', { memoryId: 'visual-guess', style: 'quiet' }, 'model');
    addCase('unconfirmed-visual-guess', s, 'A model guessed a quiet preference from one image. The user did not confirm it.',
      { memory_route: ['retain_episode'], assistance: ['one_step'], skill_evidence: ['unverified'] });
  }
  {
    const s = await fresh(); await memory(s, 'detailed');
    addCase('confirmed-preference', s, 'The user explicitly requested and confirmed detailed help.',
      { memory_route: ['apply_confirmed_preference'], assistance: ['explain'], skill_evidence: ['unverified'] });
  }
  {
    const s = await fresh(); await memory(s, 'detailed');
    await apply(s, 'correctMemory', { memoryId: 'help-style', style: 'quiet' });
    await apply(s, 'startEpisode', { episodeId: 'episode-2', templateId: 'travel-kit' });
    addCase('correction-next-episode', s, 'The user corrected detailed help to quiet. This is the next episode, with no explicit request for help.',
      { memory_route: ['apply_confirmed_preference'], assistance: ['stay_silent'], skill_evidence: ['unverified'] });
  }
  {
    const s = await fresh(); await apply(s, 'setGoal', { goal: 'learn' });
    for (let i = 1; i <= 3; i++) {
      if (i > 1) await apply(s, 'startEpisode', { episodeId: 'assisted-' + i, templateId: 'desk-kit' });
      await apply(s, 'recordOutcome', { stepId: task.nextStepId, correct: true, hints: 1 });
    }
    addCase('assisted-is-not-mastery', s, 'Three successful practices used one hint each, all in the same template.',
      { memory_route: ['retain_episode'], assistance: ['explain'], skill_evidence: ['assisted'] });
  }
  {
    const s = await fresh(); await apply(s, 'setGoal', { goal: 'learn' });
    for (let i = 1; i <= 3; i++) {
      if (i > 1) await apply(s, 'startEpisode', { episodeId: 'independent-' + i, templateId: 'kit-' + i });
      await apply(s, 'recordOutcome', { stepId: task.nextStepId, correct: true, hints: 0 });
    }
    addCase('independent-diverse-practice', s, 'Three diverse templates have explicit user-attested correct outcomes without hints. No sensor-verified mastery is claimed.',
      { memory_route: ['retain_episode'], assistance: ['one_step'], skill_evidence: ['independent'] });
  }
  {
    const s = await fresh(); await memory(s, 'detailed');
    await apply(s, 'setConsent', { enabled: false });
    addCase('revoked-consent', s, 'The user stopped learning. The historical record remains but use is disabled.',
      { memory_route: ['do_not_use'], assistance: ['stay_silent'], skill_evidence: ['unverified'] });
  }
  {
    const s = await fresh(); await memory(s, 'detailed');
    await apply(s, 'setReminder', { reminderId: 'battery-reminder', stepId: task.nextStepId });
    await apply(s, 'recordOutcome', { stepId: task.nextStepId, correct: true, hints: 0 });
    await apply(s, 'forgetAll');
    const restored = restoreLearningSession(s.exportState(), { scope, now: () => NOW });
    assert.equal(restored.snapshot().memories.length + restored.snapshot().outcomes.length + restored.snapshot().reminders.length, 0);
    addCase('forget-derived-state', restored, 'The user explicitly requested forget all learned data. The episode and dependent reminders are cleared.',
      { memory_route: ['forget_derived_state'], assistance: ['ask_one_question'], skill_evidence: ['unverified'] },
      { lastUserRequest: 'forget all learned data' });
  }
  {
    const s = await fresh(); await memory(s, 'one_step');
    const old = s.recommend(task);
    await apply(s, 'setGoal', { goal: 'learn' });
    assert.equal(s.admitDecision(modelDecision(old), task).error.code, 'STALE_DECISION');
    addCase('changed-goal-invalidates-decision', s, 'The user changed the goal from finish quickly to learn the step. There is no practice evidence yet.',
      { memory_route: ['apply_confirmed_preference'], assistance: ['explain'], skill_evidence: ['unverified'] });
  }

  await check('model-cannot-confirm-memory-or-performance', async () => {
    const s = await fresh();
    await apply(s, 'proposeMemory', { memoryId: 'guess', style: 'detailed' }, 'model');
    for (const [op, payload] of [['confirmMemory', { memoryId: 'guess' }],
      ['recordOutcome', { stepId: task.nextStepId, correct: true, hints: 0 }], ['setConsent', { enabled: true }]]) {
      const before = s.exportState();
      const result = await s.dispatch(command(s, op, payload), { actor: 'model' });
      assert.equal(result.error.code, 'USER_ACTION_REQUIRED'); assert.deepEqual(s.exportState(), before);
    }
  });
  await check('scope-isolation-and-closed-save-schema', async () => {
    const s = await fresh(); await memory(s, 'quiet');
    assert.throws(() => restoreLearningSession(s.exportState(), { scope: { ...scope, ownerId: 'other-owner' } }));
    assert.throws(() => restoreLearningSession({ ...s.exportState(), admin: true }, { scope }));
    assert.throws(() => restoreLearningSession({ ...s.exportState(), evidenceMode: 'MODEL' }, { scope }));
  });
  await check('tuple-identities-restore-with-colons', async () => {
    const s = await fresh();
    await apply(s, 'startEpisode', { episodeId: 'a:b', templateId: 'kit-a' });
    await apply(s, 'recordOutcome', { stepId: 'c', correct: true, hints: 0 });
    await apply(s, 'startEpisode', { episodeId: 'a', templateId: 'kit-b' });
    await apply(s, 'recordOutcome', { stepId: 'b:c', correct: true, hints: 0 });
    assert.equal(restoreLearningSession(s.exportState(), { scope }).snapshot().outcomes.length, 2);
  });
  await check('feedback-cannot-refer-to-an-old-task-or-reset', async () => {
    const s = await fresh(), old = s.recommend(task);
    s.recommend({ ...task, revision: 3, nextStepId: 'other-step' });
    const stale = await s.dispatch(command(s, 'recordFeedback', { proposalId: old.proposalId, value: 'distracting' }));
    assert.equal(stale.error.code, 'STALE_PROPOSAL');
    const beforeReset = s.recommend(task);
    s.invalidateProposals();
    s.recommend(task);
    assert.equal(s.admitDecision(modelDecision(beforeReset), task).error.code, 'STALE_DECISION');
  });
  await check('exact-idempotency-and-concurrent-revision', async () => {
    const s = await fresh(), c = command(s, 'setGoal', { goal: 'learn' }, 'retry-command');
    const first = await s.dispatch(c), retry = await s.dispatch(c);
    assert.equal(retry.replayed, true); assert.equal(retry.appliedRevision, first.appliedRevision);
    const changed = await s.dispatch({ ...c, payload: { goal: 'finish' } });
    assert.equal(changed.error.code, 'COMMAND_COLLISION');
    const a = command(s, 'setGoal', { goal: 'finish' }, 'writer-a');
    const b = command(s, 'setGoal', { goal: 'learn' }, 'writer-b');
    const concurrent = await Promise.all([s.dispatch(a), s.dispatch(b)]);
    assert.equal(concurrent.filter((x) => x.ok).length, 1);
    assert.equal(concurrent.filter((x) => x.error?.code === 'REVISION_CONFLICT').length, 1);
    const restored = restoreLearningSession(s.exportState(), { scope, now: () => NOW });
    assert.equal((await restored.dispatch(c)).replayed, true);
  });
  await check('late-decision-cannot-survive-revoke-forget-or-task-change', async () => {
    for (const [op, p] of [['setConsent', { enabled: false }], ['forgetAll', {}]]) {
      const s = await fresh(), proposal = s.recommend(task);
      await apply(s, op, p);
      assert.equal(s.admitDecision(modelDecision(proposal), task).error.code, 'STALE_DECISION');
    }
    const s = await fresh(), proposal = s.recommend(task);
    assert.equal(s.admitDecision(modelDecision(proposal), { ...task, revision: 3 }).error.code, 'STALE_DECISION');
    const restored = restoreLearningSession(s.exportState(), { scope, now: () => NOW });
    restored.recommend(task);
    assert.equal(restored.admitDecision(modelDecision(proposal), task).error.code, 'STALE_DECISION');
  });
  await check('expired-decision-and-silence-policy', async () => {
    let clock = NOW;
    const s = createLearningSession({ scope, now: () => clock });
    await apply(s, 'setConsent', { enabled: true });
    await apply(s, 'startEpisode', { episodeId: 'expiry-episode', templateId: 'desk-kit' });
    const p = s.recommend(task); clock += 30_001;
    assert.equal(s.admitDecision(modelDecision(p), task).error.code, 'STALE_DECISION');
    await memory(s, 'quiet'); const quiet = s.recommend(task);
    assert.equal(s.admitDecision(modelDecision(quiet, 'explain'), task).error.code, 'POLICY_REJECTED');
  });
  await check('repeated-template-does-not-inflate-independent-diversity', async () => {
    const s = await fresh(); await apply(s, 'setGoal', { goal: 'learn' });
    for (let i = 1; i <= 4; i++) {
      if (i > 1) await apply(s, 'startEpisode', { episodeId: 'repeat-' + i, templateId: 'desk-kit' });
      await apply(s, 'recordOutcome', { stepId: task.nextStepId, correct: true, hints: 0 });
    }
    assert.equal(s.recommend(task).learning.independentTemplates, 1);
    assert.equal(s.recommend(task).action, 'explain');
  });
  await check('recent-assisted-practice-restores-help', async () => {
    const s = await fresh(); await apply(s, 'setGoal', { goal: 'learn' });
    for (let i = 1; i <= 4; i++) {
      if (i > 1) await apply(s, 'startEpisode', { episodeId: 'practice-' + i, templateId: 'kit-' + i });
      await apply(s, 'recordOutcome', { stepId: task.nextStepId, correct: true, hints: i === 4 ? 1 : 0 });
    }
    assert.equal(s.recommend(task).learning.independentTemplates, 3);
    assert.equal(s.recommend(task).action, 'explain');
  });
  await check('reminder-feedback-and-minimal-handoff', async () => {
    const s = await fresh();
    for (let i = 0; i < 2; i++) {
      const p = s.recommend(task);
      await apply(s, 'recordFeedback', { proposalId: p.proposalId, value: 'distracting' });
    }
    assert.equal(s.recommend(task).action, 'stay_silent');
    assert.equal(s.recommend(task, { requested: true }).action, 'one_step');
    await apply(s, 'setReminder', { reminderId: 'battery', stepId: task.nextStepId });
    assert.equal(s.recommend(task).reasonCodes[0], 'user_requested_context_reminder');
    await apply(s, 'ackReminder', { reminderId: 'battery' });
    assert.equal(s.recommend(task).reminderId, null);
    const handoff = s.handoff('taimi', task);
    assert.equal(handoff.executionAuthorized, false);
    assert.equal(Object.hasOwn(handoff, 'memories'), false);
    assert.equal(Object.hasOwn(handoff, 'scope'), false);
  });
  await check('original-resume-progress-stays-user-owned', async () => {
    const resume = createSession(), s = await fresh();
    function resumeCommand(op, payload = {}) {
      const view = resume.snapshot();
      return { schemaVersion: 1, taskId: FIXTURE.taskId,
        commandId: globalThis.crypto.randomUUID(), expectedRevision: view.revision, operation: op, payload };
    }
    const first = FIXTURE.steps[0].stepId;
    assert.equal(resume.dispatch(resumeCommand('confirmStep', { stepId: first })).error, undefined);
    resume.dispatch(resumeCommand('interrupt'));
    const paused = resume.snapshot();
    await apply(s, 'checkpoint', { taskId: paused.taskId, taskRevision: paused.revision, nextStepId: paused.nextUnconfirmedStep });
    resume.dispatch(resumeCommand('resume', { evidenceIds: [] }));
    const view = resume.snapshot();
    const t = { taskId: view.taskId, revision: view.revision, status: view.status, nextStepId: view.nextUnconfirmedStep };
    const proposal = s.recommend(t), before = resume.snapshot();
    assert.equal(s.admitDecision(modelDecision(proposal), t).ok, true);
    assert.deepEqual(resume.snapshot(), before);
    assert.equal(before.steps.filter((x) => x.userConfirmed).length, 1);
  });

  const root = fileURLToPath(new URL('../../', import.meta.url));
  const files = {};
  for (const path of ['apps/meta-resume-web/learning-core.mjs', 'apps/meta-resume-web/state.mjs',
    'apps/meta-resume-web/fixture.mjs', 'services/lens-learning/simulate.mjs']) {
    files[path] = hash(await readFile(resolve(root, path)));
  }
  const source = { baseCommit: BASE, files };
  return {
    suite: { schema: 'lens.learning-evaluation-suite/v1', evidenceMode: 'SYNTHETIC', source, cases },
    report: { schema: 'lens.learning-simulation-report/v1', evidenceMode: 'SYNTHETIC', source,
      evaluatedCases: cases.length, checks, passed: checks.length,
      providerCalls: 0, physicalDeviceVerified: false, privateHostVerified: false,
      cases: cases.map(({ id, domain }) => ({ id, ...domain })) },
  };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== '--output') throw new Error('Usage: node simulate.mjs --output <owned-directory>');
  const { suite, report } = await runSimulations();
  await mkdir(args[1], { recursive: true });
  await writeFile(resolve(args[1], 'provider-suite.json'), JSON.stringify(suite, null, 2) + '\n');
  await writeFile(resolve(args[1], 'domain-report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ cases: report.evaluatedCases, checks: report.passed, providerCalls: 0, output: resolve(args[1]) }));
}
