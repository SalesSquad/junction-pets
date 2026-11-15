import {importReceipt, gates, declareDecision, serializeDeclaration, SOURCE, MAX_BYTES, REQUIREMENT, LIMITS} from './review.mjs';
const $ = id => document.getElementById(id);
let model = null, generation = 0;
function message(text, error = false) { $('message').textContent = text; $('message').dataset.error = String(error); }
function clear() {
  generation++; model = null; $('review').hidden = true; $('decision-form').reset();
  for (const id of ['literal', 'identity', 'gates', 'limits']) $(id).replaceChildren();
  $('review-status').textContent = 'REVIEW REQUIRED / NOT VERIFIED';
}
function textNode(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
$('clear').addEventListener('click', () => { clear(); $('receipt').value = ''; message('Local review cleared. Choose the original fixture to begin.'); $('receipt').focus(); });
$('receipt').addEventListener('change', async () => {
  clear(); const token = generation, file = $('receipt').files[0];
  if (!file) { message('Choose the original fixture to begin.'); return; }
  message('Checking exact file bytes…');
  try {
    if (file.size > MAX_BYTES) throw new Error('File exceeds 256 KiB. Choose the original public sample.');
    const imported = await importReceipt(new Uint8Array(await file.arrayBuffer()));
    if (token !== generation) return;
    model = imported;
    $('requirement').textContent = REQUIREMENT;
    const v = model.value;
    for (const [name, value] of [['Case ID', v.caseId], ['Base revision', v.repository.baseSha], ['Head revision', v.repository.headSha], ['SDK / target', `${v.environment.sdkVersion} / ${v.environment.runtimeTarget}`], ['Compatibility mode', `compatibilityExperiment: ${v.environment.compatibilityExperiment}; originalSdkExecuted: ${v.environment.originalSdkExecuted}`], ['Imported SHA256', model.digest], ['Source snapshot', SOURCE.commit]]) {
      $('identity').append(textNode('dt', name), textNode('dd', value));
    }
    for (const [name, state, evidence] of gates(model)) {
      const row = document.createElement('tr'); const status = textNode('td', state); status.dataset.status = state;
      row.append(textNode('th', name), status, textNode('td', evidence)); row.firstChild.scope = 'row'; $('gates').append(row);
    }
    LIMITS.forEach(limit => $('limits').append(textNode('li', limit)));
    $('literal').textContent = model.raw; $('review').hidden = false;
    message('Retained fixture bytes matched. Evidence and identities remain unverified. Review the gates and record a decision.');
  } catch (error) { if (token === generation) message(error.message, true); }
});
$('decision-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const declaration = declareDecision(model, {name: $('reviewer').value, decision: $('decision').value, rationale: $('rationale').value, acknowledged: $('ack').checked});
    const blob = new Blob([serializeDeclaration(declaration)], {type: 'application/json'});
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'earned-trust-MP2283-demo-declaration.json'; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('review-status').textContent = `DEMO DECLARATION: ${declaration.reviewerDeclaration.decision} / EVIDENCE NOT VERIFIED`;
    message('Local declaration download requested. Demo only, unauthenticated; evidence status is unchanged.');
  } catch (error) { message(error.message, true); $('message').scrollIntoView({block: 'nearest'}); }
});
