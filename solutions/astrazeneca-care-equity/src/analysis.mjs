// Gap detection and pathway localisation on the public-data snapshot.
// Input: data/snapshot/public-v1.json (see pipeline/fetch_public_data.py).
// Nothing here is patient-level and nothing is a causal claim: outputs are
// measured differences with their uncertainty, plus clearly marked data gaps.
import {
  benjaminiHochberg, empiricalBayesSmr, inequalityIndices, mean, normalCdf, pooledNoiseSd, round, smr, sum,
  weightedLinearRegression,
} from './stats.mjs';

export const PATHWAY_STAGES = [
  { id: 'detection', label: 'Early detection', brief: 'detection', measured: true },
  { id: 'primary_care', label: 'First contact and primary care', brief: 'referral from primary to specialist care', measured: true },
  { id: 'referral', label: 'Referral to specialist care', brief: 'referral from primary to specialist care', measured: true },
  { id: 'diagnosis', label: 'Diagnosis', brief: 'diagnosis', measured: false },
  { id: 'treatment', label: 'Treatment start', brief: 'treatment initiation', measured: false },
  { id: 'outcome', label: 'Outcome', brief: 'treatment outcomes', measured: true },
];

export const STAGE_INDICATORS = {
  detection: ['screen_breast', 'screen_cervix', 'screen_colorectal'],
  primary_care: ['gp_wait_over_7d', 'gp_wait_over_3m'],
  referral: ['referral_handled_3d', 'referral_handled_over_21d', 'specialist_wait_over_6m'],
};

export const MORTALITY_SITES = ['all_cancers', 'lung', 'colon', 'rectum', 'breast', 'pancreas', 'liver', 'prostate', 'haematological'];
const MIN_REGIONS = 15;
export const MIN_EXPECTED_DEATHS = 20; // below this a regional ratio is suppressed, not ranked

const latestYear = (indicator) => {
  const counts = {};
  for (const series of Object.values(indicator.values)) for (const y of Object.keys(series)) counts[y] = (counts[y] || 0) + 1;
  const ok = Object.keys(counts).filter((y) => counts[y] >= MIN_REGIONS).sort();
  return ok.length ? ok[ok.length - 1] : null;
};

const lastYears = (series, year, n) => {
  const ys = Object.keys(series).filter((y) => y <= year).sort().slice(-n);
  return ys.map((y) => series[y]);
};

const trendPerYear = (series) => {
  const ys = Object.keys(series).sort();
  if (ys.length < 3) return null;
  return weightedLinearRegression(ys.map(Number), ys.map((y) => series[y])).slope;
};

// Indicators whose regional values are too noisy to rank (shown as context only).
const CONTEXT_ONLY = new Set(['cervix_5y_survival']);

export function analyseIndicator(indicator, regions) {
  const year = latestYear(indicator);
  if (!year) return null;
  const noise = pooledNoiseSd(Object.values(indicator.values));
  const national = indicator.national[year] ?? null;
  const rankable = indicator.direction !== 0 && !CONTEXT_ONLY.has(indicator.key);
  const rows = [];
  for (const region of regions) {
    const series = indicator.values[region.id];
    if (!series || series[year] == null) continue;
    const recent = lastYears(series, year, 3);
    const level = mean(recent);
    const se = noise == null ? null : Math.max(noise / Math.sqrt(recent.length), 1e-6);
    // gap > 0 always means "worse than the reference".
    const aligned = (ref) => (!rankable || ref == null ? null : (ref - level) * indicator.direction);
    const gap = aligned(national);
    const targetGap = aligned(indicator.target ?? null);
    const p = (g) => (g == null || se == null ? null : round(normalCdf(g / se), 4));
    rows.push({
      regionId: region.id, year: Number(year), value: series[year], level: round(level, 2), nYears: recent.length,
      gap: gap == null ? null : round(gap, 2), se: se == null ? null : round(se, 3), pWorse: p(gap),
      targetGap: targetGap == null ? null : round(targetGap, 2), pMissesTarget: p(targetGap),
      trendPerYear: round(trendPerYear(series), 3), series,
    });
  }
  // County-specific flag: worse than the national value, false discovery rate 10% within the indicator.
  const testable = rows.filter((r) => r.pWorse != null);
  const flags = benjaminiHochberg(testable.map((r) => 1 - r.pWorse), 0.1);
  testable.forEach((r, i) => { r.flagged = flags[i] && r.gap > 0; });
  rows.forEach((r) => { if (r.flagged == null) r.flagged = false; r.missesTarget = r.pMissesTarget != null && r.pMissesTarget >= 0.95; });
  const withTarget = rows.filter((r) => r.targetGap != null);
  return {
    key: indicator.key, stage: indicator.stage, unit: indicator.unit, direction: indicator.direction, rankable,
    title: indicator.titleEn || indicator.titleFi, titleFi: indicator.titleFi, year: Number(year), national, target: indicator.target ?? null,
    countiesMissingTarget: withTarget.length ? withTarget.filter((r) => r.missesTarget).length : null, countiesWithData: rows.length,
    noiseSd: noise == null ? null : round(noise, 3), sourceId: indicator.sourceId, sourceUrl: indicator.indicatorPage, requestUrl: indicator.requestUrl,
    nationalSeries: indicator.national, rows,
  };
}

