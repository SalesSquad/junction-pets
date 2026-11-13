/** Invented experiment-plan consistency only; never executes or validates a market. */
const shape = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const id = value => typeof value === 'string' && value === value.trim() && /^[a-z][a-z0-9-]{0,47}$/.test(value);
const text = value => typeof value === 'string' && value.length > 0 && value.length <= 240
  && value === value.trim() && !/[\x00-\x1f\x7f]/.test(value);
const bounded = (value, max) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= max;
const metricValue = (value, unit) => bounded(value, unit === 'ratio' ? 1 : unit === 'count' ? 1000000 : 1000000000)
  && (unit !== 'count' || Number.isSafeInteger(value));
const rule = (value, unit) => value === null || (shape(value, ['operator', 'value'])
  && ['at-least', 'at-most'].includes(value.operator) && metricValue(value.value, unit));

function valid(plan) {
  if (!shape(plan, ['schemaVersion', 'kind', 'assumption', 'metric', 'budget', 'customerEvidence'])
    || plan.schemaVersion !== 1 || plan.kind !== 'invented-experiment-plan'
    || !shape(plan.assumption, ['id', 'category', 'statement', 'customerEvidenceIds'])
    || !id(plan.assumption.id) || !['technical', 'customer', 'delivery'].includes(plan.assumption.category)
    || !text(plan.assumption.statement)
    || !shape(plan.metric, ['id', 'unit', 'baseline', 'success', 'stop', 'sampleSize'])
    || !id(plan.metric.id) || !['count', 'ratio', 'ms'].includes(plan.metric.unit)
    || !(plan.metric.baseline === null || metricValue(plan.metric.baseline, plan.metric.unit))
    || !rule(plan.metric.success, plan.metric.unit) || !rule(plan.metric.stop, plan.metric.unit)
    || !(plan.metric.sampleSize === null || (Number.isSafeInteger(plan.metric.sampleSize)
      && plan.metric.sampleSize >= 0 && plan.metric.sampleSize <= 10000))
    || !shape(plan.budget, ['maxHours', 'maxCredits'])
    || !(plan.budget.maxHours === null || bounded(plan.budget.maxHours, 168))
    || !(plan.budget.maxCredits === null || bounded(plan.budget.maxCredits, 10000))
    || !Array.isArray(plan.customerEvidence) || plan.customerEvidence.length > 16) return false;
  const evidenceIds = new Set();
  for (const evidence of plan.customerEvidence) {
    if (!shape(evidence, ['id', 'kind', 'statement']) || !id(evidence.id) || evidenceIds.has(evidence.id)
      || !['invented-interview', 'invented-observation', 'invented-commitment'].includes(evidence.kind)
      || !text(evidence.statement)) return false;
    evidenceIds.add(evidence.id);
  }
  const links = plan.assumption.customerEvidenceIds;
  return Array.isArray(links) && links.length <= 16 && new Set(links).size === links.length
    && links.every(link => evidenceIds.has(link));
}

export function reviewExperimentPlan(jsonText) {
  const boundary = {schemaVersion: 1, basis: 'invented-declarations', experimentPerformed: false,
    marketValidationEstablished: false, hypothesisProven: false, authorization: false};
  const invalid = () => ({...boundary, status: 'invalid', issues: ['malformed-or-unsupported-plan'], card: null});
  if (typeof jsonText !== 'string' || Buffer.byteLength(jsonText, 'utf8') > 32768) return invalid();
  let plan;
  try { plan = JSON.parse(jsonText); } catch { return invalid(); }
  if (!valid(plan)) return invalid();

  const issues = [];
  for (const field of ['baseline', 'success', 'stop']) if (plan.metric[field] === null) issues.push('unknown-' + field);
  if (plan.metric.sampleSize === null) issues.push('unknown-sample-size');
  else if (plan.metric.sampleSize === 0) issues.push('no-planned-observations');
  for (const field of ['maxHours', 'maxCredits']) if (plan.budget[field] === null) issues.push('unknown-' + field);
  if (plan.budget.maxHours === 0) issues.push('no-effort-budget');
  if (!plan.assumption.customerEvidenceIds.length) issues.push('no-linked-customer-evidence');
  const {success, stop} = plan.metric;
  if (success !== null && stop !== null) {
    const separate = success.operator !== stop.operator && (success.operator === 'at-least'
      ? success.value > stop.value : success.value < stop.value);
    if (!separate) issues.push('overlapping-or-unseparated-rules');
  }
  const linked = new Set(plan.assumption.customerEvidenceIds);
  return {
    ...boundary, status: issues.length ? 'needs-review' : 'ready-for-review', issues: issues.sort(),
    card: {
      assumptionId: plan.assumption.id, category: plan.assumption.category, statement: plan.assumption.statement,
      metric: plan.metric, budget: plan.budget,
      customerEvidence: plan.customerEvidence.filter(row => linked.has(row.id)).sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
      evidenceAuthenticity: 'not-verified',
      nextAction: 'Review the proposed metric, contradictory outcomes, customer evidence and ceilings before separately authorizing any experiment.',
    },
  };
}
