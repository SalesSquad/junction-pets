// "Close loops, don't count them": the county safety-net worklist panel. Renders the precomputed
// data/safetynet/safetynet-v1.json (pass the parsed object). Pure function returning an HTML string:
// no fetch, no model call, no DOM. Everything patient-like in it is SYNTHETIC. Counts come first;
// at most three unnamed SYNTHETIC rows follow. Counts 1-4 are shown as "<5".
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const link = (label, url) => (/^https?:\/\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label));
const chip = (kind, text = kind) => `<span class="chip ${esc(kind.toLowerCase())}">${esc(text)}</span>`;
const ROUTES = { PUBLIC_PRIMARY: 'Public primary care', OCCUPATIONAL: 'Occupational health', PRIVATE: 'Private care', EMERGENCY: 'Emergency', SCREENING: 'Screening' };
const LANGS = { fi: 'Finnish', sv: 'Swedish', se: 'Sámi', other: 'Other' };
const KINDS = { imaging_follow_up: 'Imaging follow-up', suspected_cancer_referral: 'Suspected-cancer referral', recommendation_needs_person: 'Recommendation without a set date' };

function count(n, below = 5) {
  if (n == null) return 'n/a';
  return n > 0 && n < below ? `&lt;${below}` : Number(n).toLocaleString('en-GB');
}

function share(k, n, below = 5) {
  if (!n) return 'n/a';
  if ((k > 0 && k < below) || n < below) return 'suppressed (n &lt; 5)';
  return `${count(k)} of ${count(n)} (${Math.round((100 * k) / n)}%)`;
}

function tile(label, value, caption) {
  return `<article class="safetynet-count"><p class="kicker">${esc(label)} ${chip('SYNTHETIC')}</p><strong>${value}</strong>${caption ? `<p class="caption">${caption}</p>` : ''}</article>`;
}

