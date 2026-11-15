// Build the SAMA PDF deck: node submission/deck/build.mjs  ->  submission/deck/deck.html, charts/*.svg, numbers.json
// Then print: see submission/deck/print.sh. Every number is read from a JSON file (lib.mjs val/inText).
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import * as L from './lib.mjs';
import { buildDecisionBrief } from '../../src/decisions.mjs';
const { val, get, inText, find, esc, nf, pct, load } = L;

const OUT = resolve(L.ROOT, 'submission/deck');
mkdirSync(resolve(OUT, 'charts'), { recursive: true });
const charts = {};
const chart = (name, s) => { charts[name] = s; writeFileSync(resolve(OUT, 'charts', `${name}.svg`), s); return s; };

// ------------------------------------------------------------------ files
const APP = 'web/data/app.json', EV = 'submission/evidence-v2.json', LIT = 'data/evidence/literature-v1.json';
const RES = 'data/scribe/v4/eval/results-v1.json', SN = 'data/safetynet/safetynet-v1.json', GATE = 'data/flare/gate-v1.json';
const PLAN = 'data/planner/plans-v1.json', MAP = 'data/roadmap/mapping-v1.json', DS = 'data/eventlog/design-study-v1.json';
const NEMO = 'data/scribe/nemotron/reader-v1.json', VAG = 'data/scribe/vague/results-v1.json', MLX = 'data/scribe/v4/mlx/validation-v1.json';
const FLS = 'data/flare/summary.json', DIAG = 'runs/diagnose/diagnose-v1.json', HTTP = 'data/scribe/demo/http-timing.json';
const VIS = 'data/planner/vision/vision-6b-v1.json', CC = 'data/claim-check/eval-v1.json', NAR = 'data/narratives/fi-v1.json';

const evRows = get(EV, 'rows'), evIdx = (id) => { const i = evRows.findIndex((r) => r.id === id); if (i < 0) throw new Error(`evidence ${id}`); return i; };
const ev = (id, key) => val(EV, `rows[${evIdx(id)}].values.${key}`);
const litRows = get(LIT, 'rows'), litIdx = (id) => { const i = litRows.findIndex((r) => r.id === id); if (i < 0) throw new Error(`literature ${id}`); return i; };
const regions = get(APP, 'analysis.regions');
const shortName = (id) => find(regions, (r) => r.regionId === id, id).name.replace(' wellbeing services county', '').replace('City of ', '');
const names = Object.fromEntries(regions.map((r) => [r.regionId, shortName(r.regionId)]));

// ------------------------------------------------------------------ values
// Slide 1-2: survival gap
const g3 = get(APP, 'analysis.goal3.indicators');
const nsI = g3.findIndex((x) => x.id === 'nordic-survival');
const lungI = g3[nsI].rows.findIndex((r) => r.site === 'lung' && r.sex === 'male');
const LP = `analysis.goal3.indicators[${nsI}].rows[${lungI}]`;
const finS = val(APP, `${LP}.finland`), benS = val(APP, `${LP}.benchmark`), period = val(APP, `${LP}.period`);
const hist = get(APP, `${LP}.history`); hist.forEach((h, i) => { val(APP, `${LP}.history[${i}].finland`); val(APP, `${LP}.history[${i}].benchmark`); });
const tgtI = g3.findIndex((x) => x.id === 'treatment-within-target');
const tgtStatus = val(APP, `analysis.goal3.indicators[${tgtI}].status`);
const counties = ev('stm-21-counties', 'counties'), areas = ev('stm-21-counties', 'areas_in_sama');
const stageNat = ev('syopajarjestot-2026-stage-completeness', 'national'), stageAim = ev('syopajarjestot-2026-stage-completeness', 'aim');
const stagePirk = ev('syopajarjestot-2026-stage-completeness', 'pirkanmaa'), stageSisa = ev('syopajarjestot-2026-stage-completeness', 'sisa_suomi');
const stageLo = ev('syopajarjestot-2026-stage-completeness', 'others_low'), stageHi = ev('syopajarjestot-2026-stage-completeness', 'others_high');

// Slide 3: who, how, where
const sv = (k) => ev('oecd-2025-fi-survival-education', k);
const bs = (k) => ev('oecd-2025-fi-breast-screening-gaps', k);
const cervLangI = litIdx('oecd-2025-cervical-screening-language'), cervEduI = litIdx('oecd-2025-cervical-screening-education');
const cervLangLo = val(LIT, `rows[${cervLangI}].figures.nonDomesticLanguage`), cervLangHi = val(LIT, `rows[${cervLangI}].figures.domesticLanguage`);
const cervEduHi = inText(LIT, `rows[${cervEduI}].claim`, /participation of (\d+)% among women with higher/), cervEduLo = inText(LIT, `rows[${cervEduI}].claim`, /against (\d+)% among women with lower/);
const rt = (k) => ev('kuitunen-2026-route-medians-groups', k);
const sb = get(APP, 'analysis.indicators.screen_breast.rows');
const sbVal = (id) => val(APP, `analysis.indicators.screen_breast.rows[${sb.findIndex((r) => r.regionId === id)}].value`);
const sbYear = val(APP, 'analysis.indicators.screen_breast.year');
const selfI = litIdx('virtanen-2011-selfsampling-fi');
const selfRR = val(LIT, `rows[${selfI}].value`), selfLo = val(LIT, `rows[${selfI}].ciLow`), selfHi = val(LIT, `rows[${selfI}].ciHigh`, (x) => Number(x).toFixed(2));

