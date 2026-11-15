// Bundles the supporting tracks into app.json: the event-log design study (SYNTHETIC), the Gemma
// "pathway scribe" with its teaching loop (SYNTHETIC), the Evo 2 benchmark on BRCA1 (RESEARCH), and the
// two product panels of the ship wave: the county safety-net worklist (SYNTHETIC, data/safetynet/) and
// the FLARE comparability gate (SYNTHETIC clock and gate, PUBLISHED public stage chip, data/flare/).
// Every figure is copied from a result file written by executed code. This module only selects,
// renames, counts rows and averages rows that are named in the output; it types no figure itself.
//
// Rules enforced here:
// - every field a track reads is listed as required; a file that lacks one makes the build throw;
// - a part whose source file is absent is left out and named in app.trackProblems;
// - a null value in the flat teaching summary is accepted only when the summary explains it (_not_done).
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';

const at = (p) => new URL(`../${p}`, import.meta.url);
const exists = (p) => existsSync(at(p));
const load = (p) => (p.endsWith('.jsonl')
  ? readFileSync(at(p), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
  : JSON.parse(readFileSync(at(p), 'utf8')));
const sha256 = (p) => createHash('sha256').update(readFileSync(at(p))).digest('hex');
const src = (p) => ({ file: p, sha256: sha256(p) });
const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
const uniq = (a) => [...new Set(a)].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o && k in o).map((k) => [k, o[k]]));

// Product wording rule (NVIDIA_OPTIONS.md 3): a person confirms every extracted event; no note "skips review".
// The teaching summary was written before that rule, so its cascade sentences are reworded here, word for word
// otherwise; every figure in them is unchanged.
const ONE_CLICK = [
  [/\bnotes that skipped (?:human )?review\b/gi, 'notes pre-filled for one-click confirmation'],
  [/\bSkip review:/g, 'Pre-filled for one-click confirmation:'],
  [/\bskip (?:human )?review\b/gi, 'be pre-filled for one-click confirmation'],
  [/\bskipped (?:human )?review\b/gi, 'were pre-filled for one-click confirmation'],
  [/\bamong skipped\b/gi, 'among pre-filled'],
  [/\bskips? (?:the|a) person\b/gi, 'be pre-filled for one-click confirmation'],
];
export const oneClickWording = (s) => (typeof s === 'string' ? ONE_CLICK.reduce((t, [re, to]) => t.replace(re, to), s) : s);

export const SYNTHETIC = 'SYNTHETIC: simulated people and simulated notes under stated assumptions. Not Finnish patients. Not for clinical use.';
export const RESEARCH = 'Research use only; not for clinical decisions. Nothing here classifies a variant or informs any clinical choice.';
export const FILES = {
  eventLog: 'data/eventlog/design-study-v1.json',
  ablation: 'data/scribe/v2/ablation-v1.json',
  compare: 'data/scribe/v3/student/compare-v1.json',
  preregistration: 'data/scribe/v3/student/preregistration.json',
  trainingFigures: 'data/scribe/v2/training-figures-v1.json',
  smokeGuided: 'serve/smoke/smoke-guided.json',
  smokePlain: 'serve/smoke/smoke-plain.json',
  teaching: 'data/scribe/v3/summary-v1.json',
  scribeEval: 'data/scribe/eval-v1.json',
  scribePost: 'data/scribe/post-eval-v1.json',
  scribeStats: 'data/scribe/dataset-stats.json',
  scribeProvenance: 'data/scribe/provenance-v1.json',
  scribeHaiku: 'data/scribe/haiku-test.jsonl',
  scribeLabelAudit: 'data/scribe/label-audit-v1.json',
  genomics: 'data/genomics/brca1-evo2-v1.json',
  safetyNet: 'data/safetynet/safetynet-v1.json',
  flareGate: 'data/flare/gate-v1.json',
  // NVIDIA_OPTIONS.md section 3 lanes (14-15 November): "Gemma reads, code counts", the Nemotron reader and
  // county planner. The insight reads the same design-study file as the event-log track.
  diagnose: 'runs/diagnose/diagnose-v1.json',
  resolver: 'data/scribe/v4/resolver/reproduce-v1.json',
  evaluation: 'data/scribe/v4/eval/results-v1.json',
  reader: 'data/scribe/nemotron/reader-v1.json',
  planner: 'data/planner/plans-v1.json',
  plannerVision: 'data/planner/vision/vision-6b-v1.json',
  plannerRaw: 'data/planner/raw-v2',
  // Post hoc vague-phrase gate (15 November, after the stress results were seen); shown as one labelled line.
  vague: 'data/scribe/vague/results-v1.json',
};

// ------------------------------------------------------------------ required fields
export function need(obj, path, file) {
  let v = obj;
  for (const k of path.split('.')) {
    if (v === null || typeof v !== 'object' || !(k in v)) throw new Error(`${file}: required field "${path}" is missing`);
    v = v[k];
  }
  return v;
}
export const needAll = (obj, paths, file) => { for (const p of paths) need(obj, p, file); return obj; };
// The teaching summary has flat keys with dots in them ("teacher.overall.clean_final.n").
export function flatReader(summary, file) {
  const notDone = summary._not_done ?? {};
  const get = (key) => {
    if (!(key in summary)) throw new Error(`${file}: required key "${key}" is missing`);
    if (summary[key] === null && !(key in notDone)) throw new Error(`${file}: "${key}" is null and _not_done does not explain why`);
    return summary[key];
  };
  get.share = (key, { ci = true } = {}) => ({ n: get(`${key}.n`), d: get(`${key}.d`), share: get(`${key}.share`), ...(ci ? { wilson95: get(`${key}.wilson95`) } : {}) });
  get.has = (key) => key in summary;
  get.keys = () => Object.keys(summary);
  get.notDone = notDone;
  return get;
}

// ------------------------------------------------------------------ 1. event-log design study
const CORE_FOUR = ['FIRST_CONTACT', 'REFERRAL_SENT', 'DIAGNOSIS', 'TREATMENT_START'];
const INTERVALS = { primary_care: ['FIRST_CONTACT', 'REFERRAL_SENT'], diagnostic: ['REFERRAL_SENT', 'DIAGNOSIS'], treatment: ['DIAGNOSIS', 'TREATMENT_START'] };
const DESIGNS = {
  D1: "Today's public indicators (no patient timestamps)",
  D2: 'Referral received and treatment start only',
  D3: 'The core events (first contact, referral sent, diagnosis, treatment start)',
  D4: 'Every event of the pathway',
};
const EVENTLOG_REQUIRED = ['synthetic', 'seed', 'replications', 'pathway_order', 'design_grid', 'power_gap_by_condition', 'text_extraction',
  'sample_sizes.formula', 'sample_sizes.rest_of_country_formula', 'sample_sizes.idealised_sigma', 'sample_sizes.sigma_by_interval',
  'sample_sizes.cohort_implied_sigma', 'sample_sizes.national_cases_assumed', 'sample_sizes.planned_looks', 'sample_sizes.rows',
  'sample_validation.episodes', 'sample_validation.events', 'sample_validation.chronology_violations',
  'interval_log_sd.cohort_check', 'interval_log_sd.episodes', 'sample_size_check_summary.target_power', 'sample_size_check_summary.detector',
  'rest_of_country_check', 'minimum_testable_episodes', 'small_county_null', 'familywise_null', 'repeated_looks_null', 'early_warning',
  'county_detectability', 'county_population_year', 'binomial_n', 'settings.core_comparisons', 'settings.counties', 'settings.test',
  'settings.month_precision', 'settings.family', 'settings.national_cases', 'settings.assumptions', 'settings.intermediate_events', 'findings',
  'measured_text_extraction.profiles', 'measured_text_extraction.rows', 'measured_text_extraction.error_model',
  'measured_text_extraction.limits', 'measured_text_extraction.reference_episodes'];

