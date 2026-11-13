// Synthetic snapshot review only. There is no device interface or actuation path.
const ROOT_FIELDS = ['schemaVersion','fictional','requestedAction','referenceTimeMs','maxAgeMs','requiredSensors','observations','fallbacks'];
const REASON_ORDER = ['observation-missing','time-unknown','future-observation','stale-observation','status-unknown','fault-reported','conflicting-fresh-status','fallback-missing','owner-unknown','stop-condition-unknown','fallback-unknown'];
const fail = message => { throw new TypeError(`Fictional sensor log: ${message}`); };

function exact(value, fields, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== fields.length
      || !Object.keys(value).every(key=>fields.includes(key))) fail(`${label} fields must match the contract`);
}
function token(value) {
  if (typeof value !== 'string' || value.length > 64 || value.trim() !== value
      || !/^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) fail('expected a bounded fictional token');
}
function time(value) {
  if (!Number.isInteger(value) || value < 0 || value > 86400000) fail('time must be an integer from 0 to 86400000');
}
function array(value,min,max,label) {
  if (!Array.isArray(value) || value.length < min || value.length > max) fail(`${label} must contain ${min} to ${max} entries`);
}

/** Bounded primitive JSON text, with ordinary JSON.parse last-key-wins semantics. */
export function triageFictionalSensorLog(jsonText) {
  if (typeof jsonText !== 'string' || jsonText.length > 32768
      || new TextEncoder().encode(jsonText).length > 32768) fail('input must be JSON text of at most 32768 UTF-8 bytes');
  let input;
  try { input=JSON.parse(jsonText); } catch { fail('malformed JSON text'); }
  exact(input,ROOT_FIELDS,'snapshot');
  if (input.schemaVersion !== 1) fail('unsupported schemaVersion');
  if (input.fictional !== true) fail('fictional must be true');
  if (input.requestedAction !== 'review-only') fail('only review-only is supported; no live actuation or connection');
  time(input.referenceTimeMs);
  if (!Number.isInteger(input.maxAgeMs) || input.maxAgeMs < 1 || input.maxAgeMs > 60000) fail('maxAgeMs must be an integer from 1 to 60000');
  array(input.requiredSensors,1,16,'requiredSensors');
  input.requiredSensors.forEach(token);
  const required=new Set(input.requiredSensors);
  if (required.size !== input.requiredSensors.length) fail('requiredSensors must be unique');
  array(input.observations,0,64,'observations');
  for (const row of input.observations) {
    exact(row,['sensorId','atMs','status'],'observation');
    token(row.sensorId);
    if (!required.has(row.sensorId)) fail('observation must name a required sensor');
    if (row.atMs !== null) time(row.atMs);
    if (!['nominal','fault','unknown'].includes(row.status)) fail('unsupported observation status');
  }
  array(input.fallbacks,0,16,'fallbacks');
  const fallbacks=new Map();
  for (const row of input.fallbacks) {
    exact(row,['sensorId','owner','stopCondition','fallback'],'fallback');
    token(row.sensorId);
    if (!required.has(row.sensorId)) fail('fallback must name a required sensor');
    if (fallbacks.has(row.sensorId)) fail('fallback sensor IDs must be unique');
    if (row.owner !== null) token(row.owner);
    if (row.stopCondition !== null && row.stopCondition !== 'on-unresolved-or-fault') fail('unsupported stopCondition');
    if (row.fallback !== null && row.fallback !== 'hold-simulation-for-review') fail('unsupported fallback');
    fallbacks.set(row.sensorId,row);
  }
  const sensors=input.requiredSensors.map(sensorId=>{
    const rows=input.observations.filter(row=>row.sensorId===sensorId);
    const reasons=new Set();
    const freshStatuses=new Set();
    let nominalFreshCount=0;
    if (!rows.length) reasons.add('observation-missing');
    for (const row of rows) {
      let fresh=false;
      if (row.atMs === null) reasons.add('time-unknown');
      else if (row.atMs > input.referenceTimeMs) reasons.add('future-observation');
      else if (input.referenceTimeMs-row.atMs > input.maxAgeMs) reasons.add('stale-observation');
      else fresh=true;
      if (row.status === 'unknown') reasons.add('status-unknown');
      if (row.status === 'fault') reasons.add('fault-reported');
      if (fresh) {
        freshStatuses.add(row.status);
        if (row.status === 'nominal') nominalFreshCount++;
      }
    }
    if (freshStatuses.has('nominal') && freshStatuses.has('fault')) reasons.add('conflicting-fresh-status');
    const declared=fallbacks.get(sensorId);
    if (!declared) reasons.add('fallback-missing');
    else {
      if (declared.owner === null) reasons.add('owner-unknown');
      if (declared.stopCondition === null) reasons.add('stop-condition-unknown');
      if (declared.fallback === null) reasons.add('fallback-unknown');
    }
    return {
      sensorId,
      evidenceCount:rows.length,
      nominalFreshCount,
      reasons:REASON_ORDER.filter(reason=>reasons.has(reason)),
      reviewState:reasons.size ? 'needs-review' : 'consistent-fixture',
      declaredFallback:declared ? {owner:declared.owner,stopCondition:declared.stopCondition,fallback:declared.fallback} : null,
    };
  });
  return {
    schemaVersion:1,
    kind:'fictional-sensor-review',
    snapshotState:sensors.some(row=>row.reviewState==='needs-review') ? 'needs-review' : 'consistent-fixture',
    sensors,
    boundary:{observationsAuthenticated:false,deviceConnected:false,actuationAuthorized:false,actuationExecuted:false,safetyCertified:false},
  };
}
