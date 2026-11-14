import { roles, candidates, asOf } from './data.mjs';
import { rank, keywordRank, sharedSlots, createDraft } from './matcher.mjs';
import { benchmark } from './benchmark.mjs';
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let role = roles[0], selected = '', records = [];
const name = id => candidates.find(c => c.id === id)?.name ?? id;
const announce = message => { $('#status').textContent = message; };
const format = slot => `${new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(slot.start))}–${slot.end.slice(11, 16)} UTC`;
$('#role').innerHTML = roles.map(r => `<option value="${escape(r.id)}">${escape(r.title)} · ${escape(r.employer.split(' · ')[0])}</option>`).join('');
$('#role').addEventListener('change', event => {
  role = roles.find(r => r.id === event.target.value); selected = ''; render(); announce(`${role.title}. Matches updated; demo consent fields cleared.`);
});
function render() {
  const matches = rank(role, candidates, asOf);
  if (!matches.some(m => m.candidateId === selected)) selected = matches[0]?.candidateId ?? '';
  $('#role-summary').textContent = role.summary;
  $('#role-skills').innerHTML = role.requiredSkills.map(s => `<span class="chip">${escape(s.label)} <strong>×${s.weight}</strong></span>`).join('');
  $('#count').textContent = `${matches.length} fictional candidates`;
  $('#candidates').innerHTML = matches.length ? matches.map((m, i) => {
    const c = candidates.find(c => c.id === m.candidateId);
    return `<button type="button" data-candidate="${escape(c.id)}" aria-pressed="${selected === c.id}" aria-controls="detail" class="candidate ${selected === c.id ? 'selected' : ''}"><span class="person-top"><span class="person-name">${escape(c.name)}</span><span class="score">${m.score}<small> / 100</small></span></span><span class="headline">${escape(c.headline)}</span><span class="candidate-foot"><span>0${i + 1} / ${c.evidence.length} evidence cards</span><span>${m.unknown.length ? `${m.unknown.length} unknown` : 'Review evidence →'}</span></span></button>`;
  }).join('') : '<p class="empty">No candidates supplied. Add fictional fixtures to data.mjs to explore matches.</p>';
  $('#candidates').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
    selected = button.dataset.candidate; render(); $(`[data-candidate="${selected}"]`).focus(); announce(`${name(selected)} selected. Evidence and shared slots updated.`);
  }));
  renderDetail(matches.find(m => m.candidateId === selected));
  renderBaseline(); renderDrafts();
}
function renderDetail(match) {
  if (!match) { $('#detail').innerHTML = '<p class="empty">Choose a candidate to explore their evidence.</p>'; return; }
  const c = candidates.find(c => c.id === selected);
  const slots = sharedSlots(role, c, records);
  const duplicate = records.some(r => r.roleId === role.id && r.candidateId === c.id);
  $('#detail').innerHTML = `<p class="eyebrow">FOLLOW THE EVIDENCE / ${escape(c.id.toUpperCase())}</p><h3>${escape(c.name)}’s paper trail</h3><p class="muted">All cards are self-provided and fictional. No external verification. Snapshot: ${asOf}.</p>
    <h4>Role-specific support</h4>${match.skills.map(s => `<div class="skill-row"><div class="skill-top"><strong>${escape(s.label)}</strong><span class="skill-status ${s.status === 'UNKNOWN' ? 'unknown' : s.status === 'CLAIM_ONLY' ? 'claim' : ''}">${s.status === 'UNKNOWN' ? 'UNKNOWN · ASK' : s.status === 'CLAIM_ONLY' ? 'CLAIM ONLY' : 'SELF-PROVIDED'}</span></div><p class="skill-note">${s.evidence.length ? `${s.contribution.toFixed(1)} score points · strongest support ${Math.round(s.support * 100)}% · ` + s.evidence.map(e => `<a class="evidence-link" href="#evidence-${escape(e.id)}">${escape(e.id)}</a>`).join(', ') : 'No eligible card supplied. Invite a work sample or a conversation.'}</p></div>`).join('')}
    <h4>Source cards <span class="small">/ open to inspect</span></h4>${c.evidence.length ? c.evidence.map(e => `<details class="evidence-card" id="evidence-${escape(e.id)}"><summary><strong>${escape(e.id)}</strong> · ${escape(e.title)}</summary><p>${escape(e.excerpt)}</p><p><strong>Reported outcome:</strong> ${escape(e.outcome || 'No concrete outcome supplied.')}</p><dl><dt>Source type</dt><dd>${escape(e.sourceType)}</dd><dt>Issuer</dt><dd>${escape(e.issuer)}</dd><dt>Reference</dt><dd>${escape(e.ref)} (local fictional source)</dd><dt>Observed</dt><dd>${escape(e.observedDate)}</dd><dt>Verification</dt><dd>None · self-provided</dd></dl></details>`).join('') : '<p class="notice">Evidence is unknown. This is an invitation to learn more, not a rejection.</p>'}
    <details><summary>Read the bio (excluded from evidence score)</summary><p class="bio">${escape(c.bio)}</p></details>
    <form class="schedule" id="intro-form"><fieldset><legend>Make space for a conversation</legend><p class="small">20 minutes · 15 Nov 2026 · UTC (Helsinki +2 hours). Drafts temporarily hold slots within this tab only.</p>
    ${duplicate ? '<p class="notice">A draft already exists for this pair. Review it in your local notebook.</p>' : slots.length ? `<label for="slot" class="slot-label">Shared available slot</label><select id="slot" name="slot" required>${slots.map(s => `<option value="${escape(s.start)}">${escape(format(s))}</option>`).join('')}</select><div class="consents"><label class="check"><input type="checkbox" id="employer-consent" required><span><strong>Employer demo consent</strong><br>Simulate the employer agreeing to draft this introduction.</span></label><label class="check"><input type="checkbox" id="candidate-consent" required><span><strong>Candidate demo consent</strong><br>Simulate the candidate agreeing to draft this introduction.</span></label></div><button class="primary" type="submit">Create introduction draft ↗</button>` : '<p class="notice">No shared free slot. Try another role or candidate, or reset demo drafts to release held slots. Nobody is excluded.</p>'}
    <p id="form-error" role="alert" hidden></p><p class="small">Simulation only: these checkboxes do not establish real consent. Nothing is sent or booked.</p></fieldset></form>`;
  $('.detail').querySelectorAll('.evidence-link').forEach(link => link.addEventListener('click', () => { const card = document.getElementById(link.hash.slice(1)); card.open = true; card.querySelector('summary').focus(); }));
  $('#intro-form').addEventListener('submit', event => {
    event.preventDefault();
    try {
      const slot = slots.find(s => s.start === $('#slot')?.value);
      const result = createDraft({ role, candidate: c, slot, employerConsent: $('#employer-consent')?.checked, candidateConsent: $('#candidate-consent')?.checked, records });
      records = result.records; render(); $('#drafts-heading').focus(); announce('Introduction draft created locally. Nothing sent or booked.');
    } catch (error) { const box = $('#form-error'); box.hidden = false; box.className = 'error'; box.textContent = error.message; }
  });
}
function renderBaseline() {
  const b = benchmark();
  const keyword = keywordRank(role, candidates);
  $('#baseline').innerHTML = `<div class="metric-grid"><div class="metric"><span>Evidence-first</span><strong>${b.evidenceCorrect} / ${b.total}</strong><small>Prelabelled top results found</small></div><div class="metric keyword"><span>Keyword-only</span><strong>${b.keywordCorrect} / ${b.total}</strong><small>Prelabelled top results found</small></div></div><p class="small">Current keyword ranking: ${keyword.map((c, i) => `${i + 1}. ${escape(name(c.candidateId))} (${c.score} hits)`).join(' · ')}</p><div class="table-wrap"><table><caption class="sr-only">Synthetic benchmark cases, top-1 correctness</caption><thead><tr><th scope="col">Role / fixed label</th><th scope="col">Evidence-first</th><th scope="col">Keyword-only</th></tr></thead><tbody>${b.cases.map(c => `<tr><th scope="row">${c.role === 'repair' ? 'Prototype' : 'Co-design'} / ${c.expected.map(name).map(escape).join(', ')}</th><td>${escape(name(c.evidenceTop))} · ${c.evidenceCorrect ? 'correct' : 'miss'}</td><td>${escape(name(c.keywordTop))} · ${c.keywordCorrect ? 'correct' : 'miss'}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderDrafts() {
  $('#draft-list').innerHTML = records.length ? records.map(d => {
    const r = roles.find(r => r.id === d.roleId);
    return `<article class="draft-note"><span class="badge light">DRAFT · NOT SENT</span><strong>${escape(name(d.candidateId))} ↔ ${escape(r.employer)}</strong><p>${escape(r.title)}<br>${escape(format(d.slot))}</p><p class="small">Proposed topic: discuss the supplied evidence and unknown skills together. Both demo consent fields checked; real mutual confirmation remains required. No invitation, reservation or calendar event exists outside this tab.</p></article>`;
  }).join('') : '<p class="empty">No drafts yet. Explore a paper trail, choose a shared slot and simulate both sides’ agreement.</p>';
}
$('#reset').addEventListener('click', () => { records = []; render(); announce('Demo reset. All draft holds and simulated consent cleared.'); });
try { render(); } catch { $('#detail').innerHTML = '<p class="error" role="alert">The demo data could not be read. Reload the page, or check the local data fixture.</p>'; }
if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js', { scope: './' }).then(() => navigator.serviceWorker.ready).then(() => {
  $('#offline').textContent = 'Offline cache ready on this localhost origin. Local server also works without internet.';
}).catch(() => { $('#offline').textContent = 'Offline cache unavailable. Keep the local Node server running; no internet is needed.'; });
