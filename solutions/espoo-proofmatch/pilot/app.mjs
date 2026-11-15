import { createScenario, applyCommand, reviewSession, PEOPLE, OPTIONS } from './outcomes.mjs';

const $ = id => document.getElementById(id);
let state = createScenario();
const formatLabels = { 'in-person': 'In person', online: 'Online', hybrid: 'Hybrid' };
const guidance = {
  'in-person': 'At a fictional table, make room for each person to speak and ask before taking notes.',
  online: 'In a fictional call, check that both people can participate. Offer a pause if audio or access gets in the way.',
  hybrid: 'With one person remote, give them an equal turn. Check that neither side misses the other’s question.',
};
const progressText = {
  accepted: 'Accepted fictional scenario. Simulate the conversation before recording any acknowledgement.',
  'awaiting-acknowledgements': 'Waiting for two separate simulated acknowledgements. One person cannot supply both with one action.',
  'awaiting-choices': 'Both acknowledged. Each person now decides independently whether to share a reflection.',
  'awaiting-reflections': 'Sharing choices recorded. A reflection is still missing from someone who accepted sharing.',
  'ready-for-review': 'Both fictional reflections are available for review. No real-world outcome has been established.',
  'closed-without-reciprocal-evidence': 'Choices recorded. Reciprocal reflection evidence is unavailable because sharing was declined.',
  'sharing-withdrawn': 'Reflection sharing was revoked. Reciprocal evidence is unavailable; the withdrawn reflection is removed.',
  deleted: 'Active simulated session deleted. Start a new fictional scenario to continue.',
};

function selectMarkup(key, id) {
  return `<select id="${id}-${key}" name="${key}" required><option value="">Choose your fictional reflection</option>${Object.entries(OPTIONS[key]).map(([value, text]) => `<option value="${value}">${text}</option>`).join('')}</select>`;
}
// Templates contain only authored fixture text. Reflections are rendered via textContent.
$('voices').innerHTML = PEOPLE.map(({ id, name, context }) => `
  <article class="voice" aria-labelledby="${id}-title">
    <p class="eyebrow">SIMULATED participant controls</p><h3 id="${id}-title">Simulate ${name}</h3>
    <p class="voice-context">${context}. Fictional person; no sign-in.</p>
    <p id="${id}-state" class="voice-state"></p>
    <form id="${id}-ack-form" autocomplete="off"><fieldset id="${id}-ack-controls"><legend>Conversation acknowledgement</legend>
      <label class="check"><input id="${id}-ack" type="checkbox" required> In this simulation, ${name} explicitly acknowledges that the conversation took place.</label>
      <button type="submit" class="secondary">Record ${name}’s acknowledgement</button>
    </fieldset></form>
    <form id="${id}-consent-form" autocomplete="off"><fieldset id="${id}-consent-controls"><legend>Independent reflection-sharing choice</legend>
      <p class="small">Accept only shares ${name}’s reflection in this tab’s review. Declining is equally valid and says nothing about ${name}’s ability.</p>
      <label class="check"><input id="${id}-consent" type="checkbox" required> I am explicitly simulating ${name}’s own choice for this purpose.</label>
      <div class="button-row"><button type="submit" name="decision" value="accepted">Accept sharing</button><button type="submit" name="decision" value="declined" class="secondary">Decline sharing</button></div>
    </fieldset></form>
    <form id="${id}-reflection-form" autocomplete="off"><fieldset id="${id}-reflection-controls"><legend>${name}’s own words, through fictional choices</legend>
      <p class="small">Use only the authored choices. No real-person details, scores or inferred proficiency.</p>
      <label for="${id}-takeaway">What came from the conversation?</label>${selectMarkup('takeaway', id)}
      <label for="${id}-nextStep">What would I choose next?</label>${selectMarkup('nextStep', id)}
      <label for="${id}-support">What would help me?</label>${selectMarkup('support', id)}
      <button type="submit">Record ${name}’s fictional reflection</button>
    </fieldset></form>
    <form id="${id}-revoke-form" class="revoke" autocomplete="off"><fieldset id="${id}-revoke-controls"><legend>Withdraw ${name}’s sharing</legend>
      <label class="check"><input id="${id}-revoke" type="checkbox" required> Revoke ${name}’s accepted sharing and remove their reflection from the active session.</label>
      <button type="submit" class="danger">Revoke ${name}’s sharing</button>
    </fieldset></form>
  </article>`).join('');

function focus(id) { const element = $(id); if (element && !element.disabled) element.focus(); }
function dispatch(command, message, focusId) {
  try {
    state = applyCommand(state, { ...command, expectedVersion: state.version, simulation: 'SIMULATED' });
    render();
    $('notice').textContent = `SIMULATED · ${message}`;
    if (focusId) focus(focusId);
  } catch (error) { $('notice').textContent = error.message; }
}

