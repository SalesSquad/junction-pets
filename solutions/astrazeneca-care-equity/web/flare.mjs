// Comparability gate panel. Renders data/flare/gate-v1.json (pass the parsed object). Pure function returning
// an HTML string, so it works without a browser and tests can check it. No figure is typed here: every number
// is read from the gate file, wrapped in class "n" and placed inside an element whose data-kind carries the
// matching chip (SYNTHETIC for the clock and the gate, ASSUMPTION for placeholder thresholds, PUBLISHED for the
// public stage-completeness figures). A "not comparable" verdict sits in the same row as the share it qualifies,
// which stays visible; the share is shown once per row, then one verdict column per scribe arm.
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const chip = (kind) => `<span class="chip ${kind.toLowerCase()}">${kind}</span>`;
const fmt = (v, d = 0) => (v == null || Number.isNaN(Number(v)) ? 'n/a' : (Number(Number(v).toFixed(d)) || 0).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d }));
const n = (v, d = 0, unit = '') => `<span class="n">${esc(fmt(v, d))}${unit}</span>`;
const pc = (v, d = 1) => (v == null ? '<span class="n">n/a</span>' : n(100 * v, d, '%'));
const signed = (v, d = 1) => (v == null ? '<span class="n">n/a</span>' : `<span class="n">${v > 0 ? '+' : ''}${esc(fmt(v, d))}</span>`);
const link = (label, url) => (/^https?:\/\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label));
// Plain names for non-technical readers: "raw" = the model writes the dates itself; "resolver" = Gemma copies the
// date phrase and code computes the date.
const ARMS = [['raw', 'The model’s own dates'], ['resolver', 'Gemma reads, code counts']];
const EVENTS = { FIRST_CONTACT: 'first contact', REFERRAL_SENT: 'the referral being sent', DIAGNOSIS: 'diagnosis', TREATMENT_START: 'the start of treatment' };
const eventName = (e) => EVENTS[e] || String(e ?? '').toLowerCase().replace(/_/g, ' ');

function cell(row, arm) {
  const s = row.scribe?.[arm];
  if (!s) return '<span class="missing-label">not computed</span>';
  const verdict = s.comparable
    ? '<span class="gate-ok">comparable</span>'
    : `<span class="missing-label" data-gate="not-comparable">not comparable</span>`;
  return `${verdict}<br><span class="caption">median bias ${signed(s.median_bias_days)} days; missed ${pc(s.missed_share)} of ${n(s.events)} events; ${n(s.intervals)} intervals</span>`;
}