export function safetyNetHtml(data, regionId) {
  const head = `<p class="kicker">${chip('SYNTHETIC')} ${esc(data?.text?.title || 'Close loops, don’t count them')}</p>`;
  const id = regionId || data?.pilotRegionId;
  const c = data?.counties?.find((x) => x.regionId === id);
  if (!c) return `<section class="safetynet" data-kind="SYNTHETIC">${head}<p class="missing-label">No safety-net worklist is stored for this county.</p></section>`;
  const t = data.text, k = c.counts, below = data.suppression?.below ?? 5;
  const placeholder = data.thresholds?.find((x) => x.label === 'PLACEHOLDER')?.days ?? 42;
  const sensitivity = data.thresholds?.filter((x) => x.label === 'PLACEHOLDER')?.[1]?.days;
  const onTime = data.cohort?.assumptions?.p_followup_on_time;
  const replay = /^\d{4}-\d{2}-\d{2}$/.test(data.asOf || '') ? new Date(`${data.asOf}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : esc(data.asOf);
  const counts = `<div class="verdict safetynet-counts">`
    + tile('Open loops', count(k.open_loops, below), 'Imaging follow-ups not yet done, recommendations awaiting a person, referrals without a diagnosis.')
    + tile(`Overdue on the replay date (${replay})`, count(k.overdue, below), `Imaging: ${count(k.imaging.overdue, below)} · Referrals: ${count(k.referral.overdue, below)} ${sensitivity ? ` (${count(k.referral.overdue_at_sensitivity_days, below)} at ${esc(sensitivity)} days)` : ''}`)
    + tile('Imaging follow-ups done by the due date', share(k.imaging.done_by_due, k.imaging.due_passed, below), `${chip('ASSUMPTION')} Simulated: ${onTime != null ? `each follow-up had a ${esc(Math.round(100 * onTime))}% chance of being on time, the same in every county, so the share here differs from ${esc(Math.round(100 * onTime))}% only by chance on ${count(k.imaging.due_passed, below)} loops` : 'the same completion chance in every county'}; differences between counties are noise, not findings.`)
    + tile(`Referrals with a diagnosis by day ${placeholder}`, share(k.referral.diagnosed_by_threshold, k.referral.clock_passed, below), `${chip('ASSUMPTION', 'PLACEHOLDER')} day ${placeholder}. From the SYNTHETIC event-log simulator.`)
    + `</div>`;
  const breakdown = (rows, key, names) => rows.length
    ? `<table><thead><tr><th>${key === 'route' ? 'Entry route' : 'Contact language'}</th><th>Open</th><th>Overdue</th>${key === 'language' ? '<th>Interpreter</th>' : ''}</tr></thead><tbody>${rows.map((r) => `<tr><th>${esc(names[r[key]] || r[key])}</th><td>${count(r.open, below)}</td><td>${count(r.overdue, below)}</td>${key === 'language' ? `<td>${count(r.interpreter, below)}</td>` : ''}</tr>`).join('')}</tbody></table>`
    : '';
  const examples = c.examples?.length
    ? `<div class="table-wrap"><table class="safetynet-rows"><caption>At most three unnamed example rows ${chip('SYNTHETIC')}</caption><thead><tr><th>Episode code</th><th>Loop</th><th>Age band</th><th>Route</th><th>Contact language</th><th>Days overdue</th><th>Missing step</th><th>Owner role</th><th>Status</th></tr></thead><tbody>${c.examples.map((e) => `<tr><td><code>${esc(e.episode_code)}</code></td><td>${esc(KINDS[e.loop_kind] || e.loop_kind)}${e.recommendation_copied ? `<br><q lang="fi">${esc(e.recommendation_copied)}</q>` : ''}</td><td>${esc(e.age_band)}</td><td>${esc(ROUTES[e.route] || e.route)}</td><td>${esc(LANGS[e.contact_language] || e.contact_language)}${e.interpreter ? ' (interpreter)' : ''}</td><td>${e.days_overdue == null ? '—' : esc(e.days_overdue)}</td><td>${esc(e.missing_step)}</td><td>${esc(e.owner_role)}</td><td>${e.status === 'needs editing' ? '<strong>Needs editing</strong>' : 'Nurse confirms'}</td></tr>`).join('')}</tbody></table></div>`
    : '<p class="missing-label">No open SYNTHETIC example rows for this county.</p>';
  const thresholds = `<div class="table-wrap"><table><thead><tr><th>Clock</th><th>Threshold</th><th>Source of the number</th></tr></thead><tbody>${(data.thresholds || []).map((x) => `<tr><th>${esc(x.clock)}</th><td>${x.days == null ? 'As written by the radiologist' : `${esc(x.days)} days`} ${chip('ASSUMPTION', x.label)}</td><td>${esc(x.source)}</td></tr>`).join('')}</tbody></table></div>`;
  const m = data.rule?.metrics;
  const x2 = data.cohort?.imaging_loops;
  const second = x2?.errors
    ? ` Second check on ${count(x2.loops)} more lines rendered with new seeds: ${count(x2.errors.wrong_due_date + x2.errors.invented_date_for_person_line + x2.errors.invented_date_for_none_line)} wrong or invented dates, ${count(x2.errors.missed_recommendation)} missed recommendations, ${count(x2.errors.due_line_sent_to_person)} dated lines sent to a person instead (${Object.entries(x2.due_line_sent_to_person_reasons || {}).map(([k, v]) => `${esc(k.replace(/_/g, ' '))}: ${count(v)}`).join(', ')}).`
    : '';
  const rule = m
    ? `<p>${esc(t.rule)} On ${esc(m.lines)} SYNTHETIC report lines: ${esc(m.exact_due_date.k)} of ${esc(m.exact_due_date.n)} exact due dates; ${esc(m.sent_to_person_when_gold_person.k)} of ${esc(m.sent_to_person_when_gold_person.n)} ranges and vague phrases sent to a person; ${esc(m.none_correct.k)} of ${esc(m.none_correct.n)} “ei jatkotoimia” lines left off the list.${second}</p><p class="caption">${esc(data.rule.caveat)}</p>`
    : '';
  const kpis = `<ul class="safetynet-kpis">${(data.kpis || []).map((x) => `<li>${esc(x.name)} ${chip('ASSUMPTION', 'DESIGN TARGET')}</li>`).join('')}</ul>`;
  return `<section class="safetynet" data-kind="SYNTHETIC">${head}`
    + `<h3>Safety-net worklist: ${esc(c.name)}${c.regionId === data.pilotRegionId ? ' (pilot county)' : ''}</h3>`
    + `<p class="caption">${esc(t.synthetic)} ${esc(t.as_of)} As of ${esc(data.asOf)}. ${esc(t.clock)}</p>`
    + counts
    + `<div class="safetynet-breakdown">${breakdown(c.by_route || [], 'route', ROUTES)}${breakdown(c.by_language || [], 'language', LANGS)}</div>`
    + examples
    + `<h4>How a line gets on the list</h4>${rule}${thresholds}`
    + `<h4>Pilot measures</h4>${kpis}`
    + `<p><strong>Governance.</strong> ${esc(t.governance)}</p>`
    + `<p><strong>Legal basis.</strong> ${esc(t.legal)} ${link('STM, 21 May 2026', t.legal_url)}</p>`
    + `<p><strong>Regulatory.</strong> ${esc(t.regulatory)}</p>`
    + `<p>${esc(t.pilot)}</p>`
    + (c.note ? `<p class="caption">${esc(c.note)}</p>` : '')
    + `<p class="caption">${esc(t.scope)} ${esc(t.neutrality)} ${esc(t.roadmap)} Generated ${esc(String(data.generatedAt || '').slice(0, 10))} by <code>${esc(data.provenance?.command)}</code>; schema ${esc(data.schemaDoc)}.</p>`
    + `</section>`;
}