export function buildEventLog(study, regions = [], file = FILES.eventLog) {
  needAll(study, EVENTLOG_REQUIRED, file);
  if (study.synthetic !== true) throw new Error(`${file}: the event-log study is not marked synthetic`);
  const grid = study.design_grid, target = study.sample_size_check_summary.target_power;
  const clean = (x) => x.missingness === 0 && x.month_share === 0;
  const sizes = uniq(grid.map((x) => x.n)), slowdowns = uniq(grid.map((x) => x.slowdown));
  // Every design x size x slowdown at day precision without missing dates: mean over the three planted stages.
  const comparison = [];
  for (const design of Object.keys(DESIGNS)) for (const n of sizes) for (const slowdown of slowdowns) {
    const cells = grid.filter((x) => x.design === design && x.n === n && x.slowdown === slowdown && clean(x));
    if (!cells.length) throw new Error(`${file}: design_grid has no clean cell for ${design}, n ${n}, slowdown ${slowdown}`);
    comparison.push({ design, n, slowdown, cells: cells.length,
      countyPower: cells[0].county_power == null ? null : mean(cells.map((x) => x.county_power)),
      stagePower: cells[0].stage_power == null ? null : mean(cells.map((x) => x.stage_power)),
      localisation: cells[0].localisation });
  }
  // Which columns to feature: for each planted slowdown, the county size of the grid at which the core
  // design (D3) comes closest to the target power. A rule on the data, not a hand-picked cell.
  const featured = slowdowns.map((slowdown) => comparison.filter((c) => c.design === 'D3' && c.slowdown === slowdown)
    .sort((a, b) => Math.abs(a.countyPower - target) - Math.abs(b.countyPower - target) || a.n - b.n)[0]).map((c) => ({ n: c.n, slowdown: c.slowdown }));
  // Observation conditions for the core design: mean over stages, slowdowns and sizes.
  const conditions = study.power_gap_by_condition.map((g) => {
    const cells = grid.filter((x) => x.design === 'D3' && x.missingness === g.missingness && x.month_share === g.month_share);
    return { missingness: g.missingness, monthShare: g.month_share, cells: cells.length, meanCountyPower: mean(cells.map((x) => x.county_power)),
      meanStagePower: mean(cells.map((x) => x.stage_power)), largestGapToFormula: g.largest_gap,
      cellsBelowMinimumN: cells.filter((x) => x.expected_testable_episodes < study.minimum_testable_episodes).length };
  });
  const ext = study.text_extraction.filter((x) => x.design === 'D3');
  const extraction = [];
  for (const eType of uniq(ext.map((x) => x.e_type))) for (const eDate of uniq(ext.map((x) => x.e_date))) {
    const cells = ext.filter((x) => x.e_type === eType && x.e_date === eDate);
    extraction.push({ typeErrorRate: eType, dateErrorRate: eDate, cells: cells.length, n: cells[0].n, slowdown: cells[0].slowdown,
      meanStagePower: mean(cells.map((x) => x.stage_power)), meanLocalisationPowerLoss: mean(cells.map((x) => x.localisation_power_loss)),
      meanMedianBiasDays: mean(cells.map((x) => x.median_bias_days)) });
  }
  const names = Object.fromEntries(regions.map((r) => [r.regionId ?? r.id, (r.name ?? r.nameEn ?? '').replace(' wellbeing services county', '')]));
  const s = study.sample_sizes;
  const counties = study.county_detectability.map((c) => ({ ...c, name: names[c.county] ?? c.county }));
  const worst = (c, period) => Math.max(...Object.values(c[`min_detectable_slowdown_${period}`]));
  const mx = study.measured_text_extraction;
  return {
    synthetic: true, statement: SYNTHETIC,
    source: { file, sha256: sha256(file), seed: study.seed, replications: study.replications, document: 'DATA_COLLECTION.md', results: 'eventlog/RESULTS.md' },
    format: { table: 'pathway_events (Parquet, one row per event)', pathwayOrder: study.pathway_order, events: study.pathway_order.split(' <= '), coreFour: CORE_FOUR, intervals: INTERVALS,
      orderIsAConvention: 'The order is the simulator\'s convention; on real records a reversed pair is a flag for review, not an error.' },
    sample: study.sample_validation,
    sampleSizes: { formula: s.formula, restOfCountryFormula: s.rest_of_country_formula, idealisedSigma: s.idealised_sigma, sigmaByInterval: s.sigma_by_interval,
      cohortImpliedSigma: s.cohort_implied_sigma, nationalCasesAssumed: s.national_cases_assumed, plannedLooks: s.planned_looks, rows: s.rows,
      targetPower: target, comparisons: study.settings.core_comparisons, counties: study.settings.counties },
    cohortCheck: study.interval_log_sd.cohort_check, calibrationEpisodes: study.interval_log_sd.episodes,
    formulaCheck: { summary: study.sample_size_check_summary, restOfCountry: study.rest_of_country_check },
    designs: { labels: DESIGNS, condition: 'day-precision dates, no missing dates; mean over the three planted intervals', sizes, slowdowns, comparison,
      featured, featuredRule: 'for each planted slowdown, the county size of the grid at which the core design (D3) comes closest to the target power' },
    observation: { minimumTestableEpisodes: study.minimum_testable_episodes, conditions },
    nulls: { smallCounty: study.small_county_null, familywise: study.familywise_null.filter((x) => x.design === 'D3'), repeatedLooks: study.repeated_looks_null },
    earlyWarning: study.early_warning.filter((x) => x.design === 'D3' || x.design === 'D2').map((x) => pick(x, ['design', 'stage', 'slowdown', 'n_per_quarter', 'quarters', 'onset_quarter',
      'window_quarters', 'looks_in_family', 'detected_by_quarter12', 'pre_onset_false_alarm_rate', 'median_quarters_to_detection', 'localisation'])),
    extraction: { design: 'D3', note: 'assumed extraction errors (wrong event type, wrong date), drawn at fixed rates', rows: extraction },
    measuredExtraction: {
      note: 'the measured per-event error of the scribe adapters, fed back into the same detector',
      errorModel: mx.error_model, limits: mx.limits, referenceEpisodes: mx.reference_episodes,
      profiles: mx.profiles.map((p) => pick(p, ['profile', 'system', 'true_events', 'events_with_type_found', 'exact_dates', 'wrong_date_share', 'missing_share',
        'largest_absolute_error_days', 'extra_predicted_events', 'check'])),
      rows: mx.rows.map((r) => pick(r, ['kind', 'condition', 'profile', 'n', 'stage', 'slowdown', 'replications', 'stage_power', 'county_power',
        'county_false_positive_rate', 'nominal_at_most', 'median_bias_days', 'true_median_days', 'mean_complete_episodes'])),
    },
    counties,
    // How many counties could detect each slowdown of the sizing table in every interval, per period.
    reach: s.rows.map((r) => ({ slowdown: r.slowdown, quarter: counties.filter((c) => worst(c, 'quarter') <= r.slowdown).length,
      year: counties.filter((c) => worst(c, 'year') <= r.slowdown).length })),
    countyPopulationYear: study.county_population_year,
    gaps: pick(study, ['largest_absolute_power_gap', 'largest_power_gap_day_precision_complete', 'largest_sample_size_check_gap', 'largest_idealised_power_gap']),
    binomialN: study.binomial_n,
    settings: pick(study.settings, ['test', 'month_precision', 'family', 'national_cases', 'assumptions', 'intermediate_events']),
    findings: study.findings,
  };
}

// ------------------------------------------------------------------ 2. pathway scribe
// 2a. Version-2 ablation on one GPU: what was selected and what was dropped for time.
const ABLATION_REQUIRED = ['synthetic', 'status', 'host', 'started_utc', 'finished_utc', 'budget.minutes', 'budget.elapsed_seconds', 'protocol.steps',
  'protocol.effective_batch', 'protocol.selection_metric', 'protocol.seed', 'data.val', 'data.test', 'data.train', 'runs', 'selection.run', 'selection.description',
  'selection.validation_exact_match', 'selection.decoding_check.rationale', 'test.decoding',
  'test.systems.selected.splits.test_nemotron.note_exact_match', 'test.systems.selected.splits.test_haiku.note_exact_match',
  'test.systems.selected.splits.test_nemotron.event_f1', 'test.systems.selected.splits.test_haiku.event_f1',
  'test.systems.selected.splits.test_nemotron.route_accuracy', 'test.systems.selected.splits.test_haiku.route_accuracy',
  'test.systems.selected.splits.test_nemotron.invalid_output', 'test.systems.selected.splits.test_haiku.invalid_output',
  'dropped', 'stages.A.arms', 'stages.B.arms', 'stages.B.arms_completed', 'stages.C_format.arms', 'stages.C_format.arms_completed',
  'stages.C_data.arms', 'stages.C_data.arms_completed', 'stages.finalists'];
export function buildAblation(ab, file = FILES.ablation) {
  needAll(ab, ABLATION_REQUIRED, file);
  if (ab.synthetic !== true) throw new Error(`${file}: the ablation is not marked synthetic`);
  const rows = (o) => Object.values(o).reduce((sum, x) => sum + need(x, 'rows', file), 0);
  const sel = ab.test.systems.selected.splits;
  const split = (x) => ({ exact: x.note_exact_match, eventF1: x.event_f1, route: x.route_accuracy, invalid: x.invalid_output });
  const notRun = ['B', 'C_format', 'C_data'].flatMap((st) => ab.stages[st].arms.filter((a) => !ab.stages[st].arms_completed.includes(a)).map((a) => ({ stage: st, arm: a })));
  return {
    source: src(file), status: ab.status, host: ab.host, startedUtc: ab.started_utc, finishedUtc: ab.finished_utc,
    budgetMinutes: ab.budget.minutes, elapsedSeconds: ab.budget.elapsed_seconds, steps: ab.protocol.steps, effectiveBatch: ab.protocol.effective_batch, seed: ab.protocol.seed,
    selectionMetric: ab.protocol.selection_metric,
    notes: { validation: rows(ab.data.val), test: rows(ab.data.test), train: Object.fromEntries(Object.entries(ab.data.train).map(([k, v]) => [k, v.rows])) },
    trained: Object.entries(ab.runs).map(([name, r]) => ({ name, description: need(r, 'description', file), status: need(r, 'status', file), validation: need(r, 'val.note_exact_match', file) })),
    selected: { run: ab.selection.run, description: ab.selection.description, validation: ab.selection.validation_exact_match, decodingCheck: ab.selection.decoding_check.rationale },
    test: { decoding: ab.test.decoding, nemotron: split(sel.test_nemotron), haiku: split(sel.test_haiku) },
    ladder: ab.stages.A.arms,
    dropped: ab.dropped.map((d) => pick(d, ['stage', 'item', 'reason'])),
    armsNotRun: notRun, laterArms: ['B', 'C_format', 'C_data'].reduce((sum, st) => sum + ab.stages[st].arms.length, 0),
    finalists: ab.stages.finalists.flatMap((f) => (f.comparisons || []).map((c) => ({ ...pick(c, ['a', 'b', 'a_exact', 'b_exact', 'a_only_correct', 'b_only_correct', 'exact_p']), rationale: f.rationale }))),
  };
}

// 2b. Post-ablation students: one paired comparison file, plus validation figures and epochs.
const COMPARE_REQUIRED = ['synthetic', 'preregistration.file', 'preregistration.sha256', 'decoding', 'reference.run', 'reference.summary.test_nemotron.note_exact_match',
  'reference.summary.test_haiku.note_exact_match', 'reference.summary.pooled.note_exact_match', 'reference.summary.test_haiku.by_kind.no_event',
  'comparisons', 'posthoc', 'missing', 'multiplicity'];
const RUN_REQUIRED = ['run', 'what', 'summary.test_nemotron.note_exact_match', 'summary.test_haiku.note_exact_match', 'summary.pooled.note_exact_match',
  'summary.test_haiku.by_kind.no_event', 'summary.test_nemotron.event_f1', 'summary.test_haiku.event_f1',
  'paired_vs_reference.test_nemotron', 'paired_vs_reference.test_haiku', 'paired_vs_reference.pooled'];