// Slide 4: the target
const sixW = ev('oecd-2025-fi-six-weeks', 'weeks'), d42 = ev('oecd-2025-fi-six-weeks', 'days_placeholder');
const lawA = ev('stm-hoitotakuu', 'assessment_weeks'), lawT = ev('stm-hoitotakuu', 'tests_months'), lawTr = ev('stm-hoitotakuu', 'treatment_months');
const ttpB = ev('thl-ttp-person-level', 'deadline_b').slice(0, 4);

// Slide 5: pathway clock
const ss = get(DS, 'sample_sizes.rows'); const ssI = ss.findIndex((r) => r.slowdown === 1.2);
const nPc = val(DS, `sample_sizes.rows[${ssI}].primary_care`), nDx = val(DS, `sample_sizes.rows[${ssI}].diagnostic`), nTx = val(DS, `sample_sizes.rows[${ssI}].treatment`);
const reach = get(APP, 'eventLog.reach'); const rI = reach.findIndex((r) => r.slowdown === 1.2);
const reachQ = val(APP, `eventLog.reach[${rI}].quarter`), reachY = val(APP, `eventLog.reach[${rI}].year`);
const cases = val(APP, 'eventLog.sampleSizes.nationalCasesAssumed', (x) => nf(x));
const m321res = inText(MAP, ['measures', '3.2.1', 'resource', 'fi'], /määräraha ([\d\s]+) €/).trim();

// Slide 6: comparability
const ff = (k) => get(APP, `insight.falseFlag.${k}.rate`);
const ffAsIs = val(APP, 'insight.falseFlag.countyTextCountryStructured.asIs.rate', (x) => pct(x, 1)), ffRes = val(APP, 'insight.falseFlag.countyTextCountryStructured.resolver.rate', (x) => pct(x, 1));
const ffConf = val(APP, 'insight.falseFlag.confirmed.rate', (x) => pct(x, 1));
const ffW = val(APP, 'insight.falseFlag.writerStyle.asIs.rate', (x) => pct(x, 1)), ffWR = val(APP, 'insight.falseFlag.writerStyle.resolver.rate', (x) => pct(x, 1));
const ffReps = val(APP, 'insight.falseFlag.confirmed.replications', (x) => nf(x));
const gRawNC = val(GATE, 'summary.raw.not_comparable'), gResNC = val(GATE, 'summary.resolver.not_comparable'), gOf = val(GATE, 'summary.raw.of');
const gCells = val(GATE, 'flare.equivalence.cells'), gOk = val(GATE, 'flare.equivalence.cells_ok'), gSites = val(GATE, 'flare.sites'), gVer = val(GATE, 'flare.nvflare');
const gBias = val(GATE, 'rule.bias_limit_days'), gMiss = val(GATE, 'rule.missed_limit', (x) => pct(x, 0));
const gc = get(GATE, 'counties');
const gateArms = [
  { key: 'raw', label: "The model's own dates", sub: 'Gemma 3 270M writes every date itself' },
  { key: 'resolver', label: 'Gemma reads, code counts', sub: 'code computes every relative date' },
].map((a) => ({ ...a, points: gc.map((c, i) => ({ bias: val(GATE, `counties[${i}].scribe.${a.key}.median_bias_days`, Number), comparable: get(GATE, `counties[${i}].scribe.${a.key}.comparable`) })),
  nc: a.key === 'raw' ? gRawNC : gResNC, of: gOf }));
const fl92 = val(FLS, 'equivalence.none-p12.cells'), fl92ok = val(FLS, 'equivalence.none-p12.cells_ok');

// Slide 7: safety net (Satakunta)
const snC = get(SN, 'counties'), snI = snC.findIndex((c) => c.regionId === 'HVA06'), SNP = `counties[${snI}]`;
const snOpen = val(SN, `${SNP}.counts.open_loops`), snOver = val(SN, `${SNP}.counts.overdue`);
const snImg = val(SN, `${SNP}.counts.imaging.overdue`), snRef = val(SN, `${SNP}.counts.referral.overdue`), snWait = val(SN, `${SNP}.counts.imaging.awaiting_person`);
const snAsOf = val(SN, 'asOf'), snThr = val(SN, 'thresholds[0].days');
const ruleAll = val(SN, 'rule.metrics.all_correct.k'), ruleN = val(SN, 'rule.metrics.all_correct.n');
const ruleDue = val(SN, 'rule.metrics.gold_counts.DUE_DATE'), rulePer = val(SN, 'rule.metrics.gold_counts.PERSON'), ruleNone = val(SN, 'rule.metrics.gold_counts.NONE');
const exs = get(SN, `${SNP}.examples`).map((e, i) => ({
  age: val(SN, `${SNP}.examples[${i}].age_band`), route: e.route, lang: e.contact_language, interp: e.interpreter,
  over: e.days_overdue == null ? null : val(SN, `${SNP}.examples[${i}].days_overdue`), missing: e.missing_step, status: e.status, kind: e.loop_kind, code: e.episode_code,
}));
const lawDate = ev('stm-2026-proactive-care-law', 'in_force');
const lungX = ev('lungimpact-2026', 'xrays'), lungMed = ev('lungimpact-2026', 'median_days_ai'), lungR = ev('lungimpact-2026', 'ratio'), lungLo = ev('lungimpact-2026', 'ci_low'), lungHi = ev('lungimpact-2026', 'ci_high');
const snNat = { open: val(SN, 'national.open_loops', (x) => nf(x)), over: val(SN, 'national.overdue'), sens: val(SN, 'national.referral.overdue_at_sensitivity_days') };

