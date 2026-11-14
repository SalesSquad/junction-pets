// Supporting sections rendered from the optional keys of app.json: eventLog (SYNTHETIC), scribe (SYNTHETIC)
// and genomics (RESEARCH). Pure functions returning HTML strings, so tests can check them without a
// browser. Rule enforced by tests/tracks.test.mjs: every number that comes from data is wrapped in
// class "n" and sits inside an element with data-kind that carries the matching chip. No figure is
// typed here; every one is read from app.json, which src/tracks.mjs copies from the result files.
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const chip = (kind) => `<span class="chip ${kind.toLowerCase()}">${kind}</span>`;
const f = (v, d = 0) => (v == null || Number.isNaN(v) ? 'n/a' : (Number(Number(v).toFixed(d)) || 0).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d }));   // || 0 turns -0 into 0
const n = (v, d = 0, unit = '') => `<span class="n">${esc(f(v, d))}${unit}</span>`;
const raw = (v) => `<span class="n">${esc(v)}</span>`;
const pc = (v, d = 1) => (v == null ? '<span class="n">n/a</span>' : n(100 * v, d, '%'));
const pts = (v, d = 1) => (v == null ? '<span class="n">n/a</span>' : `<span class="n">${v > 0 ? '+' : ''}${esc(f(100 * v, d))}</span>`);
const pv = (p) => (p == null ? '<span class="n">n/a</span>' : `<span class="n">${esc(p >= 0.001 ? f(p, 3) : p.toExponential(1))}</span>`);
const sn = (v, d = 0, unit = '') => `<tspan class="n">${esc(f(v, d))}${unit}</tspan>`;
const lohi = (w) => w.wilson95 ?? w.ci95;
const ci = (w, d = 1) => (w?.value == null && w?.share == null ? '<span class="n">n/a</span>' : `${pc(w.value ?? w.share, d)} <span class="range">(${pc(lohi(w)[0], d)}–${pc(lohi(w)[1], d)}${w.n != null && w.k == null ? `; n = ${n(w.n)}` : ''})</span>`);
const kn = (w, d = 1) => `${n(w.k ?? w.n)}/${n(w.k != null ? w.n : w.d)} ${w.wilson95 || w.ci95 ? `<span class="range">(${pc(w.value ?? w.share, d)}; ${pc(lohi(w)[0], d)}–${pc(lohi(w)[1], d)})</span>` : `<span class="range">(${pc(w.value ?? w.share, d)})</span>`}`;
const frac = (s, d = 1) => `${n(s.n)}/${n(s.d)} <span class="range">(${pc(s.share, d)})</span>`;
const band = (b, d = 1) => `${pts(b[0], d)} to ${pts(b[1], d)} points`;
const au = (w) => (w?.value == null ? '<span class="n">not computed</span>' : `${n(w.value, 3)} <span class="range">(${n(w.ci95[0], 3)}–${n(w.ci95[1], 3)})</span>`);
// A block that holds data: the chip states what kind of number it is.
const scope = (tag, kind, inner, attrs = '') => `<${tag} data-kind="${kind}"${attrs}>${chip(kind)} ${inner}</${tag}>`;
const table = (kind, caption, head, rows) => `<div class="table-wrap" data-kind="${kind}"><p class="caption">${chip(kind)} ${caption}</p><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => (i ? `<td>${c}</td>` : `<th>${c}</th>`)).join('')}</tr>`).join('')}</tbody></table></div>`;
const figure = (kind, svg, caption) => `<figure data-kind="${kind}">${svg}<figcaption>${chip(kind)} ${caption}</figcaption></figure>`;
const details = (kind, summary, inner, open = false) => `<details class="track-details" data-kind="${kind}"${open ? ' open' : ''}><summary>${chip(kind)} ${summary}</summary>${inner}</details>`;
const words = (k) => esc(String(k).replace(/_/g, ' '));
const cap = (t) => { const x = String(t ?? '').trim(); return x ? `${x[0].toUpperCase()}${x.slice(1)}${/[.!?]$/.test(x) ? '' : '.'}` : ''; };
const slow = (r) => `${esc(f((r - 1) * 100))}%`;
const sources = (list) => list.map((s) => `<code>${esc(s.file)}</code>`).join(', ');
const INTERVAL_NAME = { primary_care: 'primary care', diagnostic: 'diagnostic', treatment: 'treatment' };
const niceTicks = (lo, hi) => { const out = []; for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) for (const m of [1, 3]) { const t = m * 10 ** e; if (t >= lo && t <= hi) out.push(t); } return out; };

// Rows of points with intervals on a common scale. series: [{value, lo, hi, cls}]; optional row.mark draws a dashed target.
function intervalChart(rows, { min, max, digits = 0, unit = '', aria, legend = [], scale = 1, left = 205 }) {
  const right = 590, rowH = 15, gap = 12;
  const x = (v) => left + (Math.min(Math.max(v, min), max) - min) / (max - min) * (right - left);
  let y = 26; const parts = [];
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => min + t * (max - min));
  const height = rows.reduce((s, r) => s + r.series.length * rowH + gap, 0) + 34 + (legend.length ? 18 : 0);
  parts.push(ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="18" y2="${height - (legend.length ? 26 : 8)}" class="grid"/><text x="${x(t)}" y="12" text-anchor="middle">${esc(f(t * scale, digits))}${unit}</text>`).join(''));
  for (const r of rows) {
    parts.push(`<text x="0" y="${y + 4 + (r.series.length - 1) * rowH / 2}">${esc(r.label)}</text>`);
    if (r.mark != null) parts.push(`<line x1="${x(r.mark)}" x2="${x(r.mark)}" y1="${y - 8}" y2="${y + (r.series.length - 1) * rowH + 8}" class="reference"/>`);
    for (const s of r.series) {
      if (s.value != null) {
        parts.push(`<line x1="${x(s.lo)}" x2="${x(s.hi)}" y1="${y}" y2="${y}" class="ci ${s.cls}"/><circle cx="${x(s.value)}" cy="${y}" r="4.2" class="pt ${s.cls}"/>`
          + `<text x="${right + 10}" y="${y + 4}">${sn(s.value * scale, digits, unit)} (${sn(s.lo * scale, digits)}–${sn(s.hi * scale, digits)})</text>`);
      } else parts.push(`<text x="${right + 10}" y="${y + 4}">${esc(s.missing || 'not computed')}</text>`);
      y += rowH;
    }
    y += gap;
  }
  if (legend.length) parts.push(legend.map((l, i) => `<circle cx="${left + i * 170 + 5}" cy="${height - 9}" r="4.2" class="pt ${l.cls}"/><text x="${left + i * 170 + 15}" y="${height - 5}">${esc(l.label)}</text>`).join(''));
  return `<svg viewBox="0 0 760 ${height}" class="track-chart" role="img" aria-label="${esc(aria)}">${parts.join('')}</svg>`;
}
const wv = (w) => (w?.value == null && w?.share == null ? { value: null, missing: 'no valid output to score' } : { value: w.value ?? w.share, lo: lohi(w)[0], hi: lohi(w)[1] });