export function buildStudents(cmp, figures, prereg, files = { compare: FILES.compare, figures: FILES.trainingFigures, prereg: FILES.preregistration }) {
  needAll(cmp, COMPARE_REQUIRED, files.compare);
  needAll(figures, ['validation_pairs.validation_exact_match', 'validation_pairs.n_validation_notes', 'validation_pairs.pairs', 'validation_pairs.note', 'epochs'], files.figures);
  needAll(prereg, ['frozen', 'frozen_utc', 'primary.run', 'primary.endpoint', 'multiplicity', 'size_ladder'], files.prereg);
  if (cmp.synthetic !== true) throw new Error(`${files.compare}: the comparison is not marked synthetic`);
  const figKey = (run) => {
    const k = Object.keys(figures.epochs).find((x) => x === run || x.startsWith(`${run} `));
    if (!k) throw new Error(`${files.figures}: no epochs entry for ${run}`);
    if (!(k in figures.validation_pairs.validation_exact_match)) throw new Error(`${files.figures}: no validation exact match for ${run}`);
    return k;
  };
  const epochs = (run) => needAll(figures.epochs[figKey(run)], ['train_rows', 'steps', 'effective_batch', 'epochs'], files.figures);
  const summary = (x) => ({ nemotron: x.test_nemotron.note_exact_match, haiku: x.test_haiku.note_exact_match, pooled: x.pooled.note_exact_match,
    haikuNoEvent: x.test_haiku.by_kind.no_event, eventF1: { nemotron: x.test_nemotron.event_f1, haiku: x.test_haiku.event_f1 } });
  const runRow = (r, kind) => {
    needAll(r, RUN_REQUIRED, files.compare);
    return { run: r.run, what: r.what, kind, sha256: r.sha256 ?? null, file: r.file ?? null, validation: figures.validation_pairs.validation_exact_match[figKey(r.run)],
      training: epochs(r.run), ...summary(r.summary), paired: r.paired_vs_reference };
  };
  return {
    source: [src(files.compare), src(files.figures), src(files.prereg)],
    preregistration: { file: cmp.preregistration.file, sha256: cmp.preregistration.sha256, frozenUtc: prereg.frozen_utc, primary: prereg.primary.run,
      endpoint: prereg.primary.endpoint, sizeLadder: prereg.size_ladder },
    decoding: cmp.decoding, multiplicity: cmp.multiplicity,
    reference: { run: cmp.reference.run, kind: 'reference', validation: figures.validation_pairs.validation_exact_match[figKey(cmp.reference.run)],
      training: epochs(cmp.reference.run), ...summary(cmp.reference.summary) },
    runs: [...cmp.comparisons.map((r) => runRow(r, 'pre-registered')), ...cmp.posthoc.map((r) => runRow(r, 'post hoc'))],
    missing: cmp.missing,
    validationNotes: figures.validation_pairs.n_validation_notes,
    validationPairs: figures.validation_pairs.pairs.map((p) => ({ first: p.first, second: p.second, ...pick(p.all, ['n', 'only_first_correct', 'only_second_correct', 'exact_mcnemar_p', 'holm_adjusted_p_over_all_pairs']) })),
    validationPairsNote: figures.validation_pairs.note,
  };
}

// 2c. Serving smoke test of the selected adapter on vLLM.
const SMOKE_REQUIRED = ['synthetic', 'ts', 'n', 'served_models', 'settings.guided', 'settings.concurrency', 'settings.max_tokens', 'requests.answered', 'requests.valid_output',
  'requests.invalid_output', 'requests.failed', 'exact_match', 'valid_output_rate', 'route_accuracy', 'event_f1', 'latency_seconds.p50', 'latency_seconds.p95',
  'latency_seconds.n', 'notes_per_second', 'decisions', 'review_reasons', 'notes_sha256', 'passed', 'limits'];
export function buildServing(guided, plain, figures, files = { guided: FILES.smokeGuided, plain: FILES.smokePlain, figures: FILES.trainingFigures }) {
  for (const [s, f] of [[guided, files.guided], [plain, files.plain]]) {
    needAll(s, SMOKE_REQUIRED, f);
    if (s.synthetic !== true) throw new Error(`${f}: the smoke result is not marked synthetic`);
  }
  needAll(figures, ['serving_parity.by_split', 'serving_parity.in_process_exact', 'serving_parity.notes_sha256', 'serving_parity.structured_outputs.same_verdict_on_every_note',
    'serving_parity.structured_outputs.compare_offline.same_prediction', 'serving_parity.plain.compare_offline.same_prediction',
    'serving_parity.structured_outputs.compare_offline.n', 'serving_parity.structured_outputs.compare_offline.offline_max_new_tokens',
    'serving_parity.structured_outputs.compare_offline.served_max_tokens', 'machine_cost.machine', 'machine_cost.instance_type'], files.figures);
  if (figures.serving_parity.notes_sha256 !== guided.notes_sha256 || guided.notes_sha256 !== plain.notes_sha256) throw new Error(`${files.figures}: the serving parity was computed on other notes than the smoke runs`);
  const run = (s) => ({ guided: s.settings.guided, n: s.n, answered: s.requests.answered, validOutput: s.requests.valid_output, invalidOutput: s.requests.invalid_output,
    failed: s.requests.failed, exact: s.exact_match, valid: s.valid_output_rate, route: s.route_accuracy, eventF1: s.event_f1,
    latency: pick(s.latency_seconds, ['p50', 'p95', 'n', 'definition']), notesPerSecond: s.notes_per_second, decisions: s.decisions, reviewReasons: s.review_reasons, passed: s.passed });
  const p = figures.serving_parity;
  return {
    source: [src(files.guided), src(files.plain), src(files.figures)],
    ts: guided.ts, servedModels: guided.served_models, concurrency: guided.settings.concurrency, maxTokens: guided.settings.max_tokens, limits: guided.limits,
    machine: figures.machine_cost.machine, instanceType: figures.machine_cost.instance_type,
    guided: run(guided), plain: run(plain),
    parity: { bySplit: p.by_split, inProcessExact: p.in_process_exact, sameVerdictEveryNote: p.structured_outputs.same_verdict_on_every_note && p.plain.same_verdict_on_every_note,
      samePredictionGuided: p.structured_outputs.compare_offline.same_prediction, samePredictionPlain: p.plain.compare_offline.same_prediction,
      n: p.structured_outputs.compare_offline.n, offlineMaxNewTokens: p.structured_outputs.compare_offline.offline_max_new_tokens, servedMaxTokens: p.structured_outputs.compare_offline.served_max_tokens },
  };
}

// 2d. Teaching loop (teacher round 2, two judges, gate, audit, cascade) from the flat summary.
const SIGNAL_LABELS = { student: 'student confidence alone', jev: 'Jev score alone', 'student+jev': 'student + Jev (logistic)', decisions: 'Decisions score alone',
  'student+jev+decisions': 'student + Jev + Decisions' };
const RULE_LABELS = { jev: 'Jev, first question set', jev_hint: 'Jev, second question set (the rule used)', decisions: 'OpenAI Decisions',
  both: 'both judges must pass a note', either: 'either judge may pass a note' };