// Slide 8: Gemma reads, code counts
const relI = 'runs.C-270m-all-v2data.test.by_has_relative.True';
const relK = val(DIAG, `${relI}.k`), relN = val(DIAG, `${relI}.n`);
const DEMO = 'data/scribe/demo/demo-outputs.json';
const dmy = (iso) => { const [y, m, d] = iso.split('-').map(Number); return `${d}.${m}.${y}`; };
const d4phrase = val(DEMO, 'results.demo-04.highlights[2].phrase'), d4code = dmy(val(DEMO, 'results.demo-04.highlights[2].date')), d4model = dmy(val(DEMO, 'results.demo-04.model.parsed.events[2].date'));
const httpK = val(HTTP, 'exact_match_with_answer_key.k'), httpN = val(HTTP, 'exact_match_with_answer_key.n'), httpMed = val(HTTP, 'http_wall_seconds.median', (x) => nf(x, 1));

// Slide 9: stress set and two readers
const S = (sys, p) => val(RES, `sets.stress.systems.${sys}.${p}`);
const stress = [
  { sys: "A'", label: 'Gemma 3 270M + Finnish code rule', sub: 'the model writes dates; a Finnish word list fixes relative ones' },
  { sys: 'B', label: 'Gemma 3 270M, phrase only', sub: 'the model copies the phrase; code computes the date' },
  { sys: 'C', label: 'Gemma 3 1B, phrase only', sub: 'same method, larger model' },
  { sys: 'nemotron', label: 'Nemotron 3.5 Super VL', sub: 'second reader; it also wrote these notes, so optimistic', optimistic: true },
].map((s) => ({ ...s, k: S(s.sys, 'exact_match.k'), n: S(s.sys, 'exact_match.n'), hk: S(s.sys, 'slices.heldout.k'), hn: S(s.sys, 'slices.heldout.n'),
  vague: S(s.sys, 'vague_outcome.sent_to_person.k'), vagueN: S(s.sys, 'vague_outcome.facts') }));
const nemoDropped = S('nemotron', 'vague_outcome.dropped.k');
const prim = { met: val(RES, 'primary_result.met'), bk: val(RES, 'primary_result.b_correct'), ak: val(RES, 'primary_result.a_correct'), n: val(RES, 'primary_result.n'), p: val(RES, 'primary_result.exact_mcnemar_p') };
const cfg = get(RES, 'cascade.configurations'); const cI = cfg.findIndex((c) => c.gemma === 'C' && c.signal === 'agreement');
if (get(RES, 'cascade.chosen.gemma') !== 'C' || get(RES, 'cascade.chosen.signal') !== 'agreement') throw new Error('cascade choice changed');
const CP = `cascade.configurations[${cI}]`;
const cas = (set) => ({ n: val(RES, `${CP}.${set}.notes`), prefilled: val(RES, `${CP}.${set}.prefilled_for_one_click_confirmation.k`), ok: val(RES, `${CP}.${set}.prefilled_and_correct.k`),
  wrong: val(RES, `${CP}.${set}.error_among_prefilled.k`), edit: val(RES, `${CP}.${set}.needs_editing.k`) });
const casTest = cas('test'), casStress = cas('stress');
const casVal = { acc: val(RES, `${CP}.validation.accepted`), wrong: val(RES, `${CP}.validation.wrong`), n: val(RES, `${CP}.validation.n`) };
const base = { pre: val(RES, 'cascade.baseline_today.prefilled'), wrong: val(RES, 'cascade.baseline_today.wrong'), n: val(RES, 'cascade.baseline_today.notes') };
const pl = { n: val(PLAN, 'summary.counties'), run: val(PLAN, 'summary.countiesRun'), kept: val(PLAN, 'summary.keptSentences'), sent: val(PLAN, 'summary.sentences'), unm: val(PLAN, 'summary.keptSentencesWithUnmatchedNumber'),
  ref: val(PLAN, 'summary.offLimits.refusedByModel'), offN: val(PLAN, 'summary.offLimits.prompts'), code: val(PLAN, 'summary.offLimits.blockedByCode') };

// Slide 10-11
const preB = ev('yle-2025-helsinki-prebooking', 'before'), preA = ev('yle-2025-helsinki-prebooking', 'after');
const lungRows = get(APP, 'analysis.mortality.lung.rows');
lungRows.forEach((r, i) => ['shrunk', 'shrunkLow', 'shrunkHigh'].forEach((k) => val(APP, `analysis.mortality.lung.rows[${i}].${k}`)));
const lr = (id, k) => val(APP, `analysis.mortality.lung.rows[${lungRows.findIndex((r) => r.regionId === id)}].${k}`, (x) => Number(x).toFixed(3));
const satLung = lr('HVA06', 'shrunk'), satLo = lr('HVA06', 'shrunkLow'), satHi = lr('HVA06', 'shrunkHigh'), lapLung = lr('HVA21', 'shrunk'), kymLung = lr('HVA10', 'shrunk');
const pilotAsk = val(MAP, 'pilotCard.ask_en');
const vmDate = ev('vm-2026-assessment-procedure', 'decided'), vmN = ev('vm-2026-assessment-procedure', 'counties_named');

