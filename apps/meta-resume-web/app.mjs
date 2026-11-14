import { FIXTURE, id } from './fixture.mjs';
import { createSession, restoreSession } from './state.mjs';
import { registerResumeTools } from './webmcp.mjs';

const $ = (selector) => document.querySelector(selector);
const STORAGE_KEY = 'chibi-resume.synthetic.camera-bag-v1';
let session = createSession();
let candidateVisible = false;
let storageAvailable = true;
let restored = false;
let pendingConfirmation = null;
let toastTimer;

try {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) {
    if (raw.length > 150_000) throw new Error('Demo journal too large');
    const saved = JSON.parse(raw);
    if (saved?.version !== 1 || typeof saved.candidateVisible !== 'boolean') throw new Error('Unsupported demo save');
    session = restoreSession(saved.journal);
    candidateVisible = saved.candidateVisible;
    restored = true;
  }
} catch { storageAvailable = false; }

if (new URLSearchParams(location.search).get('display') === '1') {
  document.body.classList.add('compact');
  const returnLink = document.createElement('a');
  returnLink.href = './';
  returnLink.className = 'compact-return';
  returnLink.textContent = 'Full context + controls ↗';
  document.body.append(returnLink);
}

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, journal: session.exportJournal(), candidateVisible }));
    storageAvailable = true;
  } catch { storageAvailable = false; }
}

function toast(message) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 6500);
}

function command(operation, payload = {}) {
  return {
    schemaVersion: 1, taskId: FIXTURE.taskId, commandId: crypto.randomUUID(),
    expectedRevision: session.snapshot().revision, operation, payload,
  };
}

/** The UI and optional assistant tools both enter this same path. */
function dispatch(input, options = { authority: 'ui' }) {
  const result = session.dispatch(input, options);
  if (!result.error) persist();
  render();
  return result;
}

function run(operation, payload = {}) {
  const result = dispatch(command(operation, payload));
  if (result.error) toast(result.message);
  return result;
}

function setAction(element, action, label, disabled = false) {
  element.dataset.action = action;
  element.textContent = label;
  element.disabled = disabled;
}

function card(kind, label, title, description) {
  const node = document.createElement('div');
  node.className = `evidence-item ${kind}`;
  const tag = document.createElement('span');
  tag.className = 'evidence-type'; tag.textContent = label;
  const heading = document.createElement('h3'); heading.textContent = title;
  const text = document.createElement('p'); text.textContent = description;
  node.append(tag, heading, text);
  return node;
}