export function flareGateHtml(gate) {
  if (!gate || !Array.isArray(gate.counties)) {
    return `<section class="flare-gate" data-kind="SYNTHETIC">${chip('SYNTHETIC')} <p class="missing-label">No comparability-gate result is stored.</p></section>`;
  }
  const { clock = {}, rule = {}, summary = {}, national = {}, flare = {}, realData } = gate;
  const where = flare.ran && flare.equivalence?.success
    ? `Computed by NVIDIA FLARE ${esc(flare.nvflare)} on ${n(flare.sites)} simulated county sites; only filtered totals left each site. FLARE equals the plain-Python central table in ${n(flare.equivalence.cells_ok)} of ${n(flare.equivalence.cells)} cells (tolerance ${esc(flare.equivalence.tolerance)}).`
    : 'FLARE-ready, not run in FLARE: every column was computed in plain Python.';
  const head = `<p class="kicker">${chip('SYNTHETIC')} ${esc(gate.title || 'Comparability gate')}: referral to treatment, ${n(gate.counties.length)} SYNTHETIC counties</p>`;
  const counts = ARMS.map(([arm, label]) => `<li><strong>${esc(label)}:</strong> ${n(summary[arm]?.not_comparable)} of ${n(summary[arm]?.of)} counties not comparable</li>`).join('');
  const headline = `<div class="headline-box" data-kind="SYNTHETIC">${chip('SYNTHETIC')}<p class="large-claim">A county is compared only when it can see itself.</p>`
    + `<ul>${counts}</ul><p>In the simulator, ${pc(national.share_within)} of ${n(national.n)} SYNTHETIC pathways started treatment within ${n(clock.threshold_days)} days of the referral being sent: the simulator's own rate, not an estimate for Finland. The ${n(clock.threshold_days)}-day threshold is a ${esc(clock.threshold_label)}.</p></div>`;
  const ruleBox = `<p data-kind="ASSUMPTION">${chip('ASSUMPTION')} <strong>Rule (${esc(rule.label)}):</strong> a cell is "not comparable" when the scribe's median bias is above ${n(rule.bias_limit_days)} days either way, or its missed-event share is above ${pc(rule.missed_limit, 0)}. Median bias: ${esc(rule.median_bias_definition)}. Missed share: ${esc(rule.missed_definition)}. The raw value stays visible.</p>`;
  const clockBox = `<p data-kind="ASSUMPTION">${chip('ASSUMPTION')} <strong>Clock:</strong> from ${esc(eventName(clock.start_event))} to ${esc(eventName(clock.end_event))}. ${esc(clock.threshold_text)} Sources: ${(clock.sources || []).map((s) => link(s.name + (s.page ? `, PDF page ${s.page}` : ''), s.url)).join('; ')}.</p>`;
  const rows = gate.counties.map((r) => `<tr><th>${esc(r.county)}</th><td>${r.rtt?.suppressed ? '<span class="n">suppressed</span>' : `${pc(r.rtt?.share_within)} <span class="range">(n = ${n(r.rtt?.n)})</span>`}</td><td>${pc(r.completeness?.complete_share)} <span class="range">(open ${pc(r.completeness?.open_share)})</span></td>${ARMS.map(([arm]) => `<td>${cell(r, arm)}</td>`).join('')}</tr>`).join('');
  const cap = (s) => String(s ?? '').replace(/^./, (x) => x.toUpperCase());
  const table = `<details class="gate-table"><summary>Show the table: every SYNTHETIC county, both ways of setting dates</summary><div class="table-wrap" data-kind="SYNTHETIC"><p class="caption">${chip('SYNTHETIC')} County codes are the real area codes, but every value in this table is SYNTHETIC and says nothing about that area. Notes were dealt to areas by a content-blind rule: ${esc(gate.scribe_input?.assignment)}. Scenario: ${esc(cap(gate.scribe_input?.scenario))}. The histogram edge sits at ${n(clock.histogram_edge_days, 1)} days, so whole-day pathways of at most ${n(clock.threshold_days)} days fall below it.</p>`
    + `<table><thead><tr><th>County code</th><th>Within ${n(clock.threshold_days)} days</th><th>Complete clocks</th>${ARMS.map(([, label]) => `<th>${esc(label)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div></details>`;
  const realKind = realData?.kind || 'PUBLISHED';
  const real = realData
    ? `<div class="real-data" data-kind="${esc(realKind)}"><p class="kicker">${chip(realKind)} ${esc(realData.question)}</p><ul>${(realData.areas || []).map((a) => `<li>${esc(a.area)}: ${a.pctRange ? `${n(a.pctRange[0])}–${n(a.pctRange[1])}%` : n(a.pct, 0, '%')} of cancers with stage recorded: <strong>${a.canSee ? 'yes' : 'no'}</strong></li>`).join('')}</ul>`
      + `<p class="caption">${chip(realKind)} Rule: ${esc(realData.rule)} (${n(realData.aim_pct, 0, '%')}). ${esc(realData.note)} Source: ${link(realData.source?.name, realData.source?.url)}.</p></div>`
    : '';
  const limits = (gate.limits || []).length ? `<p class="caption" data-kind="SYNTHETIC">${chip('SYNTHETIC')} ${gate.limits.map(esc).join(' ')}</p>` : '';
  return `<section class="flare-gate" data-kind="SYNTHETIC">${head}<h3>Measure it only where it can be seen</h3><p>${esc(gate.lede)}</p>${headline}${ruleBox}${clockBox}${table}`
    + `<p class="caption" data-kind="SYNTHETIC">${chip('SYNTHETIC')} ${where} Median bias: ${esc(rule.median_bias_computed_in)}.</p>${real}${limits}</section>`;
}
