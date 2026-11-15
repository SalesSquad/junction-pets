// The three supporting tracks in app.json and on the page: event-log design study (SYNTHETIC), pathway
// scribe with its teaching loop (SYNTHETIC) and the Evo 2 benchmark (RESEARCH). These tests bind the
// bundled figures to the result files they were copied from, check that a file without a required field
// fails the build, that an absent file leaves its part out with a reason, and that every data number on
// the page carries its chip and comes from data rather than from the code.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { buildApp } from '../src/build.mjs';
import { buildAblation, buildEvaluation, buildEventLog, buildGemmaAlone, buildGenomics, buildInsight, buildPlanner, buildPlannerVision, buildReader, buildResolver, buildServing, buildStudents, buildTeaching, buildTracks, FILES, oneClickWording, RESEARCH, SYNTHETIC } from '../src/tracks.mjs';
import { chip, dataPlanHtml, genomicsHtml, insightHtml, pilotHtml, plannerSummaryHtml, processHtml, roadmapLine, routeDisclosure, scribeHtml, whoHtml } from '../web/tracks.mjs';

const url = (p) => new URL(p, import.meta.url);
const has = (p) => existsSync(url(`../${p}`));
const read = (p) => JSON.parse(readFileSync(url(`../${p}`), 'utf8'));
const text = (p) => readFileSync(url(p), 'utf8');
const sha256 = (p) => createHash('sha256').update(readFileSync(url(`../${p}`))).digest('hex');
const clone = (x) => JSON.parse(JSON.stringify(x));
const app = buildApp();

// Minimal walk over generated HTML: returns, for every element with class "n", the data-kind of its
// nearest enclosing scope and whether that scope holds a chip of the same kind.
function numbersWithScope(html) {
  const out = [], stack = [], voids = new Set(['br', 'line', 'circle', 'rect', 'path', 'input', 'img', 'hr', 'meta', 'link']);
  const re = /<(\/?)([a-zA-Z0-9]+)((?:"[^"]*"|[^>"])*)>/g;
  let m;
  while ((m = re.exec(html))) {
    const [whole, close, tag, attrs] = m;
    if (close) { while (stack.length && stack.pop().tag !== tag); continue; }
    const kind = /data-kind="([A-Z]+)"/.exec(attrs)?.[1] ?? null;
    const node = { tag, kind, start: m.index, chips: new Set() };
    const chipKind = /class="chip ([a-z]+)"/.exec(attrs)?.[1];
    if (chipKind) for (const s of stack) s.chips.add(chipKind.toUpperCase());
    if (/class="n"/.test(attrs)) {
      const scope = [...stack].reverse().find((s) => s.kind);
      out.push({ at: m.index, scope: scope ?? null });
    }
    if (!whole.endsWith('/>') && !voids.has(tag)) stack.push(node);
  }
  return out;
}

test('the chip walker itself catches an unlabelled number', () => {
  const good = `<p data-kind="SYNTHETIC">${chip('SYNTHETIC')} <span class="n">12</span></p>`;
  const bare = `<p><span class="n">12</span></p>`;
  const wrong = `<p data-kind="SYNTHETIC">${chip('MEASURED')} <span class="n">12</span></p>`;
  const later = `<figure data-kind="RESEARCH"><svg><text><tspan class="n">0.8</tspan></text></svg><figcaption>${chip('RESEARCH')} caption</figcaption></figure>`;
  assert.equal(numbersWithScope(good)[0].scope.kind, 'SYNTHETIC');
  assert.ok(numbersWithScope(good)[0].scope.chips.has('SYNTHETIC'));
  assert.equal(numbersWithScope(bare)[0].scope, null);
  assert.ok(!numbersWithScope(wrong)[0].scope.chips.has('SYNTHETIC'));
  assert.ok(numbersWithScope(later)[0].scope.chips.has('RESEARCH'), 'a chip in the caption after the chart counts for the figure');
});

// ------------------------------------------------------------------ event log
test('event log: bundled figures equal the design-study file, and the file says it is synthetic', { skip: !has(FILES.eventLog) }, () => {
  const study = read(FILES.eventLog), e = app.eventLog;
  assert.equal(study.synthetic, true); assert.equal(e.synthetic, true); assert.equal(e.statement, SYNTHETIC);
  assert.equal(e.source.sha256, sha256(FILES.eventLog));
  assert.deepEqual(e.sampleSizes.rows, study.sample_sizes.rows);
  assert.deepEqual(e.sampleSizes.sigmaByInterval, study.sample_sizes.sigma_by_interval);
  assert.equal(e.sampleSizes.targetPower, study.sample_size_check_summary.target_power);
  assert.equal(e.sampleSizes.comparisons, study.settings.core_comparisons);
  for (const r of e.sampleSizes.rows) for (const k of ['primary_care', 'diagnostic', 'treatment']) {
    assert.ok(r.rest_of_country.year[k] >= r[k], 'a finite comparator never needs fewer episodes');
    assert.ok(r.with_planned_looks[k] > r[k], 'counting planned looks raises the required n');
  }
  assert.deepEqual(e.findings, study.findings);
  assert.deepEqual(e.cohortCheck, study.interval_log_sd.cohort_check);
  assert.deepEqual(e.nulls.repeatedLooks, study.repeated_looks_null);
  assert.deepEqual(e.nulls.smallCounty, study.small_county_null);
  assert.equal(e.counties.length, study.settings.counties);
  assert.equal(e.counties.reduce((s, c) => s + c.assumed_annual_cases, 0), e.sampleSizes.nationalCasesAssumed);
  assert.ok(e.counties.every((c) => c.name && c.name !== c.county), 'county names resolved from the public snapshot');
  // design comparison: each bundled cell is the mean of the three planted-stage cells of the grid
  for (const fc of e.designs.featured) {
    const cell = e.designs.comparison.find((x) => x.design === 'D3' && x.n === fc.n && x.slowdown === fc.slowdown);
    const grid = study.design_grid.filter((x) => x.design === 'D3' && x.n === fc.n && x.slowdown === fc.slowdown && x.missingness === 0 && x.month_share === 0);
    assert.equal(grid.length, cell.cells);
    assert.ok(Math.abs(cell.countyPower - grid.reduce((s, x) => s + x.county_power, 0) / grid.length) < 1e-12);
    // the featured size is the one closest to the target power among the sizes of the grid
    for (const other of e.designs.comparison.filter((x) => x.design === 'D3' && x.slowdown === fc.slowdown)) {
      assert.ok(Math.abs(cell.countyPower - e.sampleSizes.targetPower) <= Math.abs(other.countyPower - e.sampleSizes.targetPower));
    }
  }
  assert.equal(e.designs.featured.length, new Set(study.design_grid.map((x) => x.slowdown)).size, 'one featured column per planted slowdown');
  assert.ok(e.designs.comparison.filter((x) => x.design === 'D1').every((x) => x.countyPower === null && x.stagePower === null), 'no fabricated zeros for the design without timestamps');
  assert.ok(e.designs.comparison.filter((x) => x.design === 'D2').every((x) => x.stagePower === null), 'two timestamps cannot name the interval');
  const looks = (thr) => e.nulls.repeatedLooks.find((x) => x.threshold === thr).any_false_flag_by_look.at(-1).rate;
  assert.ok(looks('single_look') > looks('looks_in_family'), 'counting the looks lowers the false-flag rate');
  assert.equal(e.sample.chronology_violations, 0);
});