const CURRICULA = ['hard_standard', 'careful', 'no_event', 'long_multi_visit', 'terse'];
export function buildTeaching(summary, file = FILES.teaching) {
  const get = flatReader(summary, file);
  if (get('synthetic_only') !== true || get('not_for_clinical_use') !== true) throw new Error(`${file}: the teaching summary is not marked synthetic and not for clinical use`);
  for (const k of ['_sources', '_docs', '_not_done']) if (!(k in summary)) throw new Error(`${file}: required key "${k}" is missing`);
  const targets = uniq(get.keys().map((k) => /^cascade\.student\.(\d+)pct\.validation_threshold$/.exec(k)?.[1]).filter(Boolean).map(Number)).sort((a, b) => a - b);
  if (!targets.length) throw new Error(`${file}: no cascade targets (cascade.student.<n>pct.*) found`);
  const cell = (prefix, t) => ({
    target: t,
    ...(get.has(`${prefix}.${t}pct.validation_threshold`) ? { validationThreshold: get(`${prefix}.${t}pct.validation_threshold`) } : {}),
    pooled: { coverage: get.share(`${prefix}.${t}pct.test_pooled.coverage`), error: get.share(`${prefix}.${t}pct.test_pooled.error_among_accepted`) },
    nemotron: { coverage: get.share(`${prefix}.${t}pct.test_nemotron.coverage`), error: get.share(`${prefix}.${t}pct.test_nemotron.error_among_accepted`) },
    haiku: { coverage: get.share(`${prefix}.${t}pct.test_haiku.coverage`), error: get.share(`${prefix}.${t}pct.test_haiku.error_among_accepted`) },
    ...(get.has(`${prefix}.${t}pct.test_pooled.coverage_difference_vs_student`) ? { vsStudent: {
      coverageDifference: get(`${prefix}.${t}pct.test_pooled.coverage_difference_vs_student`),
      coverageDifference95: get(`${prefix}.${t}pct.test_pooled.coverage_difference_vs_student95`),
      errorDifference95: get(`${prefix}.${t}pct.test_pooled.error_difference_vs_student95`),
      coverageDifferenceRechosen95: get(`${prefix}.${t}pct.pipeline.coverage_difference_vs_student95`),
      errorDifferenceRechosen95: get(`${prefix}.${t}pct.pipeline.error_difference_vs_student95`) } } : {}),
  });
  const signals = ['student', 'jev', 'student+jev'].map((sig) => ({ signal: sig, label: SIGNAL_LABELS[sig], byTarget: targets.map((t) => cell(`cascade.${sig}`, t)),
    aurc: get(`cascade.${sig}.aurc.test_pooled`),
    ...(sig === 'student' ? {} : { aurcDifference: get(`cascade.${sig}.aurc_difference_vs_student.test_pooled`), aurcDifference95: get(`cascade.${sig}.aurc_difference_vs_student95.test_pooled`) }) }));
  const subset = ['student', 'decisions', 'student+jev', 'student+jev+decisions'].map((sig) => ({ signal: sig, label: SIGNAL_LABELS[sig],
    byTarget: targets.map((t) => ({ target: t, coverage: get.share(`cascade.decisions_subset.${sig}.${t}pct.coverage`), error: get.share(`cascade.decisions_subset.${sig}.${t}pct.error_among_accepted`) })),
    aurc: get(`cascade.decisions_subset.${sig}.aurc`) }));
  const rules = Object.keys(RULE_LABELS).map((r) => ({ rule: r, label: RULE_LABELS[r], caught: get.share(`judges.report160.${r === 'jev_hint' ? 'jev_hint' : r}.caught`),
    falseReject: get.share(`judges.report160.${r}.false_reject`) }));
  return {
    synthetic: true, source: [src(file)], generatedUtc: get('generated_utc'), docs: summary._docs, notDone: summary._not_done,
    teacher: {
      specifications: get('teacher.specifications.built'), completed: get('teacher.specifications.completed'), requests: get('teacher.requests_ledger'), requestCap: get('teacher.requests_cap'),
      codeCheckFirst: get.share('teacher.overall.code_check_pass_first_attempt', { ci: false }), codeCheckFinal: get.share('teacher.overall.code_check_pass_final', { ci: false }),
      readbackFinal: get.share('teacher.overall.readback_consistent_final', { ci: false }), cleanFinal: get.share('teacher.overall.clean_final', { ci: false }),
      repairAttempted: get.share('teacher.overall.repair_attempted', { ci: false }), repairSuccess: get.share('teacher.overall.repair_success', { ci: false }),
      noEventReadback: get.share('teacher.no_event.readback_consistent_final', { ci: false }),
    },
    judges: { rule: get('judges.policy.rule'), questionSet: get('judges.policy.jev_question_set'), chosenOn: get('judges.policy.chosen_on'), rules,
      kappa: get('judges.agreement.cohen_kappa_pass_fail'), missedByBoth: get.share('judges.agreement.corrupted_missed_by_both'),
      cost: Object.fromEntries(['jev', 'jev_hint', 'decisions'].map((j) => [j, { usdPer1000Notes: get(`judges.cost.${j}.usd_per_1000_notes`), p50: get(`judges.cost.${j}.latency_s_p50`), p95: get(`judges.cost.${j}.latency_s_p95`) }])) },
    gate: { candidates: get('gate.overall.candidates'), codeCheck: get.share('gate.overall.code_check_pass', { ci: false }), readback: get.share('gate.overall.readback_consistent', { ci: false }),
      acceptedOfJudged: get.share('gate.overall.rule_accepted_of_judged', { ci: false }), acceptedOfCandidates: get.share('gate.overall.rule_accepted_of_candidates', { ci: false }),
      readbackVsRule: get('gate.overall.readback_vs_rule'), decisionsAccepted: get.share('gate.overall.decisions_accepted', { ci: false }),
      byCurriculum: CURRICULA.map((c) => ({ curriculum: c, accepted: get.share(`gate.${c}.rule_accepted_of_candidates`, { ci: false }) })) },
    dataset: { trainRows: get('dataset.train_rows'), fromV2: get('dataset.train_rows_from_v2'), fromRound2: get('dataset.train_rows_from_round2'),
      readbackInconsistent: get('dataset.round2_added_to_train_readback_inconsistent'), startsWithStyleLabel: get('dataset.round2_added_to_train_starts_with_style_label') },
    audit: { sampling: get('audit.sampling'), verdicts: get('audit.verdicts_total'),
      accepted: { wrongLabel: get.share('audit.accepted.wrong_label'), routeNotOk: get.share('audit.accepted.route_not_ok'), either: get.share('audit.accepted.wrong_label_or_route_not_ok') },
      rejected: { wrongLabel: get.share('audit.rejected.wrong_label'), routeNotOk: get.share('audit.rejected.route_not_ok'), either: get.share('audit.rejected.wrong_label_or_route_not_ok') } },
    studentNoResult: get.keys().filter((k) => k.startsWith('student.') && summary[k] === null).map((k) => ({ key: k, run: k.split('.')[1], reason: get.notDone[k] })),
    cascade: { chosenStudent: get('cascade.chosen_student'), choiceReason: get('cascade.student_choice_reason'), thresholdRule: get('cascade.threshold_rule'),
      empiricalNotGuaranteed: get('cascade.empirical_not_guaranteed'), verdict: (get('cascade.verdict') || []).map(oneClickWording), targets, signals,
      aurcBest: get('cascade.aurc_best_possible.test_pooled'), aurcRandom: get('cascade.aurc_random_order.test_pooled'),
      decisionsSubset: { perSplit: get('cascade.decisions_subset.per_split'), signals: subset },
      cost: Object.fromEntries(['jev', 'decisions'].map((j) => [j, { notesAnswered: get(`cascade.cost.${j}.notes_answered`), errors: get(`cascade.cost.${j}.errors`),
        usdPer1000Notes: get(`cascade.cost.${j}.usd_per_1000_notes`), p50: get(`cascade.cost.${j}.latency_s_p50`), p95: get(`cascade.cost.${j}.latency_s_p95`) }])) },
    cost: { typesafe: { requests: get('cost.typesafe.requests'), tokens: get('cost.typesafe.tokens'), usd: get('cost.typesafe.usd') },
      openai: { requests: get('cost.openai_decisions.requests'), tokens: get('cost.openai_decisions.tokens'), usdListRate: get('cost.openai_decisions.usd_list_rate') },
      nemotron: { requests: get('cost.nemotron.requests'), usd: get('cost.nemotron.usd'), usdMissingBecause: get.notDone['cost.nemotron.usd'] ?? null },
      haikuAudit: { usd: get('cost.haiku_audit.tokens_and_usd'), missingBecause: get.notDone['cost.haiku_audit.tokens_and_usd'] ?? null } },
  };
}

// 2e. Version 1 (laptop fallback), kept as history. Superseded by the version-2 ablation and the students above.
const slim = (m) => pick(m, ['precision', 'recall', 'f1', 'type_only_f1', 'note_exact_match', 'route_accuracy', 'distractor_extraction']);
const slimLenient = (m) => pick(m, ['precision', 'recall', 'f1', 'note_match_ignoring_precision', 'route_accuracy', 'unreadable']);
const V1_REQUIRED = ['synthetic', 'meta.gpu.planned_model', 'meta.fallback', 'meta.gpu.setup', 'meta.base_model_snapshot', 'meta.framework', 'meta.host_hardware',
  'meta.training', 'meta.haiku', 'counts.test', 'counts.extra_test', 'base_model', 'decoding', 'max_new_tokens', 'test', 'extra_test', 'by_relative_date.test',
  'by_relative_date.extra_test', 'lenient.definition', 'lenient.test', 'lenient.extra_test', 'predictions'];
export function buildScribeV1(ev, post = null, stats = null, prov = null, haiku = [], labelAudit = null) {
  needAll(ev, V1_REQUIRED, FILES.scribeEval);
  if (ev.synthetic !== true) throw new Error(`${FILES.scribeEval}: the scribe evaluation is not marked synthetic`);
  if (post) needAll(post, ['selective.limits', 'selective.validation_notes', 'selective.notes_needed_without_error_for_claim', 'adapter_all_test', 'pathway_order_check'], FILES.scribePost);
  const m = ev.meta, n = ev.counts.test;
  const part = (p) => ({ base: slim(p.base), adapter: slim(p.adapter), mcnemar: p.mcnemar,
    inSampleRiskCoverage: { note: 'cut-off chosen and scored on the same notes; optimistic', base: p.risk_coverage.base.largest_empirical_coverage, adapter: p.risk_coverage.adapter.largest_empirical_coverage },
    byDateForm: Object.fromEntries(Object.entries(p.by_date_form).map(([k, v]) => [k, { notes: v.notes ?? v.n ?? null, base: slim(v.base ?? {}), adapter: slim(v.adapter ?? {}) }])) });
  const rel = (p) => Object.fromEntries(Object.entries(p).map(([k, v]) => [k, { base: slim(v.base), adapter: slim(v.adapter) }]));
  // Two SYNTHETIC examples from the notes written by the independent writer: the first the adapter
  // gets exactly right and the first it gets wrong. Chosen by position, not by hand.
  const examples = [];
  const preds = ev.predictions.slice(n);
  for (const want of [true, false]) {
    const i = haiku.findIndex((h, k) => preds[k] && (JSON.stringify(preds[k].adapter) === JSON.stringify(JSON.parse(h.target_json))) === want);
    if (i >= 0) examples.push({ synthetic: true, writer: haiku[i].writer, noteDate: haiku[i].note_date, noteText: haiku[i].note_text, dateForms: haiku[i].date_forms,
      truth: JSON.parse(haiku[i].target_json), adapter: preds[i].adapter, adapterCorrect: want, confidence: preds[i].adapter_mean_json_logprob });
  }
  return {
    superseded: true, supersededBy: 'the version-2 ablation on a GPU and the post-ablation students',
    source: { evaluation: FILES.scribeEval, evaluationSha256: sha256(FILES.scribeEval), postEvaluation: post ? FILES.scribePost : null,
      postEvaluationSha256: post ? sha256(FILES.scribePost) : null, results: 'scribe/RESULTS.md' },
    plannedRun: { model: m.gpu.planned_model, executed: false, what: m.fallback, setup: m.gpu.setup, unreachableFromUtc: m.gpu.unreachable_from_utc ?? null, hostKeyChangedUtc: m.gpu.host_key_changed_utc ?? null },
    models: { base: ev.base_model, baseSnapshot: m.base_model_snapshot, framework: m.framework, hardware: m.host_hardware, provenance: prov },
    dataset: stats ? { counts: stats.counts, generated: stats.generated, codeCheckFailure: stats.code_check_failure, verifierRejectionGivenCodePass: stats.verifier_rejection_given_code_pass,
      duplicateRowsRemoved: stats.duplicate_episode_rows_removed, dateForms: stats.date_forms, audit: stats.audit, usage: stats.usage } : null,
    training: m.training,
    decoding: { decoding: ev.decoding, maxNewTokens: ev.max_new_tokens },
    test: { n, ...part(ev.test), byRelativeDate: rel(ev.by_relative_date.test) },
    haiku: { n: ev.counts.extra_test, ...part(ev.extra_test), byRelativeDate: rel(ev.by_relative_date.extra_test), writer: m.haiku },
    lenient: { definition: ev.lenient.definition, test: { base: slimLenient(ev.lenient.test.base), adapter: slimLenient(ev.lenient.test.adapter), mcnemar: ev.lenient.test.mcnemar },
      haiku: { base: slimLenient(ev.lenient.extra_test.base), adapter: slimLenient(ev.lenient.extra_test.adapter), mcnemar: ev.lenient.extra_test.mcnemar } },
    invalidJson: { test: { base: ev.predictions.slice(0, n).filter((p) => p.base == null).length, adapter: ev.predictions.slice(0, n).filter((p) => p.adapter == null).length },
      haiku: { base: preds.filter((p) => p.base == null).length, adapter: preds.filter((p) => p.adapter == null).length } },
    examples,
    labelAudit: labelAudit ? pick(labelAudit, ['auditor', 'n', 'label_correct', 'label_wrong', 'wrong_rate', 'wilson95', 'by_category', 'limits']) : null,
    selective: post ? post.selective : null,
    adapterAllTest: post ? post.adapter_all_test : null,
    orderCheck: post ? post.pathway_order_check : null,
    splitOverlap: post ? post.split_overlap ?? null : null,
    dedup: post ? post.dedup_report ?? null : null,
  };
}

