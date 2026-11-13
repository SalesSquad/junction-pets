import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {triageFictionalSensorLog} from '../pets/wendy/sensor-triage.mjs';

const run = x => triageFictionalSensorLog(JSON.stringify(x));
const observation = patch => ({sensorId:'fictional-sensor-a', atMs:1000, status:'nominal', ...patch});
const mapping = patch => ({sensorId:'fictional-sensor-a', owner:'fictional-operator-a', stopCondition:'on-unresolved-or-fault', fallback:'hold-simulation-for-review', ...patch});
const input = () => ({schemaVersion:1, fictional:true, requestedAction:'review-only', referenceTimeMs:1000, maxAgeMs:100, requiredSensors:['fictional-sensor-a'], observations:[observation()], fallbacks:[mapping()]});
const codes = x => run(x).sensors[0].reasons;

test('invented snapshot keeps stale and missing evidence visible without granting device authority', () => {
  const result = run(JSON.parse(readFileSync(new URL('../pets/wendy/examples/fictional-sensor-log.json',import.meta.url),'utf8')));
  assert.equal(result.snapshotState,'needs-review');
  assert.equal(result.sensors[0].reviewState,'consistent-fixture');
  assert.ok(result.sensors[1].reasons.includes('stale-observation'));
  assert.ok(result.sensors[2].reasons.includes('observation-missing'));
  assert.ok(result.sensors[2].reasons.includes('owner-unknown'));
  assert.deepEqual(result.boundary,{observationsAuthenticated:false,deviceConnected:false,actuationAuthorized:false,actuationExecuted:false,safetyCertified:false});
});

test('fully declared current fictional evidence is only internally consistent', () => {
  const result=run(input());
  assert.equal(result.kind,'fictional-sensor-review');
  assert.equal(result.snapshotState,'consistent-fixture');
  assert.deepEqual(result.sensors[0].reasons,[]);
  assert.equal(result.sensors[0].nominalFreshCount,1);
  assert.equal(result.sensors[0].declaredFallback.owner,'fictional-operator-a');
  assert.equal(result.boundary.actuationAuthorized,false);
});

test('known timestamp zero is not an unknown timestamp and no wall clock is consulted', () => {
  const a=input();a.referenceTimeMs=0;a.observations=[observation({atMs:0})];
  assert.deepEqual(codes(a),[]);
  a.observations=[observation({atMs:null})];
  assert.deepEqual(codes(a),['time-unknown']);
  assert.equal(run(a).sensors[0].nominalFreshCount,0);
});

test('missing required sensor observations cannot borrow another sensor evidence', () => {
  const a=input();a.requiredSensors.push('fictional-sensor-b');a.fallbacks.push(mapping({sensorId:'fictional-sensor-b'}));
  const result=run(a);
  assert.deepEqual(result.sensors[1].reasons,['observation-missing']);
  assert.equal(result.sensors[1].evidenceCount,0);
});

test('freshness cutoff is inclusive and stale rows are not erased by a nominal fresh row', () => {
  const a=input();a.observations=[observation({atMs:900})];
  assert.deepEqual(codes(a),[]);
  a.observations.push(observation({atMs:899}));
  assert.deepEqual(codes(a),['stale-observation']);
  assert.equal(run(a).sensors[0].nominalFreshCount,1);
});

test('future timestamps and unknown statuses remain unresolved, not treated as freshness', () => {
  const a=input();a.observations=[observation({atMs:1001}),observation({status:'unknown'})];
  assert.deepEqual(codes(a),['future-observation','status-unknown']);
  assert.equal(run(a).sensors[0].nominalFreshCount,0);
});

test('fresh nominal and fault evidence conflict, and stale faults are still reported', () => {
  const a=input();a.observations.push(observation({status:'fault'}));
  assert.deepEqual(codes(a),['fault-reported','conflicting-fresh-status']);
  a.observations=[observation(),observation({atMs:0,status:'fault'})];
  assert.deepEqual(codes(a),['stale-observation','fault-reported']);
});

