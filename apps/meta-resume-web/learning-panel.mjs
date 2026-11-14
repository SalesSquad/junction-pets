import { createLearningSession, restoreLearningSession } from './learning-core.mjs';
import { FIXTURE } from './fixture.mjs';

const SCOPE = Object.freeze({ tenantId: 'demo-tenant', ownerId: 'demo-owner', contextId: 'camera-packing' });
const STORAGE_KEY = 'chibi-lens.learning.synthetic.camera-packing.v1';
const STYLES = [['one_step', 'One next step'], ['detailed', 'Explain the steps'], ['quiet', 'Stay quiet until I ask']];
const TEMPLATES = [['camera-bag-v1', 'Everyday camera bag'], ['camera-bag-interview', 'Interview kit'], ['camera-bag-travel', 'Travel kit']];
const styleLabel = (value) => STYLES.find(([key]) => key === value)?.[1] ?? 'Unknown preference';
const stepLabel = (value) => FIXTURE.steps.find((step) => step.stepId === value)?.label ?? 'the next unfinished step';
const uid = (prefix) => `${prefix}-${crypto.randomUUID()}`;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function button(text, action, className = 'secondary-button') {
  const element = node('button', className, text);
  element.type = 'button';
  element.dataset.learningAction = action;
  return element;
}

function field(labelText, id, choices) {
  const wrapper = node('div', 'learning-field');
  const label = node('label', null, labelText);
  label.htmlFor = id;
  const select = node('select');
  select.id = id;
  for (const [value, text] of choices) {
    const option = node('option', null, text);
    option.value = value;
    select.append(option);
  }
  wrapper.append(label, select);
  return { wrapper, select };
}

