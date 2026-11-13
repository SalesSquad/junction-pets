/** Invented multimodal plan declarations only: no training, model or provider calls. */
const modalities = new Set(['text', 'image', 'audio', 'video']);
const id = value => typeof value === 'string' && value !== 'unknown' && value === value.trim()
  && /^[a-z][a-z0-9-]{0,47}$/.test(value);
const shape = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const list = (value, predicate, max, min = 1) => Array.isArray(value)
  && value.length >= min && value.length <= max && value.every(predicate)
  && new Set(value).size === value.length;
const byId = (a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0;

function valid(plan) {
  if (!shape(plan, ['schemaVersion', 'kind', 'capabilities', 'records'])
    || plan.schemaVersion !== 1 || plan.kind !== 'invented-evaluation-plan'
    || !Array.isArray(plan.capabilities) || plan.capabilities.length < 1 || plan.capabilities.length > 32
    || !Array.isArray(plan.records) || plan.records.length > 200) return false;
  const capabilities = new Set(), records = new Set();
  for (const capability of plan.capabilities) {
    if (!shape(capability, ['id', 'requiredModalities', 'minHeldOutGroups']) || !id(capability.id)
      || capabilities.has(capability.id) || !list(capability.requiredModalities, value => modalities.has(value), 4)
      || !(capability.minHeldOutGroups === null || (Number.isSafeInteger(capability.minHeldOutGroups)
        && capability.minHeldOutGroups >= 0 && capability.minHeldOutGroups <= 200))) return false;
    capabilities.add(capability.id);
  }
  for (const record of plan.records) {
    if (!shape(record, ['id', 'sourceId', 'sceneId', 'split', 'modalities', 'capabilityIds'])
      || !id(record.id) || records.has(record.id)
      || !(record.sourceId === null || id(record.sourceId)) || !(record.sceneId === null || id(record.sceneId))
      || !['training', 'held-out', 'unknown'].includes(record.split)
      || !(record.modalities === null || list(record.modalities, value => modalities.has(value), 4, 0))
      || !list(record.capabilityIds, value => capabilities.has(value), 32)) return false;
    records.add(record.id);
  }
  return true;
}

// Source and scene labels are separate namespaces. Their transitive closure is
// one conservative grouping unit; a changed record ID cannot separate copies.
function groupRecords(records) {
  const parents = records.map((_, i) => i);
  const root = i => { while (parents[i] !== i) i = parents[i]; return i; };
  for (const key of ['sourceId', 'sceneId']) {
    const first = new Map();
    records.forEach((record, i) => {
      if (record[key] === null) return;
      if (first.has(record[key])) parents[root(i)] = root(first.get(record[key]));
      else first.set(record[key], i);
    });
  }
  const groups = new Map();
  records.forEach((record, i) => {
    const key = root(i);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  });
  return [...groups.values()].map(group => group.sort(byId)).sort((a, b) => byId(a[0], b[0]));
}

export function checkEvaluationPlan(jsonText) {
  const boundary = {basis: 'invented-declarations', grouping: 'transitive-source-or-scene',
    trainingPerformed: false, actualEvaluationPerformed: false,
    modelPerformanceVerified: false, authorization: false};
  const invalid = () => ({...boundary, status: 'invalid', issues: ['malformed-or-unsupported-plan'],
    declaredSplits: null, leakageGroups: [], coverage: [], untestedCapabilities: []});
  if (typeof jsonText !== 'string' || jsonText.length === 0 || jsonText.length > 65536) return invalid();
  let plan;
  try { plan = JSON.parse(jsonText); } catch { return invalid(); }
  if (!valid(plan)) return invalid();

  const issues = new Set(), capabilities = new Map(plan.capabilities.map(capability => [capability.id, capability]));
  const declaredSplits = {training: 0, heldOut: 0, unknown: 0};
  for (const record of plan.records) {
    declaredSplits[record.split === 'held-out' ? 'heldOut' : record.split]++;
    if (record.split === 'unknown') issues.add(`unknown-split:${record.id}`);
    if (record.sourceId === null || record.sceneId === null) issues.add(`unknown-provenance:${record.id}`);
    if (record.modalities === null) issues.add(`unknown-modalities:${record.id}`);
    else for (const capabilityId of record.capabilityIds) {
      if (!capabilities.get(capabilityId).requiredModalities.every(value => record.modalities.includes(value))) {
        issues.add(`missing-modalities:${record.id}:${capabilityId}`);
      }
    }
  }

  const groups = groupRecords(plan.records);
  const leakageGroups = [];
  const eligibleGroups = [];
  for (const group of groups) {
    const training = group.filter(record => record.split === 'training');
    const heldOut = group.filter(record => record.split === 'held-out');
    if (training.length && heldOut.length) {
      const groupId = group[0].id;
      issues.add(`leakage:${groupId}`);
      leakageGroups.push({groupId, recordIds: group.map(record => record.id),
        trainingRecordIds: training.map(record => record.id), heldOutRecordIds: heldOut.map(record => record.id)});
    }
    if (group.every(record => record.split === 'held-out' && record.sourceId !== null && record.sceneId !== null)) {
      eligibleGroups.push(group);
    }
  }

  const coverage = [...plan.capabilities].sort(byId).map(capability => {
    const tagged = plan.records.filter(record => record.capabilityIds.includes(capability.id));
    const eligibleHeldOutGroups = eligibleGroups.filter(group => group.some(record =>
      record.capabilityIds.includes(capability.id) && record.modalities !== null
      && capability.requiredModalities.every(value => record.modalities.includes(value)))).length;
    const target = capability.minHeldOutGroups;
    const planCoverage = target === null ? 'unknown-target' : target === 0 ? 'not-requested'
      : eligibleHeldOutGroups === 0 ? 'uncovered' : eligibleHeldOutGroups < target ? 'insufficient' : 'covered';
    if (planCoverage !== 'covered') issues.add(`coverage:${capability.id}:${planCoverage}`);
    return {capabilityId: capability.id, targetHeldOutGroups: target,
      declaredTrainingRecords: tagged.filter(record => record.split === 'training').length,
      declaredHeldOutRecords: tagged.filter(record => record.split === 'held-out').length,
      declaredUnknownSplitRecords: tagged.filter(record => record.split === 'unknown').length,
      eligibleHeldOutGroups, planCoverage, evaluationStatus: 'not-run'};
  });
  return {...boundary, status: issues.size ? 'needs-review' : 'consistent-plan', issues: [...issues].sort(),
    declaredSplits, leakageGroups, coverage, untestedCapabilities: coverage.map(row => row.capabilityId)};
}