function render() {
  const state = session.snapshot();
  const policy = session.getPolicy();
  const events = session.getEvents();
  const count = state.steps.filter((step) => step.userConfirmed).length;
  const next = FIXTURE.steps.find((step) => step.stepId === state.nextUnconfirmedStep);
  const nextIndex = FIXTURE.steps.findIndex((step) => step.stepId === state.nextUnconfirmedStep);
  const interrupted = state.status === 'interrupted';
  const completed = state.status === 'completed';
  const wasInterrupted = events.some((event) => event.operation === 'interrupt');
  const hasProposal = Boolean(state.proposal);
  const primary = $('#primaryAction'), secondary = $('#secondaryAction');

  $('#countBadge').replaceChildren(document.createTextNode(String(count)));
  const total = document.createElement('span'); total.textContent = '/3'; $('#countBadge').append(total);
  $('.segments').setAttribute('aria-label', `${count} of 3 steps confirmed by you`);
  document.querySelectorAll('.segments>span').forEach((segment, index) => segment.classList.toggle('filled', state.steps[index].userConfirmed));
  document.querySelectorAll('.scene-item').forEach((item, index) => {
    item.classList.toggle('packed', state.steps[index].userConfirmed);
    item.classList.toggle('current', index === nextIndex || completed);
  });
  $('#phaseLabel').textContent = completed ? 'CONFIRMED BY YOU' : interrupted ? 'PAUSED · PROGRESS SAVED' : hasProposal ? 'A PROPOSAL, NOT A CLAIM' : 'READY WHEN YOU ARE';
  $('#taskStatus').textContent = `${completed ? 'All packed' : interrupted ? 'Paused' : 'In progress'} · revision ${state.revision}`;
  $('#nextNumber').textContent = completed ? '✓' : String(nextIndex + 1).padStart(2, '0');
  $('#nextLabel').textContent = completed ? 'CONFIRMED BY YOU' : hasProposal ? 'PROPOSED NEXT STEP' : interrupted ? 'WAITING FOR YOU' : 'NEXT TO PACK';
  $('#nextItem').textContent = completed ? 'Ready to go' : next.label;
  $('#nextPill').className = `state-pill${completed ? ' complete' : candidateVisible && nextIndex === 2 ? ' observed' : ''}`;
  $('#nextPill').textContent = completed ? '3 of 3 packed' : candidateVisible && nextIndex === 2 ? 'Identity still uncertain' : 'Needs your confirmation';

  if (completed) {
    $('#momentTitle').textContent = 'You’re good to go.';
    $('#momentDescription').textContent = 'Three essentials, confirmed by you. One less thing to keep in your head.';
    $('#contextText').textContent = 'Your confirmations completed the task. No observation or assistant proposal marked an item packed.';
    setAction(primary, 'reset', 'Try the moment again ↗');
    setAction(secondary, 'correct-last', 'Correct a step');
  } else if (interrupted) {
    $('#momentTitle').textContent = 'Your place is saved.';
    $('#momentDescription').textContent = `${count} of 3 essentials confirmed. Take your time — the next step will still be here.`;
    $('#contextText').textContent = count === 2 ? 'Your charger was last observed on the desk at 11:00 in this fixture. That is history, not its current location.' : 'The task remembers your confirmations. It does not guess what you did while away.';
    setAction(primary, policy.captureEnabled ? 'look' : 'resume', policy.captureEnabled ? 'Look again & resume ↗' : 'Resume without observations ↗');
    setAction(secondary, 'resume', 'Resume without looking');
  } else if (hasProposal) {
    $('#momentTitle').textContent = nextIndex === 2 ? 'Just your charger left.' : `Next: ${next.label.toLowerCase()}.`;
    $('#momentDescription').textContent = nextIndex === 2 ? 'Camera and microphone are confirmed. Check your own charger, then put it in the bag.' : 'Continue from the first step you have not confirmed.';
    $('#contextText').textContent = candidateVisible && nextIndex === 2 ? 'The fresh white charger is a lookalike. It was rejected as evidence for your item. Check the physical charger yourself.' : 'This next step follows your confirmed progress. It has no current identity evidence attached.';
    setAction(primary, 'confirm', `Confirm ${nextIndex === 2 ? 'my charger' : next.label.toLowerCase()} packed ↗`);
    setAction(secondary, 'pause', 'Pause again');
  } else if (count === 2 && !wasInterrupted) {
    $('#momentTitle').textContent = 'Two things packed.';
    $('#momentDescription').textContent = 'Then life interrupts. Try stepping away before packing the last item.';
    $('#contextText').textContent = 'The camera and microphone are confirmed. Your charger is still unfinished — even if it was seen earlier.';
    setAction(primary, 'pause', 'Simulate an interruption ↗');
    setAction(secondary, 'confirm', 'Pack charger now');
  } else {
    $('#momentTitle').textContent = nextIndex === 0 ? 'Start with your camera.' : nextIndex === 1 ? 'Your microphone is next.' : 'One last thing.';
    $('#momentDescription').textContent = nextIndex === 0 ? 'Three essentials. You decide when each one is packed.' : next.detail;
    $('#contextText').textContent = !policy.captureEnabled ? 'Observations are stopped. Your existing confirmations remain; local controls still work.' : 'Seeing an item is not the same as packing it. Only your confirmation completes this step.';
    setAction(primary, 'confirm', `Confirm ${nextIndex === 2 ? 'my charger' : next.label.toLowerCase()} packed ↗`);
    setAction(secondary, 'pause', 'Pause task');
  }

  const list = $('#packingList'); list.replaceChildren();
  state.steps.forEach((step, index) => {
    const row = document.createElement('li');
    const circle = document.createElement('span'); circle.className = `check-circle${step.userConfirmed ? ' done' : ''}`;
    circle.textContent = step.userConfirmed ? '✓' : String(index + 1); circle.setAttribute('aria-hidden', 'true');
    const body = document.createElement('div'); body.className = 'packing-item';
    const title = document.createElement('strong'); title.textContent = step.label;
    const detail = document.createElement('small'); detail.className = step.userConfirmed ? 'done' : '';
    detail.textContent = step.userConfirmed ? 'Packed · confirmed by you' : state.proposal?.stepId === step.stepId ? 'Proposed · waiting for your confirmation' : index === nextIndex ? 'Not yet confirmed' : 'Still to pack';
    body.append(title, detail); row.append(circle, body);
    if (step.userConfirmed) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'correct-button';
      button.textContent = 'Correct'; button.dataset.action = 'correct'; button.dataset.step = step.stepId;
      button.setAttribute('aria-label', `Correct ${step.label} confirmation`); row.append(button);
    }
    list.append(row);
  });

  const evidence = $('#evidenceSummary'); evidence.replaceChildren();
  if (count) evidence.append(card('confirmed', 'CONFIRMED BY YOU', state.steps.filter((step) => step.userConfirmed).map((step) => step.label).join(' + '), `${count} ${count === 1 ? 'item' : 'items'} marked packed by an explicit user confirmation.`));
  if (wasInterrupted) evidence.append(card('observed', 'OBSERVED ONLY · 11:00 · FIXTURE', 'Your charger was on the desk.', 'Historical observation from an older capture generation. Current location is unknown.'));
  if (candidateVisible) evidence.append(card('observed', 'FRESH LOOKALIKE · 11:59:30 · FIXTURE', 'Similar does not mean yours.', 'A different white charger. Rejected as task evidence; it cannot complete or verify your step.'));
  if (hasProposal) evidence.append(card('proposed', 'PROPOSED · NOT COMPLETED', `Check and pack ${next.label.toLowerCase()}.`, 'Chosen from your confirmed progress, with no identity evidence attached. You make the final check.'));
  if (!count && !wasInterrupted) {
    const empty = document.createElement('div'); empty.className = 'empty-evidence';
    const icon = document.createElement('span'); icon.textContent = '⌁'; icon.setAttribute('aria-hidden', 'true');
    const note = document.createElement('p'); note.textContent = 'Your confirmations will appear here.'; empty.append(icon, note); evidence.append(empty);
  }
  const history = $('#eventHistory'); history.replaceChildren();
  events.forEach((event) => {
    const item = document.createElement('li');
    const step = FIXTURE.steps.find((entry) => entry.stepId === event.stepId);
    const words = {
      confirmStep: `${step?.label} confirmed by you`,
      interrupt: 'Task paused; confirmed progress retained',
      resume: 'Next step proposed; no completion recorded',
      observe: 'Synthetic exact-identity observation admitted; no completion recorded',
      correctStep: `${step?.label} corrected; this and later confirmations cleared`,
      revokeEvidence: 'Observation revoked',
      revokeCapture: 'Fixture capture stopped; generation advanced',
    };
    item.textContent = `r${event.revision} · ${words[event.operation]}`; history.append(item);
  });
  if (!events.length) { const empty = document.createElement('li'); empty.textContent = 'No commands yet.'; history.append(empty); }
  $('#captureStatus').textContent = policy.captureEnabled ? 'Synthetic observations enabled' : `Observations revoked · generation ${policy.captureGeneration}`;
  $('#revokeButton').disabled = !policy.captureEnabled;
  $('#revokeButton').textContent = policy.captureEnabled ? 'Revoke' : 'Revoked';
  $('#surfaceConnection').textContent = policy.captureEnabled ? 'Glasses disconnected · local controls available' : 'Observations stopped · confirmations preserved';
  $('#storageNote').textContent = storageAvailable ? 'Progress stays in this browser. No uploads.' : 'Storage unavailable or save invalid. Current progress is in memory only.';
  $('#chapter1').className = count >= 2 ? 'done' : 'active';
  $('#chapter2').className = wasInterrupted ? 'done' : count >= 2 ? 'active' : '';
  $('#chapter3').className = candidateVisible ? 'done' : interrupted ? 'active' : '';
  $('#chapter4').className = completed ? 'done' : hasProposal ? 'active' : '';
  document.documentElement.dataset.revision = String(state.revision);
  document.documentElement.dataset.taskStatus = state.status;
}