// ------------------------------------------------------------------ The data to collect
function pathwayStrip(fmt) {
  const ev = fmt.events, core = new Set(fmt.coreFour), x = (i) => 40 + i * 100, short = (k) => k.replace(/_REPORTED$/, '').split('_').map((w, i) => (w === 'MDT' ? w : i ? w.toLowerCase() : w[0] + w.slice(1).toLowerCase())).join(' ');
  const idx = (k) => ev.indexOf(k);
  const brackets = Object.entries(fmt.intervals).map(([k, [a, b]]) => `<path d="M${x(idx(a))} 96 v10 H${x(idx(b))} v-10" class="bracket"/><text x="${(x(idx(a)) + x(idx(b))) / 2}" y="122" text-anchor="middle">${esc(INTERVAL_NAME[k])} interval</text>`).join('');
  return `<svg viewBox="0 0 ${80 + (ev.length - 1) * 100} 132" class="track-chart" role="img" aria-label="The pathway events in order; the core events are filled"><line x1="${x(0)}" x2="${x(ev.length - 1)}" y1="70" y2="70" class="axis"/>${ev.map((k, i) => `<circle cx="${x(i)}" cy="70" r="${core.has(k) ? 8 : 5}" class="${core.has(k) ? 'node core' : 'node'}"/><text x="${x(i)}" y="${i % 2 ? 48 : 30}" text-anchor="middle" class="${core.has(k) ? 'strong' : ''}">${esc(short(k))}</text>`).join('')}${brackets}</svg>`;
}
function requiredChart(ss) {
  const keys = Object.keys(INTERVAL_NAME), vals = ss.rows.flatMap((r) => keys.map((k) => r[k]));
  const lo = Math.log(Math.min(...vals) / 2), hi = Math.log(Math.max(...vals) * 1.6), left = 150, right = 600;
  const x = (v) => left + (Math.log(v) - lo) / (hi - lo) * (right - left);
  let y = 30; const parts = niceTicks(Math.exp(lo), Math.exp(hi)).map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="18" y2="${30 + ss.rows.length * 62}" class="grid"/><text x="${x(t)}" y="12" text-anchor="middle">${esc(f(t))}</text>`);
  for (const r of ss.rows) {
    parts.push(`<text x="0" y="${y + 20}">county slower by ${slow(r.slowdown)}</text>`);
    keys.forEach((k, i) => parts.push(`<rect x="${left}" y="${y + i * 15}" width="${x(r[k]) - left}" height="10" class="bar s${i}"/><text x="${x(r[k]) + 8}" y="${y + i * 15 + 9}">${sn(r[k])} ${esc(INTERVAL_NAME[k])}</text>`));
    y += 62;
  }
  return `<svg viewBox="0 0 760 ${y}" class="track-chart" role="img" aria-label="Complete episodes a county needs, by size of slowdown and interval, logarithmic scale">${parts.join('')}</svg>`;
}
function countyChart(counties, refs) {
  const rows = [...counties].sort((a, b) => b.assumed_annual_cases - a.assumed_annual_cases), left = 170, right = 600;
  const worst = (c, p) => Math.max(...Object.values(c[`min_detectable_slowdown_${p}`])) - 1;
  const max = Math.max(...rows.map((c) => worst(c, 'quarter')), ...refs) * 1.05, x = (v) => left + Math.min(v, max) / max * (right - left);
  const parts = refs.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="18" y2="${26 + rows.length * 17}" class="reference"/><text x="${x(t)}" y="12" text-anchor="middle">${esc(f(t * 100))}%</text>`);
  rows.forEach((c, i) => { const y = 32 + i * 17, q = worst(c, 'quarter'), yr = worst(c, 'year');
    parts.push(`<text x="0" y="${y + 4}">${esc(c.name)}</text><line x1="${x(yr)}" x2="${x(q)}" y1="${y}" y2="${y}" class="ci adapter"/><circle cx="${x(yr)}" cy="${y}" r="4" class="pt adapter"/><circle cx="${x(q)}" cy="${y}" r="4" class="pt hollow"/><text x="${right + 12}" y="${y + 4}">${sn(yr * 100)}% / ${sn(q * 100)}% · ${sn(c.assumed_annual_cases)}</text>`); });
  return `<svg viewBox="0 0 760 ${38 + rows.length * 17}" class="track-chart" role="img" aria-label="Smallest slowdown each county could detect in one year and in one quarter">${parts.join('')}</svg>`;
}
export function dataPlanHtml(app) {
  const e = app.eventLog;
  if (!e) return `<p class="missing-label">The design study is not in this build: ${esc(problemFor(app, 'eventLog') || 'data/eventlog/design-study-v1.json is missing')}.</p>`;
  const K = 'SYNTHETIC', ss = e.sampleSizes, co = e.cohortCheck, det = e.formulaCheck.summary.detector;
  const cmp = (d, size, r) => e.designs.comparison.find((x) => x.design === d && x.n === size && x.slowdown === r);
  const cell = (c) => (c.countyPower == null ? 'no patient dates to test' : `${pc(c.countyPower, 0)} found · ${c.stagePower == null ? 'cannot tell the intervals apart' : `${pc(c.stagePower, 0)} named`}`);
  const designRows = Object.entries(e.designs.labels).map(([d, label]) => [`${d} · ${esc(label)}`, ...e.designs.featured.map((fc) => cell(cmp(d, fc.n, fc.slowdown)))]);
  const looks = e.nulls.repeatedLooks, lk = (layout, thr, i) => looks.find((x) => x.layout === layout && x.threshold === thr).any_false_flag_by_look[i].rate;
  const L0 = looks[0].layout, last = looks[0].quarters - 1;
  const sc = e.nulls.smallCounty;
  const month = e.observation.conditions.find((c) => c.monthShare > 0 && c.missingness === 0), day = e.observation.conditions.find((c) => c.monthShare === 0 && c.missingness === 0);
  const ew = e.earlyWarning.filter((x) => x.design === 'D3'), ewSlow = [...new Set(ew.map((x) => x.slowdown))].sort();
  const ewCell = (stage, r) => { const x = ew.find((y) => y.stage === stage && y.slowdown === r); return x.median_quarters_to_detection == null ? `not reached in half of the runs (${pc(x.detected_by_quarter12, 0)} found by the last quarter)` : `${n(x.median_quarters_to_detection)} quarters`; };
  const ex = e.extraction.rows, exT = [...new Set(ex.map((r) => r.typeErrorRate))].sort(), exD = [...new Set(ex.map((r) => r.dateErrorRate))].sort();
  const exCell = (t, d) => { const x = ex.find((r) => r.typeErrorRate === t && r.dateErrorRate === d); return `${pc(x.meanStagePower, 0)} located, median off by ${n(x.meanMedianBiasDays, 1)} days`; };
  const refs = ss.rows.map((r) => r.slowdown - 1);
  const perRow = (fn) => ss.rows.map((r) => `${fn(r)} (<span class="n">${slow(r.slowdown)}</span>)`).join(', ');
  return [
    `<p>Finland publishes no figure for how long a cancer patient waits between first contact, referral, diagnosis and first treatment in any county. The smallest collection that closes that blind spot is a patient-level event log: one row per dated event, in an open columnar format (Parquet). Everything in this section is simulated to plan that collection.</p>`,
    scope('p', K, `${esc(e.statement)} Source: <code>${esc(e.source.file)}</code>, seed ${raw(e.source.seed)}, ${n(e.source.replications)} simulated counties per grid cell. Method and every table: <code>${esc(e.source.document)}</code>.`),
    `<h3>The format: dated events, the core ones essential</h3>`,
    `<figure>${pathwayStrip(e.format)}<figcaption>One row per event in the table <code>pathway_events</code>, with the county, entry route, cancer site, age band, date precision and source of each. The filled events are the core ones; they define the three intervals. ${esc(e.format.orderIsAConvention)}</figcaption></figure>`,
    scope('p', K, `A simulated sample in this format holds ${n(e.sample.episodes)} episodes and ${n(e.sample.events)} event rows and passes the validator with ${n(e.sample.chronology_violations)} order violations.`),
    `<h3>How many records make it useful</h3>`,
    scope('p', K, `To detect that a county is slower by a given ratio in one interval, at ${pc(ss.targetPower, 0)} power and with ${n(ss.comparisons)} county-by-interval comparisons (${n(ss.counties)} counties) controlled together:`),
    figure(K, requiredChart(ss), `Complete episodes needed per county and period, for one look, against a very large reference. Logarithmic scale. The spread of each interval is measured in ${n(e.calibrationEpisodes)} simulated episodes; with the wider single-step spread implied by the published cohort the rows would need ${perRow((r) => n(r.cohort_spread))}.`),
    scope('p', K, `Checked by simulation at exactly those sizes: the test as run reaches ${pc(det.min_power, 1)} to ${pc(det.max_power, 1)} power where the formula promises ${pc(ss.targetPower, 0)}. Against the rest of the country in one quarter instead of an infinite reference, the diagnostic interval needs ${perRow((r) => `${n(r.rest_of_country.quarter.diagnostic)} instead of ${n(r.diagnostic)}`)} episodes.`),
    scope('p', K, `The simulator matches the published mean of the cohort it was calibrated to (${n(co.simulated_mean_days, 1)} against ${n(co.published_mean_days)} days on the public route) but not its median (${n(co.simulated_median_days, 1)} against ${n(co.published_median_days)} days). Real waits are probably more spread than the simulated ones, which would raise every figure here.`),
    `<h3>What that means county by county</h3>`,
    figure(K, countyChart(e.counties, refs), `Smallest slowdown each county could detect in every interval: filled dot within one year, hollow dot within one quarter; the last figure is the assumed number of new cases a year. County sizes share an assumed ${n(ss.nationalCasesAssumed)} cases a year by ${raw(e.countyPopulationYear)} population; that total is an assumption, not an observed incidence. Dashed lines mark the slowdowns of the sizing table.`),
    table(K, `Counties (of ${n(e.counties.length)}) that could detect each slowdown in every interval, under these assumptions.`, ['County slower by', 'Within one quarter', 'Within one year'],
      e.reach.map((r) => [slow(r.slowdown), n(r.quarter), n(r.year)]).map(([a, ...b]) => [`<span class="n">${a}</span>`, ...b])),
    `<h3>Which design can locate which stage</h3>`,
    table(K, `Share of simulated counties in which a planted slowdown is found, and in which the right interval is named. Day-precision dates, no missing dates, mean over the three intervals. Columns: ${esc(e.designs.featuredRule)}.`,
      ['Collection design', ...e.designs.featured.map((fc) => `${n(fc.n)} episodes, <span class="n">${slow(fc.slowdown)}</span> slower`)], designRows),
    `<h3>What goes wrong if the plan is naive</h3>`,
    `<ul>${[
      `Repeated looks. With no slowdown anywhere, a quarterly report at the one-look threshold flags some county in ${pc(lk(L0, 'single_look', last), 0)} of simulated countries within ${n(looks[0].quarters)} quarters. Counting the looks in the threshold brings that to ${pc(lk(L0, 'looks_in_family', last), 1)}.`,
      `Small counties. With a normal critical value, a county of ${n(sc[0].n)} episodes raises a false flag ${n(sc[0].false_positive_rate_normal_quantile / sc[0].nominal_at_most, 1)} times as often as intended; with the t value now used the rate is ${n(sc[0].false_positive_rate_t / sc[0].nominal_at_most, 2)} times the intended one.`,
      `Dates known to the month only. Such an interval is not tested, so with ${pc(month.monthShare, 0)} of the dates at month precision ${pc((1 - month.monthShare) ** 2, 0)} of the intervals remain testable. Mean chance of naming the right interval across the grid: ${pc(day.meanStagePower, 0)} with day-precision dates, ${pc(month.meanStagePower, 0)} with month precision at that share.`,
    ].map((t) => scope('li', K, t)).join('')}</ul>`,
    `<h3>How soon would a new slowdown show?</h3>`,
    table(K, `A slowdown starts in one county of ${n(ew[0].n_per_quarter)} episodes a quarter; each quarter the last ${n(ew[0].window_quarters)} quarters are tested, with all ${n(ew[0].looks_in_family)} looks counted in the threshold. Median quarters from onset to the first flag.`,
      ['Interval slowed', ...ewSlow.map((r) => `<span class="n">${slow(r)}</span> slower`)], Object.keys(INTERVAL_NAME).map((k) => [esc(INTERVAL_NAME[k]), ...ewSlow.map((r) => ewCell(k, r))])),
    `<h3>Could dates read from text feed the log?</h3>`,
    table(K, `${esc(e.extraction.note[0].toUpperCase() + e.extraction.note.slice(1))}. Core design, ${n(ex[0].n)} episodes, a <span class="n">${slow(ex[0].slowdown)}</span> slowdown.`,
      ['Share of event types read wrongly', ...exD.map((d) => `${pc(d, 0)} of dates wrong`)], exT.map((t) => [pc(t, 0), ...exD.map((d) => exCell(t, d))])),
    measuredExtractionHtml(e, K),
    `<p class="caption">Full method, every table and the limits: <code>${esc(e.source.document)}</code> and <code>${esc(e.source.results)}</code>.</p>`,
  ].join('');
}
function measuredExtractionHtml(e, K) {
  const mx = e.measuredExtraction;
  if (!mx?.profiles?.length) return '';
  const sizes = [...new Set(mx.rows.map((r) => r.n))].sort((a, b) => a - b);
  const stages = Object.keys(INTERVAL_NAME);
  const planted = (cond, profile, size) => stages.map((st) => mx.rows.find((r) => r.kind === 'planted' && r.condition === cond && r.profile === profile && r.n === size && r.stage === st));
  const nul = (cond, profile, size) => mx.rows.find((r) => r.kind === 'null' && r.condition === cond && r.profile === profile && r.n === size);
  const locRow = (label, cells) => [label, cells.map((c) => pc(c.stage_power, 1)).join(' / '), cells.map((c) => n(c.median_bias_days, 1)).join(' / ')];
  const rows = sizes.flatMap((size) => [locRow(`${n(size)} episodes, every event confirmed by a person`, planted('confirmed', null, size)),
    ...mx.profiles.map((p) => locRow(`${n(size)} episodes, ${esc(p.system)}`, planted('measured_everywhere', p.profile, size)))]);
  const mixing = mx.profiles.flatMap((p) => sizes.map((size) => [`${esc(p.system)}, ${n(size)} episodes`, pc(nul('measured_everywhere', p.profile, size).county_false_positive_rate, 1), pc(nul('measured_county_only', p.profile, size).county_false_positive_rate, 1)]));
  const nominal = nul('confirmed', null, sizes[0]).nominal_at_most;
  return [
    `<h3>With the scribe's measured errors instead of assumed ones</h3>`,
    scope('p', K, `The same detector, fed with the per-event error the <a href="#scribe">pathway scribe</a> actually made on held-out synthetic notes. ${esc(mx.errorModel)}`),
    table(K, 'Measured per-event error of each adapter on its test notes.', ['Adapter and notes', 'True events', 'Found with the right type', 'Wrong-date share among those', 'Not found', 'Largest error, days'],
      mx.profiles.map((p) => [esc(p.system), n(p.true_events), n(p.events_with_type_found), pc(p.wrong_date_share), pc(p.missing_share), n(p.largest_absolute_error_days)])),
    table(K, `A slowdown planted in one interval of one county, ${n(mx.rows[0].replications)} runs per cell. Located: share of runs in which the planted interval is the one flagged (primary care / diagnostic / treatment); bias: error of the county's median interval in days.`,
      ['County and dates', 'Located', 'Median bias, days'], rows),
    table(K, `No slowdown anywhere: share of runs in which the county is flagged (intended at most ${pc(nominal, 2)}).`, ['Adapter, county size', 'County and country both extracted', 'Only the county extracted, the rest from structured fields'], mixing),
    `<ul>${mx.limits.map((t) => scope('li', K, esc(t))).join('')}</ul>`,
  ].join('');
}