// ------------------------------------------------------------------ charts
chart('equals', L.equalsMark(benS, finS));
chart('history', L.historyChart(hist));
chart('dumbbell', L.dumbbell([
  { label: 'Five-year cancer survival, men', sub: 'by education', low: sv('lower_men'), high: sv('higher_men'), group: false },
  { label: 'Five-year cancer survival, women', sub: 'by education', low: sv('lower_women'), high: sv('higher_women') },
  { label: 'Breast screening attendance', sub: 'by mother tongue, 2020-21', low: bs('other_language'), high: bs('domestic_language'), group: true },
  { label: 'Breast screening attendance', sub: 'by education, 2020-21', low: bs('lower_education'), high: bs('higher_education') },
  { label: 'Cervical screening attendance', sub: 'by mother tongue', low: cervLangLo, high: cervLangHi, group: true },
  { label: 'Cervical screening attendance', sub: 'by education', low: Number(cervEduLo), high: Number(cervEduHi) },
]));
chart('route', L.routeBars(rt('median_public'), rt('median_fast'), rt('n_public'), rt('n_fast')));
chart('law', L.lawTimeline([
  { days: lawA * 7, big: `${lawA} weeks`, text: 'need assessed (law)', up: false },
  { days: d42, big: `${sixW} weeks`, text: 'OECD/EU-reported target: referral to treatment', up: true, kind: 'target' },
  { days: lawT * 30.4, big: `${lawT} months`, text: 'tests and specialist assessment (law)', up: false },
  { days: lawTr * 30.4, big: `${lawTr} months`, text: 'treatment, counted from the date the need is established (law)', up: true, anchor: 'end' },
]));
chart('reach', L.reachGrid([{ label: 'Within a quarter', k: reachQ }, { label: 'Within a year', k: reachY }], areas));
chart('gate', L.gateStrip(gateArms, gBias));
chart('units', L.unitChart(snOpen, snImg, snRef));
chart('stress', L.stressPanels(stress));
chart('cascade', L.cascadeBars([
  { label: `${casTest.n} test notes`, sub: 'seen before, so post hoc', ...casTest },
  { label: `${casStress.n} frozen stress notes`, sub: 'new phrasings and vague dates', ...casStress },
]));
chart('slope', L.slope(preB, preA));
const geo = load('web/data/counties.geo.json');
chart('map', L.finlandMap(geo, 'HVA06', 230, 400));
const lungLab = val(APP, 'analysis.mortality.lung.label'), lungWin = get(APP, 'analysis.mortality.lung.window');
const lungW0 = val(APP, 'analysis.mortality.lung.window[0]'), lungW1 = val(APP, `analysis.mortality.lung.window[${lungWin.length - 1}]`);
chart('lung', L.lungDots(lungRows, names, 'HVA06', ['HVA21', 'HVA10'], [`Deaths: ${lungLab.charAt(0).toLowerCase()}${lungLab.slice(1)}, ${lungW0}-${lungW1}, against the`, 'age-structure expectation; shrunk estimate with 95% interval']));

// ------------------------------------------------------------------ slide scaffolding
const SYN = (what = 'simulated people and model-written notes') => `<span class="syn"><b>SYNTHETIC</b> ${esc(what)}</span>`;
let pageNo = 0;
const TOTAL_MAIN = 11;
function slide({ id, kicker, rubric, title, lede, body, sources, synthetic, cls = '' }) {
  pageNo++;
  const num = id.startsWith('A') ? id : `${pageNo} / ${TOTAL_MAIN}`;
  return `<section class="slide ${cls}" id="${id}">
  <header class="top"><p class="kicker">${rubric ? `<span class="rubric">${esc(rubric)}</span>` : ''}${esc(kicker || '')}</p>${synthetic ? SYN(synthetic === true ? undefined : synthetic) : ''}</header>
  ${title ? `<h1>${title}</h1>` : ''}${lede ? `<p class="lede">${lede}</p>` : ''}
  <div class="body">${body}</div>
  <footer><p class="src"><span>Sources</span> ${sources}</p><p class="pn"><span class="mark">SAMA</span> ${num}</p></footer>
</section>`;
}
const code = (s) => `<code>${esc(s)}</code>`;
const fact = (big, text, cls = '') => `<div class="fact ${cls}"><p class="big">${big}</p><p>${text}</p></div>`;

const slides = [];

