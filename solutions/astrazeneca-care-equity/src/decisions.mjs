// Source-scoped decision briefs. No registry context changes a county score,
// allocation, measured observation or modelled intervention effect.
import { INTERVENTIONS } from './recommend.mjs';

const KINDS = new Set(['observed_aggregate', 'source_limitation', 'strategy_target']);
const finite = Number.isFinite;
const STAGES = ['detection', 'primary_care', 'referral'];
const PROPOSALS = {
  screen_cervix: 'self-sampling',
  screen_breast: 'screening-reminders',
  screen_colorectal: 'screening-reminders',
  gp_wait_over_7d: 'equal-fast-lane',
  gp_wait_over_3m: 'navigation',
  referral_handled_3d: 'timed-pathways',
  referral_handled_over_21d: 'timed-pathways',
  specialist_wait_over_6m: 'timed-pathways',
};

export function validateRegistryContext(context) {
  if (context?.schemaVersion !== 'care-equity-registry-context-v1' || !Array.isArray(context.records)) {
    throw new Error('Invalid registry evidence contract');
  }
  const ids = new Set();
  for (const record of context.records) {
    if (!record.id || ids.has(record.id) || !KINDS.has(record.kind)) throw new Error('Invalid evidence identity or kind');
    ids.add(record.id);
    if (!record.source?.url?.startsWith('https://') || !record.source.locator || !record.source.publisher
        || !record.source.retrievedAt || !record.scope?.population || !record.scope.geography
        || record.scope.regionId !== null || !Array.isArray(record.scope.cancerCodes)
        || !Number.isInteger(record.scope.period?.start) || !Number.isInteger(record.scope.period?.end)
        || record.scope.period.start > record.scope.period.end
        || !record.limitations?.length || !record.comparability || !record.nextEvidenceNeeded) {
      throw new Error('National context requires complete provenance, scope and limitations');
    }
    if (record.kind === 'observed_aggregate') {
      const m = record.measure;
      if (!m || m.unit !== '%' || !m.definition || !Number.isInteger(m.numerator)
          || !Number.isInteger(m.denominator) || m.denominator <= 0 || m.numerator < 0
          || m.numerator > m.denominator || !finite(m.reportedValue)
          || Math.abs(100 * m.numerator / m.denominator - m.reportedValue) > 0.05) {
        throw new Error('Invalid observed proportion or denominator');
      }
    } else if (record.measure !== null) throw new Error('Policy and limitations cannot become observed measures');
  }
  if (context.future?.kind !== 'future_capability' || context.future.status !== 'NOT_IMPLEMENTED'
      || !context.future.source?.url?.startsWith('https://') || !context.future.boundary) {
    throw new Error('Future capability must retain its implementation boundary');
  }
  return context;
}

// Match the actual county years with national years before using a flag as a
// reason to investigate. A latest-year national value is not a three-year mean.
export function comparableSignal(indicator, row) {
  if (!indicator || !row || !indicator.rankable || ![1, -1].includes(indicator.direction)) return null;
  const years = Object.keys(row.series || {}).map(Number)
    .filter(y => y <= row.year && finite(row.series[y])).sort((a, b) => a - b).slice(-3);
  if (!years.length || years.some(y => !finite(indicator.nationalSeries?.[y]))) return null;
  const mean = values => values.reduce((a, b) => a + b, 0) / values.length;
  const county = mean(years.map(y => row.series[y]));
  const national = mean(years.map(y => indicator.nationalSeries[y]));
  if ((national - county) * indicator.direction <= 0) return null;
  return {
    indicator: indicator.key, title: indicator.title, years, county, national, unit: indicator.unit,
    scope: indicator.stage === 'detection' ? 'screening_participation' : 'general_access_proxy',
    source: { publisher: 'THL Sotkanet', url: indicator.sourceUrl, locator: indicator.title },
    interpretation: indicator.stage === 'detection'
      ? 'A participation signal; it does not identify the cause of a county outcome gap.'
      : 'General healthcare access is a proxy; it does not measure a cancer-specific delay.',
  };
}

function investigation(app, region) {
  for (const stage of STAGES) {
    // Existing flags are only a candidate-discovery rule. Confirm the direction
    // on identical observation years; do not label this a new significance test.
    for (const key of region.stages[stage]?.flagged || []) {
      const ind = app.analysis.indicators[key];
      const signal = comparableSignal(ind, ind?.rows.find(r => r.regionId === region.regionId));
      const intervention = INTERVENTIONS.find(i => i.id === PROPOSALS[key]);
      if (signal && intervention) return { stage, signal, intervention };
    }
  }
  return { stage: 'treatment', signal: null, intervention: INTERVENTIONS.find(i => i.id === 'pathway-timestamps') };
}

