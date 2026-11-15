import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { buildApp } from '../src/build.mjs';
import { buildDecisionBrief, comparableSignal, validateRegistryContext } from '../src/decisions.mjs';
import { auditForecast } from '../src/forecast-integrity.mjs';
import { renderDecisionCard } from '../web/decision-view.mjs';

const app = buildApp();
const context = app.registryContext;
const copy = x => structuredClone(x);
test('registry context retains the exact national lung numerator, denominator and period', () => {
  const r = context.records.find(r => r.id === 'fi-lung-extent-missing-2019-2023');
  assert.equal(r.measure.numerator, 7097);
  assert.equal(r.measure.denominator, 14873);
  assert.equal(r.measure.reportedValue, 47.7);
  assert.deepEqual(r.scope.cancerCodes, ['C33', 'C34']);
  assert.deepEqual(r.scope.period, { start: 2019, end: 2023 });
  assert.equal(r.scope.regionId, null);
  assert.match(r.limitations.join(' '), /does not mean staging was not performed/);
  assert.match(r.source.url, /^https:\/\/syoparekisteri\.fi\//);
});

test('invalid proportions, missing denominators and county reassignment fail explicitly', () => {
  for (const denominator of [null, 0, -1, 1]) {
    const c = copy(context); c.records[0].measure.denominator = denominator;
    assert.throws(() => validateRegistryContext(c), /proportion|denominator/);
  }
  const c = copy(context); c.records[0].scope.regionId = 'HVA06';
  assert.throws(() => validateRegistryContext(c), /National context/);
  const policy = copy(context); policy.records[0].kind = 'strategy_target';
  assert.throws(() => validateRegistryContext(policy), /observed measures/);
});

test('matched-year evidence cannot reuse the latest national value as a multi-year mean', () => {
  const row = { year: 2023, series: { 2021: 60, 2022: 60, 2023: 60 } };
  const indicator = { key: 'screen_breast', title: 'Participation', rankable: true, direction: 1,
    stage: 'detection', national: 90, nationalSeries: { 2021: 40, 2022: 40, 2023: 90 } };
  assert.equal(comparableSignal(indicator, row), null); // Matched mean < county mean.
  indicator.nationalSeries = { 2021: 70, 2022: 75, 2023: 80 };
  const signal = comparableSignal(indicator, row);
  assert.deepEqual(signal.years, [2021, 2022, 2023]);
  assert.equal(signal.national, 75);
  delete indicator.nationalSeries[2022];
  assert.equal(comparableSignal(indicator, row), null);
});

test('every county gets an accountable proposal with unknowns and unchanged analytical inputs', () => {
  const analysisBefore = JSON.stringify(app.analysis), recommendationBefore = JSON.stringify(app.recommendation);
  for (const region of app.analysis.regions) {
    const d = buildDecisionBrief(app, region.regionId);
    assert.equal(d.humanApproval, 'REQUIRED_NOT_GRANTED');
    assert.ok(d.action.owner && d.action.monitoring.denominator && d.action.first30Days.length);
    assert.equal(d.action.cost.value, null);
    assert.equal(d.action.monitoring.baseline, null);
    assert.equal(d.action.monitoring.target, null);
    assert.ok(d.action.sources.every(s => s.url.startsWith('https://')));
    assert.ok(d.nationalContext.every(r => r.scope.regionId === null));
    assert.equal(d.future.status, 'NOT_IMPLEMENTED');
    if (d.signal?.scope === 'general_access_proxy') assert.match(d.signal.interpretation, /does not measure a cancer-specific delay/);
  }
  assert.equal(JSON.stringify(app.analysis), analysisBefore);
  assert.equal(JSON.stringify(app.recommendation), recommendationBefore);
  assert.throws(() => buildDecisionBrief(app, 'unknown'), /Unknown county/);
});

test('visible and exported decision evidence keep scope, limitations and provenance', () => {
  const d = buildDecisionBrief(app, 'HVA06');
  const html = renderDecisionCard(d, { detailed: true });
  for (const text of ['47.7%', '7,097 / 14,873', '2019–2023', 'C33, C34', 'Missing registry information', 'Denominator', 'human review required']) assert.ok(html.includes(text), text);
  assert.equal(d.registryContextSha256, createHash('sha256').update(readFileSync(new URL('../data/evidence/registry-context-v1.json', import.meta.url))).digest('hex'));
  const unsafe = copy(d); unsafe.action.title = '<script>bad()</script>';
  assert.ok(!renderDecisionCard(unsafe).includes('<script>'));
  assert.equal(JSON.parse(JSON.stringify(d)).nationalContext[0].measure.denominator, 14873);
});

function eligibleForecast() {
  const q = { year: 2026, q05: 60, q25: 65, q50: 70, q75: 75, q95: 80 };
  return {
    metrics: { screening: { chosen: 'ridge' } },
    forecasts: { screening: { HVA06: { lastYear: 2025, lastValue: 68, h1: q, pWorse: { h1: .99 } } } },
    evaluation: {
      panelSha256: 'a'.repeat(64),
      split: { protocol: 'target-year-disjoint-v1', trainOrigins: [2020], trainLabelsThrough: 2021,
        validationOrigins: [2021], testOrigins: [2023], horizons: [1, 2],
        targetYears: { train: [2021], validation: [2022, 2023], test: [2024, 2025] } },
      indicators: { screening: { chosen: 'ridge', horizons: { h1: { status: 'ELIGIBLE', validationN: 3, testN: 3, trainingN: 4 } } } },
    },
  };
}

test('historical forecasts remain byte-identical and cannot become qualified after a code change', () => {
  const bytes = readFileSync(new URL('../data/ml/forecast-v1.json', import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), '30befeb52603bcb9698ab41cff324b52fcd9ebd25b9ae2a0288c0be69a91e52c');
  assert.equal(app.forecast, null);
  assert.equal(app.forecastStatus.status, 'WITHHELD');
  assert.match(app.forecastStatus.reasons.join(' '), /2023/);
  assert.match(app.forecastStatus.indicators.screen_colorectal.reasons.join(' '), /No validation observations/);
});

test('forecast admission rejects overlap, missing evidence and unsupported training', () => {
  const f = eligibleForecast();
  assert.equal(auditForecast(f).status, 'ELIGIBLE');
  assert.deepEqual(auditForecast(f).forecast.forecasts.screening.HVA06.pWorse, {});
  for (const change of [
    x => { delete x.evaluation; },
    x => { x.evaluation.split.targetYears.test = [2023, 2024]; },
    x => { x.evaluation.split.testOrigins = [2022, 2023]; },
    x => { x.evaluation.indicators.screening.horizons.h1.validationN = 0; },
    x => { x.evaluation.indicators.screening.horizons.h1.testN = 0; },
    x => { x.evaluation.indicators.screening.horizons.h1.trainingN = 0; },
    x => { x.metrics.screening.chosen = null; },
  ]) { const bad = copy(f); change(bad); assert.equal(auditForecast(bad).forecast, null); }
});

test('collapsed, unordered and non-finite bands cannot produce an admitted forecast', () => {
  for (const q of [
    { q05: 70, q25: 70, q50: 70, q75: 70, q95: 70 },
    { q05: 60, q25: 65, q50: 90, q75: 75, q95: 80 },
    { q05: NaN, q25: 65, q50: 70, q75: 75, q95: 80 },
  ]) {
    const f = eligibleForecast(); Object.assign(f.forecasts.screening.HVA06.h1, q);
    assert.equal(auditForecast(f).forecast, null);
  }
});