// ------------------------------------------------------------------ 3. Evo 2 on BRCA1
const GENOMICS_REQUIRED = ['statement', 'status', 'status_reason', 'generated_utc', 'model.name', 'model.repository', 'model.revision', 'model.licence', 'model.route', 'data', 'limits'];
const GENOMICS_RUN_REQUIRED = ['headline.evidence_strength_basis', 'headline.labels', 'headline.variants_scored', 'headline.variants_in_table', 'headline.n_lof', 'headline.n_func',
  'headline.missense_n_lof', 'headline.missense_n_func', 'headline.auroc_lof_vs_func', 'headline.auroc_missense', 'headline.missense_strongest_reached',
  'headline.missense_strongest_reached_with_clustered_exact_bound_in_every_bin', 'headline.missense_n_bins', 'headline.evo2_minus_cadd_same_variants',
  'headline.all_consequences_strongest_reached_reference_only', 'headline.window_caveat', 'gpu_host.host', 'gpu_host.gpu', 'gpu_host.provider', 'gpu_host.status',
  'method.window_bp', 'method.notebook_window_bp', 'runtime', 'metrics.interval_method', 'metrics.auroc_lof_vs_func', 'metrics.auroc_by_consequence',
  'metrics.average_precision_lof_vs_func', 'metrics.calibration', 'missense_evidence.n_lof', 'missense_evidence.n_func', 'missense_evidence.n_bins',
  'missense_evidence.likelihood_ratio_table.rows', 'missense_evidence.strongest_reached', 'missense_evidence.bin_count_sensitivity',
  'acmg_amp_evidence.tavtigian2018.strength_targets', 'acmg_amp_evidence.tavtigian2018.strongest_reached', 'acmg_amp_evidence.pejaver2022.strongest_reached',
  'likelihood_ratio_table.rows', 'likelihood_ratio_table.bound_definition', 'same_sample_comparison.scores', 'same_sample_comparison.evo2_minus', 'same_sample_comparison.n_variants',
  'windows_compared.by_window', 'windows_compared.difference_longer_minus_shorter', 'windows_compared.spearman_between_windows', 'baselines_from_supplement'];
export function buildGenomics(g, file = FILES.genomics) {
  needAll(g, GENOMICS_REQUIRED, file);
  if (!/research use only/i.test(g.statement || '')) throw new Error(`${file}: the genomics result does not carry the research-only statement`);
  const base = { research: true, statement: RESEARCH, status: g.status, statusReason: g.status_reason,
    source: { file, sha256: sha256(file), generatedUtc: g.generated_utc, readme: 'genomics/README.md' },
    model: g.model, data: pick(g.data, ['benchmark', 'citation', 'url', 'sha256', 'coordinates', 'variants_in_table', 'variants_scored', 'counts_by_class', 'counts_by_consequence']),
    published: g.published_values_not_reproduced ?? null, limits: g.limits };
  if (g.status === 'not_run') return { ...base, baselines: g.baselines_from_supplement ? baselines(g.baselines_from_supplement) : null };
  needAll(g, GENOMICS_RUN_REQUIRED, file);
  const m = g.metrics;
  const evidence = (a) => Object.fromEntries(Object.entries(a).map(([k, v]) => [k, pick(v, ['prior', 'source', 'strength_targets', 'thresholds', 'share_reaching_at_least', 'strongest_reached', 'consequence_mix_at_or_above_pathogenic_threshold'])]));
  const rows = (t) => t.rows.map((r) => pick(r, ['bin', 'score_min', 'score_max', 'n_lof', 'n_func', 'lr_plus', 'lr_lower_95_one_sided', 'lr_upper_95_one_sided', 'pathogenic_strength_tavtigian2018', 'pathogenic_strength_pejaver2022']));
  return { ...base,
    headline: g.headline,
    gpuHost: pick(g.gpu_host, ['host', 'gpu', 'provider', 'status', 'basis', 'end_state']),
    method: pick(g.method, ['window_bp', 'strand', 'window_rule', 'delta', 'notebook_window_bp', 'deviations_from_notebook', 'window_choice']),
    runtime: pick(g.runtime, ['host', 'seconds_per_forward', 'score_seconds_this_run', 'peak_allocated_bytes', 'nvidia_smi_process_mib_max_sampled', 'cap_gib', 'complete', 'stopped_early_by_time_budget']),
    metrics: { intervalMethod: m.interval_method, countsScoredByClass: m.counts_scored_by_class, positionsScored: m.positions_scored,
      auroc: pick(m.auroc_lof_vs_func, ['value', 'ci95', 'n_pos', 'n_neg']), aurocNotebookDefinition: pick(m.auroc_lof_vs_func_and_int, ['value', 'ci95']),
      averagePrecision: pick(m.average_precision_lof_vs_func, ['value', 'ci95', 'prevalence_lof']), byConsequence: m.auroc_by_consequence,
      calibration: pick(m.calibration, ['method', 'brier_score', 'brier_score_prevalence_only', 'expected_calibration_error']), sensitivity: m.sensitivity,
      clinvar: m.clinvar_cross_check, binCountSensitivity: m.bin_count_sensitivity },
    windowsCompared: g.windows_compared,
    sameSample: g.same_sample_comparison,
    missenseEvidence: { ...pick(g.missense_evidence, ['n_lof', 'n_func', 'n_bins', 'bin_rule', 'bin_rule_set', 'why', 'strongest_reached', 'strongest_reached_with_clustered_exact_bound_in_every_bin', 'bin_count_sensitivity', 'note']),
      rows: rows(g.missense_evidence.likelihood_ratio_table) },
    evidenceAllConsequences: { evidence: evidence(g.acmg_amp_evidence), rows: rows(g.likelihood_ratio_table), boundDefinition: g.likelihood_ratio_table.bound_definition },
    baselines: baselines(g.baselines_from_supplement),
  };
}

function baselines(b) {
  return Object.fromEntries(Object.entries(b).map(([k, v]) => [k, k === 'consequence_only' ? v : {
    label: v.label, nWithValue: v.n_with_value, auroc: pick(v.auroc_lof_vs_func ?? {}, ['value', 'ci95']),
    aurocMissense: pick(v.auroc_by_consequence?.Missense ?? {}, ['value', 'ci95']),
    strongestReached: Object.fromEntries(Object.entries(v.acmg_amp_evidence ?? {}).map(([c, e]) => [c, e.strongest_reached])), missenseStrongestReached: v.missense_strongest_reached ?? null }]));
}

// ------------------------------------------------------------------ 4. safety-net worklist (DO #2)
// Rendered on the page by web/safetynet.mjs, which reads the file's own shape; the bundle keeps that shape
// and adds the source and its SHA-256. Every field the panel reads is required. A county carries at most
// three example rows, every row is SYNTHETIC, and every numeric clock threshold is labelled PLACEHOLDER.
const SAFETYNET_REQUIRED = ['schemaVersion', 'schemaDoc', 'dataClass', 'synthetic', 'generatedAt', 'asOf', 'pilotRegionId',
  'text.title', 'text.synthetic', 'text.clock', 'text.as_of', 'text.governance', 'text.legal', 'text.legal_url', 'text.regulatory', 'text.pilot',
  'text.scope', 'text.rule', 'text.neutrality', 'text.roadmap', 'thresholds', 'kpis', 'suppression.below',
  'rule.version', 'rule.sha256', 'rule.caveat', 'rule.metrics.lines', 'rule.metrics.exact_due_date.k', 'rule.metrics.exact_due_date.n',
  'rule.metrics.sent_to_person_when_gold_person.k', 'rule.metrics.sent_to_person_when_gold_person.n', 'rule.metrics.none_correct.k', 'rule.metrics.none_correct.n',
  'cohort.assumptions.p_followup_on_time', 'cohort.imaging_loops.loops', 'cohort.imaging_loops.errors.wrong_due_date',
  'cohort.imaging_loops.errors.invented_date_for_person_line', 'cohort.imaging_loops.errors.invented_date_for_none_line',
  'cohort.imaging_loops.errors.missed_recommendation', 'cohort.imaging_loops.errors.due_line_sent_to_person',
  'national.open_loops', 'national.overdue', 'counties', 'provenance.command'];
const SAFETYNET_COUNTY_REQUIRED = ['regionId', 'name', 'synthetic', 'counts.open_loops', 'counts.overdue', 'counts.imaging.overdue', 'counts.imaging.done_by_due',
  'counts.imaging.due_passed', 'counts.referral.overdue', 'counts.referral.overdue_at_sensitivity_days', 'counts.referral.diagnosed_by_threshold',
  'counts.referral.clock_passed', 'by_route', 'by_language', 'examples'];
const SAFETYNET_EXAMPLE_REQUIRED = ['episode_code', 'loop_kind', 'age_band', 'route', 'contact_language', 'interpreter', 'days_overdue', 'missing_step', 'owner_role', 'status', 'synthetic'];
export function buildSafetyNet(data, regions = [], file = FILES.safetyNet) {
  needAll(data, SAFETYNET_REQUIRED, file);
  if (data.synthetic !== true || data.dataClass !== 'SYNTHETIC') throw new Error(`${file}: the safety-net worklist is not marked synthetic`);
  if (!Array.isArray(data.counties) || !data.counties.length) throw new Error(`${file}: no county rows`);
  const known = new Set(regions.map((r) => r.regionId ?? r.id));
  for (const c of data.counties) {
    needAll(c, SAFETYNET_COUNTY_REQUIRED, `${file} county ${c.regionId}`);
    if (c.synthetic !== true) throw new Error(`${file}: county ${c.regionId} is not marked synthetic`);
    if (known.size && !known.has(c.regionId)) throw new Error(`${file}: county ${c.regionId} is not an area of the public snapshot`);
    if (c.examples.length > 3) throw new Error(`${file}: county ${c.regionId} has ${c.examples.length} example rows; at most three are shown`);
    for (const e of c.examples) {
      needAll(e, SAFETYNET_EXAMPLE_REQUIRED, `${file} county ${c.regionId} example`);
      if (e.synthetic !== true) throw new Error(`${file}: an example row of ${c.regionId} is not marked synthetic`);
    }
  }
  if (!data.counties.some((c) => c.regionId === data.pilotRegionId)) throw new Error(`${file}: the pilot county ${data.pilotRegionId} has no row`);
  for (const t of data.thresholds) {
    needAll(t, ['clock', 'days', 'label', 'source'], `${file} threshold`);
    if (typeof t.days === 'number' && t.label !== 'PLACEHOLDER') throw new Error(`${file}: the ${t.days}-day threshold "${t.clock}" is not labelled PLACEHOLDER`);
  }
  return { ...data, statement: SYNTHETIC, source: src(file) };
}