test('fallback mapping needs an explicit declared owner and stop condition', () => {
  const a=input();a.fallbacks=[];
  assert.deepEqual(codes(a),['fallback-missing']);
  a.fallbacks=[mapping({owner:null,stopCondition:null,fallback:null})];
  assert.deepEqual(codes(a),['owner-unknown','stop-condition-unknown','fallback-unknown']);
  a.fallbacks=[mapping({stopCondition:'never-stop'})];
  assert.throws(()=>run(a),/stopCondition/);
  a.fallbacks=[mapping({fallback:'restart-device'})];
  assert.throws(()=>run(a),/fallback/);
});

test('live actuation and command fields are refused rather than converted to authority', () => {
  for(const requestedAction of ['actuate','connect','deploy',null]) assert.throws(()=>run({...input(),requestedAction}),/review-only/);
  assert.throws(()=>run({...input(),command:'restart'}),/fields/);
  const a=input();a.fallbacks=[mapping({execute:true})];
  assert.throws(()=>run(a),/fields/);
});

test('closed records, unique mappings and explicit fictional sensor scope are enforced', () => {
  const a=input();a.observations=[observation({sensorId:'fictional-other'})];
  assert.throws(()=>run(a),/required sensor/);
  a.observations=[observation()];a.fallbacks=[mapping({sensorId:'fictional-other'})];
  assert.throws(()=>run(a),/required sensor/);
  assert.throws(()=>run({...input(),requiredSensors:['fictional-sensor-a','fictional-sensor-a']}),/unique/);
  assert.throws(()=>run({...input(),fallbacks:[mapping(),mapping()]}),/unique/);
  assert.throws(()=>run({...input(),requiredSensors:['live-device']}),/fictional token/);
  assert.throws(()=>run({...input(),fallbacks:[mapping({owner:'fictional-operator\n'})]}),/fictional token/);
  const missing=observation();delete missing.atMs;
  assert.throws(()=>run({...input(),observations:[missing]}),/fields/);
});

test('JSON bytes, arrays, time ranges and status vocabulary are bounded', () => {
  for(const raw of [null,{},0,'','{','null','[]']) assert.throws(()=>triageFictionalSensorLog(raw));
  assert.throws(()=>triageFictionalSensorLog(' '.repeat(32769)),/32768/);
  assert.throws(()=>triageFictionalSensorLog('é'.repeat(16385)),/32768/);
  assert.throws(()=>run({...input(),observations:Array.from({length:65},()=>observation())}),/observations/);
  assert.throws(()=>run({...input(),requiredSensors:[]}),/requiredSensors/);
  assert.throws(()=>run({...input(),requiredSensors:Array.from({length:17},(_,i)=>`fictional-${i}`)}),/requiredSensors/);
  for(const t of [-1,0.5,86400001,'1000',null]) assert.throws(()=>run({...input(),referenceTimeMs:t}),/time/);
  for(const t of [-1,0,0.5,60001,null]) assert.throws(()=>run({...input(),maxAgeMs:t}),/maxAgeMs/);
  assert.throws(()=>run({...input(),observations:[observation({status:'safe'})]}),/status/);
  assert.throws(()=>run({...input(),fictional:false}),/fictional/);
});

test('ordinary JSON duplicate semantics and deterministic independent outputs are explicit', () => {
  const raw=JSON.stringify(input()).replace('"referenceTimeMs":1000','"referenceTimeMs":0,"referenceTimeMs":1000');
  const first=triageFictionalSensorLog(raw),snapshot=structuredClone(first);
  first.sensors[0].declaredFallback.owner='fictional-changed';
  first.boundary.actuationExecuted=true;
  assert.deepEqual(triageFictionalSensorLog(raw),snapshot);
  assert.equal(snapshot.snapshotState,'consistent-fixture');
});