function requestConfirmation() {
  const state = session.snapshot();
  const step = FIXTURE.steps.find((item) => item.stepId === state.nextUnconfirmedStep);
  if (!step || state.status !== 'active') return;
  pendingConfirmation = command('confirmStep', { stepId: step.stepId });
  $('#confirmTitle').textContent = `${step.label} packed?`;
  $('#confirmDescription').textContent = step.stepId === id(203) ? 'A similar charger or an old sighting cannot answer this. Check the physical item and your bag.' : 'Check the physical item and your bag. An observation alone cannot complete this step.';
  $('#confirmCheckboxText').textContent = step.stepId === id(203) ? 'I checked that this is my charger and put it in the bag.' : `I checked my ${step.label.toLowerCase()} and put it in the bag.`;
  $('#confirmCheckbox').checked = false;
  $('#commitConfirmation').disabled = true;
  $('#confirmDialog').showModal();
}

function act(action, button) {
  if (action === 'confirm') return requestConfirmation();
  if (action === 'pause') {
    if (!run('interrupt').error) toast('Paused. Your confirmed progress is saved in this browser.');
  } else if (action === 'look') {
    if (!session.getPolicy().captureEnabled) return toast('Observations are revoked. You can resume without looking.');
    const result = dispatch(command('observe', { evidenceId: id(502) }));
    if (result.code !== 'SUBJECT_MISMATCH') return toast(result.message ?? 'Unexpected fixture result.');
    candidateVisible = true;
    if (!run('resume', { evidenceIds: [] }).error) toast('The lookalike was rejected. Your next step is still yours to check.');
    persist(); render();
  } else if (action === 'resume') {
    if (!run('resume', { evidenceIds: [] }).error) toast('Resumed from your last confirmed progress. No item was marked packed.');
  } else if (action === 'correct' || action === 'correct-last') {
    const stepId = action === 'correct-last' ? id(203) : button.dataset.step;
    if (!run('correctStep', { stepId }).error) toast('Correction saved. This step and later confirmations need checking again.');
    $('#primaryAction').focus();
  } else if (action === 'revoke') {
    session.revokeCapture(); persist(); render();
    toast('Observations revoked. Late results are fenced out; your confirmations remain.');
  } else if (action === 'reset') {
    session = createSession(); candidateVisible = false; persist(); render();
    toast('A fresh local camera-bag demo is ready.');
    $('#primaryAction').focus();
  }
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (button && !button.disabled) act(button.dataset.action, button);
});
$('#confirmCheckbox').addEventListener('change', () => { $('#commitConfirmation').disabled = !$('#confirmCheckbox').checked; });
$('#confirmDialog').addEventListener('close', () => {
  if ($('#confirmDialog').returnValue === 'confirm' && $('#confirmCheckbox').checked && pendingConfirmation) {
    const result = dispatch(pendingConfirmation);
    toast(result.error ? result.message : 'Packed — confirmed by you.');
  }
  pendingConfirmation = null;
  $('#confirmDialog').returnValue = '';
  $('#primaryAction').focus();
});
$('#historyToggle').addEventListener('click', () => {
  const expanded = $('#historyToggle').getAttribute('aria-expanded') === 'true';
  $('#historyToggle').setAttribute('aria-expanded', String(!expanded));
  $('#historyPanel').hidden = expanded;
});

render();
if (restored) toast('Your local demo progress is restored. No account or device was contacted.');
const cleanup = registerResumeTools(document, {
  read: () => session.snapshot(), dispatch,
  onStatus: (status) => {
    $('#voiceStatus').textContent = ({ unavailable: 'Unavailable in this browser', registered: 'Native surface detected · unqualified', failed: 'Registration failed · controls still work' })[status];
  },
});
window.addEventListener('pagehide', cleanup, { once: true });
