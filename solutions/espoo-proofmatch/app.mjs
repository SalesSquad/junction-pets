import { roles, candidates, asOf } from './data.mjs';
import { conversation, renderEvidence } from './skill-graph.mjs';
import { sharedEventSlots, proposeMeeting, transitionMeeting } from './event-meetings.mjs';
import { benchmark } from './benchmark.mjs';
import { ESCO_CATALOG } from './esco/catalog.mjs';
import { validateCatalog, definitionUrl } from './esco/validation.mjs';
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let role = roles[0], selected = candidates[0].id, records = [];
const name = id => candidates.find(c => c.id === id)?.name ?? id;
const announce = message => { $('#status').textContent = message; };
const format = slot => `${new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(slot.start))}–${slot.end.slice(11, 16)} UTC`;
const evidenceLine = item => `<li>${escape(renderEvidence(item))}</li>`;
function renderEsco() {
  const container = $('#esco-results');
  try {
    validateCatalog(ESCO_CATALOG);
    container.innerHTML = ESCO_CATALOG.categories.map(category =>
      `<div class="esco-group"><h3>${escape(category.query)} · public glossary examples</h3>
      <ul class="esco-list">${category.results.map(term =>
        `<li><strong>${escape(term.en)}</strong><span lang="fi">${escape(term.fi)}</span>
        <a href="${escape(definitionUrl(term.uri))}" target="_blank" rel="noopener noreferrer">Open EU concept ↗</a></li>`).join('')}</ul></div>`).join('') +
      `<p class="small">Six illustrative European Commission terms. Fetched: ${escape(ESCO_CATALOG.observedAt.slice(0, 10))}.
      This glossary never changes candidate evidence, proficiency, visibility or event proposals.</p>`;
  } catch {
    container.textContent = 'Public vocabulary source is unavailable; the fictional conversation demo is unchanged.';
  }
}
$('#role').innerHTML = roles.map(r => `<option value="${escape(r.id)}">${escape(r.title)} · ${escape(r.employer.split(' · ')[0])}</option>`).join('');
$('#role').addEventListener('change', event => {
  role = roles.find(r => r.id === event.target.value); render(); announce(`${role.title}. All candidates remain visible; conversation evidence updated.`);
});
function render() {
  const conversations = candidates.map(c => conversation(role, c, asOf));
  $('#role-summary').textContent = role.summary;
  $('#role-skills').innerHTML = [...role.requiredSkills.map(s => ({ ...s, kind: 'Required' })), ...(role.preferredSkills ?? []).map(s => ({ ...s, kind: 'Preferred' }))].map(s => `<span class="chip">${escape(s.label)} · ${s.kind}</span>`).join('');
  $('#count').textContent = `${candidates.length} fictional candidates · all visible`;
  $('#candidates').innerHTML = candidates.map((c, i) => {
    const match = conversations[i];
    const related = match.alignment.rows.filter(s => s.status === 'related').length;
    const unknown = match.alignment.rows.filter(s => s.status === 'unknown').length;
    return `<button type="button" data-candidate="${escape(c.id)}" aria-pressed="${selected === c.id}" aria-controls="detail" class="candidate ${selected === c.id ? 'selected' : ''}"><span class="person-name">${escape(c.name)}</span><span class="headline">${escape(c.headline)}</span><span class="candidate-foot"><span>${c.evidence.length ? `${c.evidence.length} self-provided cards` : 'No portfolio · still welcome'}</span><span>${related ? `${related} transferable · ` : ''}${unknown} unknown</span></span><span class="interest-note">${match.interest === 'interested' ? 'Explicit interest in this topic' : match.interest === 'unknown' ? 'Interest unknown · ask' : 'Other interests stated · ask'}</span></button>`;
  }).join('');
  $('#candidates').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
    selected = button.dataset.candidate; render(); $(`[data-candidate="${selected}"]`).focus(); announce(`${name(selected)} selected. Evidence, questions and shared times updated.`);
  }));
  renderDetail(conversations.find(m => m.candidateId === selected));
  renderBaseline(); renderMeetings();
}
function renderDetail(match) {
  const c = candidates.find(c => c.id === selected);
  const slots = sharedEventSlots(role, c, records);
  const existing = records.find(r => r.roleId === role.id && r.candidateId === c.id && ['pending', 'accepted'].includes(r.status));
  const questions = [
    match.alignment.rows.some(s => s.status === 'related') ? 'Which parts of your related experience would transfer here, and what would you need to learn?' : 'Which part of this topic would you like to explore together?',
    c.evidence.length ? 'Could you walk us through one decision in your example and what you would change?' : 'Would you prefer to talk through an example or try a small shared exercise?',
    match.interest === 'interested' ? 'What would make a first conversation useful to you?' : 'Does this topic interest you, or would another conversation be more useful?',
  ];
  $('#detail').innerHTML = `<p class="eyebrow">A CONVERSATION, WITH CONTEXT</p><h3>${escape(c.name)}’s conversation card</h3><p class="muted">Fictional, self-provided material. No external verification. Evidence snapshot: ${asOf}.</p>
    <h4>Candidate’s side</h4><p class="notice">${escape(renderEvidence(match.interestEvidence))}</p>
    <h4>Role’s side · exact, transferable or unknown</h4>${match.alignment.rows.map(s => `<div class="skill-row"><div class="skill-top"><strong>${escape(s.id)} · ${s.required ? 'Required' : 'Preferred'}</strong><span class="skill-status ${s.status === 'unknown' ? 'unknown' : ''}">${s.status.toUpperCase()}</span></div><p class="skill-note">${escape(renderEvidence(s.evidence))}</p>${s.evidence.args.sources.length ? `<p class="skill-note">Inspect: ${s.evidence.args.sources.map(e => `<a class="evidence-link" href="#evidence-${escape(e.id)}">${escape(e.id)}</a>`).join(', ')}</p>` : ''}${s.status === 'related' ? `<details><summary>Inspect the transfer rule</summary><p>One authored seed edge: ${escape(s.via)} ↔ ${escape(s.id)}, relation ${s.relation}. Partial requirement credit = 0.6 × ${s.relation} = ${s.credit}. This is a heuristic for discussion, never a proficiency probability or a person score. No multi-hop inference.</p></details>` : ''}</div>`).join('')}
    <h4>Human-authored conversation questions</h4><ul class="questions">${questions.map(q => `<li>${escape(q)}</li>`).join('')}</ul>
    <h4>Source cards · inspect the material</h4>${c.evidence.length ? c.evidence.map(e => `<details class="evidence-card" id="evidence-${escape(e.id)}"><summary><strong>${escape(e.id)}</strong> · ${escape(e.title)}</summary><p>${escape(e.excerpt)}</p><p><strong>Reported outcome:</strong> ${escape(e.outcome || 'No concrete outcome supplied.')}</p><dl><dt>Source type</dt><dd>${escape(e.sourceType)} · self-declared</dd><dt>Issuer</dt><dd>${escape(e.issuer)}</dd><dt>Reference</dt><dd>${escape(e.ref)} · local fictional source</dd><dt>Observed</dt><dd>${escape(e.observedDate)}</dd><dt>Verification</dt><dd>None · not externally verified</dd></dl></details>`).join('') : '<p class="notice">No portfolio supplied. Ability is unknown; offer another way to explore it. This person remains selectable.</p>'}
    <details><summary>Read the bio · no bio-based aptitude inference</summary><p class="bio">${escape(c.bio)}</p></details>
    <details><summary>Inspect structured reasons and cautions</summary><p>Stable codes describe supplied labels and unknowns, never verified ability.</p><pre>${escape(JSON.stringify({ reasons: match.reasons, cautions: match.cautions }, null, 2))}</pre></details>
    <form class="schedule" id="proposal-form"><fieldset><legend>Employer simulation · propose a conversation</legend><p class="small">15 minutes · fictional 15 Nov 2026 · UTC (Helsinki +2 hours). Pending and accepted proposals hold time in this tab only.</p>
    ${existing ? `<p class="notice">${existing.status.toUpperCase()} proposal already exists for this role and candidate. Use the separate party controls in the meeting notebook.</p><a href="#meetings-heading">Review proposal status and actions</a>` : slots.length ? `<label for="slot" class="slot-label">Shared available time</label><select id="slot" name="slot" required>${slots.map(s => `<option value="${escape(s.start)}">${escape(format(s))}</option>`).join('')}</select><button class="primary" type="submit">Simulate employer: Propose 15-minute meeting</button>` : '<p class="notice">No shared free time for this role. Try another conversation or cancel a held proposal. This does not remove the candidate.</p>'}
    <p id="form-error" role="alert" hidden></p><p class="small">SIMULATED: one demo person can act as either party. Proposing does not accept for the candidate or establish real consent. No invitation is sent.</p></fieldset></form>`;
  $('#detail').querySelectorAll('.evidence-link').forEach(link => {
    link.addEventListener('click', event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey ||
          event.shiftKey || event.altKey) return;
      const card = document.getElementById(link.hash.slice(1));
      const summary = card?.querySelector('summary');
      if (!summary) return;

      // Native fragment navigation would move focus away from the summary.
      // Preserve the source URL while making the opened disclosure operable.
      event.preventDefault();
      card.open = true;
      if (location.hash !== link.hash) {
        history.pushState(history.state, '', link.hash);
      }
      summary.focus();
      card.scrollIntoView({ block: 'nearest' });
    });
  });
  $('#proposal-form').addEventListener('submit', event => {
    event.preventDefault();
    try {
      const slot = slots.find(s => s.start === $('#slot')?.value);
      const result = proposeMeeting({ role, candidate: c, slot, actor: { kind: 'employer', id: role.employerId }, records });
      records = result.records; render(); $('#meetings-heading').focus(); announce('SIMULATED pending proposal created. Candidate acceptance is a separate action. Nothing sent.');
    } catch (error) { const box = $('#form-error'); box.hidden = false; box.className = 'error'; box.textContent = error.message; }
  });
}
function renderBaseline() {
  const b = benchmark();
  $('#baseline').innerHTML = `<p>Legacy evidence heuristic: <strong>${b.evidenceCorrect}/${b.total}</strong> fixed labels; keyword baseline: <strong>${b.keywordCorrect}/${b.total}</strong>. Only <strong>2 illustrative cases</strong>, deliberately authored and non-independent. This does not evaluate the v2 skill graph, interest or meeting lifecycle.</p><ul>${b.cases.map(c => `<li>${escape(roles.find(r => r.id === c.role).title)}: fixed label ${escape(c.expected.map(name).join(', '))}; legacy result ${escape(name(c.evidenceTop))}; keyword result ${escape(name(c.keywordTop))}.</li>`).join('')}</ul>`;
}
function renderMeetings() {
  $('#meeting-list').innerHTML = records.length ? records.map(d => {
    const r = roles.find(r => r.id === d.roleId), held = ['pending', 'accepted'].includes(d.status);
    const buttons = (kind, actions) => `<fieldset class="party-actions"><legend>Simulate ${kind}${kind === 'candidate' ? ` · ${escape(name(d.candidateId))}` : ` · ${escape(r.employer.split(' · ')[0])}`}</legend>${actions.map(action => `<button type="button" class="text-button" data-meeting="${escape(d.id)}" data-actor="${kind}" data-action="${action}">${action[0].toUpperCase() + action.slice(1)}</button>`).join('')}</fieldset>`;
    return `<article class="draft-note"><span class="badge light">SIMULATED · ${d.status.toUpperCase()}</span><h3>${escape(name(d.candidateId))} ↔ ${escape(r.employer.split(' · ')[0])}</h3><p>${escape(r.title)}<br>${escape(format(d.slot))}</p><p>${d.status === 'pending' ? 'Awaiting simulated candidate response. Time held.' : d.status === 'accepted' ? 'Accepted in this simulation only. Time held.' : 'Time released. A new proposal may be made.'}</p>${held ? buttons('candidate', d.status === 'pending' ? ['accept', 'decline', 'cancel'] : ['cancel']) + buttons('employer', ['cancel']) : ''}<p class="small">No authenticated actors, real consent, job application, message or external booking.</p></article>`;
  }).join('') : '<p class="empty">No proposals yet. An employer may propose a shared slot, then the candidate may accept or decline separately.</p>';
  $('#meeting-list').querySelectorAll('button[data-action]').forEach(button => button.addEventListener('click', () => {
    try {
      const meeting = records.find(r => r.id === button.dataset.meeting);
      const kind = button.dataset.actor;
      const result = transitionMeeting({ records, meetingId: meeting.id, action: button.dataset.action, actor: { kind, id: kind === 'candidate' ? meeting.candidateId : meeting.employerId } });
      records = result.records; render(); $('#meetings-heading').focus(); announce(`SIMULATED proposal ${result.meeting.status}. ${['declined', 'cancelled'].includes(result.meeting.status) ? 'Time released.' : 'Time remains held.'} Nothing sent.`);
    } catch (error) { $('#meeting-error').textContent = error.message; $('#meeting-error').hidden = false; }
  }));
}
$('#reset').addEventListener('click', () => { records = []; $('#meeting-error').hidden = true; render(); announce('Simulation reset. All local proposals and time holds cleared.'); });
try { render(); renderEsco(); } catch { $('#detail').innerHTML = '<p class="error" role="alert">Demo fixtures could not be read. Reload or check the local data files.</p>'; }
if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js', { scope: './' }).then(() => navigator.serviceWorker.ready).then(() => {
  $('#offline').textContent = 'Offline shell cached on this localhost origin. Proposals remain in memory only.';
}).catch(() => { $('#offline').textContent = 'Offline cache unavailable. Keep the local Node server running; no internet needed.'; });
