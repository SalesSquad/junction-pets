import test from 'node:test';
import assert from 'node:assert/strict';
import { METER_SCHEMA, parseMeterDocument, reviewMeterDocument, syntheticMeterDocument } from '../measurement.mjs';
const doc = () => syntheticMeterDocument('positive');
const reject = (d, match) => assert.throws(() => reviewMeterDocument(d), match || /refused/i);
test('positive aligned energy is exact and explicitly noncausal', () => {
  const r = reviewMeterDocument(doc());
  assert.deepEqual(r.totalsMWh, {baseline:510, scenario:270, device:30});
  assert.equal(r.netDifferenceMWh,210);
  assert.equal(r.netDifferenceKWh,.00021);
  assert.equal(r.measuredEnvironmentalBenefit, false);
  assert.equal(r.actuationAuthorized, false);
  assert.equal(r.intervalCount,3);
});
test('negative net remains signed, never clipped', () => {
  const r = reviewMeterDocument(syntheticMeterDocument('negative'));
  assert.equal(r.netDifferenceMWh, -135);
  assert.equal(r.netDifferenceKWh, -.000135);
});
test('explicit user-supplied evidence remains unverified', () => {
  const d = doc();d.evidence='USER_SUPPLIED_UNVERIFIED';
  const r=reviewMeterDocument(d);
  assert.equal(r.status,'UNVERIFIED_COMPARISON');
  assert.match(r.caveat,/unverified/);
});
test('JSON parser rejects untrusted personally identifying fields',()=>{const d=doc();d.name='private occupant';reject(d,/invalid document fields/);});
test('parsing accepts bounded serialised synthetic document',()=>assert.equal(parseMeterDocument(JSON.stringify(doc())).netDifferenceMWh,210));
test('oversized input and unknown schema fail',()=>{assert.throws(()=>parseMeterDocument(' '.repeat(131073)),/128 KiB/);const d=doc();d.schema=METER_SCHEMA+'2';reject(d,/unsupported schema/);});
test('missing channel, unknown units or bogus evidence fail',()=>{const d=doc();delete d.channels.device;reject(d,/invalid channels/);const u=doc();u.unit='Wh';reject(u,/unit must/);const e=doc();e.evidence='MEASURED_PROVEN';reject(e,/evidence type/);});
test('non-integer, negative and overflow energies fail',()=>{for(const x of [-1,.1,Number.MAX_SAFE_INTEGER,NaN,Infinity]){const d=doc();d.channels.device[0].mWh=x;reject(d,/energy/);}});
test('gap, overlap, out-of-order and duplicate fail closed',()=>{for(const start of [8000,11000,0,-10]){const d=doc();d.channels.baseline[1].startMs=start;reject(d,/gap|start/);}});
test('mismatched timestamps, missing intervals and duplicated coverage fail',()=>{const d=doc();d.channels.device[1].endMs=20001;reject(d,/match/);const d2=doc();d2.channels.scenario.pop();reject(d2,/match|coverage/);});
test('empty and one-interval records fail',()=>{const d=doc();d.channels.baseline=[];reject(d,/2–96/);const d2=doc();for (const k of ['baseline','scenario','device'])d2.channels[k].pop();d2.channels.baseline.pop();d2.channels.scenario.pop();d2.channels.device.pop();reject(d2,/2–96/);});
test('expired, missing and invalid self-reported calibration fail',()=>{const d=doc();d.calibration.device.validUntilMs=19999;reject(d,/calibration window/);const d2=doc();delete d2.calibration.device.meterId;reject(d2,/calibration fields/);const d3=doc();d3.calibration.device.checkedAtMs=40000;reject(d3,/expired/);});
test('invalid meter ids and extraneous personal metadata fail',()=>{const d=doc();d.calibration.baseline.meterId='A person email@example.com';reject(d,/meter id/);const e=doc();e.channels.device[0].personName='X';reject(e,/interval/);});
test('noncontiguous comparison and invalid duration fail',()=>{const d=doc();d.channels.baseline[0].endMs=1;reject(d,/gap/);const e=doc();e.channels.baseline[0].endMs=3600001;reject(e,/duration/);});
test('input is not allowed to infer benefit by removing device power',()=>{const d=doc();delete d.channels.device;reject(d,/invalid channels/);});

test('one meter cannot silently masquerade as three independent channels',()=>{const d=doc();d.calibration.device.meterId=d.calibration.scenario.meterId;reject(d,/duplicate meter id/);});