/** Synthetic UI only. Real personal memory belongs to the authenticated Chibi host. */
export function createLearningPanel({ mount, taskView, resetTask, onChange = () => {} }) {
  if (!(mount instanceof HTMLElement) || typeof taskView !== 'function' || typeof resetTask !== 'function') {
    throw new TypeError('Learning panel needs a mount, current task and reset callback.');
  }
  let session = createLearningSession({ scope: SCOPE, now: () => Date.now() });
  let busy = false;
  let recommendation = null;
  let recommendationKey = '';
  let handoffProposal = null;
  let storageAvailable = true;
  let restored = false;
  let restoreMessage = '';
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      if (raw.length > 500_000) throw new Error('Saved learning demo is too large.');
      session = restoreLearningSession(JSON.parse(raw), { scope: SCOPE, now: () => Date.now() });
      restored = true;
    }
  } catch {
    storageAvailable = false;
    restoreMessage = 'The previous learning demo could not be loaded. This session starts with no learned preferences.';
  }

  mount.classList.add('learning-panel');
  mount.setAttribute('aria-labelledby', 'learningTitle');
  const header = node('div', 'learning-header');
  const heading = node('div');
  heading.append(node('p', 'eyebrow', 'LENS · YOUR WAY OF DOING THINGS'));
  const title = node('h2', null, 'Help that learns your way.');
  title.id = 'learningTitle';
  heading.append(title, node('p', 'learning-intro', 'Teach a preference. Correct it. Bring it into the next moment.'));
  const headerActions = node('div', 'learning-header-actions');
  const badge = node('span', 'learning-badge', 'SYNTHETIC LEARNING');
  const consentButton = button('Start learning demo', 'consent', 'primary-button');
  headerActions.append(badge, consentButton);
  header.append(heading, headerActions);

  const steps = node('ol', 'learning-journey');
  for (const [number, text] of [['01', 'Teach'], ['02', 'Pause & return'], ['03', 'Correct'], ['04', 'Reuse']]) {
    const item = node('li');
    item.append(node('span', null, number), node('strong', null, text));
    steps.append(item);
  }

  const grid = node('div', 'learning-grid');
  const adviceCard = node('article', 'learning-advice');
  const adviceKicker = node('div', 'card-kicker');
  adviceKicker.append(node('span', 'eyebrow', 'THE NEXT USEFUL HELP'), node('span', 'learning-advisory', 'ADVICE'));
  const adviceTitle = node('h3', null, 'A preference starts with you.');
  adviceTitle.id = 'learningAdviceTitle';
  const adviceText = node('p', 'learning-advice-text');
  const adviceMeta = node('p', 'learning-meta');
  const reminderNote = node('div', 'learning-reminder');
  reminderNote.hidden = true;
  const reminderText = node('p');
  const ackButton = button('Got it', 'ack-reminder', 'link-button');
  reminderNote.append(reminderText, ackButton);
  const adviceActions = node('div', 'learning-actions');
  const askButton = button('Ask for the next step', 'ask', 'primary-button');
  const checkpointButton = button('Save my place', 'checkpoint');
  adviceActions.append(askButton, checkpointButton);
  const feedbackRow = node('div', 'learning-feedback');
  const usefulButton = button('Useful', 'useful', 'link-button');
  const distractingButton = button('Too much', 'distracting', 'link-button');
  feedbackRow.append(node('span', null, 'Was this the right amount of help?'), usefulButton, distractingButton);
  const checkpointNote = node('p', 'learning-fineprint');
  adviceCard.append(adviceKicker, adviceTitle, adviceText, adviceMeta, reminderNote, adviceActions, feedbackRow, checkpointNote);

  const memoryCard = node('article', 'learning-memory');
  const memoryKicker = node('div', 'card-kicker');
  memoryKicker.append(node('h3', null, 'What Lens remembers'), node('span', 'local-badge', 'THIS CONTEXT'));
  const memoryList = node('div', 'learning-memories');
  memoryList.id = 'learningMemories';
  const styleField = field('How should Lens help?', 'learningStyle', STYLES);
  const restoredPreference = session.snapshot().memories.findLast((memory) => memory.status === 'active');
  if (restoredPreference) styleField.select.value = restoredPreference.style;
  const teachButton = button('Suggest this preference', 'teach', 'primary-button');
  const forgetButton = button('Forget learning', 'forget-all', 'link-button learning-forget');
  const memoryActions = node('div', 'learning-actions');
  memoryActions.append(teachButton, forgetButton);
  memoryCard.append(memoryKicker, memoryList, styleField.wrapper, memoryActions,
    node('p', 'learning-fineprint', 'A proposal becomes a preference only when you approve it.'));
  grid.append(adviceCard, memoryCard);

  const controls = node('details', 'learning-more');
  controls.append(node('summary', null, 'Practice, reminders & specialist help'));
  const controlsGrid = node('div', 'learning-controls-grid');
  const practiceCard = node('section', 'learning-control-card');
  practiceCard.append(node('h3', null, 'What are you aiming for?'));
  const goalField = field('This episode’s goal', 'learningGoal', [['finish', 'Finish the task'], ['learn', 'Understand and learn']]);
  const templateField = field('Next synthetic practice scene', 'learningTemplate', TEMPLATES);
  const nextButton = button('Start next episode', 'next-episode');
  practiceCard.append(goalField.wrapper, templateField.wrapper, nextButton,
    node('p', 'learning-fineprint', 'A new episode keeps approved preferences and restarts the packing task. Repeating one scene does not count as a new skill context.'));

  const evidenceCard = node('section', 'learning-control-card');
  evidenceCard.append(node('h3', null, 'Record a practice result'));
  const stepField = field('Step you practised', 'learningStep', FIXTURE.steps.map(({ stepId, label }) => [stepId, label]));
  const resultField = field('Your report', 'learningResult', [['independent', 'Correct, without a hint'], ['assisted', 'Correct, with a hint'], ['retry', 'Needs another try']]);
  const recordButton = button('Record my result', 'record-outcome');
  const evidenceNote = node('p', 'learning-fineprint');
  evidenceCard.append(stepField.wrapper, resultField.wrapper, recordButton, evidenceNote);

  const futureCard = node('section', 'learning-control-card');
  futureCard.append(node('h3', null, 'Leave help for later'));
  const reminderField = field('Remind me when this is next', 'learningReminderStep', FIXTURE.steps.map(({ stepId, label }) => [stepId, label]));
  const reminderButton = button('Add contextual reminder', 'set-reminder');
  const recipientField = field('Prepare a specialist handoff', 'learningRecipient', [['taimi', 'Taimi · explain and practise'], ['meta', 'Meta · task context'], ['nvidia', 'NVIDIA · visual interpretation']]);
  const handoffButton = button('Preview handoff', 'handoff');
  const handoffOutput = node('div', 'learning-handoff');
  handoffOutput.id = 'learningHandoff';
  handoffOutput.hidden = true;
  futureCard.append(reminderField.wrapper, reminderButton, recipientField.wrapper, handoffButton, handoffOutput);
  controlsGrid.append(practiceCard, evidenceCard, futureCard);
  controls.append(controlsGrid);

  const status = node('p', 'learning-status');
  status.id = 'learningStatus';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const storageNote = node('p', 'learning-storage');
  storageNote.id = 'learningStorage';
  mount.replaceChildren(header, steps, grid, controls, status, storageNote);

  function announce(message, error = false) {
    status.textContent = message;
    status.classList.toggle('learning-error', error);
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session.exportState()));
      storageAvailable = true;
    } catch {
      storageAvailable = false;
    }
  }

  async function dispatch(operation, payload = {}) {
    const result = await session.dispatch({
      schema: 'lens.learning-command/v1', commandId: uid('command'),
      expectedRevision: session.snapshot().revision, operation, payload,
    }, { actor: 'user' });
    if (!result.ok) throw new Error(result.error?.code ?? 'LEARNING_COMMAND_REJECTED');
    persist();
    handoffProposal = null;
    recommendationKey = '';
    return result;
  }

  function currentTask() {
    const task = taskView();
    return { taskId: task.taskId, revision: task.revision, status: task.status, nextStepId: task.nextStepId };
  }

  function refreshRecommendation(requested = false) {
    const state = session.snapshot();
    const task = currentTask();
    const key = JSON.stringify([state.revision, state.memoryEpoch, task]);
    if (state.consent.enabled && state.episode) {
      if (requested || recommendationKey !== key || !recommendation || recommendation.binding.expiresAt <= Date.now()) {
        recommendation = session.recommend(task, { requested });
        recommendationKey = key;
      }
    } else {
      recommendation = null;
      recommendationKey = '';
    }
  }

  function renderMemory(state) {
    memoryList.replaceChildren();
    if (!state.memories.length) {
      const empty = node('p', 'learning-empty', 'No learned preference yet. Choose how you would like to be helped.');
      memoryList.append(empty);
    }
    for (const memory of state.memories) {
      const item = node('div', `learning-memory-item ${memory.status}`);
      item.dataset.memoryId = memory.id;
      item.dataset.memoryStatus = memory.status;
      const copy = node('div');
      copy.append(node('span', 'learning-memory-state', memory.status === 'active' ? 'APPROVED BY YOU' : 'WAITING FOR YOU'),
        node('strong', null, styleLabel(memory.style)),
        node('small', null, `Source: your teaching episode · version ${memory.version}`));
      const source = node('details', 'learning-memory-source');
      source.append(node('summary', null, 'View source'), node('code', null, memory.sourceEpisodeId));
      copy.append(source);
      const actions = node('div', 'learning-memory-actions');
      if (memory.status === 'proposed') {
        const confirm = button('Approve preference', 'approve-memory', 'secondary-button');
        confirm.dataset.memoryId = memory.id;
        confirm.disabled = busy || !state.consent.enabled;
        actions.append(confirm);
      }
      const forget = button('Forget', 'forget-memory', 'link-button learning-forget');
      forget.dataset.memoryId = memory.id;
      forget.disabled = busy;
      actions.append(forget);
      item.append(copy, actions);
      memoryList.append(item);
    }
    const active = state.memories.findLast((memory) => memory.status === 'active');
    const proposed = state.memories.some((memory) => memory.status === 'proposed');
    teachButton.textContent = active ? 'Correct preference' : 'Suggest this preference';
    teachButton.disabled = busy || !state.consent.enabled || !state.episode || proposed;
    styleField.select.disabled = busy || !state.consent.enabled || proposed;
    forgetButton.disabled = busy || !state.memories.length && !state.outcomes.length && !state.feedback.length && !state.reminders.length && !state.checkpoint;
  }

  function renderAdvice(state) {
    const task = currentTask();
    adviceTitle.dataset.learningRecommendation = recommendation?.action ?? 'off';
    if (!recommendation) {
      adviceTitle.textContent = 'A preference starts with you.';
      adviceText.textContent = 'Start this synthetic learning demo, then teach Lens how much help you want. Your packing progress stays under your control.';
    } else {
      const next = stepLabel(recommendation.nextStepId);
      const copy = {
        one_step: [`One next step: ${next.toLowerCase()}.`, 'Check the item, then use the packing controls above to confirm it.'],
        explain: [`Take a moment with ${next.toLowerCase()}.`, 'Think through what this step is for and what you need to check. Ask for an explanation when it would help.'],
        ask_one_question: ['One check before you continue.', 'What is the next unfinished step? Confirm your place in the task before acting on a suggestion.'],
        stay_silent: [task.status === 'completed' ? 'You have this moment covered.' : 'Room to do it your way.', task.status === 'completed' ? 'Your confirmations completed this task. Start another episode when you want to practise again.' : 'Lens is holding back. You can ask for the next step whenever you want.'],
      }[recommendation.action];
      adviceTitle.textContent = copy?.[0] ?? 'A suggestion needs another check.';
      adviceText.textContent = copy?.[1] ?? 'No task progress has changed.';
    }
    adviceMeta.textContent = state.episode
      ? `${state.goal === 'learn' ? 'Learning together' : 'Getting it done'} · ${TEMPLATES.find(([value]) => value === state.episode.templateId)?.[1] ?? 'Synthetic practice'} · revision ${state.revision}`
      : 'No learning episode active';
    reminderNote.hidden = !recommendation?.reminderId;
    if (recommendation?.reminderId) reminderText.textContent = `Your reminder: pause and check ${stepLabel(recommendation.nextStepId).toLowerCase()}.`;
    checkpointNote.textContent = state.checkpoint
      ? `Saved place: ${state.checkpoint.nextStepId ? stepLabel(state.checkpoint.nextStepId) : 'all steps confirmed'} · task revision ${state.checkpoint.taskRevision}.`
      : 'Save your place, use Pause above, then return for a fresh suggestion.';
    const hasProposal = Boolean(recommendation?.proposalId);
    usefulButton.disabled = busy || !hasProposal;
    distractingButton.disabled = busy || !hasProposal;
    ackButton.disabled = busy || !recommendation?.reminderId;
  }

  function renderHandoff() {
    handoffOutput.replaceChildren();
    handoffOutput.hidden = !handoffProposal;
    if (!handoffProposal) return;
    handoffOutput.append(node('strong', null, 'Proposed handoff · not sent'),
      node('p', null, `${handoffProposal.recipient}: ${handoffProposal.goal === 'learn' ? 'help explain and practise' : 'help with the next step'}.`),
      node('p', null, `Next: ${stepLabel(handoffProposal.nextStepId)}. Only task context is included; your learned preferences stay here.`));
  }

  function update() {
    const state = session.snapshot();
    const task = currentTask();
    if (handoffProposal && (handoffProposal.context.taskId !== task.taskId ||
        handoffProposal.context.taskRevision !== task.revision || handoffProposal.goal !== state.goal)) {
      handoffProposal = null;
    }
    try { refreshRecommendation(); } catch { recommendation = null; announce('The current task could not be used for a learning suggestion.', true); }
    const enabled = state.consent.enabled && Boolean(state.episode);
    consentButton.textContent = state.consent.enabled && state.episode ? 'Pause learning' : 'Start learning demo';
    consentButton.disabled = busy;
    badge.textContent = state.consent.enabled ? 'SYNTHETIC · LEARNING ON' : 'SYNTHETIC · LEARNING OFF';
    goalField.select.value = state.goal;
    goalField.select.disabled = busy || !enabled;
    templateField.select.disabled = busy || !enabled;
    stepField.select.disabled = busy || !enabled;
    resultField.select.disabled = busy || !enabled;
    reminderField.select.disabled = busy || !enabled;
    recipientField.select.disabled = busy || !enabled;
    for (const item of [askButton, checkpointButton, nextButton, recordButton, reminderButton, handoffButton]) item.disabled = busy || !enabled;
    renderMemory(state);
    renderAdvice(state);
    renderHandoff();
    const correct = state.outcomes.filter((item) => item.correct && item.hints === 0);
    const independent = new Set(correct.map((item) => `${item.stepId}:${item.templateId}`)).size;
    const assisted = state.outcomes.filter((item) => item.hints > 0).length;
    evidenceNote.textContent = `${independent} independent step/scene record${independent === 1 ? '' : 's'} · ${assisted} assisted attempt${assisted === 1 ? '' : 's'}. These are your reports in a synthetic demo, not verified mastery.`;
    storageNote.textContent = storageAvailable
      ? `${restored ? 'Restored learning. ' : ''}Synthetic learning stays in this browser. No camera, personal account or specialist is connected.`
      : 'Browser storage is unavailable. This learning session may be lost when you leave.';
  }

  async function perform(action, source) {
    if (busy) return;
    const selectedValue = source?.value;
    busy = true;
    update();
    try {
      const state = session.snapshot();
      if (action === 'consent') {
        const starting = !state.consent.enabled || !state.episode;
        if (!state.consent.enabled || !starting) await dispatch('setConsent', { enabled: starting });
        if (starting && !session.snapshot().episode) {
          await dispatch('startEpisode', { episodeId: uid('episode'), templateId: templateField.select.value });
        }
        announce(starting ? 'Learning is on for this synthetic camera-bag context. Choose a preference to teach.' : 'Learning paused. Saved preferences will not be used while it is off.');
      } else if (action === 'teach') {
        const active = state.memories.findLast((memory) => memory.status === 'active');
        await dispatch(active ? 'correctMemory' : 'proposeMemory', active
          ? { memoryId: active.id, style: styleField.select.value }
          : { memoryId: uid('memory'), style: styleField.select.value });
        announce(active ? 'Preference corrected. The next suggestion uses your change.' : 'Preference proposed. Review it and choose Approve preference.');
      } else if (action === 'approve-memory') {
        await dispatch('confirmMemory', { memoryId: source.dataset.memoryId });
        announce('Preference approved for this context. Try pausing and returning to your task.');
      } else if (action === 'forget-memory') {
        await dispatch('forgetMemory', { memoryId: source.dataset.memoryId });
        announce('That preference has been forgotten.');
      } else if (action === 'forget-all') {
        await dispatch('forgetAll');
        announce('Learned preferences and derived learning state have been cleared. Your packing confirmations stay in the task.');
      } else if (action === 'ask') {
        refreshRecommendation(true);
        announce('A fresh suggestion is ready. Your task progress is unchanged.');
      } else if (action === 'checkpoint') {
        const task = currentTask();
        await dispatch('checkpoint', { taskId: task.taskId, taskRevision: task.revision, nextStepId: task.nextStepId });
        announce('Your place is saved. Use Pause task above, then return when you are ready.');
      } else if (action === 'useful' || action === 'distracting') {
        if (!recommendation?.proposalId) throw new Error('NO_CURRENT_PROPOSAL');
        await dispatch('recordFeedback', { proposalId: recommendation.proposalId, value: action });
        announce(action === 'useful' ? 'Feedback saved: this amount of help was useful.' : 'Feedback saved: give this context more space.');
      } else if (action === 'goal') {
        await dispatch('setGoal', { goal: selectedValue });
        announce('Goal updated. Suggestions will follow your current goal.');
      } else if (action === 'next-episode') {
        await dispatch('startEpisode', { episodeId: uid('episode'), templateId: templateField.select.value });
        await resetTask();
        announce('A new episode is ready. Your approved preferences carried forward.');
      } else if (action === 'record-outcome') {
        await dispatch('recordOutcome', { stepId: stepField.select.value, correct: resultField.select.value !== 'retry', hints: resultField.select.value === 'assisted' ? 1 : 0 });
        announce('Your practice report is recorded separately from packing progress.');
      } else if (action === 'set-reminder') {
        await dispatch('setReminder', { reminderId: uid('reminder'), stepId: reminderField.select.value });
        announce('Reminder saved for when that step is next.');
      } else if (action === 'ack-reminder') {
        if (!recommendation?.reminderId) throw new Error('NO_CURRENT_REMINDER');
        await dispatch('ackReminder', { reminderId: recommendation.reminderId });
        announce('Reminder acknowledged.');
      } else if (action === 'handoff') {
        handoffProposal = session.handoff(recipientField.select.value, currentTask());
        announce('Handoff prepared for review. It has not been sent to a specialist.');
      }
      onChange(session.snapshot());
    } catch (error) {
      const code = typeof error?.message === 'string' && /^[A-Z0-9_]{1,80}$/.test(error.message) ? ` (${error.message})` : '';
      announce(`This learning action could not be applied${code}. Read the current state and try again.`, true);
    } finally {
      busy = false;
      update();
    }
  }

  mount.addEventListener('click', (event) => {
    const source = event.target.closest?.('[data-learning-action]');
    if (source && mount.contains(source) && !source.disabled) void perform(source.dataset.learningAction, source);
  });
  goalField.select.addEventListener('change', () => void perform('goal', goalField.select));
  update();
  if (restoreMessage) announce(restoreMessage, true);
  else if (restored) announce('Your previous synthetic learning state was restored.');
  return {
    update,
    invalidateTask() {
      session.invalidateProposals();
      recommendation = null;
      recommendationKey = '';
      handoffProposal = null;
    },
    exportState: () => session.exportState(),
  };
}