export function analyseMortality(site, regions) {
  const eligible = regions
    .map((region) => ({ regionId: region.id, ...(site.regions[region.id] || {}) }))
    .filter((r) => Number.isFinite(r.observed) && Number.isFinite(r.expected) && r.expected > 0);
  const stable = eligible.filter((r) => r.expected >= MIN_EXPECTED_DEATHS);
  const eb = empiricalBayesSmr(stable.map((r) => ({ regionId: r.regionId, observed: r.observed, expected: r.expected })));
  const byId = Object.fromEntries(eb.rows.map((r) => [r.regionId, r]));
  const years = site.window.length;
  const rows = eligible.map((r) => {
    const raw = smr(r.observed, r.expected);
    const s = byId[r.regionId];
    if (!s) {
      return { regionId: r.regionId, observed: r.observed, expected: round(r.expected, 1), suppressed: true, reason: 'EXPECTED_DEATHS_BELOW_MINIMUM' };
    }
    return {
      regionId: r.regionId, observed: r.observed, expected: round(r.expected, 1), suppressed: false,
      smr: round(raw.smr, 3), smrLow: round(raw.low, 3), smrHigh: round(raw.high, 3),
      shrunk: round(s.shrunk, 3), shrunkLow: round(s.low, 3), shrunkHigh: round(s.high, 3),
      pAboveOne: round(s.pAboveOne, 4), reliability: round(s.weight, 3),
      excessDeathsPerYear: round(((s.shrunk - 1) * r.expected) / years, 1),
      excessLow: round(((s.low - 1) * r.expected) / years, 1), excessHigh: round(((s.high - 1) * r.expected) / years, 1),
      series: r.series,
    };
  });
  const testable = rows.filter((r) => !r.suppressed);
  const flags = benjaminiHochberg(testable.map((r) => 1 - r.pAboveOne), 0.1);
  testable.forEach((r, i) => { r.flagged = flags[i] && r.shrunk > 1; });
  return {
    label: site.label, window: site.window, nationalDeathsByYear: site.nationalDeathsByYear,
    priorVariance: round(eb.priorVariance, 5), betweenRegionSd: round(Math.sqrt(eb.priorVariance), 4), rows,
  };
}

function nordicGap(nordcanSurvival) {
  const out = [];
  for (const [site, block] of Object.entries(nordcanSurvival || {})) {
    const periods = [...new Set(block.rows.map((r) => r.period))].sort();
    const period = periods[periods.length - 1];
    for (const sex of ['male', 'female']) {
      const pick = (country) => block.rows.find((r) => r.period === period && r.sex === sex && r.country === country);
      const fi = pick('Finland'); const se = pick('Sweden'); const no = pick('Norway');
      if (!fi || !se || !no) continue;
      const benchmark = (se.value + no.value) / 2;
      const history = periods.map((p) => {
        const f = block.rows.find((r) => r.period === p && r.sex === sex && r.country === 'Finland');
        const s = block.rows.find((r) => r.period === p && r.sex === sex && r.country === 'Sweden');
        const n = block.rows.find((r) => r.period === p && r.sex === sex && r.country === 'Norway');
        return f && s && n ? { period: p, finland: f.value, benchmark: round((s.value + n.value) / 2, 1) } : null;
      }).filter(Boolean);
      out.push({
        site, sex, period, finland: fi.value, finlandLow: fi.low, finlandHigh: fi.high, sweden: se.value, norway: no.value,
        benchmark: round(benchmark, 1), gap: round(fi.value - benchmark, 1),
        // The gap is "clear" when Finland's interval lies entirely below the benchmark.
        clear: fi.high != null && fi.high < benchmark, requestUrl: block.requestUrl, history,
      });
    }
  }
  return out.sort((a, b) => a.gap - b.gap);
}

const zScores = (values) => {
  const xs = values.filter((v) => v != null);
  if (xs.length < 3) return values.map(() => null);
  const m = mean(xs);
  const sd = Math.sqrt(sum(xs.map((x) => (x - m) ** 2)) / (xs.length - 1)) || 1;
  return values.map((v) => (v == null ? null : (v - m) / sd));
};