// ------------------------------------------------------------------ 5. FLARE comparability gate (DO #3)
// Rendered by web/flare.mjs from the file's own shape. Every field the panel reads is required; the FLARE
// equivalence block is required only when the file says FLARE ran, and the public stage chip only when it
// is present (the panel shows the fallback wording otherwise). The 42-day clock must carry its placeholder label.
const GATE_REQUIRED = ['schema', 'synthetic', 'label', 'title', 'lede', 'clock.start_event', 'clock.end_event', 'clock.starts', 'clock.threshold_days',
  'clock.histogram_edge_days', 'clock.threshold_label', 'clock.threshold_text', 'clock.sources', 'rule.label', 'rule.bias_limit_days', 'rule.missed_limit',
  'rule.median_bias_definition', 'rule.missed_definition', 'rule.median_bias_computed_in', 'scribe_input.assignment', 'scribe_input.scenario', 'counties',
  'national.n', 'national.share_within', 'summary.raw.not_comparable', 'summary.raw.of', 'summary.resolver.not_comparable', 'summary.resolver.of',
  'flare.ran', 'limits'];
const GATE_FLARE_REQUIRED = ['flare.nvflare', 'flare.sites', 'flare.equivalence.success', 'flare.equivalence.cells', 'flare.equivalence.cells_ok', 'flare.equivalence.tolerance'];
const GATE_REAL_REQUIRED = ['kind', 'question', 'rule', 'aim_pct', 'areas', 'note', 'source.name', 'source.url'];
const GATE_ARM_REQUIRED = ['comparable', 'median_bias_days', 'missed_share', 'events', 'intervals'];
export function buildFlareGate(gate, regions = [], file = FILES.flareGate) {
  needAll(gate, GATE_REQUIRED, file);
  if (gate.synthetic !== true || gate.label !== 'SYNTHETIC') throw new Error(`${file}: the comparability gate is not marked synthetic`);
  if (!/placeholder/i.test(gate.clock.threshold_label)) throw new Error(`${file}: the ${gate.clock.threshold_days}-day clock threshold is not labelled a placeholder`);
  if (gate.flare.ran === true) needAll(gate, GATE_FLARE_REQUIRED, file);
  if (gate.realData != null) {
    needAll(gate.realData, GATE_REAL_REQUIRED, `${file} realData`);
    if (gate.realData.kind !== 'PUBLISHED') throw new Error(`${file}: realData is not labelled PUBLISHED`);
  }
  if (!Array.isArray(gate.counties) || !gate.counties.length) throw new Error(`${file}: no county rows`);
  const known = new Set(regions.map((r) => r.regionId ?? r.id));
  for (const c of gate.counties) {
    needAll(c, ['county', 'rtt.n', 'rtt.share_within', 'rtt.suppressed', 'completeness.complete_share', 'completeness.open_share', 'scribe.raw', 'scribe.resolver'], `${file} county ${c.county}`);
    for (const arm of ['raw', 'resolver']) needAll(c.scribe[arm], GATE_ARM_REQUIRED, `${file} county ${c.county} ${arm}`);
    if (known.size && !known.has(c.county)) throw new Error(`${file}: county ${c.county} is not an area of the public snapshot`);
  }
  return { ...gate, statement: SYNTHETIC, source: src(file) };
}

// ------------------------------------------------------------------ 6. the "fake inequality" insight
// From the event-log design study's measured_interval_extraction block (eventlog/extraction_intervals.py): the
// county detector fed with the scribe's measured interval errors, as is and with the frozen code date resolver.
// Every row the panel shows is looked up by its labels; a missing row fails the build.
const INSIGHT_REQUIRED = ['synthetic', 'findings', 'measured_interval_extraction.run', 'measured_interval_extraction.rows', 'measured_interval_extraction.limits',
  'measured_interval_extraction.error_model', 'measured_interval_extraction.extra_events_model', 'measured_interval_extraction.checks.recomputed_equals_stored',
  'measured_interval_extraction.checks.product_default_arm_Aprime_equals_A_on_these_notes', 'measured_interval_extraction.checks.frozen_at_utc',
  'measured_interval_extraction.note_exact_match.validation.as_is', 'measured_interval_extraction.note_exact_match.validation.resolver',
  'measured_interval_extraction.note_exact_match.test.as_is', 'measured_interval_extraction.note_exact_match.test.resolver', 'measured_interval_extraction.note_exact_match.test.role',
  'measured_interval_extraction.agreement_with_interval_impact_v1.compared_rates', 'measured_interval_extraction.agreement_with_interval_impact_v1.beyond_3_se',
  'measured_interval_extraction.agreement_with_interval_impact_v1.source'];
const FAKE_INEQUALITY = /^Extraction errors manufacture fake county inequality/;
export function buildInsight(study, file = FILES.eventLog) {
  needAll(study, INSIGHT_REQUIRED, file);
  if (study.synthetic !== true) throw new Error(`${file}: the event-log study is not marked synthetic`);
  const mx = study.measured_interval_extraction;
  const finding = study.findings.find((f) => FAKE_INEQUALITY.test(f));
  if (!finding) throw new Error(`${file}: the fake-inequality finding is missing from findings`);
  const row = (kind, condition, arm, writer, extras, n) => {
    const r = mx.rows.find((x) => x.kind === kind && x.condition === condition && x.arm === arm && x.writer === writer && x.extras_modelled === extras && (n == null || x.n === n));
    if (!r) throw new Error(`${file}: measured_interval_extraction has no ${kind} row for ${condition}, arm ${arm}, writer ${writer}, extras ${extras}${n == null ? '' : `, n ${n}`}`);
    return r;
  };
  const rate = (r) => ({ rate: need(r, 'county_false_positive_rate', file), ci95: need(r, 'county_false_positive_rate_ci95', file), n: need(r, 'n', file), replications: need(r, 'replications', file) });
  const pair = (condition, writer) => ({ asIs: rate(row('null', condition, 'off', writer, false)), resolver: rate(row('null', condition, 'A', writer, false)),
    asIsExtras: rate(row('null', condition, 'off', writer, true)), resolverExtras: rate(row('null', condition, 'A', writer, true)) });
  const confirmed = row('null', 'confirmed', null, null, false);
  const size = confirmed.n;
  const located = [['confirmed', null], ['measured_everywhere', 'off'], ['measured_everywhere', 'A']].map(([condition, arm]) => {
    const r = row('planted', condition, arm, 'all', false, size);
    return { condition, arm, label: need(r, 'label', file), n: r.n, slowdown: need(r, 'slowdown', file), replications: need(r, 'replications', file),
      intervals: Object.fromEntries(Object.keys(INTERVALS).map((k) => [k, { located: need(r, `intervals.${k}.located`, file), medianBiasDays: need(r, `intervals.${k}.median_bias_days`, file) }])) };
  });
  return {
    synthetic: true, statement: SYNTHETIC, source: src(file), document: 'DATA_COLLECTION.md', code: 'eventlog/extraction_intervals.py',
    run: mx.run, headline: finding.slice(0, finding.indexOf('. ') + 1) || finding, finding, countyEpisodes: size, replications: confirmed.replications,
    falseFlag: { countyTextCountryStructured: pair('county_extracted_country_structured', 'all'), writerStyle: pair('county_haiku_like_country_nemotron_like', 'haiku vs nemotron'), confirmed: rate(confirmed) },
    located,
    noteExactMatch: { validation: mx.note_exact_match.validation, test: mx.note_exact_match.test },
    resolverFrozenUtc: mx.checks.frozen_at_utc, recomputedEqualsStored: mx.checks.recomputed_equals_stored,
    agreement: pick(mx.agreement_with_interval_impact_v1, ['source', 'compared_rates', 'beyond_3_se', 'largest_rate_difference']),
    errorModel: mx.error_model, extraEventsModel: mx.extra_events_model, limits: mx.limits,
  };
}

// ------------------------------------------------------------------ 7. Gemma reads, code counts
// 7a. What the adapter does alone on notes with a relative date (runs/diagnose/diagnose-v1.json).
const PRODUCT_RUN = 'C-270m-all-v2data';
export function buildGemmaAlone(diag, file = FILES.diagnose) {
  needAll(diag, ['synthetic', 'generated', `runs.${PRODUCT_RUN}.test.n`, `runs.${PRODUCT_RUN}.test.by_has_relative.True`, `runs.${PRODUCT_RUN}.test.by_has_relative.False`], file);
  if (diag.synthetic !== true) throw new Error(`${file}: the diagnosis is not marked synthetic`);
  const t = diag.runs[PRODUCT_RUN].test;
  return { source: src(file), run: PRODUCT_RUN, generatedUtc: diag.generated, testNotes: t.n, withRelativeDate: t.by_has_relative.True, withoutRelativeDate: t.by_has_relative.False };
}

// 7b. The frozen code date resolver on the stored outputs of that adapter (data/scribe/v4/resolver/reproduce-v1.json).
const RESOLVER_REQUIRED = ['synthetic', 'rule', 'freeze.frozen_at_utc', 'freeze.files', 'primary.run', 'primary.arm', 'primary.validation.k', 'primary.validation.n',
  'primary.validation.wilson95', 'primary.validation.role', 'primary.validation.before', 'primary.test.k', 'primary.test.n', 'primary.test.wilson95', 'primary.test.role',
  'primary.test.before', 'primary.test.by_writer', 'notes_made_worse_arm_A_all_runs', 'port_identical_to_diagnose_rule.notes_compared', 'port_identical_to_diagnose_rule.mismatches',
  'arm_Aprime.lexicon', 'arm_Aprime.selection_rule', 'caveats'];
