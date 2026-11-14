const sourceKinds = new Set(['SYNTHETIC_DEMONSTRATION', 'CLEARED_AGGREGATE_INPUT']);
const safeString = (value) => typeof value === 'string' && value.length > 0 && value.length <= 200;
const pct = (value) => Math.round(value * 100) / 100;
export const MIN_COHORT_N = 30;

export async function digest(value) {
  // Native WebCrypto runs in Node >=22 and modern browsers; no bundled crypto dependency.
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const hash = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}

function validateRow(row, indicator, sourceId) {
  if (!row || typeof row !== 'object' || row.sourceRef !== sourceId) return 'SOURCE_MISMATCH';
  if (!['AGE_STANDARDIZED', 'NOT_STANDARDIZED'].includes(row.standardization)) return 'UNKNOWN_STANDARDIZATION';
  if (row.standardization !== indicator.standardization) return 'NONCOMPARABLE_STANDARDIZATION';
  for (const key of ['value', 'low', 'high', 'n']) {
    if (typeof row[key] !== 'number' || !Number.isFinite(row[key])) return 'INVALID_MEASUREMENT';
  }
  if (!Number.isInteger(row.n) || row.n < 0 || row.low > row.value || row.value > row.high) return 'INVALID_MEASUREMENT';
  if (indicator.unit === 'percent' && (row.low < 0 || row.high > 100)) return 'INVALID_MEASUREMENT';
  if (row.low < 0) return 'INVALID_MEASUREMENT';
  return null;
}

export async function assess(dataset, { indicatorId, focusId, peerId }) {
  if (!dataset || !sourceKinds.has(dataset.dataClass) || dataset.schemaVersion !== 'equity-fixture-v1') {
    return { status: 'REFUSED', reason: 'UNKNOWN_DATA_PROVENANCE' };
  }
  if (!safeString(dataset.source?.id) || !safeString(dataset.datasetId) ||
      !safeString(dataset.source?.license) || !safeString(dataset.source?.retrievedAt)) {
    return { status: 'REFUSED', reason: 'UNTRACEABLE_SOURCE' };
  }
  if (dataset.dataClass === 'CLEARED_AGGREGATE_INPUT' && dataset.source?.isObservedPublicDataset !== true) {
    return { status: 'REFUSED', reason: 'SOURCE_NOT_ATTESTED' };
  }
  const indicator = dataset.indicators?.find(item => item.id === indicatorId);
  const focus = dataset.regions?.find(item => item.id === focusId);
  const peer = dataset.regions?.find(item => item.id === peerId);
  if (!indicator || !focus || !peer || focusId === peerId) return { status: 'REFUSED', reason: 'UNKNOWN_COMPARISON' };
  const evidence = {
    datasetId: dataset.datasetId,
    dataClass: dataset.dataClass,
    sourceId: dataset.source.id,
    sourceTitle: dataset.source.title,
    sourceLicense: dataset.source.license,
    retrievedAt: dataset.source.retrievedAt,
    goal3: dataset.strategy?.goalReference || 'GOAL_3_UNVERIFIED',
    goal3Verified: dataset.strategy?.clauseVerified === true,
    period: dataset.period,
    stage: indicator.stage,
    standardization: indicator.standardization,
    indicator: { id: indicator.id, label: indicator.label, unit: indicator.unit },
    sourceDigest: await digest(dataset),
    comparison: { focus: focus.name, peer: peer.name, focusId, peerId },
  };
  const withEvidence = (status, reason, details = {}) => ({ status, reason, evidence, ...details });
  if (focus.period !== peer.period || focus.period !== dataset.period) {
    return withEvidence('NOT_COMPARABLE', 'MISMATCHED_PERIOD');
  }
  const f = focus.measures?.[indicator.id];
  const p = peer.measures?.[indicator.id];
  const fv = validateRow(f, indicator, dataset.source.id);
  const pv = validateRow(p, indicator, dataset.source.id);
  if (fv || pv) return withEvidence('NOT_COMPARABLE', fv || pv);
  if (f.n < MIN_COHORT_N || p.n < MIN_COHORT_N) {
    return withEvidence('SUPPRESSED', 'SMALL_COHORT', { minimumCohort: MIN_COHORT_N });
  }
  const observations = [{ region: focus.name, ...f }, { region: peer.name, ...p }];
  if (f.low <= p.high && p.low <= f.high) {
    return withEvidence('INSUFFICIENT_EVIDENCE', 'UNCERTAINTY_INTERVALS_OVERLAP', { observations });
  }
  const gap = pct(f.value - p.value);
  const focusIsWorse = indicator.better === 'higher' ? f.value < p.value : f.value > p.value;
  if (!focusIsWorse) {
    return withEvidence('NO_ACTION_GAP', 'FOCUS_NOT_WORSE_THAN_PEER', { observations, gap });
  }
  return withEvidence('ACTION_REVIEW', 'NONOVERLAPPING_SYNTHETIC_INTERVALS', {
    observations,
    gap,
    proposedAction: {
      ...indicator.action,
      decision: 'HUMAN_REVIEW_REQUIRED',
      gapLabel: `Example difference: ${Math.abs(gap)} ${indicator.unit}`,
      caveats: [
        'Observational association is not a causal effect.',
        'Never infer individual patient characteristics from regional aggregates.',
        'Check age adjustment, small areas, time period and source license independently.',
        dataset.strategy?.clauseVerified ? 'Goal 3 clause matched to provided primary source.' : 'Goal 3 exact clause needs a primary-source verification before sponsor submission.',
      ],
    },
  });
}

export function exportProposal(result) {
  if (result?.status !== 'ACTION_REVIEW') return { ok: false, reason: 'NO_DEFENSIBLE_ACTION_TO_EXPORT' };
  return {
    ok: true,
    schemaVersion: 'equity-action-review-v1',
    effect: 'DRAFT_ONLY',
    verifiedLiveData: false,
    sourceKind: result.evidence.dataClass,
    action: result.proposedAction,
    evidence: result.evidence,
    observations: result.observations,
    humanApproval: 'REQUIRED_NOT_GRANTED',
  };
}