export function analyse(snapshot) {
  const regions = snapshot.regions.map((r) => ({ id: r.id, name: r.nameEn || r.nameFi, nameFi: r.nameFi }));
  const ind = snapshot.indicators;
  const indicators = {};
  for (const key of Object.keys(ind)) {
    const a = analyseIndicator(ind[key], regions);
    if (a) indicators[key] = a;
  }
  const mortality = {};
  for (const key of MORTALITY_SITES) if (snapshot.mortality[key]) mortality[key] = analyseMortality(snapshot.mortality[key], regions);

  const valueOf = (key, regionId) => indicators[key]?.rows.find((r) => r.regionId === regionId)?.value ?? null;
  const levelOf = (key, regionId) => indicators[key]?.rows.find((r) => r.regionId === regionId)?.level ?? null;

  // Stage scores: direction-aligned z-scores across regions, averaged within a stage.
  const stageZ = {};
  for (const [stage, keys] of Object.entries(STAGE_INDICATORS)) {
    const perIndicator = keys.filter((k) => indicators[k]).map((k) => {
      const a = indicators[k];
      const worse = regions.map((r) => { const v = levelOf(k, r.id); return v == null ? null : -v * a.direction; });
      return zScores(worse);
    });
    stageZ[stage] = regions.map((_, i) => {
      const zs = perIndicator.map((col) => col[i]).filter((z) => z != null);
      return zs.length ? mean(zs) : null;
    });
  }
  const all = mortality.all_cancers;
  const outcomeZ = zScores(regions.map((r) => all?.rows.find((x) => x.regionId === r.id && !x.suppressed)?.shrunk ?? null));

  const profiles = regions.map((region, i) => {
    const stages = {};
    for (const stage of Object.keys(STAGE_INDICATORS)) {
      const rows = STAGE_INDICATORS[stage].map((k) => ({ key: k, row: indicators[k]?.rows.find((r) => r.regionId === region.id) })).filter((x) => x.row);
      const flagged = rows.filter((x) => x.row.flagged).map((x) => x.key);
      const missesTarget = rows.filter((x) => x.row.missesTarget).map((x) => x.key);
      stages[stage] = { z: stageZ[stage][i] == null ? null : round(stageZ[stage][i], 2), flagged, missesTarget, measured: rows.length > 0 };
    }
    const mRow = all?.rows.find((x) => x.regionId === region.id);
    stages.outcome = {
      z: outcomeZ[i] == null ? null : round(outcomeZ[i], 2),
      flagged: Object.entries(mortality).filter(([, m]) => m.rows.find((x) => x.regionId === region.id)?.flagged).map(([k]) => k),
      measured: !!mRow && !mRow.suppressed,
    };
    const ordered = ['detection', 'primary_care', 'referral'];
    const earliestFlagged = ordered.find((s) => stages[s].flagged.length > 0) ?? null;
    const worst = ordered.filter((s) => stages[s].z != null).sort((a, b) => stages[b].z - stages[a].z)[0] ?? null;
    const population = valueOf('population', region.id);
    return {
      regionId: region.id, name: region.name, nameFi: region.nameFi, population,
      age65Plus: valueOf('age_65_plus', region.id), educationIndex: valueOf('education_index', region.id),
      unemployment: valueOf('unemployment', region.id), lowIncome: valueOf('low_income', region.id),
      cancerIndex: valueOf('cancer_index', region.id), privateReferralShare: valueOf('private_referral_share', region.id),
      stages, gapEmergesAt: earliestFlagged, weakestMeasuredStage: worst,
      allCancer: mRow && !mRow.suppressed ? { smr: mRow.shrunk, low: mRow.shrunkLow, high: mRow.shrunkHigh, pAboveOne: mRow.pAboveOne, excessDeathsPerYear: mRow.excessDeathsPerYear } : null,
      projection: snapshot.projection?.[region.id] ?? null,
    };
  });

  // Socioeconomic gradient across counties (ecological: describes places, not individuals).
  const gradient = (getter, sesKey) => {
    const rows = profiles.map((p) => ({ value: getter(p), ses: p[sesKey], population: p.population })).filter((r) => r.value != null && r.ses != null && r.population);
    return rows.length >= 10 ? inequalityIndices(rows) : null;
  };
  const gradients = [];
  const addGradient = (id, label, unit, getter, worseWhen) => {
    const g = gradient(getter, 'educationIndex');
    if (!g) return;
    gradients.push({
      id, label, unit, ses: 'education_index', sii: round(g.sii, 2), siiLow: round(g.siiLow, 2), siiHigh: round(g.siiHigh, 2),
      r: round(g.r, 2), leastAdvantaged: round(g.bottom, 2), mostAdvantaged: round(g.top, 2), n: g.n,
      // Inverse care law signal: the less-educated end of the country is also the worse-served end.
      disadvantagesLowSes: worseWhen === 'higher' ? g.sii < 0 : g.sii > 0,
      excludesZero: g.siiLow != null && (g.siiLow > 0 || g.siiHigh < 0),
    });
  };
  for (const key of [...STAGE_INDICATORS.detection, ...STAGE_INDICATORS.primary_care, 'specialist_wait_over_6m']) {
    const a = indicators[key];
    if (a) addGradient(key, a.title, a.unit, (p) => levelOf(key, p.regionId), a.direction === 1 ? 'lower' : 'higher');
  }
  for (const site of ['all_cancers', 'lung', 'colon', 'breast']) {
    if (mortality[site]) addGradient(`smr_${site}`, `Age-standardised mortality ratio, ${mortality[site].label}`, 'ratio (FI=1)', (p) => mortality[site].rows.find((x) => x.regionId === p.regionId && !x.suppressed)?.shrunk ?? null, 'higher');
  }

  const deathsByYear = snapshot.mortality.all_cancers.nationalDeathsByYear;
  const window = snapshot.mortality.all_cancers.window;
  const latestDeaths = deathsByYear[window[window.length - 1]];
  const meanDeaths = mean(window.map((y) => deathsByYear[y]));
  const projected = (year) => sum(profiles.map((p) => p.projection?.[year]?.expectedCancerDeathsPerYear ?? 0));

  const goal3 = {
    title: 'Ensuring equal and effective cancer care',
    source: 'fi-strategy-goal3',
    indicators: [
      {
        id: 'nordic-survival', label: 'Five-year survival of poor-prognosis cancers reaches the Nordic level', status: 'MEASURED_NATIONAL',
        note: 'NORDCAN five-year relative survival; benchmark is the mean of Sweden and Norway, as defined in the strategy.',
        rows: nordicGap(snapshot.nordcanSurvival),
      },
      {
        id: 'mortality-minus-10', label: 'Cancer mortality decreases by 10%', status: 'MEASURED_REGIONAL',
        baselineDeathsPerYear: round(meanDeaths, 0), latestDeaths, targetDeathsPerYear: round(meanDeaths * 0.9, 0),
        // Constant age-specific death rates applied to the official population projection.
        demographicPressure: { 2024: round(projected('2024'), 0), 2030: round(projected('2030'), 0), 2035: round(projected('2035'), 0) },
        note: 'With unchanged age-specific rates, ageing alone raises the yearly death count; the -10% target therefore needs a larger fall in rates.',
      },
      {
        id: 'treatment-within-target', label: 'Patients access treatment within the established target times', status: 'NOT_PUBLICLY_MEASURABLE',
        note: 'No open county-level statistic reports cancer-specific time from referral to diagnosis or to treatment start. The closest public signals are general primary-care and specialised-care waiting indicators, shown under the pathway stages.',
      },
    ],
  };

  const dataGaps = [
    { stage: 'diagnosis', missing: 'Time from referral to diagnosis, by cancer and county', why: 'Needed to tell a referral problem from a diagnostic-capacity problem.' },
    { stage: 'treatment', missing: 'Time from diagnosis (or MDT decision) to first treatment, by cancer and county', why: 'This is the Goal 3 indicator "treatment within target times"; it cannot be computed from open data today.' },
    { stage: 'detection', missing: 'Stage at diagnosis by county (stage is unrecorded for a large share of cases)', why: 'Needed for the strategy target of 70% diagnosed at stages I-II.' },
    { stage: 'route', missing: 'Entry route (public, occupational, private) per cancer patient', why: 'The Finnish DLBCL cohort shows an 84-day mean difference by entry route; nationally the route is not reported.' },
  ];

  return {
    schemaVersion: 'care-equity-analysis-v1',
    dataClass: snapshot.dataClass,
    snapshotGeneratedAt: snapshot.generatedAt,
    regions: profiles, indicators, mortality, gradients, goal3, dataGaps, stages: PATHWAY_STAGES,
    methods: {
      indicatorGap: 'Three-year mean of each county vs the national value (county-specific flag) and vs the strategy target where one exists (target shortfall). Uncertainty from the pooled year-to-year noise of the same indicator (variance of first differences / 2). County flags control the false discovery rate at 10% within each indicator (Benjamini-Hochberg); a target shortfall needs 95% probability.',
      mortality: `Indirectly age-standardised mortality ratio (${window[0]}-${window[window.length - 1]} pooled) with exact Poisson intervals, then gamma-Poisson empirical Bayes shrinkage towards the national ratio. Regions with fewer than ${MIN_EXPECTED_DEATHS} expected deaths are suppressed.`,
      gradient: 'Slope index of inequality: population-weighted regression on the county rank by education index, bootstrap interval over counties. Ecological; not an individual-level effect.',
    },
  };
}