// ------------------------------------------------------------------ Pathway scribe
const eventsList = (o) => (o ? `${esc(o.entry_route)} · ${o.events.map((x) => `${esc(x.type)} ${esc(x.date)}`).join(', ')}` : 'no valid output');
const problemFor = (app, track) => (app.trackProblems || []).filter((p) => p.track === track || p.track.startsWith(`${track}.`)).map((p) => `${p.track}: ${p.problem}`).join('; ');
export function scribeHtml(app) {
  const s = app.scribe;
  if (!s) return `<p class="missing-label">The scribe is not in this build: ${esc(problemFor(app, 'scribe') || 'no scribe result file is present')}.</p>`;
  const K = 'SYNTHETIC', out = [
    `<p>The dates the event log needs already sit in referral letters and visit notes. The idea tested here: a small open model (Gemma) with a trained adapter reads a Finnish note and proposes the dated pathway events and the entry route as structured data, and a person confirms each proposal. A large teacher model writes the training notes, two judge models check them, and a fourth model audits samples. Every note is written by a language model about simulated people.</p>`,
    scope('p', K, `${esc(s.statement)} Nothing here shows that the idea works on real clinical text.`),
  ];
  const missing = problemFor(app, 'scribe');
  if (missing) out.push(`<p class="missing-label">Parts left out of this build: ${esc(missing)}.</p>`);
  out.push(headlineHtml(s, K), ablationHtml(s.ablation, K), studentsHtml(s.students, K), servingHtml(s.serving, K), teachingHtml(s.teaching, K), historyHtml(s.history, K));
  const p = s.provenance;
  out.push(`<h3>Models and terms</h3>`, `<p class="caption">Student: Gemma 3 with LoRA adapters${s.ablation ? ` (selected run <code>${esc(s.ablation.selected.run)}</code>)` : ''}${p ? `, base converted from <code>${esc(p.base_model.upstream_repository)}</code>` : ''}. Teacher: NVIDIA Nemotron on Verda. Judges: TypeSafe Jev and OpenAI Decisions. Independent writer and auditor: Claude Haiku.${p ? ` Gemma and the adapters derived from it are subject to the <a href="${esc(p.terms.gemma_terms_of_use)}" target="_blank" rel="noopener noreferrer">Gemma Terms of Use</a> and the <a href="${esc(p.terms.gemma_prohibited_use_policy)}" target="_blank" rel="noopener noreferrer">Prohibited Use Policy</a>, which restricts automated decisions in healthcare.` : ''} Every extraction stays a proposal until a person confirms it. Research artefact, not a medical device. Details: <code>TRAINING.md</code>, <code>scribe/TEACHING.md</code>, <code>scribe/v2/RESULTS.md</code>.</p>`);
  return out.join('');
}
function headlineHtml(s, K) {
  const a = s.ablation, st = s.students;
  if (!a && !st) return '';
  const lines = [];
  if (a) lines.push(`The version-2 ablation selected <code>${esc(a.selected.run)}</code> on validation notes (${ci(a.selected.validation)}). On held-out notes it gets the whole note exactly right in ${ci(a.test.nemotron.exact)} of notes written by the teacher and ${ci(a.test.haiku.exact)} of notes written by a different model.`);
  if (st) {
    const best = [...st.runs].sort((x, y) => y.pooled.value - x.pooled.value)[0];
    const role = best.run === st.preregistration.primary ? 'the pre-registered primary comparison' : best.kind === 'post hoc' ? 'a post hoc comparison' : 'a pre-registered secondary comparison, not the primary';
    lines.push(`After the ablation, the highest pooled test figure is ${kn(best.pooled)} for <code>${esc(best.run)}</code> (${esc(best.what)}), against ${kn(st.reference.pooled)} for the reference (${best.paired.pooled.holm_adjusted_p != null ? `Holm p ${pv(best.paired.pooled.holm_adjusted_p)}` : `exact McNemar p ${pv(best.paired.pooled.exact_mcnemar_p)}`}). On teacher-written notes it is ${kn(best.nemotron)} against ${kn(st.reference.nemotron)} (exact McNemar p ${pv(best.paired.test_nemotron.exact_mcnemar_p)})${best.paired.test_nemotron.difference_in_exact_match <= 0 && best.paired.test_haiku.difference_in_exact_match > 0 ? ': the gain is on notes by the other writer' : ''}. It is ${role}; calling it the best uses the test notes, so it is a result to confirm on new notes, not a selection.`);
    const top = Math.max(st.reference.pooled.value, ...st.runs.map((r) => r.pooled.value));
    lines.push(`Even for the best run, ${pc(1 - top)} of the held-out notes are not exactly right (a wrong, missing or extra event, a wrong date or route, or no valid output), so every extraction goes to a person.`);
  }
  return `<h3>Where the scribe stands now</h3><div class="headline-box" data-kind="${K}">${chip(K)}${lines.map((l) => `<p>${l}</p>`).join('')}</div>`;
}
function ablationHtml(a, K) {
  if (!a) return '';
  const rows = [['Teacher-written (Nemotron)', a.test.nemotron], ['Different writer (Haiku)', a.test.haiku]].map(([label, t]) => [label, `${ci(t.exact)}`, n(t.eventF1, 3), ci(t.route), ci(t.invalid)]);
  const fin = a.finalists[0];
  return [
    `<h3>Version 2: what one GPU had time for</h3>`,
    scope('p', K, `An ablation on <code>${esc(a.host)}</code> within a ${n(a.budgetMinutes)}-minute budget (${n(a.elapsedSeconds / 60, 1)} minutes used), every run ${n(a.steps)} optimisation steps at an effective batch of ${n(a.effectiveBatch)}, selection by ${esc(a.selectionMetric)} on ${n(a.notes.validation)} notes. Runs that finished: ${a.trained.map((t) => `<code>${esc(t.name)}</code> ${pc(t.validation.value)}`).join(', ')}.${fin ? ` The full fine-tune did not displace the adapter (${n(fin.a_only_correct)} notes only it got right, ${n(fin.b_only_correct)} only the adapter, exact p ${pv(fin.exact_p)}).` : ''} ${esc(cap(a.selected.decodingCheck))}`),
    scope('p', K, `<strong>Dropped for time:</strong> ${a.dropped.map((d) => `<code>${esc(d.item)}</code>`).join(', ')}. ${a.armsNotRun.length === a.laterArms ? `None of the ${n(a.laterArms)} arms planned after the size ladder ran, so the ablation cannot say whether any of them beats the selected adapter.` : `${n(a.armsNotRun.length)} of the ${n(a.laterArms)} arms planned after the size ladder did not run.`}`),
    details(K, 'The planner\'s reason for each dropped item', `<ul>${a.dropped.map((d) => `<li><code>${esc(d.item)}</code>: ${esc(d.reason)}</li>`).join('')}</ul>`),
    table(K, `Selected adapter on held-out test notes (${a.test.decoding === 'off' ? 'unconstrained greedy' : esc(a.test.decoding)} decoding). Wilson 95% intervals. Source: <code>${esc(a.source.file)}</code>.`, ['Notes', 'Whole note exactly right', 'Event F1', 'Entry route right', 'Invalid output'], rows),
  ].join('');
}
function studentsHtml(st, K) {
  if (!st) return '';
  const all = [st.reference, ...st.runs];
  const label = (r) => (r.kind === 'reference' ? `${r.run} (reference)` : r.run);
  const chart = intervalChart(all.map((r) => ({ label: label(r), series: [{ ...wv(r.pooled), cls: 'adapter' }, { ...wv(r.nemotron), cls: 'base' }, { ...wv(r.haiku), cls: 'third' }] })),
    { min: 0, max: 1, scale: 100, unit: '%', digits: 0, left: 190, legend: [{ cls: 'adapter', label: 'pooled' }, { cls: 'base', label: 'teacher-written' }, { cls: 'third', label: 'other writer' }], aria: 'Whole-note exact match of each student on held-out notes, with Wilson 95% intervals' });
  const rows = all.map((r) => [`<code>${esc(label(r))}</code>${r.kind === 'post hoc' ? ' · post hoc' : ''}`, n(r.training.train_rows), n(r.training.epochs, 1), kn(r.validation), kn(r.nemotron), kn(r.haiku), kn(r.pooled),
    r.paired ? `${n(r.paired.pooled.only_new_correct)} vs ${n(r.paired.pooled.only_reference_correct)}, p ${pv(r.paired.pooled.exact_mcnemar_p)}${r.paired.pooled.holm_adjusted_p != null ? ` (Holm ${pv(r.paired.pooled.holm_adjusted_p)})` : ''}` : '']);
  const byRun = Object.fromEntries(st.runs.map((r) => [r.run, r]));
  const prim = byRun[st.preregistration.primary];
  const bullets = [
    `Every run used ${n(st.reference.training.steps)} optimisation steps at an effective batch of ${n(st.reference.training.effective_batch)}, so a larger training set is seen for fewer epochs (${all.map((r) => `${n(r.training.train_rows)} notes ${n(r.training.epochs, 1)}`).join(', ')}). The data arms differ in epochs as well as in data.`,
    prim ? `The pre-registered primary, <code>${esc(prim.run)}</code>, changed nothing on teacher-written notes (${kn(prim.nemotron)} against ${kn(st.reference.nemotron)}, p ${pv(prim.paired.test_nemotron.exact_mcnemar_p)}) and helped on notes by the other writer (${kn(prim.haiku)} against ${kn(st.reference.haiku)}, p ${pv(prim.paired.test_haiku.exact_mcnemar_p)}). On that writer's notes with no event it went from ${kn(st.reference.haikuNoEvent)} to ${kn(prim.haikuNoEvent)}.` : '',
    ...st.runs.filter((r) => r !== prim).map((r) => `<code>${esc(r.run)}</code> (${esc(r.what)}): teacher-written ${pts(r.paired.test_nemotron.difference_in_exact_match)} points (p ${pv(r.paired.test_nemotron.exact_mcnemar_p)}), other writer ${pts(r.paired.test_haiku.difference_in_exact_match)} points (p ${pv(r.paired.test_haiku.exact_mcnemar_p)}).`),
    `The comparisons were fixed in <code>${esc(st.preregistration.file)}</code>, frozen ${raw(st.preregistration.frozenUtc)}; multiplicity: ${esc(st.multiplicity)}. ${esc(cap(st.preregistration.sizeLadder))}`,
    ...(st.noResult || []).map((x) => `<code>${esc(x.run)}</code>: no number. ${esc(cap(x.reason))}`),
    `On the ${n(st.validationNotes)} validation notes (${esc(st.validationPairsNote)}): ${st.validationPairs.filter((p) => /reference/.test(p.second)).map((p) => `<code>${esc(p.first)}</code> against the reference: ${n(p.only_first_correct)} vs ${n(p.only_second_correct)} notes, p ${pv(p.exact_mcnemar_p)}, Holm ${pv(p.holm_adjusted_p_over_all_pairs)}`).join('; ')}.`,
  ].filter(Boolean);
  return [
    `<h3>After the ablation: more notes, a larger model</h3>`,
    figure(K, chart, `Whole-note exact match on the ${n(st.reference.pooled.n)} held-out test notes (${n(st.reference.nemotron.n)} written by the teacher, ${n(st.reference.haiku.n)} by a different model). Dots: share of notes; lines: Wilson 95% intervals. ${esc(st.decoding)}.`),
    table(K, `Paired against the reference on the same notes (notes only the run got right vs only the reference got right, exact McNemar p). Source: ${sources(st.source)}.`,
      ['Run', 'Training notes', 'Epochs', 'Validation', 'Teacher-written', 'Other writer', 'Pooled', 'Pooled vs reference'], rows),
    `<ul>${bullets.map((b) => scope('li', K, b)).join('')}</ul>`,
  ].join('');
}
function servingHtml(sv, K) {
  if (!sv) return '';
  const row = (label, r) => [label, `${n(r.validOutput)}/${n(r.n)}`, ci(r.exact), ci(r.route), n(r.eventF1, 3), `${n(r.latency.p50, 2)} s / ${n(r.latency.p95, 2)} s`, n(r.notesPerSecond, 1)];
  const reasons = Object.entries(sv.guided.reviewReasons).map(([k, v]) => `${words(k)} ${n(v)}`).join(', ');
  return [
    `<h3>Serving: the selected adapter behind vLLM</h3>`,
    table(K, `${n(sv.guided.n)} held-out notes (${Object.entries(sv.parity.bySplit).map(([k, v]) => `${n(v)} from ${esc(k.replace('test_', ''))}`).join(', ')}), concurrency ${n(sv.concurrency)}, on <code>${esc(sv.machine)}</code> (Verda ${esc(sv.instanceType)}). Run ${raw(sv.ts)}. Source: ${sources(sv.source)}.`,
      ['Decoding', 'Valid JSON', 'Whole note exactly right', 'Entry route right', 'Event F1', 'Latency p50 / p95', 'Notes per second'],
      [row('Structured outputs', sv.guided), row('Plain', sv.plain)]),
    scope('p', K, `The verdict (exact or not) matched the offline evaluation of the same adapter on every one of the ${n(sv.parity.n)} notes; the answers themselves were identical on ${n(sv.parity.samePredictionGuided)} (structured) and ${n(sv.parity.samePredictionPlain)} (plain), with the offline run cut at ${n(sv.parity.offlineMaxNewTokens[0])} new tokens against ${n(sv.parity.servedMaxTokens)} here. ${n(sv.parity.bySplit.test_haiku)} of these ${n(sv.parity.n)} notes are by the other writer, so this exact-match figure is not comparable with the test figures above. Every note went to human review (${reasons}), because no confidence threshold was calibrated for the server.`),
  ].join('');
}
function teachingHtml(t, K) {
  if (!t) return '';
  const tc = t.teacher, g = t.gate, d = t.dataset, j = t.judges, a = t.audit, c = t.cascade;
  const step = (title, who, body) => `<li><p class="kicker">${esc(who)}</p><h4>${esc(title)}</h4><p>${body}</p></li>`;
  const flow = `<div class="flow-wrap" data-kind="${K}"><ol class="flow" aria-label="The teaching loop, step by step">${[
    step('Answer keys', 'code', `${n(tc.specifications)} sampled routes and dated events`),
    step('Teacher writes a note', 'Nemotron on Verda', `${n(tc.requests)} requests of a cap of ${n(tc.requestCap)}`),
    step('Code check', 'code', `${frac(tc.codeCheckFinal)} pass`),
    step('Blind read-back', 'Nemotron, no key', `${frac(tc.readbackFinal)} read back exactly`),
    step('Gate', `Jev, question set ${esc(j.questionSet)}`, `${frac(g.acceptedOfJudged)} accepted`),
    step('Training set', 'code', `${n(d.trainRows)} notes: ${n(d.fromV2)} earlier + ${n(d.fromRound2)} round 2`),
    step('Student', 'Gemma + LoRA', `trained and compared above`),
    step('Cascade', `student + Jev`, `which notes may skip a person`),
  ].join('')}</ol><p class="caption">${chip(K)} Measured alongside, not in the gate rule: OpenAI Decisions accepted ${frac(g.decisionsAccepted)} of the notes it was asked about. Audited afterwards by Claude Haiku: ${frac(a.accepted.wrongLabel)} wrong labels among sampled accepted notes. Different model families on purpose: a model reads its own writing too kindly.</p></div>`;
  const ruleRows = j.rules.map((r) => [esc(r.label), kn(r.caught), kn(r.falseReject)]);
  const curr = g.byCurriculum.map((x) => [words(x.curriculum), frac(x.accepted)]);
  const sig = Object.fromEntries(c.signals.map((x) => [x.signal, x]));
  const cascadeRows = c.targets.flatMap((tg) => c.signals.map((x) => { const b = x.byTarget.find((y) => y.target === tg);
    return [`${n(tg)}% · ${esc(x.label)}`, frac(b.pooled.coverage), `${frac(b.pooled.error)}`, `${n(b.haiku.error.n)}/${n(b.haiku.error.d)}`,
      b.vsStudent ? `${pts(b.vsStudent.coverageDifference)} (${band(b.vsStudent.coverageDifference95)}; re-chosen ${band(b.vsStudent.coverageDifferenceRechosen95)})` : '—',
      b.vsStudent ? `${band(b.vsStudent.errorDifference95)}; re-chosen ${band(b.vsStudent.errorDifferenceRechosen95)}` : '—']; }));
  const errChart = intervalChart(c.targets.map((tg) => ({ label: `${f(tg)}% target`, mark: tg / 100, series: c.signals.map((x, i) => ({ ...wv(x.byTarget.find((y) => y.target === tg).pooled.error), cls: ['base', 'adapter', 'third'][i] })) })),
    { min: 0, max: Math.max(...c.signals.flatMap((x) => x.byTarget.map((y) => y.pooled.error.wilson95[1]))) * 1.1, scale: 100, unit: '%', digits: 0, left: 120,
      legend: c.signals.map((x, i) => ({ cls: ['base', 'adapter', 'third'][i], label: x.label })), aria: 'Error among the test notes that skipped review, by signal and target, with Wilson 95% intervals; dashed line: the target' });
  return [
    `<h3>The teaching loop</h3>`,
    scope('p', K, `How a large teacher, two judges and an independent auditor teach the small model, and whether a judge can let some notes skip the person at inference. Source: <code>${esc(t.source[0].file)}</code>, written ${raw(t.generatedUtc)} by <code>scribe/v3/summarise.py</code>; method in <code>scribe/TEACHING.md</code>.`),
    flow,
    `<h4>Teacher, round 2</h4>`,
    scope('p', K, `${n(tc.completed)} of ${n(tc.specifications)} specifications completed. First attempt: ${frac(tc.codeCheckFirst)} passed the code check; after one repair ${frac(tc.codeCheckFinal)}. A repair was tried for ${n(tc.repairAttempted.n)} notes and worked for ${frac(tc.repairSuccess)}. Hardest: notes that should contain no event, where only ${frac(tc.noEventReadback)} were read back as specified.`),
    `<h4>Two judges on planted errors</h4>`,
    table(K, `Code plants one error in a note's claimed answer (shifted date, swapped type, removed or added event, swapped route); a good judge fails the corrupted pair and passes the clean one. Report half of the benchmark. ${esc(cap(t.docs['judges.report160.*']))} ${esc(cap(j.chosenOn))}`,
      ['Rule', 'Corruptions caught', 'Clean pairs rejected'], ruleRows),
    scope('p', K, `Agreement between the two judges: Cohen's kappa ${n(j.kappa, 2)}; ${frac(j.missedByBoth)} of corruptions were missed by both. Cost per 1,000 notes: Jev USD ${n(j.cost.jev_hint.usdPer1000Notes, 3)} (p50 ${n(j.cost.jev_hint.p50, 2)} s), Decisions USD ${n(j.cost.decisions.usdPer1000Notes, 3)} at the list rate (p50 ${n(j.cost.decisions.p50, 2)} s).`),
    `<h4>Gate and audit</h4>`,
    table(K, `The gate (Jev rule) on ${n(g.candidates)} round-2 candidates, by curriculum. ${n(d.readbackInconsistent)} accepted notes were not read back as specified and stay in training, flagged; ${n(d.startsWithStyleLabel)} start with a literal style label that neither the code check nor the gate caught. The rule was not calibrated for notes with no event, terse notes or long notes.`,
      ['Curriculum', 'Accepted of candidates'], curr),
    table(K, `Audit of sampled round-2 notes. ${esc(cap(t.docs['audit.*']))}`, ['Gate decision', 'Notes audited', 'Wrong label', 'Route not right', 'Either'],
      [['Accepted', `${n(a.accepted.wrongLabel.d)} of ${n(a.sampling.accepted.available)}`, kn(a.accepted.wrongLabel), kn(a.accepted.routeNotOk), kn(a.accepted.either)],
        ['Rejected', `${n(a.rejected.wrongLabel.d)} of ${n(a.sampling.rejected.available)}`, kn(a.rejected.wrongLabel), kn(a.rejected.routeNotOk), kn(a.rejected.either)]]),
    `<h4>Cascade: can a judge let notes skip the person?</h4>`,
    scope('p', K, `Student: <code>${esc(c.chosenStudent)}</code>. ${esc(cap(c.choiceReason))} Threshold rule, ${esc(cap(c.thresholdRule))} ${esc(cap(c.empiricalNotGuaranteed))}`),
    `<ul>${c.verdict.map((v) => scope('li', K, esc(v))).join('')}</ul>`,
    figure(K, errChart, `Error among the held-out test notes that skipped review, pooled over both writers. The dashed line is the target the threshold was set for on validation notes; a dot right of it means the target did not hold on test.`),
    table(K, `All ${n(sig.student.byTarget[0].pooled.coverage.d)} test notes. Differences are paired bootstrap 95% intervals in percentage points; "re-chosen" also re-chooses the thresholds on resampled validation notes. Source: <code>data/scribe/v3/cascade/cascade-v1.json</code> via the summary.`,
      ['Target · signal', 'Skip review', 'Wrong among skipped', 'Of them, other writer', 'Coverage vs student', 'Error vs student'], cascadeRows),
    scope('p', K, `Spend recorded for this loop: TypeSafe USD ${n(t.cost.typesafe.usd, 4)} over ${n(t.cost.typesafe.requests)} requests; OpenAI ${n(t.cost.openai.tokens)} tokens over ${n(t.cost.openai.requests)} requests (USD ${n(t.cost.openai.usdListRate, 4)} at the list rate). The Nemotron teacher (${n(t.cost.nemotron.requests)} requests) is not priced: ${esc(t.cost.nemotron.usdMissingBecause)}. The Haiku audit is not priced: ${esc(t.cost.haikuAudit.missingBecause)}.`),
  ].join('');
}
function historyHtml(h, K) {
  if (!h) return '';
  const t = h.test, hk = h.haiku, d = h.dataset, sel = h.selective, all = h.adapterAllTest;
  const rows = (p) => [['Whole note exactly right', 'note_exact_match'], ['Entry route right', 'route_accuracy'], ['Events found (recall)', 'recall'], ['Events right when stated (precision)', 'precision']].map(([label, k]) => ({ label,
    series: [{ ...wv(p.base[k]), cls: 'base' }, { ...wv(p.adapter[k]), cls: 'adapter' }] }));
  const legend = [{ cls: 'base', label: 'base model' }, { cls: 'adapter', label: 'base model + adapter' }];
  const chart = (p, size, who) => intervalChart(rows(p), { min: 0, max: 1, scale: 100, unit: '%', digits: 0, legend, aria: `Version 1: base model against adapter on ${size} notes written by ${who}, with 95% intervals` });
  const cell = (c) => (!c?.admitted ? 'none admitted' : `${n(c.admitted)} of ${n(c.n)} admitted, ${n(c.errors_among_admitted)} wrong (${pc(c.error_rate_among_admitted)}; at most ${pc(c.error_upper_bound_95_one_sided)})`);
  const out = [
    `<div class="empty"><h3>The first planned run did not happen</h3><p>The plan was an adapter on <code>${esc(h.plannedRun.model)}</code> on a rented GPU. The machine stopped answering before training started. What ran instead is a reduced fallback on a laptop: <code>${esc(h.models.base)}</code>, ${esc(h.models.framework)}.</p></div>`,
    figure(K, chart(t, t.n, 'the teacher model'), `${n(t.n)} held-out notes written by the teacher model. The base model produced no valid output for ${n(h.invalidJson.test.base)} of ${n(t.n)} notes, so most of the difference is the output format. McNemar test on whole-note correctness: ${n(t.mcnemar.adapter_only_correct)} notes right with the adapter only, ${n(t.mcnemar.base_only_correct)} with the base model only.`),
    figure(K, chart(hk, hk.n, 'a different model'), `${n(hk.n)} notes written by a different model (Claude Haiku). Same reading: ${n(hk.mcnemar.adapter_only_correct)} notes right with the adapter only, ${n(hk.mcnemar.base_only_correct)} with the base model only.`),
    scope('p', K, `Where it failed: relative dates. The version-1 adapter copied dates that are written out and did not calculate dates given as "three weeks ago". Notes with a relative date: ${ci(t.byRelativeDate.with_relative_date.adapter.note_exact_match)} fully right. Notes with written-out dates only: ${ci(t.byRelativeDate.absolute_dates_only.adapter.note_exact_match)}.${all ? ` On all ${n(all.n)} test notes: ${ci(all.adapter.note_exact_match)}.` : ''}`),
  ];
  if (h.examples?.length) out.push(`<div class="examples">${h.examples.map((x) => scope('article', K, `<p class="kicker">${x.adapterCorrect ? 'Read correctly' : 'Read wrongly'} · note dated ${esc(x.noteDate)}</p><p lang="fi" class="note">${esc(x.noteText)}</p><dl><dt>Ground truth</dt><dd>${eventsList(x.truth)}</dd><dt>Adapter</dt><dd>${eventsList(x.adapter)}</dd></dl>`)).join('')}</div>`);
  if (sel) {
    const [lo, hi] = Object.keys(sel.limits).sort((x, y) => Number(x) - Number(y)), one = sel.limits[lo], five = sel.limits[hi], need = sel.notes_needed_without_error_for_claim;
    out.push(scope('p', K, `<strong>How much could skip human review in version 1? None, on this evidence.</strong> A confidence cut-off was fixed on ${n(sel.validation_notes)} validation notes and applied unchanged to the test notes. Aimed at ${pc(Number(lo), 0)} error it admits ${n(one.test_all.admitted)} of ${n(one.test_all.n)} test notes with ${n(one.test_all.errors_among_admitted)} wrong, compatible with an error rate up to ${pc(one.test_all.error_upper_bound_95_one_sided)}. Aimed at ${pc(Number(hi), 0)} it admits ${n(five.test_all.admitted)} with ${n(five.test_all.errors_among_admitted)} wrong (${pc(five.test_all.error_rate_among_admitted)}). A claim of at most ${pc(Number(lo), 0)} error would need ${n(need[lo])} admitted notes without one error. Superseded by the cascade above.`),
      table(K, '"At most" is the exact one-sided 95% upper bound on the error among admitted notes.', ['Target error', 'Validation notes (cut-off set here)', 'All test notes', 'Notes by a different writer'],
        Object.entries(sel.limits).map(([lim, v]) => [`at most ${pc(Number(lim), 0)}`, cell(v.validation), cell(v.test_all), cell(v.haiku)])));
  }
  const warn = [];
  if (d) warn.push(`Training data: ${n(d.counts.train)} notes for training, ${n(d.counts.val)} validation, ${n(d.counts.test)} test, ${n(d.counts.rejected)} rejected.`);
  if (d?.audit) warn.push(`A stricter second pass of the verifier disagreed with ${n(d.audit.strata.True.strict_disagreements)} of ${n(d.audit.strata.True.sampled)} accepted notes.`);
  if (h.labelAudit) warn.push(`A second model reading ${n(h.labelAudit.n)} sampled notes in full judged ${n(h.labelAudit.label_wrong)} labels wrong. Neither audit was done by a person.`);
  if (h.orderCheck) warn.push(`${n(h.orderCheck.accepted_episodes_with_reversed_pair)} of ${n(h.orderCheck.accepted_episodes)} accepted episodes break the pathway order of the event-log section, because the note sampler still uses an older order.`);
  if (warn.length) out.push(`<ul>${warn.map((w) => scope('li', K, w)).join('')}</ul>`);
  out.push(`<p class="caption">Sources: <code>${esc(h.source.evaluation)}</code>${h.source.postEvaluation ? `, <code>${esc(h.source.postEvaluation)}</code>` : ''}; details in <code>${esc(h.source.results)}</code>.</p>`);
  return `<h3>History</h3>${details(K, `Version 1 (laptop fallback, ${esc(h.models.base)}), superseded by ${esc(h.supersededBy)}`, out.join(''))}`;
}