export function buildResolver(rep, file = FILES.resolver) {
  needAll(rep, RESOLVER_REQUIRED, file);
  if (rep.synthetic !== true) throw new Error(`${file}: the resolver reproduction is not marked synthetic`);
  const p = rep.primary, kw = (x) => pick(x, ['k', 'n', 'value', 'wilson95']);
  return { source: src(file), rule: rep.rule, frozenUtc: rep.freeze.frozen_at_utc, frozenFiles: rep.freeze.files, run: p.run, arm: p.arm,
    validation: { role: p.validation.role, before: kw(p.validation.before), after: kw(p.validation) },
    test: { role: p.test.role, before: kw(p.test.before), after: kw(p.test), byWriter: p.test.by_writer },
    notesMadeWorse: rep.notes_made_worse_arm_A_all_runs, port: rep.port_identical_to_diagnose_rule, lexicon: rep.arm_Aprime.lexicon, aPrimeRule: rep.arm_Aprime.selection_rule, caveats: rep.caveats };
}

// 7c. The preregistered evaluation on the frozen stress set, the test and validation notes, and the two-reader
// cascade recalibrated on validation only (data/scribe/v4/eval/results-v1.json, Lane A step 8).
const EVAL_SYSTEMS = ['A', "A'", 'B', 'C', 'v2data', 'nemotron'];
const EVAL_REQUIRED = ['schema', 'synthetic', 'created_utc', 'person_confirms', 'verify.all_ok', 'preregistration.file', 'preregistration.sha256', 'preregistration.frozen_utc',
  'preregistration.primary.success', 'systems', 'sets.val.role', 'sets.val.notes', 'sets.val.systems', 'sets.test.role', 'sets.test.notes', 'sets.test.systems',
  'sets.stress.role', 'sets.stress.notes', 'sets.stress.systems', 'sets.stress.not_scored', 'comparisons.test', 'comparisons.stress_heldout', 'comparisons.stress_standard',
  'primary_result.comparison', 'primary_result.a', 'primary_result.b', 'primary_result.n', 'primary_result.a_correct', 'primary_result.b_correct', 'primary_result.exact_mcnemar_p',
  'primary_result.difference_b_minus_a_points', 'primary_result.B_standard_slice', 'primary_result.criterion', 'primary_result.met', 'primary_result.A_prime_wins', 'primary_result.headline',
  'cascade.alpha_pct', 'cascade.rule', 'cascade.selection_rule', 'cascade.leak_guard', 'cascade.chosen.gemma', 'cascade.chosen.signal', 'cascade.configurations',
  'cascade.baseline_today.prefilled', 'cascade.baseline_today.wrong', 'cascade.baseline_today.notes', 'cascade.baseline_today.source'];
const kci = (x) => pick(x, ['k', 'n', 'value', 'ci95']);
export function buildEvaluation(res, file = FILES.evaluation) {
  needAll(res, EVAL_REQUIRED, file);
  if (res.synthetic !== true) throw new Error(`${file}: the evaluation is not marked synthetic`);
  if (res.verify.all_ok !== true) throw new Error(`${file}: the hash checks before scoring did not all pass`);
  const system = (setName, name, s) => {
    const where = `${file} sets.${setName}.systems.${name}`;
    needAll(s, ['exact_match', 'parse_failures', 'by_writer'], where);
    const out = { exact: kci(s.exact_match), parseFailures: kci(s.parse_failures), byWriter: Object.fromEntries(Object.entries(s.by_writer).map(([w, v]) => [w, kci(v)])) };
    if (setName === 'stress') {
      needAll(s, ['slices.heldout', 'slices.standard', 'slices.vague', 'slices.no_event', 'heldout_slice_by_family', 'vague_outcome.facts', 'vague_outcome.sent_to_person',
        'vague_outcome.invented_precise_date', 'vague_outcome.month_without_flag', 'vague_outcome.dropped'], where);
      out.slices = Object.fromEntries(['heldout', 'standard', 'vague', 'no_event'].map((k) => [k, kci(s.slices[k])]));
      out.heldoutByFamily = Object.fromEntries(Object.entries(s.heldout_slice_by_family).map(([k, v]) => [k, kci(v)]));
      out.vague = { facts: s.vague_outcome.facts, ...Object.fromEntries(['sent_to_person', 'invented_precise_date', 'month_without_flag', 'dropped'].map((k) => [k, kci(s.vague_outcome[k])])) };
    }
    return out;
  };
  const sets = Object.fromEntries(['val', 'test', 'stress'].map((setName) => {
    const st = res.sets[setName];
    const systems = Object.fromEntries(EVAL_SYSTEMS.filter((k) => k in st.systems).map((k) => [k, system(setName, k, st.systems[k])]));
    return [setName, { role: st.role, notes: st.notes, notScored: st.not_scored ?? {}, systems }];
  }));
  for (const k of ['A', "A'", 'B', 'C', 'nemotron']) if (!sets.stress.systems[k]) throw new Error(`${file}: the stress set has no result for system ${k}`);
  const cmp = (list) => list.map((c) => ({ a: c.a, b: c.b, n: c.n, aCorrect: c.a_correct, bCorrect: c.b_correct, aOnly: c.a_only_correct, bOnly: c.b_only_correct, p: c.exact_mcnemar_p, points: c.difference_b_minus_a_points }));
  const part = (x) => (x ? { prefilled: kci(x.prefilled_for_one_click_confirmation), correct: kci(x.prefilled_and_correct), wrong: kci(x.error_among_prefilled),
    needsEditing: kci(x.needs_editing), per100: x.per_100_notes_prefilled_correctly, haikuWritten: x.haiku_written ?? null } : null);
  const configurations = res.cascade.configurations.map((c) => {
    needAll(c, ['gemma', 'signal', 'validation.accepted', 'validation.wrong', 'validation.n', 'test.prefilled_for_one_click_confirmation', 'test.error_among_prefilled', 'test.needs_editing'], `${file} cascade configuration`);
    return { gemma: c.gemma, signal: c.signal, validation: pick(c.validation, ['threshold', 'accepted', 'wrong', 'n', 'coverage', 'error']), test: part(c.test), stress: part(c.stress) };
  });
  const { gemma, signal } = res.cascade.chosen;
  if (!configurations.some((c) => c.gemma === gemma && c.signal === signal)) throw new Error(`${file}: the chosen cascade configuration ${gemma} + ${signal} is not among the configurations`);
  const pr = res.primary_result;
  return {
    source: src(file), createdUtc: res.created_utc, personConfirms: res.person_confirms, systems: pick(res.systems, EVAL_SYSTEMS),
    preregistration: { file: res.preregistration.file, sha256: res.preregistration.sha256, frozenUtc: res.preregistration.frozen_utc, success: res.preregistration.primary.success },
    primary: { comparison: pr.comparison, a: pr.a, b: pr.b, n: pr.n, aCorrect: pr.a_correct, bCorrect: pr.b_correct, p: pr.exact_mcnemar_p, points: pr.difference_b_minus_a_points,
      bStandard: kci(pr.B_standard_slice), criterion: pr.criterion, met: pr.met, aPrimeWins: pr.A_prime_wins, headline: pr.headline },
    sets,
    comparisons: { test: cmp(res.comparisons.test), stressHeldout: cmp(res.comparisons.stress_heldout), stressStandard: cmp(res.comparisons.stress_standard) },
    cascade: { alphaPct: res.cascade.alpha_pct, rule: res.cascade.rule, selectionRule: res.cascade.selection_rule, leakGuard: res.cascade.leak_guard, chosen: { gemma, signal },
      baseline: pick(res.cascade.baseline_today, ['prefilled', 'wrong', 'notes', 'source']), configurations },
  };
}

// 7e. Post hoc vague-phrase gate (data/scribe/vague/results-v1.json): a frozen Finnish rule that sends a note with a vague
// time phrase to "needs editing". Designed after the stress results were seen and scored on stored outputs only, so it is
// never part of the preregistered result; the page shows it as one line labelled POST HOC.
const VAGUE_REQUIRED = ['synthetic', 'post_hoc', 'label', 'rule.version', 'rule.frozen_at_utc', 'rule.matches_freeze', 'sets.stress.notes', 'sets.test.notes',
  'sets.stress.detector_rule_v1.vague_notes_caught', 'sets.stress.detector_rule_v1.false_flags_on_notes_without_a_vague_fact',
  'sets.stress.cascade_C_agreement.without_gate', 'sets.stress.cascade_C_agreement.with_gate_rule_v1',
  'sets.test.cascade_C_agreement.without_gate', 'sets.test.cascade_C_agreement.with_gate_rule_v1',
  'sets.stress.vague_facts.cascade_without_gate.sent_to_person', 'sets.stress.vague_facts.cascade_with_gate_rule_v1.sent_to_person'];
export function buildVague(v, file = FILES.vague) {
  needAll(v, VAGUE_REQUIRED, file);
  if (v.synthetic !== true) throw new Error(`${file}: the vague-phrase gate result is not marked synthetic`);
  if (v.rule.matches_freeze !== true) throw new Error(`${file}: the rule file no longer matches its freeze record`);
  const arm = (x, where) => {
    needAll(x, ['prefilled_for_one_click_confirmation', 'error_among_prefilled', 'needs_editing'], where);
    return { prefilled: kci(x.prefilled_for_one_click_confirmation), wrong: kci(x.error_among_prefilled), needsEditing: kci(x.needs_editing) };
  };
  const set = (name) => {
    const c = v.sets[name].cascade_C_agreement;
    return { notes: v.sets[name].notes, without: arm(c.without_gate, `${file} sets.${name} without_gate`), withGate: arm(c.with_gate_rule_v1, `${file} sets.${name} with_gate_rule_v1`) };
  };
  const st = v.sets.stress, d = st.detector_rule_v1;
  return {
    source: src(file), label: v.label, postHoc: v.post_hoc, rule: { version: v.rule.version, frozenUtc: v.rule.frozen_at_utc },
    stress: { ...set('stress'), caught: kci(d.vague_notes_caught), falseFlags: kci(d.false_flags_on_notes_without_a_vague_fact),
      vagueToPerson: { without: kci(st.vague_facts.cascade_without_gate.sent_to_person), withGate: kci(st.vague_facts.cascade_with_gate_rule_v1.sent_to_person) } },
    test: set('test'),
  };
}

// 7d. Nemotron 3.5 Super VL as the escalation reader: one change at a time, on validation (data/scribe/nemotron/reader-v1.json).
const READER_REQUIRED = ['synthetic', 'title', 'model', 'generated_utc', 'versions', 'selection_rule', 'validation', 'validation_ladder', 'validation_ladder_relative_dates',
  'selected_by_rule', 'test.version', 'test.run_once', 'test.notes', 'test.exact_match', 'test.by_writer', 'test.parse_failures_final', 'caveats', 'requests_ledger'];