export function buildDecisionBrief(app, regionId) {
  validateRegistryContext(app.registryContext);
  const region = app.analysis.regions.find(r => r.regionId === regionId);
  if (!region) throw new Error('Unknown county');
  const { stage, signal, intervention: iv } = investigation(app, region);
  const screening = signal?.scope === 'screening_participation';
  const sources = iv.evidence.map(id => {
    const evidence = app.evidence.find(e => e.id === id && e.verified);
    if (!evidence) throw new Error('Unbound decision evidence: ' + id);
    return { id, title: evidence.citation, url: evidence.url, claim: evidence.claim };
  });
  const mortality = app.analysis.mortality.all_cancers;
  const m = mortality.rows.find(r => r.regionId === regionId && !r.suppressed);
  const observation = m ? {
    kind: 'observed_aggregate', measure: 'Age-standardised all-cancer mortality ratio',
    value: m.shrunk, low: m.shrunkLow, high: m.shrunkHigh, period: mortality.window,
    scope: 'county', regionId, reference: 'Finland = 1; empirical-Bayes estimate',
    source: app.provenance.sources.statfin,
    interpretation: 'This describes an outcome difference, not its cause or a number of avoidable deaths.',
  } : { kind: 'unavailable', reason: 'Mortality is missing or suppressed; no outcome ranking is supplied.' };
  return {
    schemaVersion: 'care-equity-decision-v1',
    regionId, regionName: region.name, snapshotSha256: app.provenance.snapshotSha256,
    registryContextSha256: app.provenance.registryContextSha256,
    humanApproval: 'REQUIRED_NOT_GRANTED',
    status: signal ? 'INVESTIGATE_SIGNAL' : 'MEASUREMENT_FIRST',
    prioritisation: 'Existing statistical flags, checked against matched national years; screening, primary care, then referral. An investigation order, not a causal or benefit ranking.',
    observation, signal, stage,
    action: {
      id: iv.id, title: signal ? iv.title : 'Establish a comparable cancer-pathway baseline',
      decision: screening ? 'Review an outreach pilot after checking local participation barriers.'
        : signal ? 'Check the cancer-specific pathway before committing to a service intervention.'
          : 'Assign a measurement owner before selecting a service intervention.',
      proposedChange: iv.action, owner: iv.owner, mechanism: iv.mechanism,
      mechanismKind: 'HYPOTHESIS', strategyMeasure: iv.strategyMeasure,
      goal3: '3.1 timely pathways; 3.2 comparable quality information. Screening also supports Goal 2.',
      first30Days: screening
        ? ['Confirm invited and participating populations and exclusions.', 'Check contact reach, language and access barriers with the screening lead.', 'Agree a bounded pilot, comparison and review date.']
        : ['Name a county cancer-pathway lead and registry/data steward.', 'Agree one cancer pathway, timestamp definitions, exclusions and target.', 'Publish an aggregate baseline with denominator and missingness before choosing a pilot.'],
      reviewAt90Days: screening
        ? 'Compare participation against the prespecified baseline/comparison and report reach, exclusions and unintended access barriers.'
        : 'Review timestamp completeness, median and 90th-percentile waits, and target-time attainment; investigate missing data before regional interpretation.',
      monitoring: {
        metric: screening ? 'Participation among people invited to the selected screening programme'
          : 'Cancer-specific pathway completeness and time-to-treatment',
        numerator: screening ? 'Eligible invited people who participated'
          : 'Eligible new cases with the required dates; separately, cases treated within the agreed cancer-specific target',
        denominator: screening ? 'All eligible invited people, with exclusions reported'
          : 'All eligible new cases in the chosen cancer pathway; report cases missing dates separately',
        baseline: null, target: null,
        missingness: 'Report unknown and excluded cases separately; do not count unknown as no care.',
        design: 'Local baseline and comparison to be agreed before a pilot; dates are planning proposals, not observed outcomes.',
      },
      cost: { value: null, status: 'NOT_ESTIMATED', note: 'The pilot needs a local cost estimate. The portfolio below is a separate assumption-based scenario.' },
      unknowns: [iv.unknown, 'Local feasibility and effect are unmeasured; the proposed owner has not accepted the work.'],
      sources,
    },
    nationalContext: structuredClone(app.registryContext.records),
    future: structuredClone(app.registryContext.future),
    limitations: [
      'Diagnosis and cancer-specific treatment-start times are unavailable in this snapshot.',
      'National lung recording figures are context only; they are not county estimates or model inputs.',
      'This is a proposal for human review. No intervention has been approved or shown to improve outcomes.',
    ],
  };
}