// ------------------------------------------------------------------ Same variant, same answer?
function lrChart(rows, targets) {
  const left = 60, right = 600, top = 16, bottom = 150;
  const bounds = rows.flatMap((r) => [r.lr_lower_95_one_sided, r.lr_upper_95_one_sided, r.lr_plus]).filter((v) => v != null && v > 0);
  const lo = Math.log(Math.min(...bounds, 1 / targets.supporting.lr) / 1.5), hi = Math.log(Math.max(...bounds, targets.strong.lr) * 1.5);
  const y = (v) => bottom - (Math.log(Math.min(Math.max(v, Math.exp(lo)), Math.exp(hi))) - lo) / (hi - lo) * (bottom - top), x = (i) => left + (i + 0.5) * (right - left) / rows.length;
  const lines = [[1, 'no evidence', 'axis'], [targets.supporting.lr, 'supporting', 'reference'], [targets.moderate.lr, 'moderate', 'reference'], [targets.strong.lr, 'strong', 'reference'], [1 / targets.supporting.lr, 'supporting, functional direction', 'reference']];
  return `<svg viewBox="0 0 760 178" class="track-chart" role="img" aria-label="Likelihood ratio of loss-of-function per score bin for missense variants, with one-sided bounds and the evidence thresholds">${lines.map(([v, label, cls]) => `<line x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}" class="${cls}"/><text x="${right + 8}" y="${y(v) + 4}">${esc(label)}</text>`).join('')}${rows.map((r, i) => `<line x1="${x(i)}" x2="${x(i)}" y1="${y(r.lr_lower_95_one_sided)}" y2="${y(r.lr_upper_95_one_sided ?? Math.exp(hi))}" class="ci adapter"/><circle cx="${x(i)}" cy="${y(r.lr_plus)}" r="4" class="pt adapter"/><text x="${x(i)}" y="172" text-anchor="middle">${sn(r.n_lof)}/${sn(r.n_func)}</text>`).join('')}<text x="0" y="${y(1) + 4}">ratio 1</text></svg>`;
}
export function genomicsHtml(app) {
  const g = app.genomics;
  if (!g) return `<p class="missing-label">The genomics benchmark is not in this build: ${esc(problemFor(app, 'genomics') || 'data/genomics/brca1-evo2-v1.json is missing')}.</p>`;
  const K = 'RESEARCH', out = [
    `<p>The idea behind the title: a fixed, open genomic model gives the same score for the same DNA change wherever it is run, which could make one line of evidence in variant reading reproducible. This section tests that idea on a public laboratory benchmark and reports what held and what did not. Variant classification itself is done by accredited laboratories with several lines of evidence and expert review.</p>`,
    scope('p', K, `${esc(g.statement)} Source: <code>${esc(g.source.file)}</code>.`)];
  if (g.status === 'not_run') { out.push(`<div class="empty"><h3>The model was not run</h3><p>${esc(g.statusReason)}</p></div>`); return out.join(''); }
  const h = g.headline, m = g.metrics, ss = g.sameSample, ms = g.missenseEvidence, ev = g.evidenceAllConsequences.evidence, wc = g.windowsCompared, d = g.data;
  const strongest = (x) => (x ? `${words(x.pathogenic)} towards loss of function, ${words(x.benign)} towards normal function` : 'not established');
  const em = ss.evo2_minus, zero = (w) => w.ci95[0] <= 0 && w.ci95[1] >= 0;
  const cadd = h.evo2_minus_cadd_same_variants;
  out.push(`<div class="headline-box" data-kind="${K}">${chip(K)}<p class="kicker">Headline · missense variants only</p>`
    + `<p class="large-claim">Strongest evidence level reached: <strong>${words(h.missense_strongest_reached.tavtigian2018.pathogenic)}</strong> towards loss of function and <strong>${words(h.missense_strongest_reached.tavtigian2018.benign)}</strong> towards normal function (Tavtigian 2018; ${strongest(h.missense_strongest_reached.pejaver2022)} with the Pejaver 2022 targets).</p>`
    + `<p>${esc(cap(h.evidence_strength_basis))} ${n(h.missense_n_lof)} loss-of-function and ${n(h.missense_n_func)} functional missense variants in ${n(h.missense_n_bins)} score bins; the same level holds with the clustered exact bound in every bin (${strongest(h.missense_strongest_reached_with_clustered_exact_bound_in_every_bin.tavtigian2018)}). Missense AUROC ${au(h.auroc_missense)}; Evo 2 minus CADD on the same variants ${n(cadd.auroc_missense.value, 3)} (${n(cadd.auroc_missense.ci95[0], 3)} to ${n(cadd.auroc_missense.ci95[1], 3)})${zero(cadd.auroc_missense) ? ', no clear difference' : ''}. On all types of change together the level is ${words(h.all_consequences_strongest_reached_reference_only.tavtigian2018.pathogenic)}, for reference only. Labels: ${esc(h.labels)}. ${esc(h.window_caveat[0].toUpperCase() + h.window_caveat.slice(1))}.</p></div>`);
  out.push(scope('p', K, `<strong>Partial run.</strong> ${n(d.variants_scored)} of ${n(d.variants_in_table)} single-letter changes in BRCA1 were scored (${pc(d.variants_scored / d.variants_in_table, 0)}), with a ${n(g.method.window_bp)} letter window instead of the ${n(g.method.notebook_window_bp)} of the published method, because the full window did not fit in the memory allowed for this job. ${esc(g.statusReason || '')} The benchmark is the laboratory function assay of ${esc(d.citation)}. GPU host: <code>${esc(g.gpuHost.host)}</code>, ${esc(g.gpuHost.gpu)} on ${esc(g.gpuHost.provider)}, recorded as ${esc(g.gpuHost.status)}.`));
  const names = { evo2: `Evo 2 (${f(g.method.window_bp)} bp window)`, cadd: 'CADD', phylop_mammalian: 'phyloP conservation', consequence_only: 'Consequence class only, no model' };
  const one = (w) => (w?.value == null ? { value: null, missing: 'not applicable' } : { value: w.value, lo: w.ci95[0], hi: w.ci95[1] });
  const rows = Object.entries(names).map(([k, label]) => ({ label, series: [{ ...one(ss.scores[k].auroc_lof_vs_func), cls: 'adapter' }, { ...one(ss.scores[k].auroc_missense), cls: 'base' }] }));
  const minA = Math.floor(Math.min(...rows.flatMap((r) => r.series.filter((s) => s.value != null).map((s) => s.lo))) * 10) / 10;
  out.push(`<h3>How well does the score separate damaging from harmless changes?</h3>`,
    figure(K, intervalChart(rows, { min: minA, max: 1, digits: 2, legend: [{ cls: 'adapter', label: 'all types of change' }, { cls: 'base', label: 'missense changes only' }], aria: 'AUROC of Evo 2 and three comparison scores on the same variants, with 95% intervals' }),
      `Area under the ROC curve on the same ${n(ss.n_variants)} variants (${n(ss.n_lof)} loss of function, ${n(ss.n_func)} functional; 0.5 is chance, 1 is perfect). Lines: 95% intervals from resampling positions, because the changes at one position are not independent.`),
    scope('p', K, `Evo 2 minus CADD: ${n(em.cadd.auroc_lof_vs_func.value, 3)} (${n(em.cadd.auroc_lof_vs_func.ci95[0], 3)} to ${n(em.cadd.auroc_lof_vs_func.ci95[1], 3)})${zero(em.cadd.auroc_lof_vs_func) ? ', no clear difference' : ''}. For missense changes, where a computed score matters most: ${n(em.cadd.auroc_missense.value, 3)} (${n(em.cadd.auroc_missense.ci95[0], 3)} to ${n(em.cadd.auroc_missense.ci95[1], 3)})${zero(em.cadd.auroc_missense) ? ', no clear difference' : ''}. Against a lookup of the type of change with no model at all: ${n(em.consequence_only.auroc_lof_vs_func.value, 3)} (${n(em.consequence_only.auroc_lof_vs_func.ci95[0], 3)} to ${n(em.consequence_only.auroc_lof_vs_func.ci95[1], 3)}).`));
  if (wc) { const ks = Object.keys(wc.by_window).map(Number), big = String(Math.max(...ks)), small = String(Math.min(...ks)), dd = wc.difference_longer_minus_shorter.auroc_lof_vs_func;
    out.push(`<h3>Same variant, same answer? Only if the settings are fixed</h3>`, scope('p', K, `${n(wc.n_variants)} variants were scored with two window lengths. AUROC ${au(wc.by_window[small].auroc_lof_vs_func)} at ${n(Number(small))} letters and ${au(wc.by_window[big].auroc_lof_vs_func)} at ${n(Number(big))}; difference ${n(dd.value, 3)} (${n(dd.ci95[0], 3)} to ${n(dd.ci95[1], 3)}). The two scores rank the variants similarly but not identically (rank correlation ${n(wc.spearman_between_windows, 2)}). The longer window was kept after an interim look at the data, so its figure is the larger of two estimates.`)); }
  out.push(`<h3>What strength of evidence could the score carry?</h3>`,
    `<p>In the ACMG/AMP framework a computed score is one line of evidence, graded supporting, moderate, strong or very strong by how much it shifts the odds. The grades below are measured against laboratory classes, not clinical classifications, on the same variants that set the score bins.</p>`);
  if (ms.rows) out.push(figure(K, lrChart(ms.rows, ev.tavtigian2018.strength_targets), `Missense changes only: ${n(ms.n_lof)} loss of function and ${n(ms.n_func)} functional, in ${n(ms.n_bins)} score bins from low to high. Dot: likelihood ratio of loss of function in the bin; line: one-sided 95% bounds; below each bin, the loss-of-function and functional counts. Thresholds from Tavtigian 2018.`));
  out.push(table(K, 'Strongest grade reached. The grade moves with the number of score bins, so none of these is a calibration.', ['Variants', 'Tavtigian 2018 thresholds', 'Pejaver 2022 thresholds'],
    [['Missense only (headline)', strongest(ms.strongest_reached?.tavtigian2018), strongest(ms.strongest_reached?.pejaver2022)], ['All types of change together (reference only)', strongest(ev.tavtigian2018.strongest_reached), strongest(ev.pejaver2022.strongest_reached)],
      ...(ms.bin_count_sensitivity || []).map((r) => [`Missense, ${n(r.n_bins)} bins`, strongest(r.strongest_reached.tavtigian2018), strongest(r.strongest_reached.pejaver2022)])]));
  const mix = ev.tavtigian2018.consequence_mix_at_or_above_pathogenic_threshold?.moderate;
  if (mix) out.push(scope('p', K, `Above the moderate threshold for all types of change there are ${n(mix.n)} variants; of the ${n(mix.by_class.LOF)} loss-of-function ones, ${Object.entries(mix.lof_by_consequence).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${n(v)} ${esc(k.toLowerCase())}`).join(', ')}. Splice and nonsense changes are already covered by other criteria.`));
  if (g.published?.bionemo_framework_docs) out.push(scope('p', K, `Published values for the full ${n(g.method.notebook_window_bp)} letter window, not reproduced here: ${g.published.bionemo_framework_docs.rows.map((r) => `${n(r.auroc, 2)} for ${esc(r.model)}`).join(', ')}.`));
  out.push(`<h3>Limits</h3>${details(K, `All ${n(g.limits.length)} limits recorded with the result`, `<ul>${g.limits.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>`)}`,
    `<p class="caption">Model: <code>${esc(g.model.repository)}</code> revision <code>${esc((g.model.revision || '').slice(0, 12))}</code>, open weights (${esc(g.model.licence)}), ${esc(g.model.route)}. Every table and limit: <code>${esc(g.source.readme)}</code>.</p>`);
  return out.join('');
}