test('event log: the county reach table recounts the study and agrees with its own finding', { skip: !has(FILES.eventLog) }, () => {
  const e = app.eventLog;
  const worst = (c, p) => Math.max(...Object.values(c[`min_detectable_slowdown_${p}`]));
  for (const r of e.reach) {
    assert.equal(r.quarter, e.counties.filter((c) => worst(c, 'quarter') <= r.slowdown).length);
    assert.equal(r.year, e.counties.filter((c) => worst(c, 'year') <= r.slowdown).length);
    assert.ok(r.year >= r.quarter, 'a year never detects less than a quarter');
  }
  const finding = e.findings.find((f) => /can detect a 20% slowdown in every interval within one quarter/.test(f));
  if (finding) {
    const [, q, y, ten] = /(\d+) of \d+ counties can detect a 20% slowdown in every interval within one quarter, (\d+) within one year, and (\d+) can detect 10%/.exec(finding).map(Number);
    const r20 = e.reach.find((r) => Math.abs(r.slowdown - 1.2) < 1e-9), r10 = e.reach.find((r) => Math.abs(r.slowdown - 1.1) < 1e-9);
    assert.deepEqual([r20.quarter, r20.year, r10.year], [q, y, ten]);
  }
});

test('event log: the scribe\'s measured errors are fed back and bundled unchanged', { skip: !has(FILES.eventLog) }, () => {
  const mx = read(FILES.eventLog).measured_text_extraction, b = app.eventLog.measuredExtraction;
  assert.equal(b.profiles.length, mx.profiles.length);
  for (const [i, p] of mx.profiles.entries()) for (const k of ['true_events', 'events_with_type_found', 'wrong_date_share', 'missing_share', 'largest_absolute_error_days']) assert.equal(b.profiles[i][k], p[k]);
  assert.equal(b.rows.length, mx.rows.length);
  for (const [i, r] of mx.rows.entries()) for (const k of ['stage_power', 'county_false_positive_rate', 'median_bias_days']) assert.equal(b.rows[i][k], r[k]);
  assert.deepEqual(b.limits, mx.limits);
  assert.ok(!/were not fed back/.test(JSON.stringify(app.eventLog)), 'the stale "not fed back" note is gone');
  const html = dataPlanHtml(app);
  assert.match(html, /With the scribe's measured errors instead of assumed ones/);
  assert.match(html, /href="#scribe"/);
});

// ------------------------------------------------------------------ scribe
test('scribe ablation: the version-2 selection and its test figures equal ablation-v1.json', { skip: !has(FILES.ablation) }, () => {
  const ab = read(FILES.ablation), a = app.scribe.ablation;
  assert.equal(a.selected.run, ab.selection.run);
  assert.deepEqual(a.selected.validation, ab.selection.validation_exact_match);
  assert.deepEqual(a.test.nemotron.exact, ab.test.systems.selected.splits.test_nemotron.note_exact_match);
  assert.deepEqual(a.test.haiku.exact, ab.test.systems.selected.splits.test_haiku.note_exact_match);
  assert.equal(a.steps, ab.protocol.steps);
  assert.deepEqual(a.dropped.map((d) => d.item), ab.dropped.map((d) => d.item));
  assert.ok(a.dropped.some((d) => /1b/.test(d.item)) && a.dropped.some((d) => /4b/.test(d.item)), 'the dropped sizes are reported');
  assert.equal(a.source.sha256, sha256(FILES.ablation));
});

test('scribe students: every run equals compare-v1.json, and epochs and validation come from the training figures', { skip: !has(FILES.compare) || !has(FILES.trainingFigures) }, () => {
  const cmp = read(FILES.compare), fig = read(FILES.trainingFigures), st = app.scribe.students;
  assert.deepEqual(st.reference.pooled, cmp.reference.summary.pooled.note_exact_match);
  const src = [...cmp.comparisons.map((r) => [r, 'pre-registered']), ...cmp.posthoc.map((r) => [r, 'post hoc'])];
  assert.equal(st.runs.length, src.length);
  for (const [r, kind] of src) {
    const b = st.runs.find((x) => x.run === r.run);
    assert.equal(b.kind, kind);
    assert.deepEqual(b.pooled, r.summary.pooled.note_exact_match); assert.deepEqual(b.nemotron, r.summary.test_nemotron.note_exact_match); assert.deepEqual(b.haiku, r.summary.test_haiku.note_exact_match);
    assert.deepEqual(b.paired, r.paired_vs_reference);
    assert.equal(b.pooled.k, b.nemotron.k + b.haiku.k, 'pooled is the sum of the two writers');
    assert.deepEqual(b.validation, fig.validation_pairs.validation_exact_match[r.run]);
    assert.deepEqual(b.training, fig.epochs[r.run]);
  }
  const steps = new Set([st.reference, ...st.runs].map((r) => r.training.steps));
  assert.equal(steps.size, 1, 'every run has the same number of optimisation steps');
  const byRows = [st.reference, ...st.runs].sort((x, y) => x.training.train_rows - y.training.train_rows);
  for (let i = 1; i < byRows.length; i++) assert.ok(byRows[i].training.epochs <= byRows[i - 1].training.epochs, 'more training notes means fewer epochs');
  assert.ok((st.noResult || []).some((x) => /4b/i.test(x.run) && /memory/.test(x.reason)), 'the missing 4B result is reported with its reason');
  const html = scribeHtml(app);
  assert.match(html, /fewer epochs/); assert.match(html, /no number/);
});

test('scribe serving: the vLLM smoke figures equal the smoke files', { skip: !has(FILES.smokeGuided) || !has(FILES.smokePlain) }, () => {
  const g = read(FILES.smokeGuided), p = read(FILES.smokePlain), sv = app.scribe.serving;
  assert.equal(sv.guided.validOutput, g.requests.valid_output); assert.equal(sv.plain.validOutput, p.requests.valid_output);
  assert.deepEqual(sv.guided.exact, g.exact_match); assert.deepEqual(sv.plain.exact, p.exact_match);
  assert.equal(sv.guided.latency.p50, g.latency_seconds.p50); assert.equal(sv.guided.latency.p95, g.latency_seconds.p95);
  assert.equal(sv.concurrency, g.settings.concurrency);
  assert.equal(sv.guided.decisions.HUMAN_REVIEW, g.n, 'every served note went to a person');
});

test('scribe teaching loop: teacher, judges, gate, audit and cascade equal summary-v1.json', { skip: !has(FILES.teaching) }, () => {
  const s = read(FILES.teaching), t = app.scribe.teaching;
  assert.equal(t.teacher.specifications, s['teacher.specifications.built']);
  assert.equal(t.teacher.readbackFinal.n, s['teacher.overall.readback_consistent_final.n']);
  assert.equal(t.gate.acceptedOfJudged.n, s['gate.overall.rule_accepted_of_judged.n']);
  assert.equal(t.dataset.trainRows, s['dataset.train_rows']);
  assert.equal(t.dataset.trainRows, t.dataset.fromV2 + t.dataset.fromRound2);
  assert.equal(t.audit.accepted.wrongLabel.n, s['audit.accepted.wrong_label.n']);
  assert.equal(t.cascade.chosenStudent, s['cascade.chosen_student']);
  assert.deepEqual(t.cascade.verdict, s['cascade.verdict'].map(oneClickWording), 'the verdict is the summary reworded for one-click confirmation, figures unchanged');
  for (const [v, w] of s['cascade.verdict'].map((x) => [x, oneClickWording(x)])) assert.deepEqual(v.match(/[-+]?\d[\d.,/]*/g), w.match(/[-+]?\d[\d.,/]*/g), 'rewording keeps every figure');
  for (const sig of t.cascade.signals) for (const b of sig.byTarget) {
    const k = `cascade.${sig.signal}.${b.target}pct.test_pooled`;
    assert.equal(b.pooled.coverage.n, s[`${k}.coverage.n`]); assert.equal(b.pooled.error.n, s[`${k}.error_among_accepted.n`]);
    assert.equal(b.pooled.error.d, b.pooled.coverage.n, 'the error is among the notes that skipped review');
    assert.equal(b.pooled.coverage.n, b.nemotron.coverage.n + b.haiku.coverage.n);
  }
  assert.equal(t.cost.nemotron.usd, null); assert.ok(t.cost.nemotron.usdMissingBecause, 'an unpriced step says why');
  const html = scribeHtml(app);
  for (const v of s['cascade.verdict'].map(oneClickWording)) assert.ok(html.includes(v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')), 'each cascade verdict is shown as written');
});

test('scribe history: version 1 is kept, marked superseded, and still equals its evaluation file', { skip: !has(FILES.scribeEval) }, () => {
  const ev = read(FILES.scribeEval), h = app.scribe.history;
  assert.equal(h.superseded, true);
  assert.equal(h.source.evaluationSha256, sha256(FILES.scribeEval));
  assert.equal(h.plannedRun.executed, false); assert.equal(h.plannedRun.model, ev.meta.gpu.planned_model);
  for (const who of ['base', 'adapter']) for (const k of ['note_exact_match', 'route_accuracy', 'precision', 'recall']) {
    assert.deepEqual(h.test[who][k], ev.test[who][k]); assert.deepEqual(h.haiku[who][k], ev.extra_test[who][k]);
  }
  assert.ok(h.examples.every((x) => x.synthetic === true && /haiku/i.test(x.writer)));
  const html = scribeHtml(app);
  const hist = html.indexOf('<h3>History</h3>'), now = html.indexOf('Where the scribe stood before the code date resolver');
  assert.ok(now >= 0 && hist > now, 'the current headline comes first and version 1 is shown below it as history');
  assert.match(html.slice(hist), /superseded/); assert.match(html.slice(hist), /<details/);
});

// ------------------------------------------------------------------ genomics
test('genomics: bundled figures equal the result file; the missense-only evidence strength is the headline', { skip: !has(FILES.genomics) }, () => {
  const src = read(FILES.genomics), g = app.genomics;
  assert.equal(g.research, true); assert.equal(g.statement, RESEARCH); assert.match(src.statement, /research use only/i);
  assert.equal(g.source.sha256, sha256(FILES.genomics));
  assert.equal(g.status, src.status); assert.deepEqual(g.limits, src.limits);
  if (src.status === 'not_run') return;
  assert.deepEqual(g.headline, src.headline);
  assert.deepEqual(g.missenseEvidence.strongest_reached, src.missense_evidence.strongest_reached);
  assert.deepEqual(g.headline.missense_strongest_reached, src.missense_evidence.strongest_reached, 'headline and table agree');
  assert.equal(g.metrics.auroc.value, src.metrics.auroc_lof_vs_func.value);
  assert.deepEqual(g.sameSample, src.same_sample_comparison); assert.deepEqual(g.windowsCompared, src.windows_compared);
  if (src.data.variants_scored < src.data.variants_in_table) assert.equal(g.status, 'partial', 'an incomplete run is never shown as complete');
  for (const r of g.missenseEvidence.rows ?? []) assert.ok(r.lr_lower_95_one_sided <= r.lr_plus && (r.lr_upper_95_one_sided == null || r.lr_upper_95_one_sided >= r.lr_plus));
  const html = genomicsHtml(app);
  const head = html.indexOf('Headline · missense variants only'), allc = html.indexOf('All types of change together');
  assert.ok(head >= 0 && head < allc, 'the missense headline comes before the all-consequence level');
  assert.ok(html.slice(head, head + 600).includes(`<strong>${src.headline.missense_strongest_reached.tavtigian2018.pathogenic}</strong>`));
  assert.ok(!/address/.test(JSON.stringify(g.gpuHost)), 'no machine address is bundled');
});

// ------------------------------------------------------------------ build contract
test('a file that lacks a required field makes the build fail loudly', () => {
  const drop = (obj, path) => { const o = clone(obj), ks = path.split('.'), last = ks.pop(); let x = o; for (const k of ks) x = x[k]; delete x[last]; return o; };
  if (has(FILES.eventLog)) assert.throws(() => buildEventLog(drop(read(FILES.eventLog), 'measured_text_extraction.rows')), /required field "measured_text_extraction.rows" is missing/);
  if (has(FILES.ablation)) assert.throws(() => buildAblation(drop(read(FILES.ablation), 'selection.validation_exact_match')), /required field "selection.validation_exact_match"/);
  if (has(FILES.compare)) {
    const c = read(FILES.compare); delete c.comparisons[0].paired_vs_reference;
    assert.throws(() => buildStudents(c, read(FILES.trainingFigures), read(FILES.preregistration)), /paired_vs_reference/);
  }
  if (has(FILES.smokeGuided)) assert.throws(() => buildServing(drop(read(FILES.smokeGuided), 'latency_seconds.p95'), read(FILES.smokePlain), read(FILES.trainingFigures)), /latency_seconds.p95/);
  if (has(FILES.teaching)) {
    const s = read(FILES.teaching); delete s['cascade.jev.5pct.test_pooled.coverage.n'];
    assert.throws(() => buildTeaching(s), /required key "cascade.jev.5pct.test_pooled.coverage.n" is missing/);
    const u = read(FILES.teaching); u['gate.overall.candidates'] = null;
    assert.throws(() => buildTeaching(u), /null and _not_done does not explain why/);
  }
  if (has(FILES.genomics)) assert.throws(() => buildGenomics(drop(read(FILES.genomics), 'headline.missense_strongest_reached')), /headline.missense_strongest_reached/);
});

test('an absent file leaves its part out and names the reason in trackProblems', () => {
  const none = 'data/does-not-exist.json';
  const t = buildTracks([], { teaching: none });
  assert.ok(t.scribe && t.scribe.teaching === null && t.scribe.students);
  assert.deepEqual(t.trackProblems, [{ track: 'scribe.teaching', problem: `source file missing: ${none}` }]);
  assert.match(scribeHtml({ scribe: t.scribe, trackProblems: t.trackProblems }), /Parts left out of this build: scribe.teaching/);
  const all = buildTracks([], { eventLog: none, ablation: none, compare: none, smokeGuided: none, teaching: none, scribeEval: none, genomics: none, diagnose: none, resolver: none, evaluation: none, reader: none });
  assert.ok(!('eventLog' in all) && !('scribe' in all) && !('genomics' in all) && !('insight' in all));
  assert.deepEqual(all.trackProblems.map((p) => p.track).sort(), ['eventLog', 'genomics', 'insight', 'scribe', 'scribe.ablation', 'scribe.evaluation', 'scribe.gemmaAlone', 'scribe.history', 'scribe.reader', 'scribe.resolver', 'scribe.serving', 'scribe.students', 'scribe.teaching']);
  for (const [render, key] of [[dataPlanHtml, 'eventLog'], [scribeHtml, 'scribe'], [genomicsHtml, 'genomics']]) assert.match(render({ trackProblems: all.trackProblems }), new RegExp(`missing-label[^<]*${key}`));
});

test('the app file on disk carries the same tracks as a fresh build', { skip: !has('web/data/app.json') }, () => {
  const disk = read('web/data/app.json');
  for (const k of ['eventLog', 'insight', 'scribe', 'planner', 'genomics', 'safetyNet', 'flareGate']) assert.deepEqual(disk[k], JSON.parse(JSON.stringify(app[k] ?? null)) ?? undefined, `web/data/app.json is stale for ${k}: run node src/build.mjs`);
  assert.deepEqual(disk.trackProblems, app.trackProblems);
});

test('the side tracks do not touch the analysis or the recommendations', () => {
  const disk = has('web/data/app.json') ? read('web/data/app.json') : null;
  assert.equal(app.schemaVersion, 'care-equity-app-v1');
  assert.ok(app.analysis.regions.length === 23 && app.recommendation.portfolio.picks.length > 0);
  if (disk) assert.deepEqual(disk.recommendation.portfolio, JSON.parse(JSON.stringify(app.recommendation.portfolio)));
  const cited = JSON.stringify(app.recommendation) + JSON.stringify(app.analysis.goal3);
  assert.ok(!/eventLog|scribe|genomics|evo2|gemma|safetyNet|flareGate|insight|planner|nemotron/i.test(cited), 'no recommendation is derived from synthetic, research-only or drafted tracks');
});

// ------------------------------------------------------------------ page
const sections = [['The data to collect', dataPlanHtml, 'SYNTHETIC', 'eventLog'], ['Pathway scribe', scribeHtml, 'SYNTHETIC', 'scribe'], ['Same variant, same answer', genomicsHtml, 'RESEARCH', 'genomics'], ['The insight', insightHtml, 'SYNTHETIC', 'insight']];
for (const [title, render, kind, key] of sections) {
  test(`page section "${title}": every data number sits in a block that carries the ${kind} chip`, { skip: !app[key] }, () => {
    const html = render(clone(app));
    assert.ok(!/undefined|NaN|\[object Object\]/.test(html), 'no unrendered value');
    const nums = numbersWithScope(html);
    assert.ok(nums.length >= 40, `expected many data numbers, found ${nums.length}`);
    const unlabelled = nums.filter((x) => !x.scope), mislabelled = nums.filter((x) => x.scope && (x.scope.kind !== kind || !x.scope.chips.has(kind)));
    assert.equal(unlabelled.length, 0, `numbers outside a labelled block near: ${unlabelled.slice(0, 3).map((x) => html.slice(Math.max(0, x.at - 80), x.at + 60)).join(' | ')}`);
    assert.equal(mislabelled.length, 0, `numbers under the wrong chip near: ${mislabelled.slice(0, 3).map((x) => html.slice(Math.max(0, x.at - 80), x.at + 60)).join(' | ')}`);
    assert.ok(html.includes(kind === 'SYNTHETIC' ? 'Not for clinical use' : 'not for clinical decisions'));
    assert.ok(!/<(script|img|iframe|link)\b/i.test(html) && !/url\(\s*['"]?https?:/i.test(html), 'no external resource is loaded');
    assert.ok(!/class="chip (measured|scenario)"/.test(html), 'synthetic or research figures are never labelled MEASURED or SCENARIO');
  });

  // Every digit in the visible text must come from data: a number span, a code path, or a string of the
  // track's own JSON. What is left is the short list of names and method constants below.
  test(`page section "${title}": no figure is typed into the page code`, { skip: !app[key] }, () => {
    const dec = (t) => t.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    const strings = (o, acc = []) => { if (typeof o === 'string') acc.push(o); else if (o && typeof o === 'object') for (const v of Object.values(o)) strings(v, acc); return acc; };
    let t = dec(render(clone(app)).replace(/<svg[\s\S]*?<\/svg>/g, ' ').replace(/<(t?span) class="n">[^<]*<\/\1>/g, ' ').replace(/<code>[^<]*<\/code>/g, ' ').replace(/<[^>]+>/g, ' '));
    const js = [...new Set(strings(app[key]))].filter((s) => s.length >= 8).flatMap((s) => [s, `${s[0].toUpperCase()}${s.slice(1)}`]).sort((a, b) => b.length - a.length);
    for (const s of js) t = t.split(s).join(' ');
    const allowedPhrases = [/Figure 1\b/g, /Tavtigian 2018/g, /Pejaver 2022/g, /Evo 2/g, /Gemma 3/g, /[Vv]ersion [12]\b/g, /round 2/g, /0\.5 is chance, 1 is perfect/g, /stage [BC]\b/g];
    for (const re of allowedPhrases) t = t.replace(re, ' ');
    const allowed = /^(D[1-4]|F1|p50|p95|BRCA1|95%|1,000|v[12]|version-[12]|round-2|data\/scribe\/v3\/)$/;
    const left = [...t.matchAll(/\S*\d\S*/g)].map((m) => m[0].replace(/^[(]+|[.,;:()]+$/g, '')).filter((w) => !allowed.test(w));
    assert.deepEqual(left, [], `typed digits found in the page text: ${left.slice(0, 10).join(' ')}`);
  });
}

test('page sections show failures instead of hiding them', () => {
  for (const [, render] of sections) assert.match(render({}), /class="missing-label"/);
  if (app.scribe) {
    const html = scribeHtml(app);
    assert.match(html, /The first planned run did not happen/);
    assert.match(html, /None, on this evidence/);
    assert.match(html, /Dropped for time/);
    assert.ok(!/skip(s|ped)? (human )?review|skips? (the|a) person|among skipped/i.test(html), 'no wording that notes skip review');
    const noTeaching = scribeHtml({ scribe: { ...app.scribe, teaching: null }, trackProblems: [{ track: 'scribe.teaching', problem: 'source file missing: x' }] });
    assert.ok(!/The teaching loop/.test(noTeaching) && /Parts left out/.test(noTeaching));
  }
  if (app.genomics) {
    const html = genomicsHtml(app);
    if (app.genomics.status === 'partial') assert.match(html, /Partial run/);
    const notRun = genomicsHtml({ genomics: { ...app.genomics, status: 'not_run', statusReason: 'No scores were produced.' } });
    assert.match(notRun, /The model was not run/); assert.ok(!/AUROC/.test(notRun), 'no model figure when the model did not run');
    assert.ok(!/eligib/i.test(html.replace(app.genomics.statement, '')), 'no statement about treatment eligibility beyond the disclaimer');
  }
});

test('the page shell keeps the main product first, then the two synthetic tracks; the research benchmark lives on its own appendix page', () => {
  const html = text('../web/index.html'), css = text('../web/styles.css'), appJs = text('../web/app.mjs'), research = text('../web/research.html');
  const order = ['gap', 'who', 'county', 'goal', 'action', 'insight', 'plan', 'brief', 'collect', 'scribe', 'evidence'].map((s) => html.indexOf(`<section id="${s}"`));
  assert.ok(order.every((i) => i > 0) && order.every((v, i) => !i || v > order[i - 1]), 'section order');
  assert.ok(html.indexOf('class="tracks-intro"') > html.indexOf('<section id="brief"') && html.indexOf('class="tracks-intro"') < html.indexOf('<section id="collect"'), 'the tracks are introduced as supporting, after the product');
  assert.ok(html.indexOf('<section id="who"') === html.indexOf('</section>', html.indexOf('<section id="gap"')) + '</section>\n'.length, 'the who, how and where panel comes directly after the map');
  const nav = html.slice(html.indexOf('<nav'), html.indexOf('</nav>'));
  for (const [href, label] of [['#who', 'Who, how and where'], ['#plan', 'Nemotron county plan'], ['#collect', 'The data to collect'], ['#scribe', 'Gemma demo']]) assert.ok(nav.includes(`<a href="${href}">${label}</a>`));
  // Off the AstraZeneca page: the Evo 2 benchmark (appendix page only) and the early-warning signals section.
  assert.ok(!/<section id="(variant|warning)"/.test(html) && !/TREATMENT SELECTION/i.test(html) && !nav.includes('#variant'));
  assert.ok(research.includes('<section id="variant"') && /RESEARCH ONLY/.test(research) && !/treatment/i.test(research) && html.includes('href="/research.html"'));
  assert.ok(!/genomicsHtml|renderForecast/.test(appJs), 'the main page renders neither the genomics benchmark nor the forecast');
  // Mount points for the integrator, and the two lane modules imported, not copied.
  for (const id of ['safety-net', 'comparability-gate']) assert.match(html, new RegExp(`<div id="${id}"[^>]*data-mount="${id}"`));
  assert.match(appJs, /from '\.\/planner\.mjs'/); assert.match(appJs, /from '\.\/scribe-demo\.mjs'/); assert.match(appJs, /\/api\/scribe/); assert.match(appJs, /demo-outputs\.json/);
  assert.match(html, /wherever they live, whoever they are, however they enter care/);
  assert.match(css, /nav\{position:sticky/); assert.match(css, /\.chip\.synthetic\{/); assert.match(css, /\.chip\.research\{/); assert.match(css, /\.chip\.ecological\{/); assert.match(css, /\.chip\.published\{/);
  assert.match(css, /\.flow\{[^}]*grid-template-columns/); assert.match(css, /@media\(max-width:640px\)\{\.flow\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(appJs, /from '\.\/tracks\.mjs'/);
  for (const f of readdirSync(url('../web/')).filter((x) => /\.(html|css|mjs)$/.test(x))) {
    const body = text(`../web/${f}`);
    assert.ok(!/(src|href)=["']https?:\/\/[^"']+\.(js|css|woff2?|png|jpg|svg)/i.test(body) && !/@import|url\(\s*['"]?https?:/i.test(body), `${f} loads nothing from the network`);
    if (/\.(html|mjs)$/.test(f)) assert.ok(!/\sstyle=/.test(body), `${f} uses no inline style (the CSP blocks it)`);
  }
});

// ------------------------------------------------------------------ product panels
test('who, how and where: county gradients are labelled ECOLOGICAL with intervals, individual figures come from verified evidence rows', () => {
  const html = whoHtml(clone(app));
  assert.ok(!/undefined|NaN|\[object Object\]/.test(html));
  const nums = numbersWithScope(html);
  assert.ok(nums.length >= 40, `expected many data numbers, found ${nums.length}`);
  assert.equal(nums.filter((x) => !x.scope || !x.scope.chips.has(x.scope.kind)).length, 0, 'every number sits in a block that carries its own chip');
  const grads = app.analysis.gradients;
  const zero = grads.filter((g) => g.siiLow <= 0 && g.siiHigh >= 0).length;
  if (zero === grads.length) assert.match(html, new RegExp(`could be zero in all <span class="n">${grads.length}</span> indicators`));
  for (const g of grads) assert.ok(html.includes(`(<span class="n">${g.siiLow.toFixed(2)}</span> to <span class="n">${g.siiHigh.toFixed(2)}</span>)`.replace('-0.00', '0.00')), g.id);
  const ids = ['oecd-2025-survival-education', 'oecd-2025-breast-screening-education', 'oecd-2025-breast-screening-language', 'oecd-2025-cervical-screening-education', 'oecd-2025-cervical-screening-language', 'kuitunen-2026-route-medians'];
  for (const id of ids) {
    const r = app.evidence.find((x) => x.id === id);
    assert.ok(r && r.verified && r.url && r.citation && r.checked?.at, id);
    for (const v of Object.values(r.figures).filter((x) => typeof x === 'number' && x > 1 && x !== r.figures.cohortPatients && !String(x).includes('.'))) {
      if (['publicMeanDays', 'privateOccupationalMeanDays', 'occupationalPatients', 'privatePatients'].some((k) => r.figures[k] === v)) continue;
      assert.ok(html.includes(`<span class="n">${v}</span>`), `${id} figure ${v} on the panel`);
    }
  }
  const med = app.evidence.find((x) => x.id === 'kuitunen-2026-route-medians').figures;
  assert.deepEqual([med.publicMedianDays, med.privateOccupationalMedianDays, med.publicPatients, med.privateOccupationalPatients, med.p], [127, 76, 48, 39, 0.027]);
  assert.match(app.evidence.find((x) => x.id === 'kuitunen-2026-route-medians').citation, /^Kuitunen J,/);
  assert.ok(!app.evidence.some((r) => /Kuitunen H,/.test(r.citation)), 'first author is Kuitunen J');
  assert.match(html, /1\.3\.1/);
});

test('route, target and area wording: medians, OECD-reported six weeks against six months in law, 21 counties plus Helsinki and Åland', () => {
  const html = text('../web/index.html'), appJs = text('../web/app.mjs'), readme = text('../README.md');
  assert.ok(!/207 vs 123|207 days|123 days/.test(html + appJs + readme.replace(/[^.]*Figure 1[^.]*\./g, '')), 'the Figure 1 means appear only where they are labelled as read from Figure 1');
  assert.match(readme, /127 vs 76/); assert.match(readme, /48 vs 39/); assert.match(readme, /Kuitunen J/);
  assert.ok(!/23 wellbeing services counties/i.test(html + appJs + readme));
  assert.match(readme, /21 wellbeing services counties/);
  const process = processHtml(clone(app));
  assert.match(process, /OECD\/EU reports/); assert.match(process, /months of the need being established/);
  assert.ok(app.evidence.find((x) => x.id === 'oecd-2025-six-week-target').verified && app.evidence.find((x) => x.id === 'stm-2026-care-guarantee').figures.treatmentMonths === 6);
  assert.match(routeDisclosure(clone(app)), /read from Figure 1/);
});

test('every action carries its roadmap measure id, and the pilot card is Satakunta with its language scope', () => {
  for (const iv of app.recommendation.interventions) {
    const line = roadmapLine(clone(app), iv.id);
    assert.match(line, /\d\.\d\.\d+|No roadmap measure/, iv.id);
  }
  const card = pilotHtml(clone(app));
  assert.match(card, /Satakunta/); assert.match(card, /Finnish notes only/); assert.match(card, /No patient data leaves the county/);
  assert.ok(!/highest lung/i.test(card));
  for (const w of ['auto-confirmed', 'skips review', 'clinically accurate', 'works on real notes']) {
    for (const body of [card, whoHtml(clone(app)), processHtml(clone(app)), text('../web/index.html'), text('../web/app.mjs')]) assert.ok(!body.toLowerCase().includes(w), w);
  }
  assert.ok(!/low-dose CT screening, starting where/.test(JSON.stringify(app.recommendation.interventions)), 'the lung action joins the existing pilot');
});

// ------------------------------------------------------------------ lanes of NVIDIA_OPTIONS.md section 3 (integrated 15 November)
const WORDING = ['auto-confirmed', 'skips review', 'skip review', 'clinically accurate', 'works on real notes', 'hospital-grade'];
const drop = (obj, path) => { const o = clone(obj), ks = path.split('.'), last = ks.pop(); let x = o; for (const k of ks) x = x[k]; delete x[last]; return o; };

test('insight: the fake-inequality figures equal the design-study rows they are looked up from', { skip: !has(FILES.eventLog) }, () => {
  const study = read(FILES.eventLog), i = app.insight, mx = study.measured_interval_extraction;
  assert.equal(i.source.sha256, sha256(FILES.eventLog)); assert.equal(i.statement, SYNTHETIC);
  assert.ok(study.findings.includes(i.finding) && i.finding.startsWith(i.headline));
  const nul = (cond, arm, writer, extras) => mx.rows.find((r) => r.kind === 'null' && r.condition === cond && r.arm === arm && r.writer === writer && r.extras_modelled === extras).county_false_positive_rate;
  assert.equal(i.falseFlag.countyTextCountryStructured.asIs.rate, nul('county_extracted_country_structured', 'off', 'all', false));
  assert.equal(i.falseFlag.countyTextCountryStructured.resolver.rate, nul('county_extracted_country_structured', 'A', 'all', false));
  assert.equal(i.falseFlag.countyTextCountryStructured.resolverExtras.rate, nul('county_extracted_country_structured', 'A', 'all', true));
  assert.equal(i.falseFlag.writerStyle.asIs.rate, nul('county_haiku_like_country_nemotron_like', 'off', 'haiku vs nemotron', false));
  assert.equal(i.falseFlag.writerStyle.resolver.rate, nul('county_haiku_like_country_nemotron_like', 'A', 'haiku vs nemotron', false));
  assert.equal(i.falseFlag.confirmed.rate, nul('confirmed', null, null, false));
  // the finding sentence carries the same rates the table shows
  for (const v of [i.falseFlag.countyTextCountryStructured.asIs.rate, i.falseFlag.countyTextCountryStructured.resolver.rate, i.falseFlag.writerStyle.asIs.rate, i.falseFlag.writerStyle.resolver.rate]) assert.ok(i.finding.includes(v.toFixed(3)), v);
  for (const r of i.located) {
    const src = mx.rows.find((x) => x.kind === 'planted' && x.condition === r.condition && x.arm === r.arm && x.writer === 'all' && !x.extras_modelled && x.n === i.countyEpisodes);
    for (const k of ['primary_care', 'diagnostic', 'treatment']) assert.equal(r.intervals[k].located, src.intervals[k].located);
  }
  assert.deepEqual(i.noteExactMatch.test.resolver, mx.note_exact_match.test.resolver);
  assert.throws(() => buildInsight(drop(study, 'measured_interval_extraction.rows')), /required field "measured_interval_extraction.rows" is missing/);
  const noFinding = clone(study); noFinding.findings = noFinding.findings.filter((f) => !f.startsWith('Extraction errors manufacture'));
  assert.throws(() => buildInsight(noFinding), /fake-inequality finding is missing/);
  const noRow = clone(study); noRow.measured_interval_extraction.rows = noRow.measured_interval_extraction.rows.filter((r) => !(r.kind === 'null' && r.arm === 'A'));
  assert.throws(() => buildInsight(noRow), /has no null row/);
  const html = insightHtml(clone(app));
  assert.match(html, /manufacture fake county inequality/);
  for (const w of WORDING) assert.ok(!html.toLowerCase().includes(w), w);
});

test('scribe, Gemma reads, code counts: adapter alone, resolver, stress evaluation and reader equal their result files', { skip: !has(FILES.evaluation) || !has(FILES.resolver) || !has(FILES.reader) || !has(FILES.diagnose) }, () => {
  const s = app.scribe, res = read(FILES.evaluation), rep = read(FILES.resolver), rd = read(FILES.reader), dg = read(FILES.diagnose);
  assert.deepEqual(s.gemmaAlone.withRelativeDate, dg.runs['C-270m-all-v2data'].test.by_has_relative.True);
  assert.equal(s.resolver.test.after.k, rep.primary.test.k); assert.equal(s.resolver.test.before.k, rep.primary.test.before.k);
  assert.equal(s.resolver.validation.after.k, rep.primary.validation.k); assert.equal(s.resolver.notesMadeWorse, rep.notes_made_worse_arm_A_all_runs);
  const ev = s.evaluation, pr = res.primary_result;
  assert.equal(ev.source.sha256, sha256(FILES.evaluation));
  assert.deepEqual([ev.primary.aCorrect, ev.primary.bCorrect, ev.primary.n, ev.primary.p, ev.primary.met, ev.primary.headline], [pr.a_correct, pr.b_correct, pr.n, pr.exact_mcnemar_p, pr.met, pr.headline]);
  for (const setName of ['val', 'test', 'stress']) for (const [k, v] of Object.entries(res.sets[setName].systems)) assert.deepEqual(ev.sets[setName].systems[k].exact, v.exact_match, `${setName} ${k}`);
  for (const k of ["A'", 'B', 'C', 'nemotron']) {
    assert.deepEqual(ev.sets.stress.systems[k].slices.heldout, res.sets.stress.systems[k].slices.heldout);
    assert.deepEqual(ev.sets.stress.systems[k].vague.sent_to_person, res.sets.stress.systems[k].vague_outcome.sent_to_person);
  }
  const chosen = res.cascade.configurations.find((c) => c.gemma === res.cascade.chosen.gemma && c.signal === res.cascade.chosen.signal);
  const mine = ev.cascade.configurations.find((c) => c.gemma === ev.cascade.chosen.gemma && c.signal === ev.cascade.chosen.signal);
  assert.deepEqual(mine.test.prefilled, chosen.test.prefilled_for_one_click_confirmation); assert.deepEqual(mine.test.wrong, chosen.test.error_among_prefilled);
  assert.deepEqual(mine.stress.prefilled, chosen.stress.prefilled_for_one_click_confirmation);
  assert.equal(ev.cascade.baseline.prefilled, res.cascade.baseline_today.prefilled);
  assert.equal(s.reader.selected, rd.selected_by_rule); assert.deepEqual(s.reader.test.exact, rd.test.exact_match);
  for (const x of s.reader.ladder) assert.equal(x.after, rd.validation_ladder[x.step].after);
  for (const v of s.reader.versions) assert.deepEqual(v.exact, rd.validation[v.id].exact_match);
  // loud failures
  assert.throws(() => buildEvaluation(drop(res, 'primary_result.met')), /required field "primary_result.met" is missing/);
  const bad = clone(res); bad.verify.all_ok = false;
  assert.throws(() => buildEvaluation(bad), /hash checks before scoring did not all pass/);
  const noChoice = clone(res); noChoice.cascade.chosen.signal = 'nothing';
  assert.throws(() => buildEvaluation(noChoice), /chosen cascade configuration/);
  assert.throws(() => buildReader(drop(rd, 'validation_ladder')), /required field "validation_ladder" is missing/);
  assert.throws(() => buildResolver(drop(rep, 'primary.test.before')), /required field "primary.test.before" is missing/);
  assert.throws(() => buildGemmaAlone(drop(dg, 'runs.C-270m-all-v2data.test.by_has_relative')), /by_has_relative/);
  // the page
  const html = scribeHtml(clone(app));
  assert.match(html, /Gemma reads, code counts/); assert.match(html, /preregistered/i); assert.match(html, /pre-filled for one-click confirmation/);
  assert.ok(html.includes(`<span class="n">${ev.primary.bCorrect}</span>/<span class="n">${ev.primary.n}</span>`), 'the primary result is on the page');
  assert.ok(html.indexOf('Gemma reads, code counts') < html.indexOf('How the scribe got here'), 'the new result leads; the earlier versions follow');
  for (const w of WORDING) assert.ok(!html.toLowerCase().includes(w), w);
});

test('scribe: without the stress evaluation the section says so and labels the resolver figure post hoc', { skip: !has(FILES.resolver) }, () => {
  const none = 'data/does-not-exist.json';
  const t = buildTracks(app.analysis.regions, { evaluation: none });
  assert.equal(t.scribe.evaluation, null);
  assert.deepEqual(t.trackProblems, [{ track: 'scribe.evaluation', problem: `source file missing: ${none}` }]);
  const html = scribeHtml({ scribe: t.scribe, trackProblems: t.trackProblems });
  assert.match(html, /Parts left out of this build: scribe.evaluation/); assert.match(html, /not in this build/); assert.match(html, /post hoc/);
});

test('planner: the summary in app.json equals plans-v1.json, the tool re-check is complete, and the panel labels every number', { skip: !has(FILES.planner) }, () => {
  const plans = read(FILES.planner), p = app.planner;
  assert.equal(p.source.sha256, sha256(FILES.planner)); assert.equal(p.label, plans.label);
  assert.equal(p.summary.keptSentences, plans.summary.keptSentences); assert.equal(p.summary.keptSentencesWithUnmatchedNumber, 0);
  assert.equal(p.summary.promptComparison.v1.keptSentences, plans.summary.promptComparison.v1.keptSentences);
  assert.deepEqual(p.summary.offLimits, { prompts: plans.summary.offLimits.prompts, pass: plans.summary.offLimits.pass, passWithoutCodeGuard: plans.summary.offLimits.passWithoutCodeGuard, refusedByModel: plans.summary.offLimits.refusedByModel, blockedByCode: plans.summary.offLimits.blockedByCode });
  assert.deepEqual(p.countyIds.sort(), Object.keys(plans.counties).sort());
  if (p.toolCheck.checked) {
    assert.equal(p.toolCheck.identical + p.toolCheck.changed.length, p.toolCheck.counties);
    assert.equal(p.toolCheck.counties, Object.keys(plans.counties).length);
  }
  if (has(FILES.plannerVision)) { const v = read(FILES.plannerVision); assert.equal(p.vision.imageExact, v.summary.image_exact); assert.equal(p.vision.verdict, v.summary.verdict); }
  assert.throws(() => buildPlanner(drop(plans, 'summary.promptComparison')), /required field "summary.promptComparison.v1.keptSentences" is missing/);
  if (has(FILES.plannerVision)) assert.throws(() => buildPlannerVision(drop(read(FILES.plannerVision), 'summary.verdict')), /summary.verdict/);
  const html = plannerSummaryHtml(clone(app));
  assert.ok(!/undefined|NaN|\[object Object\]/.test(html));
  const nums = numbersWithScope(html);
  assert.ok(nums.length >= 20, `expected many data numbers, found ${nums.length}`);
  assert.equal(nums.filter((x) => !x.scope || !x.scope.chips.has(x.scope.kind)).length, 0, 'every number sits in a block that carries its own chip');
  for (const c of p.toolCheck.changed || []) assert.ok(html.includes(`<code>${c.county}</code>`), c.county);
  for (const w of WORDING) assert.ok(!html.toLowerCase().includes(w), w);
  // absent files: the planner, then only its image test
  const none = 'data/does-not-exist.json';
  const t = buildTracks(app.analysis.regions, { planner: none });
  assert.ok(!('planner' in t)); assert.deepEqual(t.trackProblems, [{ track: 'planner', problem: `source file missing: ${none}` }]);
  assert.match(plannerSummaryHtml({ trackProblems: t.trackProblems }), /missing-label[^<]*planner/);
  const u = buildTracks(app.analysis.regions, { plannerVision: none });
  assert.equal(u.planner.vision, null); assert.deepEqual(u.trackProblems, [{ track: 'planner.vision', problem: `source file missing: ${none}` }]);
});

test('page shell: the insight sits between the product actions and the Nemotron plan; app.mjs renders it and the planner summary', () => {
  const html = text('../web/index.html'), appJs = text('../web/app.mjs');
  assert.ok(html.indexOf('<section id="insight"') > html.indexOf('<section id="action"') && html.indexOf('<section id="insight"') < html.indexOf('<section id="plan"'));
  assert.match(html, /<div id="insight-content"><\/div>/); assert.match(html, /<div id="planner-summary"><\/div>/);
  assert.ok(html.slice(html.indexOf('<nav'), html.indexOf('</nav>')).includes('href="#insight"'));
  assert.match(appJs, /\['insight-content',insightHtml\]/); assert.match(appJs, /\['planner-summary',plannerSummaryHtml\]/);
  assert.match(appJs, /toolCheck\?\.changed/);
});