// The page's "One county. One next step." card for the pilot county, read from the same app.json.
const dec = buildDecisionBrief(load(APP), 'HVA06');
if (dec.regionId !== 'HVA06' || dec.action.first30Days.length !== 3) throw new Error('decision brief changed');
// 1 -------------------------------------------------------------- title
slides.push(slide({ id: 's1', kicker: 'Junction 2026 · AstraZeneca challenge "Equal Care Across Finland"', cls: 'title',
  body: `<div class="t-left">
    <p class="wordmark">SAMA</p>
    <p class="gloss"><i>sama</i> is Finnish for "the same"</p>
    <p class="promise">The same cancer pathway for everyone in Finland: wherever they live, whoever they are, however they enter care.</p>
    <div class="monday"><p class="vh">Start here · ${esc(dec.regionName)} · one county, one next step · proposal for human review</p>
      <ol>${dec.action.first30Days.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
      <p>Then a nurse-confirmed list of people whose next step is overdue (slide 7). Review at 90 days: ${esc(dec.action.reviewAt90Days.charAt(0).toLowerCase() + dec.action.reviewAt90Days.slice(1))}</p></div>
  </div>
  <div class="t-right">${charts.equals}
    <ol class="rubric-map">
      <li><b>Actionability</b><span>slides 5, 7, 10, 11</span></li>
      <li><b>Insight</b><span>slides 2, 3, 4</span></li>
      <li><b>Data quality and transparency</b><span>slide 6, appendix</span></li>
      <li><b>Execution</b><span>slides 8, 9</span></li>
      <li><b>Clarity</b><span>one message per slide; every number sourced</span></li>
    </ol>
    <p class="scope">Public data for ${areas} areas: the ${counties} wellbeing services counties, Helsinki and Åland. Everything patient-like is SYNTHETIC and labelled. A person confirms every extracted event and every list item.</p>
  </div>`,
  sources: `${code(APP)} analysis.goal3 nordic-survival (NORDCAN); ${code(EV)} stm-21-counties; the first-30-days steps are ${code('src/decisions.mjs')} buildDecisionBrief for ${dec.regionId}, as on the page's Start here section.` }));

// 2 -------------------------------------------------------------- the gap
slides.push(slide({ id: 's2', rubric: 'Insight', kicker: 'The gap',
  title: `Finnish men with lung cancer: ${finS}% alive after five years. Sweden and Norway: ${benS}%.`,
  body: `<div class="split"><div class="viz">${charts.history}</div>
    <div class="facts">
      ${fact('By chance', 'Finland\'s national lung programme: lung cancers found in time are mostly found by chance, on scans taken for something else. What happens after that scan decides how early treatment starts.')}
      ${fact(`${stageNat}%`, `of cancers have their stage recorded nationally. The aim is at least ${stageAim}%.`)}
    </div></div>`,
  sources: `${code(APP)} analysis.goal3 nordic-survival, lung, men, ${period} and history (NORDCAN, Sweden-Norway mean as the strategy defines it); ${code(EV)} filha-2026-found-by-chance, syopajarjestot-2026-stage-completeness.` }));

// 3 -------------------------------------------------------------- who, how, where
slides.push(slide({ id: 's3', rubric: 'Insight', kicker: 'Who, how and where',
  title: 'The gap follows who you are and how you enter care. County averages cannot see it yet.',
  body: `<div class="split s3"><div class="viz"><p class="vh">Who is missed (individual-level figures, Finland)</p>${charts.dumbbell}
      <p class="action"><b>Act on it.</b> Roadmap measure 1.3.1: raise screening among people whose mother tongue is not Finnish or Swedish. Mailed HPV self-sampling to cervical-screening non-attenders: relative participation ${selfRR} (${selfLo}-${selfHi}) in a Finnish trial.</p></div>
    <div class="facts">
      <div class="fact"><p class="vh">How you enter care</p><p>Median days from first symptom to treatment, one Finnish lymphoma cohort (p = ${rt('p')})</p>${charts.route}</div>
      <div class="fact"><p class="vh">Where you live</p><p>Five-year survival <b>does not differ significantly between regions</b>. County averages cannot see who is missed: breast-screening attendance is lowest in Helsinki (${sbVal('HVA90')}%, ${sbYear}), where many women screen privately.</p></div>
    </div></div>`,
  sources: `${code(EV)} oecd-2025-fi-survival-education, oecd-2025-fi-breast-screening-gaps, kuitunen-2026-route-medians-groups; ${code(LIT)} oecd-2025-cervical-screening-language, -education, virtanen-2011-selfsampling-fi; ${code(APP)} analysis.indicators.screen_breast; ${code(MAP)} measure 1.3.1.` }));