for (const { id, name } of PEOPLE) {
  $(`${id}-ack-form`).addEventListener('submit', event => {
    event.preventDefault();
    const other = state.participants.find(p => p.id !== id);
    dispatch({ type: 'acknowledge', actorId: id, confirmed: $(`${id}-ack`).checked }, `${name}’s acknowledgement recorded; sharing is a separate choice.`, other?.acknowledged ? `${id}-consent` : `${other?.id}-ack`);
  });
  $(`${id}-consent-form`).addEventListener('submit', event => {
    event.preventDefault();
    const decision = event.submitter?.value;
    dispatch({ type: 'consent', actorId: id, decision, confirmed: $(`${id}-consent`).checked }, `${name} ${decision === 'accepted' ? 'accepted' : 'declined'} fictional reflection sharing.`, decision === 'accepted' ? `${id}-takeaway` : 'review-title');
  });
  $(`${id}-reflection-form`).addEventListener('submit', event => {
    event.preventDefault();
    const reflection = Object.fromEntries(Object.keys(OPTIONS).map(key => [key, $(`${id}-${key}`).value]));
    dispatch({ type: 'reflect', actorId: id, reflection }, `${name}’s fictional reflection recorded. No follow-up action was taken.`, 'review-title');
  });
  $(`${id}-revoke-form`).addEventListener('submit', event => {
    event.preventDefault();
    dispatch({ type: 'revoke', actorId: id, confirmed: $(`${id}-revoke`).checked }, `${name}’s sharing revoked. Their reflection was removed from the active session.`, 'review-title');
    if (state.participants.find(p => p.id === id)?.consent === 'revoked') {
      $(`${id}-reflection-form`).reset();
      $(`${id}-consent-form`).reset();
      $(`${id}-revoke-form`).reset();
    }
  });
}
$('end-form').addEventListener('submit', event => {
  event.preventDefault();
  dispatch({ type: 'end-conversation', confirmed: $('end-confirm').checked }, 'Conversation end simulated. Each person must now acknowledge separately.', `${PEOPLE[0].id}-ack`);
});
$('scenario-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!$('restart-confirm').checked) return;
  state = createScenario($('mode').value);
  clearInputs(); render();
  $('notice').textContent = 'SIMULATED · New fictional scenario. Previous active session replaced; nothing was saved.';
  focus('end-confirm');
});
$('delete-form').addEventListener('submit', event => {
  event.preventDefault();
  dispatch({ type: 'delete', confirmed: $('delete-confirm').checked }, 'Active meeting and participant records deleted. No persistent copy was created.', 'mode');
  if (state.phase === 'deleted') clearInputs();
});

function clearInputs() {
  for (const form of document.querySelectorAll('form')) if (form.id !== 'scenario-form') form.reset();
  $('restart-confirm').checked = false;
}
function addText(tag, text, parent) {
  const element = document.createElement(tag); element.textContent = text; parent.append(element); return element;
}
function render() {
  const review = reviewSession(state);
  const deleted = state.phase === 'deleted';
  const bothAck = !deleted && state.participants.every(p => p.acknowledged);
  $('format-label').textContent = `SIMULATED · ${formatLabels[state.mode]}`;
  $('format-guidance').textContent = guidance[state.mode];
  $('progress').textContent = progressText[review.label];
  $('end-form').hidden = state.phase !== 'accepted';
  $('voices').hidden = deleted;
  $('delete-form').hidden = deleted;
  const step = deleted ? 'step-review' : state.phase === 'accepted' ? 'step-before' : !bothAck ? 'step-during' :
    ['ready-for-review', 'closed-without-reciprocal-evidence', 'sharing-withdrawn'].includes(review.label) ? 'step-review' : 'step-after';
  for (const li of document.querySelectorAll('.steps li')) {
    if (li.id === step) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  }
  for (const person of state.participants) {
    const id = person.id;
    $(`${id}-state`).textContent = `${person.acknowledged ? 'Acknowledged' : 'Not acknowledged'} · Reflection sharing: ${person.consent}${person.reflection ? ' · Reflection recorded' : ''}`;
    $(`${id}-ack-controls`).disabled = state.phase !== 'ended' || person.acknowledged;
    $(`${id}-consent-controls`).disabled = !bothAck || person.consent !== 'pending';
    $(`${id}-reflection-controls`).disabled = person.consent !== 'accepted' || person.reflection !== null;
    $(`${id}-revoke-controls`).disabled = person.consent !== 'accepted';
  }
  if (deleted) for (const { id } of PEOPLE) {
    $(`${id}-state`).textContent = 'No active simulated record.';
    for (const section of ['ack', 'consent', 'reflection', 'revoke']) $(`${id}-${section}-controls`).disabled = true;
  }
  $('review-summary').textContent = review.reciprocalEvidence
    ? review.nextSteps === 'same-choice'
      ? 'Both fictional reflections are available. The next-step choices match; no action is scheduled and usefulness is not proven.'
      : 'Both fictional reflections are available. The next-step choices differ. Leave that difference open; neither person is ranked or overruled.'
    : `${progressText[review.label]} No reciprocal conclusion can be drawn.`;
  const container = $('shared-reflections'); container.replaceChildren();
  if (!deleted) for (const { id, name } of PEOPLE) {
    const item = document.createElement('div'); item.className = 'shared-item';
    addText('h3', `${name} · SIMULATED`, item);
    const shared = review.shared.find(p => p.actorId === id);
    const person = state.participants.find(p => p.id === id);
    if (shared) {
      const list = document.createElement('dl');
      for (const [key, label] of [['takeaway', 'My reflection'], ['nextStep', 'My next-step choice'], ['support', 'What would help me']]) {
        addText('dt', label, list); addText('dd', OPTIONS[key][shared.reflection[key]], list);
      }
      item.append(list);
    } else addText('p', person.consent === 'revoked' ? 'Sharing revoked. Reflection removed.' : person.consent === 'declined' ? 'Sharing declined. No reflection recorded.' : 'No shared reflection yet.', item);
    container.append(item);
  }
}
$('review-title').tabIndex = -1;
// Avoid leaving form values or conversation records in the browser's back/forward page cache.
window.addEventListener('pagehide', () => {
  state = createScenario();
  $('mode').value = state.mode;
  clearInputs(); render();
  $('notice').textContent = '';
});
clearInputs();
render();