export function buildReader(rd, file = FILES.reader) {
  needAll(rd, READER_REQUIRED, file);
  if (!/SYNTHETIC/.test(rd.synthetic)) throw new Error(`${file}: the reader results are not marked SYNTHETIC`);
  const versions = Object.entries(rd.versions).map(([id, v]) => {
    const x = rd.validation[id];
    if (!x) throw new Error(`${file}: version ${id} has no validation result`);
    needAll(x, ['exact_match', 'parse_failures_final', 'tokens_per_note.completion', 'latency_seconds.mean', 'calls_per_note', 'relative_date_slice'], `${file} validation.${id}`);
    return { id, what: need(v, 'what', file), thinking: v.thinking, exact: kci(x.exact_match), parseFailures: x.parse_failures_final, completionTokensPerNote: x.tokens_per_note.completion,
      meanSeconds: x.latency_seconds.mean, callsPerNote: x.calls_per_note };
  });
  const ladder = (o) => Object.entries(o).map(([step, s]) => ({ step, ...needAll(pick(s, ['change', 'notes', 'before', 'after', 'gained', 'lost', 'change_points', 'mcnemar_exact_p']),
    ['notes', 'before', 'after', 'gained', 'lost', 'change_points', 'mcnemar_exact_p'], `${file} ladder ${step}`) }));
  if (!versions.some((v) => v.id === rd.selected_by_rule)) throw new Error(`${file}: the selected version ${rd.selected_by_rule} has no validation result`);
  return { source: src(file), title: rd.title, modelName: rd.title.split(' as ')[0], model: rd.model, generatedUtc: rd.generated_utc, versions, selectionRule: rd.selection_rule,
    selected: rd.selected_by_rule, ladder: ladder(rd.validation_ladder), ladderRelative: ladder(rd.validation_ladder_relative_dates),
    test: { version: rd.test.version, runOnce: rd.test.run_once, notes: rd.test.notes, exact: kci(rd.test.exact_match), parseFailures: rd.test.parse_failures_final,
      byWriter: Object.fromEntries(Object.entries(rd.test.by_writer).map(([w, v]) => [w, kci(v)])) },
    caveats: rd.caveats, requests: rd.requests_ledger };
}

// ------------------------------------------------------------------ 8. Nemotron county planner (summary for the page)
// The full drafts stay in data/planner/plans-v1.json (fetched by the page); app.json carries what the panel says
// about them, so a missing field fails the build here. Section 06b of the page also needs the image-input test.
const PLANNER_REQUIRED = ['schemaVersion', 'label', 'generatedAt', 'model', 'route', 'promptVersion', 'tools', 'gate.rule', 'gate.version', 'notes', 'appSha256', 'counties',
  'summary.counties', 'summary.countiesWithAtLeast3Kept', 'summary.sentences', 'summary.keptSentences', 'summary.droppedSentences', 'summary.sentencesFailingNumberCheck',
  'summary.keptSentencesWithUnmatchedNumber', 'summary.roadmapMeasureCodeChecked', 'summary.keptByField', 'summary.offLimits.prompts', 'summary.offLimits.pass',
  'summary.offLimits.passWithoutCodeGuard', 'summary.offLimits.refusedByModel', 'summary.offLimits.blockedByCode', 'summary.promptComparison.v1.keptSentences',
  'summary.promptComparison.v1.keptByField', 'summary.promptComparison.v2.keptSentences', 'summary.promptComparison.v2.keptByField', 'summary.gateV1Comparison.keptV1',
  'summary.selectionRule', 'summary.promptNote', 'summary.codeGuardNote', 'summary.gateNote', 'summary.jev.cost_usd', 'summary.jev.requests', 'summary.nemotron.ledgerRequestsAllRuns'];
const VISION_REQUIRED = ['schemaVersion', 'model', 'synthetic', 'summary.notes', 'summary.image_exact', 'summary.text_exact', 'summary.relative_date_notes.image',
  'summary.relative_date_notes.text', 'summary.relative_date_notes.n', 'summary.transcription.notes_with_umlaut_misread', 'summary.transcription.notes_with_date_misread',
  'summary.notes_with_umlaut_or_date_misread', 'summary.kill_criterion', 'summary.verdict'];
export function buildPlanner(plans, file = FILES.planner) {
  needAll(plans, PLANNER_REQUIRED, file);
  const s = plans.summary;
  return { source: src(file), label: plans.label, model: plans.model, route: plans.route, generatedAt: plans.generatedAt, promptVersion: plans.promptVersion, tools: plans.tools,
    gate: pick(plans.gate, ['rule', 'version']), notes: plans.notes, draftedOnAppSha256: plans.appSha256,
    summary: { ...pick(s, ['counties', 'countiesWithAtLeast3Kept', 'sentences', 'keptSentences', 'droppedSentences', 'sentencesFailingNumberCheck', 'keptSentencesWithUnmatchedNumber',
      'roadmapMeasureCodeChecked', 'keptByField', 'selectionRule', 'promptNote', 'codeGuardNote', 'gateNote']),
    offLimits: pick(s.offLimits, ['prompts', 'pass', 'passWithoutCodeGuard', 'refusedByModel', 'blockedByCode']),
    promptComparison: { v1: pick(s.promptComparison.v1, ['keptSentences', 'keptByField']), v2: pick(s.promptComparison.v2, ['keptSentences', 'keptByField']) },
    keptUnderGateV1: s.gateV1Comparison.keptV1, jev: pick(s.jev, ['requests', 'cost_usd']), nemotronRequests: s.nemotron.ledgerRequestsAllRuns },
    countyIds: Object.keys(plans.counties) };
}
export function buildPlannerVision(v, file = FILES.plannerVision) {
  needAll(v, VISION_REQUIRED, file);
  if (v.synthetic !== true && !/SYNTHETIC/.test(String(v.synthetic))) throw new Error(`${file}: the image-input test is not marked synthetic`);
  const s = v.summary;
  return { source: src(file), model: v.model, notes: s.notes, imageExact: s.image_exact, textExact: s.text_exact, relativeDateNotes: s.relative_date_notes,
    umlautMisread: s.transcription.notes_with_umlaut_misread, dateMisread: s.transcription.notes_with_date_misread, eitherMisread: s.notes_with_umlaut_or_date_misread,
    killCriterion: s.kill_criterion, verdict: s.verdict };
}

// ------------------------------------------------------------------ assembly
// Optional keys for app.json. A part whose source file is absent is left out and reported; a part whose
// file is present but lacks a required field throws, so the build fails loudly instead of guessing.
export function buildTracks(regions = [], files = FILES) {
  const F = { ...FILES, ...files };
  const problems = [];
  const part = (track, paths, fn) => {
    const missing = paths.filter((p) => !exists(p));
    if (missing.length) { problems.push({ track, problem: `source file missing: ${missing.join(', ')}` }); return null; }
    return fn(...paths.map(load));
  };
  const opt = (p) => (exists(p) ? load(p) : null);
  const out = {};
  const eventLog = part('eventLog', [F.eventLog], (s) => buildEventLog(s, regions, F.eventLog));
  if (eventLog) out.eventLog = eventLog;

  const ablation = part('scribe.ablation', [F.ablation], (a) => buildAblation(a, F.ablation));
  const students = part('scribe.students', [F.compare, F.trainingFigures, F.preregistration], (c, f, p) => buildStudents(c, f, p, { compare: F.compare, figures: F.trainingFigures, prereg: F.preregistration }));
  const serving = part('scribe.serving', [F.smokeGuided, F.smokePlain, F.trainingFigures], (g, p, f) => buildServing(g, p, f, { guided: F.smokeGuided, plain: F.smokePlain, figures: F.trainingFigures }));
  const teaching = part('scribe.teaching', [F.teaching], (s) => buildTeaching(s, F.teaching));
  const history = part('scribe.history', [F.scribeEval], (ev) => buildScribeV1(ev, opt(F.scribePost), opt(F.scribeStats), opt(F.scribeProvenance),
    exists(F.scribeHaiku) ? load(F.scribeHaiku) : [], opt(F.scribeLabelAudit)));
  if (students && teaching) students.noResult = teaching.studentNoResult;
  // "Gemma reads, code counts" (NVIDIA_OPTIONS.md section 3): each part is left out on its own when its file is absent.
  const gemmaAlone = part('scribe.gemmaAlone', [F.diagnose], (d) => buildGemmaAlone(d, F.diagnose));
  const resolver = part('scribe.resolver', [F.resolver], (r) => buildResolver(r, F.resolver));
  const evaluation = part('scribe.evaluation', [F.evaluation], (r) => buildEvaluation(r, F.evaluation));
  const reader = part('scribe.reader', [F.reader], (r) => buildReader(r, F.reader));
  const vague = part('scribe.vague', [F.vague], (r) => buildVague(r, F.vague));
  if (ablation || students || serving || teaching || history || gemmaAlone || resolver || evaluation || reader) {
    out.scribe = { synthetic: true, statement: SYNTHETIC, gemmaAlone, resolver, evaluation, reader, vague, ablation, students, serving, teaching, history,
      provenance: history?.models?.provenance ?? null };
  } else problems.push({ track: 'scribe', problem: 'no scribe result file is present' });

  // The insight panel (section 06): the same design-study file as the event-log track, its own required fields.
  const insight = part('insight', [F.eventLog], (s) => buildInsight(s, F.eventLog));
  if (insight) out.insight = insight;

  // The Nemotron county planner (section 07): summary in app.json, full drafts fetched by the page.
  const planner = part('planner', [F.planner], (p) => buildPlanner(p, F.planner));
  if (planner) {
    planner.vision = part('planner.vision', [F.plannerVision], (v) => buildPlannerVision(v, F.plannerVision));
    out.planner = planner;
  }

  const genomics = part('genomics', [F.genomics], (g) => buildGenomics(g, F.genomics));
  if (genomics) out.genomics = genomics;

  // Product panels of the ship wave (section 05 of the page): same missing-file and required-field rules.
  const safetyNet = part('safetyNet', [F.safetyNet], (s) => buildSafetyNet(s, regions, F.safetyNet));
  if (safetyNet) out.safetyNet = safetyNet;
  const flareGate = part('flareGate', [F.flareGate], (g) => buildFlareGate(g, regions, F.flareGate));
  if (flareGate) out.flareGate = flareGate;
  return { ...out, trackProblems: problems };
}
