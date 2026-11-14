import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  benjaminiHochberg, empiricalBayesSmr, gammaP, inequalityIndices, normalCdf, poissonInterval, pooledNoiseSd, smr,
} from '../src/stats.mjs';
import { analyse, analyseIndicator, analyseMortality, MIN_EXPECTED_DEATHS } from '../src/analysis.mjs';
import {
  ASSUMPTIONS, INTERVENTIONS, TIMELINESS_IDS, centralParameters, costOf, daysSaved, deathsPostponed, detectionTrack, optimise,
  optimiseExact, recommend, regionFacts, relativeReduction, weightedValue,
} from '../src/recommend.mjs';
import { buildApp } from '../src/build.mjs';
import { buildBrief } from '../src/claims.mjs';
import { verdictFrom, verifyClaims } from '../src/claim-check.mjs';

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const snapshot = read('../data/snapshot/public-v1.json');
const evidence = read('../data/evidence/literature-v1.json');
const analysis = analyse(snapshot);
const close = (a, b, tol) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b} (tol ${tol})`);

// ------------------------------------------------------------------ statistics
test('exact Poisson interval matches published values', () => {
  const ci = poissonInterval(10);
  close(ci.low, 4.795, 0.005); close(ci.high, 18.39, 0.01);
  assert.equal(poissonInterval(0).low, 0); close(poissonInterval(0).high, 3.689, 0.005);
});
test('incomplete gamma and normal CDF agree with closed forms', () => {
  close(gammaP(1, 1), 1 - Math.exp(-1), 1e-9); close(normalCdf(1.96), 0.975, 1e-4); close(normalCdf(-1.96), 0.025, 1e-4);
});
test('SMR interval contains the point estimate', () => {
  const r = smr(120, 100); assert.ok(r.low < 1.2 && r.high > 1.2 && r.low > 0.99);
});
test('empirical Bayes shrinks a small region more than a large one', () => {
  const rows = [{ observed: 15, expected: 10 }, { observed: 1500, expected: 1000 }, { observed: 900, expected: 1000 }, { observed: 480, expected: 500 }, { observed: 260, expected: 250 }];
  const eb = empiricalBayesSmr(rows);
  assert.ok(Math.abs(eb.rows[0].shrunk - 1.5) > Math.abs(eb.rows[1].shrunk - 1.5), 'small region moved further from its raw ratio');
  assert.ok(eb.rows[0].weight < eb.rows[1].weight);
  assert.ok(eb.rows.every((r) => r.low <= r.shrunk && r.shrunk <= r.high));
});
test('no real between-region variation means full shrinkage, nothing to rank', () => {
  const eb = empiricalBayesSmr([{ observed: 100, expected: 100 }, { observed: 101, expected: 100 }, { observed: 99, expected: 100 }]);
  assert.equal(eb.priorVariance, 0); assert.ok(eb.rows.every((r) => r.shrunk === eb.priorMean));
});
test('Benjamini-Hochberg keeps the false discovery rate rule', () => {
  assert.deepEqual(benjaminiHochberg([0.001, 0.02, 0.04, 0.5], 0.1), [true, true, true, false]);
  assert.deepEqual(benjaminiHochberg([0.2, 0.3, 0.9], 0.1), [false, false, false]);
});
test('slope index recovers a known gradient', () => {
  const rows = Array.from({ length: 10 }, (_, i) => ({ ses: i, population: 100, value: 60 + 2 * i }));
  const g = inequalityIndices(rows, { bootstrap: 50 });
  close(g.sii, 20, 0.5); assert.ok(g.top > g.bottom);
});
test('pooled noise ignores a smooth trend', () => {
  const noisy = { 2020: 10, 2021: 12, 2022: 10, 2023: 12, 2024: 10 };
  const trend = { 2020: 10, 2021: 11, 2022: 12, 2023: 13, 2024: 14 };
  assert.ok(pooledNoiseSd([noisy]) > 1); close(pooledNoiseSd([trend]), 0, 1e-9);
});

// --------------------------------------------------------------- real-data analysis
test('snapshot is public aggregate data with attested sources and a request manifest', () => {
  assert.equal(snapshot.dataClass, 'CLEARED_AGGREGATE_INPUT'); assert.equal(snapshot.regions.length, 23);
  assert.ok(Object.values(snapshot.sources).every((s) => s.license && s.isObservedPublicDataset === true));
  assert.ok(snapshot.manifest.length > 40 && snapshot.manifest.every((m) => /^[0-9a-f]{64}$/.test(m.sha256) && m.url.startsWith('https://')));
});
test('indirect standardisation reproduces the national death count', () => {
  for (const site of Object.values(snapshot.mortality)) {
    const o = Object.values(site.regions).reduce((s, r) => s + r.observed, 0); const e = Object.values(site.regions).reduce((s, r) => s + r.expected, 0);
    close(e / o, 1, 0.005);
  }
});
test('national cancer deaths match the strategy baseline of about 13,300 a year', () => {
  close(analysis.goal3.indicators[1].baselineDeathsPerYear, 13300, 150);
  assert.ok(analysis.goal3.indicators[1].demographicPressure[2035] > analysis.goal3.indicators[1].demographicPressure[2024]);
});
test('Goal 3 survival gap is Finland minus the Sweden-Norway mean, and lung in men is clearly below', () => {
  const rows = analysis.goal3.indicators[0].rows; const lung = rows.find((r) => r.site === 'lung' && r.sex === 'male');
  close(lung.gap, lung.finland - (lung.sweden + lung.norway) / 2, 0.06); assert.ok(lung.gap < -5 && lung.clear === true);
  assert.equal(analysis.goal3.indicators[2].status, 'NOT_PUBLICLY_MEASURABLE');
});
test('a flag always means worse than the national value, and target shortfall is separate', () => {
  for (const ind of Object.values(analysis.indicators)) {
    for (const row of ind.rows) {
      if (row.flagged) assert.ok(row.gap > 0 && row.pWorse > 0.5, `${ind.key} ${row.regionId}`);
      if (!ind.rankable) assert.equal(row.flagged, false);
      if (row.missesTarget) assert.ok(row.targetGap > 0);
    }
  }
  assert.equal(analysis.indicators.screen_colorectal.countiesMissingTarget, analysis.indicators.screen_colorectal.countiesWithData);
});
test('adversarial: small expected counts are suppressed, never ranked', () => {
  const site = { label: 'toy', window: ['2021'], nationalDeathsByYear: {}, regions: { A: { observed: 9, expected: 3 }, B: { observed: 300, expected: 250 }, C: { observed: 190, expected: 200 }, D: { observed: 110, expected: 100 } } };
  const out = analyseMortality(site, ['A', 'B', 'C', 'D'].map((id) => ({ id })));
  const a = out.rows.find((r) => r.regionId === 'A');
  assert.equal(a.suppressed, true); assert.equal(a.smr, undefined); assert.equal(a.flagged, undefined);
  assert.ok(3 < MIN_EXPECTED_DEATHS);
  const aland = analysis.mortality.liver.rows.find((r) => r.regionId === 'HVA91') ?? analysis.mortality.rectum.rows.find((r) => r.regionId === 'HVA91');
  assert.equal(aland.suppressed, true);
});
test('adversarial: a year reported by too few counties is not used for comparison', () => {
  const regions = Array.from({ length: 20 }, (_, i) => ({ id: `R${i}` }));
  const values = Object.fromEntries(regions.map((r, i) => [r.id, { 2022: 70 + i, 2023: 71 + i }]));
  values.R0[2024] = 10; // only one county has reported 2024
  const out = analyseIndicator({ key: 'x', stage: 'detection', direction: 1, unit: '%', target: 80, values, national: { 2023: 80, 2024: 50 } }, regions);
  assert.equal(out.year, 2023); assert.equal(out.national, 80);
});
test('adversarial: an indicator with pure noise raises no county flags', () => {
  const regions = Array.from({ length: 20 }, (_, i) => ({ id: `R${i}` }));
  const values = Object.fromEntries(regions.map((r, i) => [r.id, { 2020: 50 + ((i * 7) % 5), 2021: 50 - ((i * 3) % 5), 2022: 50 + ((i * 5) % 4), 2023: 50 - ((i * 11) % 4), 2024: 50 + ((i * 2) % 3) }]));
  const out = analyseIndicator({ key: 'n', stage: 'primary_care', direction: -1, unit: '%', values, national: { 2024: 50 } }, regions);
  assert.equal(out.rows.filter((r) => r.flagged).length, 0);
});
test('every county gets a pathway profile; unmeasured stages are named as data gaps', () => {
  for (const r of analysis.regions) assert.ok([null, 'detection', 'primary_care', 'referral'].includes(r.gapEmergesAt));
  assert.deepEqual(analysis.stages.filter((s) => !s.measured).map((s) => s.id), ['diagnosis', 'treatment']);
  assert.ok(analysis.dataGaps.some((g) => g.stage === 'treatment'));
});

// ------------------------------------------------------------------ recommendations
const regions = regionFacts(analysis);
const P = centralParameters();
test('no delay effect means no modelled benefit from timeliness actions', () => {
  assert.equal(relativeReduction(1, 84), 0);
  const p = { ...P, hr: 1 };
  assert.equal(deathsPostponed(regions[0], new Set(['timed-pathways', 'equal-fast-lane', 'navigation']), p).deaths, 0);
  assert.ok(deathsPostponed(regions[0], new Set(['ldct-pilot']), p).deaths > 0);
});
test('days saved never exceed the route gap, and actions overlap with diminishing returns', () => {
  const all = new Set(['timed-pathways', 'equal-fast-lane', 'navigation']);
  assert.ok(daysSaved(all, P) <= P.gapDays + 1e-9);
  const single = ['timed-pathways', 'equal-fast-lane', 'navigation'].map((id) => daysSaved(new Set([id]), P));
  assert.ok(daysSaved(all, P) < single.reduce((a, b) => a + b, 0));
  for (const r of regions) {
    for (const x of TIMELINESS_IDS) {
      for (const y of TIMELINESS_IDS.filter((id) => id !== x)) {
        const alone = deathsPostponed(r, new Set([x]), P).deaths;
        const withY = deathsPostponed(r, new Set([x, y]), P).deaths - deathsPostponed(r, new Set([y]), P).deaths;
        assert.ok(withY >= -1e-9, 'adding an action never hurts'); assert.ok(withY <= alone + 1e-9, 'submodular');
      }
    }
  }
});
test('the optimiser respects the budget and does nothing without one', () => {
  for (const budget of [0, 1e5, 2e6, 6e6, 2e7]) {
    const res = optimise(regions, { budget }); assert.ok(res.spent <= budget);
    close(res.picks.reduce((s, p) => s + p.cost, 0), res.spent, 1e-6);
  }
  assert.equal(optimise(regions, { budget: 0 }).picks.length, 0);
});
test('greedy portfolio is within 10% of the exhaustive optimum on a small instance', () => {
  const small = regions.slice(0, 3);
  for (const budget of [3e5, 8e5, 2e6]) {
    const exact = optimiseExact(small, { budget, epsilon: 3 });
    const greedy = weightedValue(small, optimise(small, { budget, epsilon: 3, thorough: true }), 3);
    assert.ok(greedy >= 0.9 * exact.value, `budget ${budget}: ${greedy} vs ${exact.value}`);
  }
});
test('stronger inequality aversion never moves benefit away from high-mortality counties', () => {
  const rec = recommend(analysis, { draws: 20 });
  const shares = rec.frontier.map((f) => f.shareInHighMortalityCounties);
  for (let i = 1; i < shares.length; i += 1) assert.ok(shares[i] >= shares[i - 1] - 1e-9);
  assert.ok(rec.frontier[0].deathsPostponed >= rec.frontier.at(-1).deathsPostponed - 1e-9, 'equity has a visible efficiency price');
});
test('sensitivity analysis is reproducible and every scenario number carries a range', () => {
  const a = recommend(analysis, { draws: 40 }); const b = recommend(analysis, { draws: 40 });
  assert.deepEqual(a.portfolio, b.portfolio); assert.equal(a.label, 'SCENARIO');
  for (const p of a.portfolio.picks) { assert.ok(p.low <= p.deathsPostponed && p.deathsPostponed <= p.high); assert.ok(p.stability >= 0 && p.stability <= 1); }
  assert.equal(a.samePathway.low, 0, 'the honest lower bound of the same-pathway scenario is zero');
});
test('the model is more conservative than the Danish natural experiment', () => {
  const v = recommend(analysis, { draws: 5 }).validation;
  assert.ok(v.modelHazardRatio > v.observedHazardRatio && v.modelHazardRatio < v.observedHigh);
});
test('every action and assumption is bound to a verified evidence row', () => {
  const rows = new Map(evidence.rows.map((r) => [r.id, r]));
  const cited = [...INTERVENTIONS.flatMap((i) => i.evidence), ...Object.values(ASSUMPTIONS).flatMap((a) => a.evidence || [])];
  assert.ok(cited.length > 20);
  for (const id of cited) { assert.ok(rows.has(id), `missing evidence ${id}`); assert.equal(rows.get(id).verified, true, `unverified evidence used: ${id}`); }
  for (const i of INTERVENTIONS) assert.ok(i.owner && i.metric && i.unknown && i.action && i.evidence.length > 0, i.id);
  assert.ok(evidence.rows.filter((r) => r.verified).every((r) => r.citation && r.url.startsWith('https://')));
});
test('detection track only proposes action where the 80% target is missed, and never over-claims the gain', () => {
  const rows = detectionTrack(analysis);
  assert.ok(rows.length > 10);
  for (const d of rows) { assert.ok(d.targetGap > 0 && d.gainPoints <= d.targetGap + 1e-9 && d.shareOfGapClosed <= 1); }
  assert.ok(costOf('navigation', regions[0]) > 0);
});

// ------------------------------------------------------------------ brief and claim check
const app = buildApp();
test('build binds evidence and provenance into the app file', () => {
  assert.match(app.provenance.snapshotSha256, /^[0-9a-f]{64}$/); assert.equal(app.analysis.regions.length, 23);
  assert.ok(app.evidence.length >= 25);
});
test('county brief is templated from the analysis, sourced, and never self-approved', () => {
  for (const id of ['HVA06', 'HVA90', 'HVA91', 'HVA21']) {
    const brief = buildBrief(app, id); assert.equal(brief.humanApproval, 'REQUIRED_NOT_GRANTED');
    assert.ok(brief.claims.length >= 3);
    for (const c of brief.claims) {
      assert.ok(['MEASURED', 'SCENARIO'].includes(c.kind)); assert.ok(c.text.length > 20 && !/undefined|NaN|null/.test(c.text), c.text);
      for (const e of c.evidence) assert.ok(app.evidence.some((r) => r.id === e && r.verified));
      if (c.kind === 'SCENARIO') assert.match(c.text, /range|expected to add/);
    }
  }
  const sat = buildBrief(app, 'HVA06').claims.find((c) => c.id === 'HVA06-mortality');
  assert.ok(sat.text.includes(String(app.analysis.regions.find((r) => r.regionId === 'HVA06').allCancer.smr)));
  assert.equal(buildBrief(app, 'NOPE'), null);
});
test('claim check without a key reports NOT_CONFIGURED instead of guessing', async () => {
  const brief = buildBrief(app, 'HVA06');
  const out = await verifyClaims(brief.claims, { apiKey: '', app });
  assert.equal(out.status, 'NOT_CONFIGURED'); assert.ok(out.results.every((r) => r.verdict === null && r.known && r.evidenceBound));
});
test('claim check routes by calibrated probability and sends server-side text only', async () => {
  const brief = buildBrief(app, 'HVA06'); const sent = [];
  const fake = (probabilities, choice, overclaim = 0.03) => async (url, init) => { sent.push(JSON.parse(init.body)); return { ok: true, json: async () => ({ model: 'jev-test', answers: { faithful: { type: 'choice', choice, confidence: 0.9, probabilities }, overclaim: { type: 'noul', noul: overclaim } }, usage: { input_tokens: 10, output_tokens: 1 } }) }; };
  const tampered = brief.claims.map((c, i) => (i === 0 ? { ...c, text: 'Cancer care here is the best in the world.' } : c));
  const ok = await verifyClaims(tampered, { apiKey: 'k', app, fetchImpl: fake({ supports: 0.95, contradicts: 0.02, says_nothing: 0.03 }, 'supports') });
  assert.equal(ok.status, 'CHECKED'); assert.ok(ok.results.every((r) => r.verdict === 'SUPPORTED'));
  assert.equal(ok.results[0].textMatchesServer, false);
  assert.ok(sent.every((b) => !JSON.stringify(b.state).includes('best in the world') && typeof b.state.claim === 'string' && b.questions.faithful.type === 'choice' && b.questions.overclaim.type === 'noul' && Object.keys(b.state.facts).length > 0));
  const weak = await verifyClaims(brief.claims.slice(0, 2), { apiKey: 'k', app, fetchImpl: fake({ supports: 0.6, contradicts: 0.1, says_nothing: 0.3 }, 'supports') });
  assert.ok(weak.results.every((r) => r.verdict === 'UNCLEAR' && r.needsHumanReview));
  const bad = await verifyClaims(brief.claims.slice(0, 1), { apiKey: 'k', app, fetchImpl: fake({ supports: 0.1, contradicts: 0.7, says_nothing: 0.2 }, 'contradicts') });
  assert.equal(bad.results[0].verdict, 'NOT_SUPPORTED');
  const over = await verifyClaims(brief.claims.slice(0, 1), { apiKey: 'k', app, fetchImpl: fake({ supports: 0.95, contradicts: 0.02, says_nothing: 0.03 }, 'supports', 0.8) });
  assert.equal(over.results[0].verdict, 'NOT_SUPPORTED', 'a faithful sentence that overclaims is still rejected');
  const unknown = await verifyClaims([{ id: 'HVA06-made-up' }], { apiKey: 'k', app, fetchImpl: fake({ supports: 0.99 }, 'supports') });
  assert.equal(unknown.results[0].reason, 'UNKNOWN_CLAIM');
  const down = await verifyClaims(brief.claims.slice(0, 2), { apiKey: 'k', app, fetchImpl: async () => { throw new Error('offline'); } });
  assert.equal(down.status, 'SERVICE_ERROR'); assert.ok(down.results.every((r) => r.needsHumanReview));
  assert.equal(verdictFrom(undefined).verdict, 'UNCLEAR');
});