// 4 -------------------------------------------------------------- a target nobody can see
slides.push(slide({ id: 's4', rubric: 'Insight', kicker: 'A target nobody can see',
  title: 'Finland reports a six-week cancer target. No open dataset can check it.',
  body: `<div class="viz wide">${charts.law}</div>
    <div class="row3">
      ${fact('No legal limit found', `The OECD/EU reports a target of ${sixW} weeks from a suspected-cancer referral to treatment. The treatment-guarantee law allows treatment up to ${lawTr} months after the need is established and names no cancer-specific limit. THL guidance 21/2016 not checked (unverified).`)}
      ${fact('Not measured', `THL's access statistic covers non-urgent care only, as month-end snapshots. Person-level reporting through THL's waiting-list feed (TTP) is due by ${ttpB} at the latest.`)}
      ${fact('Not computable', `The strategy's own Goal 3 indicator, "treatment within target times", has status <span class="tag">${esc(tgtStatus.replace(/_/g, ' ').toLowerCase())}</span> from open data today.`)}
    </div>`,
  sources: `${code(EV)} oecd-2025-fi-six-weeks, stm-hoitotakuu, thl-ttp-person-level; ${code(APP)} analysis.goal3 indicator treatment-within-target.` }));

// 5 -------------------------------------------------------------- the pathway clock
slides.push(slide({ id: 's5', rubric: 'Actionability', kicker: 'The Pathway Clock', synthetic: 'simulation for the data-size estimate',
  title: 'Ask every county for two dates and an end reason.',
  body: `<div class="clock">
      <div class="c-end"><p class="c-k">Date 1</p><p class="c-v">Well-founded suspicion of cancer</p></div>
      <div class="c-line"><span>the clock</span></div>
      <div class="c-end"><p class="c-k">Date 2 + reason</p><p class="c-v">End: treated, ruled out or other</p></div>
      <div class="c-plus"><p class="c-k">With each pathway</p><p class="c-v">County of residence · entry route (public primary care, occupational or private, emergency, other)</p></div>
    </div>
    <p class="optional"><b>Optional, for a pilot county that wants to find where a delay sits:</b> first contact · referral sent · diagnosis · treatment start.</p>
    <div class="split s5">
      <div class="facts">
        ${fact('Carriers exist', `THL's person-level waiting-list feed (TTP) for the clock; the cancer quality register at THL's Cancer Registry (roadmap 3.2.1, EUR ${m321res.replace(/\s/g, ',')}) for stage and route. Add the fields while 3.2.1's variable set is being fixed.`)}
        ${fact('Placeholders', `Thresholds are placeholders: ${d42} days from referral to treatment is the OECD/EU-reported target, not a legal limit.`)}
      </div>
      <div class="viz"><p class="vh">How much data is enough? To see a county that is 20% slower in one interval, a county needs ${nPc} / ${nDx} / ${nTx} complete pathways (primary care / diagnostic / treatment). At an assumed ${cases} cases a year, areas that get there:</p>${charts.reach}</div>
    </div>`,
  sources: `${code('submission/PATHWAY_CLOCK.md')}; ${code(MAP)} measure 3.2.1; ${code(DS)} sample_sizes (20% slowdown, 80% power, 69 comparisons); ${code(APP)} eventLog.reach, eventLog.sampleSizes; ${code(EV)} thl-ttp-person-level, oecd-2025-fi-six-weeks.` }));

// 6 -------------------------------------------------------------- comparability gate
slides.push(slide({ id: 's6', rubric: 'Data quality and transparency', kicker: 'Can this county see itself?', synthetic: true,
  title: 'Compare a county only when it can see itself.',
  lede: `A county whose dates are read badly looks slow when it is not. Each dot is one of ${gOf} simulated counties: how far off its referral-to-treatment interval is. Outside the band, the figure stays visible but is labelled "not comparable".`,
  body: `<div class="split s6"><div class="viz">${charts.gate}<p class="legend"><i class="dot lake"></i>comparable <i class="dot lingon"></i>not comparable (median error above ±${gBias} days or over ${gMiss} of events missed; placeholder limits)</p></div>
    <div class="facts">
      ${fact(`${ffAsIs} → ${ffRes}`, `No county is truly slower, yet one whose dates come from free text is flagged "slow" in ${ffAsIs} of ${ffReps} simulated runs. With Gemma reads, code counts: ${ffRes}, the same as when a person confirms every event (${ffConf}).`)}
      ${fact(`${gOk} of ${gCells}`, `county cells computed with NVIDIA FLARE ${gVer} on ${gSites} simulated sites equal the central computation. Only totals leave a site.`)}
      ${fact(`${stagePirk}%`, `Real data: only Pirkanmaa records stage for at least ${stageAim}% of cancers (Sisä-Suomi ${stageSisa}%, others ${stageLo}-${stageHi}%). It is the only area that could be compared on stage today.`)}
    </div></div>`,
  sources: `${code(GATE)} summary, rule, counties, flare.equivalence, realData; ${code(APP)} insight.falseFlag (from ${code(DS)}); ${code(EV)} syopajarjestot-2026-stage-completeness.` }));

// 7 -------------------------------------------------------------- close the loop
const routeName = { PUBLIC_PRIMARY: 'public primary care', PRIVATE: 'private', OCCUPATIONAL: 'occupational', EMERGENCY: 'emergency' };
const langName = (l, i) => `${{ fi: 'Finnish', sv: 'Swedish', se: 'Sámi', other: 'other language' }[l] || l}${i ? ', interpreter' : ''}`;
slides.push(slide({ id: 's7', rubric: 'Actionability', kicker: 'Close the loop', synthetic: 'replay of simulated people',
  title: 'Turn the clock into a nurse\'s daily list of overdue pathways.',
  body: `<div class="split s7">
    <div class="viz"><p class="vh">Satakunta, replayed as of ${snAsOf}: <b>${snOpen}</b> open loops, <b>${snOver}</b> overdue</p>${charts.units}
      <p class="legend"><span class="li"><i class="sq lingon"></i> ${snImg} imaging follow-ups past the date the radiologist wrote</span> <span class="li"><i class="sq hatch"></i> ${snRef} referrals with no diagnosis by day ${snThr}</span> <span class="li">(placeholder: OECD/EU-reported target)</span></p>
      <p class="note">${snWait} more written recommendations wait for a person to set a date. A code rule copies the radiologist's written follow-up and computes the due date; vague lines go to a person (${ruleAll} of ${ruleN} SYNTHETIC test lines right).</p>
      <div class="worklist">${exs.map((e) => `<div class="wl-row"><span class="wl-syn">SYNTHETIC</span><span>Age ${esc(e.age)}</span><span>${esc(routeName[e.route] || e.route)}</span><span>${esc(langName(e.lang, e.interp))}</span><span class="wl-over">${e.over == null ? 'date not set' : `${e.over} days overdue`}</span><span class="wl-st">${esc(e.status)}</span></div>`).join('')}</div>
    </div>
    <div class="facts">
      ${fact(`Since ${dmy(lawDate)}`, 'a county may identify patients whose care does not follow recommendations; contacting them must respect data protection and self-determination. <b>Whether this covers pathway timing is unverified; to confirm with STM and THL before a pilot.</b>')}
      ${fact(`${lungMed} days`, `Close loops before buying speed: in a trial of ${nf(lungX)} GP chest X-rays, AI prioritisation left the median time to CT at ${lungMed} days in both arms (ratio ${lungR}, ${lungLo}-${lungHi}).`)}
      ${fact('County-owned', 'The county owns the list and the care; a nurse confirms each item and calls. In the pilot no patient data leaves the county: Gemma runs locally, and the second reader must run in a county-controlled environment (designed, not built) or a person does that step.')}
    </div></div>`,
  sources: `${code(SN)} counties HVA06 (counts, examples), rule.metrics, thresholds; ${code(EV)} stm-2026-proactive-care-law (in force ${lawDate}), lungimpact-2026; ${code(MAP)} measure 1.2.3.` }));

// 8 -------------------------------------------------------------- Gemma reads, code counts
slides.push(slide({ id: 's8', rubric: 'Execution', kicker: 'Gemma reads, code counts', synthetic: 'notes written by language models',
  title: `Pre-filled only when two readers agree: ${casStress.prefilled} of ${casStress.n} stress notes, ${casStress.wrong} wrong.`,
  body: `<div class="split s8">
    <div class="facts">
      ${fact(`"${esc(d4phrase)}"`, `${/^(\d+) viikkoa sitten$/.test(d4phrase) ? `("${d4phrase.split(' ')[0]} weeks ago") ` : ''}Dates in referral letters are often relative. Gemma 3 270M finds the phrase; code counts back from the note date to <b>${d4code}</b>; Gemma's own date, <s>${d4model}</s>, is not used.`)}
      ${fact(`${relK} of ${relN}`, 'test notes with a relative date came out right when Gemma did the subtraction itself. That is why code counts.')}
      ${fact(`${httpK} of ${httpN}`, `demo notes exact on the laptop CPU through the product's own endpoint, median ${httpMed} s per note. Finnish notes only; other languages go to manual entry.`)}
      <p class="note">The demo runs the 270M product adapter on a laptop CPU. Nemotron's answer is stored, or asked live from the page with one button (the SYNTHETIC note goes to the hosted endpoint). The two-reader figures in the title and on slide 9 use Gemma 3 1B.</p>
    </div>
    <div class="shots"><p class="shot-cap">The product: demo note 4, stored output (SYNTHETIC)</p>
      <img src="img/demo04-note.png" alt="Synthetic Finnish referral note with date phrases marked"/>
      <img src="img/demo04-events.png" alt="Proposed events table: date proposed, phrase in the note, Gemma's own date, how the date was set"/>
      <img src="img/demo04-verdict.png" alt="Verdict: pre-filled for one-click confirmation, a person confirms every event" class="verdict"/>
    </div></div>`,
  sources: `${code('submission/shots/14b-gemma-demo-demo-04-1440.png')} (stored output, SAMA_SCRIBE_LIVE=0); ${code(DIAG)} C-270m-all-v2data test by_has_relative; ${code(HTTP)}.` }));

// 9 -------------------------------------------------------------- how good is the reading
const v = (s) => `${s.vague}`;
const critPts = inText(RES, 'primary_result.criterion', /\((\d+) points\)/), critStd = inText(RES, 'primary_result.criterion', /B >= 0\.(\d+) exact/);
const primDiff = val(RES, 'primary_result.difference_b_minus_a_points', (x) => nf(x, 1));
const primStdK = val(RES, 'primary_result.B_standard_slice.k'), primStdN = val(RES, 'primary_result.B_standard_slice.n');
const cAloneN = Number(val(RES, 'sets.stress.systems.C.exact_match.n')), cAloneWrong = cAloneN - Number(val(RES, 'sets.stress.systems.C.exact_match.k'));
slides.push(slide({ id: 's9', rubric: 'Execution', kicker: 'Tested on a frozen stress set', synthetic: 'notes written by language models',
  title: `Gemma 1B alone: ${cAloneWrong} of ${cAloneN} wrong. With a second reader: ${casStress.wrong}.`,
  body: `<div class="viz"><p class="vh">1 · Each reader alone, on ${stress[0].n} stress notes frozen before any system read them</p>${charts.stress}
      <p class="note"><b>Goal set in advance for the small 270M phrase model: not met.</b> It got ${prim.bk} of ${prim.n} new phrasings right against ${prim.ak} for the code rule (it needed ${critPts} points more), and ${primStdK} of ${primStdN} standard notes (it needed ${critStd}%).<br>Vague dates such as "a couple of weeks ago" sent to a person: ${stress.map((s) => v(s)).join(', ')} of ${stress[0].vagueN} (code rule, 270M, 1B, Nemotron); Nemotron left the date out in ${nemoDropped}.</p></div>
    <div class="split s9b">
      <div class="viz"><p class="vh">2 · Gemma 3 1B and Nemotron together: pre-filled only when both agree exactly</p>${charts.cascade}</div>
      <div class="side"><p class="note">The pairing was chosen on ${casVal.n} validation notes only (${casVal.acc} pre-filled, ${casVal.wrong} wrong). The earlier single-reader setup pre-filled ${base.pre} of ${base.n} test notes with ${base.wrong} wrong. A person confirms every note either way.</p>
        <div class="planner"><p class="vh">Nemotron also drafts each county's plan; code checks every number</p>
        <p><b>${pl.run} of ${pl.n}</b> areas drafted · <b>${pl.kept} of ${pl.sent}</b> sentences kept · <b>${pl.unm}</b> kept with a number not in a tool output · <b>${pl.ref} of ${pl.offN}</b> off-limits requests refused by the model (${pl.code} stopped by a code guard added afterwards)</p></div>
      </div></div>`,
  sources: `${code(RES)} sets.stress.systems (exact_match, slices.heldout, vague_outcome), primary_result, cascade (chosen C + agreement), baseline_today; ${code(PLAN)} summary.` }));

// 10 ------------------------------------------------------------- zero-euro 2027
slides.push(slide({ id: 's10', rubric: 'Actionability', kicker: 'The zero-euro 2027 plan',
  title: 'Three actions for 2027 that need staff time, not new money.',
  lede: 'The Cancer Organisations say no strategy money is in sight for 2027. These actions need no capital spending.',
  body: `<div class="split s10"><table class="plan">
      <thead><tr><th>Action</th><th>Owner</th><th>Roadmap</th><th>Measured by</th></tr></thead>
      <tbody>
      <tr><td><b>Put pre-booked appointment times back</b> into screening invitations</td><td>County screening unit</td><td>1.3.1</td><td>Attendance by mother tongue and education</td></tr>
      <tr><td><b>Run the overdue-pathway list</b> with existing care coordinators</td><td>County cancer centre</td><td>1.2.3</td><td>Follow-ups closed on time; items resolved within 14 days</td></tr>
      <tr><td><b>Send two dates and an end reason</b> in THL's person-level feed</td><td>County data team with THL</td><td>3.2.1</td><td>Share of new suspected-cancer pathways with both dates and an end reason</td></tr>
      </tbody></table>
    <div class="viz"><p class="vh">Why action 1: Helsinki cervical screening attendance (one city, before and after)</p>${charts.slope}</div></div>`,
  sources: `${code('submission/ZERO_EURO_2027.md')}; ${code(EV)} stt-2026-no-strategy-money-2027, yle-2025-helsinki-prebooking; ${code(MAP)} measures 1.3.1, 1.2.3, 3.2.1.` }));

// 11 ------------------------------------------------------------- the ask
slides.push(slide({ id: 's11', rubric: 'Actionability', kicker: 'The ask', cls: 'ask',
  title: 'Satakunta, lung follow-up first: a 2027 pilot at no new capital cost.',
  body: `<div class="split s11">
    <div class="ask-l">
      <p class="askline">${esc(pilotAsk)}</p>
      <h3>Why Satakunta</h3>
      <ul><li>Finnish-language services (share of Finnish notes not measured): the scribe reads Finnish only.</li><li>Not among the ${vmN} counties put under the state assessment procedure on ${dmy(vmDate)}.</li><li>High lung burden: ${satLung} times the national level (${satLo}-${satHi}). Not the highest: Lapland ${lapLung}, Kymenlaakso ${kymLung}.</li><li>Fits roadmap 1.2.3 (named care coordinator) and 3.5.3 (AI pilots in counties).</li></ul>
      <h3>Pilot measures, each by entry route, education and contact language</h3>
      <ul><li>Share of follow-ups closed on time</li><li>Share of new pathways with both clock dates</li><li>Share of pre-filled events confirmed in one click</li></ul>
      <p class="noclaim"><b>We do not claim</b> a diagnosis, a statement about any patient, or that any county's care is worse. Nothing from simulated people or model-written notes is a finding about Finnish patients. AstraZeneca sponsors the challenge; no AstraZeneca data or product information is used and no medicine is recommended.</p>
    </div>
    <div class="ask-r"><div class="mapwrap">${charts.map}<p class="maplabel">Satakunta</p></div>${charts.lung}</div>
  </div>`,
  sources: `${code(MAP)} pilotCard (ask, rationale, roadmap hooks 1.2.3, 3.5.3); ${code(EV)} vm-2026-assessment-procedure (Finnish Government release, 16 June 2026); ${code(APP)} analysis.mortality.lung rows HVA06, HVA21, HVA10; ${code('web/data/counties.geo.json')}.` }));

// ------------------------------------------------------------------ appendix
const A = await import('./appendix.mjs');
const app = A.build({ L, val, get, inText, nf, pct, esc, code, stress, casTest, casStress, casVal, base, gateArms, files: { APP, EV, LIT, RES, SN, GATE, PLAN, MAP, DS, NEMO, VAG, MLX, FLS, DIAG, HTTP, VIS, CC, NAR } });
const appendixHtml = app.map((p) => slide(p)).join('\n');

// ------------------------------------------------------------------ page
const css = (await import('node:fs')).readFileSync(resolve(OUT, 'deck.css'), 'utf8');
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SAMA deck</title><style>${css}</style></head><body>
${slides.join('\n')}
${appendixHtml}
</body></html>`;
writeFileSync(resolve(OUT, 'deck.html'), html);
writeFileSync(resolve(OUT, 'numbers.json'), JSON.stringify({ generated_utc: new Date().toISOString(), note: 'every value read from a JSON file by submission/deck/build.mjs, with its file and path', values: L.ledger }, null, 1));
console.log(`deck.html: ${slides.length} slides + ${app.length} appendix pages; ${L.ledger.length} sourced values; ${Object.keys(charts).length} charts`);
