import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { initialState, transition, ASSUMPTIONS, UPPER_PROXY_WATTS } from '../core.mjs';
import { runDemo } from '../demo.mjs';

const thermo = (at, temperature = 22, humidity = 45) => ({
  type: 'thermo', sample: { at, temperature, humidity },
});
const fixture = (at, overrides = {}) => ({ type: 'camera', fixture: {
  state: 'open', at, quality: 0.95, regionOfInterestOnly: true,
  storedFrames: false, frameFingerprint: '0123456789abcdef', queryId: 1, ...overrides,
} });
function anomaly() {
  const first = transition(initialState(), thermo(0), 0);
  return transition(first.state, thermo(10_000, 21), 10_000);
}
const tick = (state, now) => transition(state, { type: 'tick' }, now);
const intent = (at, durationMs = 300_000, confirmed = true) => ({ type: 'intent', at, confirmed, durationMs });

test('rollback, duplicate clock and duplicate/out-of-order Thermo fail closed', () => {
  const { state } = anomaly();
  for (const now of [9_999, 10_000, NaN, Infinity, -1]) {
    const r = tick(state, now);
    assert.equal(r.receipt.accepted, false);
    assert.equal(r.receipt.windowEvidence, 'UNKNOWN');
    assert.equal(r.state.now, 10_000);
    assert.deepEqual(r.receipt.proposals, []);
  }
  for (const at of [9_000, 10_000]) {
    const r = transition(state, thermo(at, 20), 11_000);
    assert.equal(r.receipt.reason, 'DUPLICATE_OR_OUT_OF_ORDER_THERMO');
    assert.equal(r.state.samples.length, 0);
  }
});

test('requires two fresh finite in-range T/RH samples; stale recovery starts over', () => {
  const first = transition(initialState(), thermo(0), 0);
  assert.equal(first.receipt.thermal.status, 'UNKNOWN');
  assert.equal(first.receipt.proposals.length, 0);
  for (const event of [thermo(1, NaN), thermo(1, -41), thermo(1, 86),
    thermo(1, 22, Infinity), thermo(1, 22, -1), thermo(1, 22, 101), thermo(40_000)]) {
    assert.equal(transition(first.state, event, 30_000).receipt.accepted, false);
  }
  assert.equal(transition(first.state, thermo(1), 30_000).receipt.reason, 'STALE_OR_FUTURE_THERMO');
  const stale = tick(anomaly().state, 30_001);
  assert.equal(stale.receipt.thermal.status, 'UNKNOWN');
  assert.equal(transition(stale.state, thermo(31_000, 20), 31_000).receipt.thermal.status, 'UNKNOWN');
});

test('ROI-only schema and single-use query IDs refuse unmatched answers', () => {
  const { state } = anomaly();
  for (const overrides of [{ regionOfInterestOnly: false }, { storedFrames: true },
    { frameFingerprint: 'identity@example.com' }]) {
    const r = transition(state, fixture(11_000, overrides), 11_000);
    assert.equal(r.receipt.accepted, false);
    assert.equal(r.receipt.windowEvidence, 'UNKNOWN');
  }
  const open = transition(state, fixture(11_000), 11_000);
  assert.equal(open.receipt.windowEvidence, 'SYNTHETIC_OPEN_ROI');
  const replay = transition(open.state, fixture(12_000), 12_000);
  assert.equal(replay.receipt.reason, 'UNISSUED_QUERY_ID');
  assert.equal(replay.receipt.windowEvidence, 'UNKNOWN');
});

test('full occlusion, error, low quality and stale CLOSED fixtures remain UNKNOWN', () => {
  for (const overrides of [{ state: 'occluded' }, { state: 'error' },
    { state: 'closed', quality: 0.79 }, { state: 'closed', at: 0 }, { at: 50_000 }]) {
    const r = transition(anomaly().state, fixture(21_000, overrides), 21_000);
    assert.equal(r.receipt.accepted, false);
    assert.equal(r.receipt.windowEvidence, 'UNKNOWN');
    assert.equal(r.receipt.proposals.length, 0);
  }
  const open = transition(anomaly().state, fixture(11_000), 11_000);
  const occluded = transition(open.state, fixture(12_000, { state: 'occluded', frameFingerprint: '0000000000000002' }), 12_000);
  assert.equal(occluded.receipt.windowEvidence, 'UNKNOWN');
  assert.equal(tick(open.state, 21_001).receipt.windowEvidence, 'UNKNOWN');
});

test('4W board and reserved camera Wh accounted separately, including invalid packets', () => {
  const start = tick(initialState(), 0);
  const hour = tick(start.state, 3_600_000);
  assert.equal(hour.receipt.energy.boardAssumedWh, 4);
  assert.equal(hour.receipt.energy.cameraAssumedWh, 0);
  const a = anomaly();
  assert.equal(a.receipt.energy.cameraAssumedWh, ASSUMPTIONS.cameraWhPerProposal);
  const bad = transition(a.state, { type: 'bad' }, 3_600_000);
  assert.equal(bad.receipt.energy.boardAssumedWh, 4);
  assert.equal(bad.receipt.energy.cameraAssumedWh, 0.01);
  assert.equal(bad.receipt.energy.totalAssumedWh, 4.01);
});

test('confirmed Knob intent debounces without extending and expires monotonically', () => {
  const a = anomaly();
  const accepted = transition(a.state, intent(11_000), 11_000);
  assert.equal(accepted.state.intent.expiresAt, 311_000);
  const bounce = transition(accepted.state, intent(12_000), 12_000);
  assert.equal(bounce.receipt.reason, 'INTENT_DEBOUNCED');
  assert.equal(bounce.state.intent.expiresAt, 311_000);
  assert.equal(tick(bounce.state, 310_999).receipt.intent.expiresAt, 311_000);
  const expired = tick(bounce.state, 311_000);
  assert.equal(expired.receipt.intent, null);
  assert.equal(tick(expired.state, 312_000).receipt.intent, null);
  for (const event of [intent(11_000, 900_001), intent(11_000, Infinity),
    intent(11_000, 0), intent(11_000, 100, false), intent(0)]) {
    assert.equal(transition(a.state, event, 11_000).receipt.accepted, false);
  }
  assert.equal(transition(a.state, intent(11_000, 900_000), 11_000).state.intent.expiresAt, 911_000);
  const delayed = transition(a.state, intent(11_000, 100), 12_000);
  assert.equal(delayed.receipt.intent, null);
});

test('thermal cause remains hypothetical even with OPEN; steam confound suppresses query', () => {
  const a = anomaly(); // Could equally be radiator shutdown or weather; no cause feature.
  assert.equal(a.receipt.thermal.status, 'COOLING_ANOMALY_HYPOTHESIS');
  const open = transition(a.state, fixture(11_000), 11_000);
  assert.equal(open.receipt.causalHeatLossCertified, false);
  assert.equal(open.receipt.thermal.causeCertified, false);
  assert.equal(open.receipt.proposals[0].type, 'HUMAN_ADVISORY_BUZZER_LED_PROPOSAL');
  const first = transition(initialState(), thermo(0, 24, 85), 0);
  const steam = transition(first.state, thermo(10_000, 23, 65), 10_000);
  assert.equal(steam.receipt.thermal.status, 'HUMIDITY_CONFOUND');
  assert.equal(steam.receipt.proposals.length, 0);
});

test('privacy: reject extra personal/frame fields, never persist or echo them', () => {
  const marker = 'PRIVATE_PERSON_FULL_FRAME_MARKER';
  for (const event of [
    { ...thermo(11_000), person: marker },
    { type: 'thermo', sample: { at: 11_000, temperature: 20, humidity: 45, identity: marker } },
    fixture(11_000, { fullFrame: marker }),
    { ...intent(11_000), userId: marker },
  ]) {
    const result = transition(anomaly().state, event, 11_000);
    assert.equal(result.receipt.accepted, false);
    assert.equal(JSON.stringify(result).includes(marker), false);
  }
});

test('no mains/green claims: flags, proxy units, no I/O/hardware/model imports', () => {
  const r = transition(anomaly().state, intent(11_000), 11_000).receipt;
  assert.deepEqual(r.labels, ['SYNTHETIC', 'HYPOTHETICAL']);
  for (const key of ['measuredEnvironmentalBenefit', 'physicalActuation', 'onDeviceInference', 'networkRequired']) {
    assert.equal(r[key], false);
  }
  assert.equal(UPPER_PROXY_WATTS, 720);
  assert.equal(r.energy.prospectiveScenarioIllustration.unverifiedPotentialHeatExposureWh, 60);
  assert.equal(r.energy.prospectiveScenarioIllustration.userDeclaredDurationMs, 300_000);
  assert.equal(r.energy.prospectiveScenarioIllustration.evidenceStatus, 'UNVERIFIED_ASSUMPTIONS_ONLY');
  assert.equal(r.energy.prospectiveScenarioIllustration.physicalUpperBound, false);
  assert.equal(r.watchdog, 'FUTURE_MCU_INTERFACE_NOT_IMPLEMENTED');
  assert.deepEqual(r.proposals, []);
  const source = readFileSync(new URL('../core.mjs', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /\bimport\s|\bfetch\s*\(|\bDate\s*\(|\bsetTimeout\s*\(|process\./);
});

test('deterministic pure transition and exact reproducible 90s demo with one camera proposal', () => {
  const { state } = anomaly();
  const snapshot = structuredClone(state);
  const event = fixture(11_000);
  const before = structuredClone(event);
  assert.deepEqual(transition(state, event, 11_000), transition(state, event, 11_000));
  assert.deepEqual(state, snapshot);
  assert.deepEqual(event, before);
  const a = runDemo(), b = runDemo();
  assert.deepEqual(a, b);
  assert.equal(a.durationSeconds, 90);
  assert.equal(a.finalReceipt.energy.cameraProposals, 1);
  assert.equal(a.finalReceipt.energy.boardAssumedWh, 0.1);
  assert.equal(a.finalReceipt.energy.cameraAssumedWh, 0.01);
  assert.equal(a.finalReceipt.windowEvidence, 'UNKNOWN');
  assert.equal(a.trace.find(r => r.second === 55).windowEvidence, 'UNKNOWN');
});

test('auction abstains at low assumed information value; no repeated query in same episode', () => {
  const first = transition(initialState(), thermo(0), 0);
  const weak = transition(first.state, thermo(10_000, 22 - 0.5001 / 6), 10_000);
  assert.equal(weak.receipt.thermal.status, 'COOLING_ANOMALY_HYPOTHESIS');
  assert.ok(weak.receipt.informationAuction.assumedInformationValueWh < 0.01);
  assert.deepEqual(weak.receipt.proposals, []);
  const a = anomaly();
  assert.equal(a.receipt.proposals[0].type, 'SELECTIVE_CAMERA_QUERY_PROPOSAL');
  assert.equal(tick(a.state, 10_001).receipt.energy.cameraProposals, 1);
  const intentional = transition(first.state, intent(1_000), 1_000);
  const cooling = transition(intentional.state, thermo(10_000, 21), 10_000);
  assert.deepEqual(cooling.receipt.proposals, []);
});

test('camera alone or pre-query frame cannot corroborate; distinct frames do not mean independence', () => {
  const alone = transition(initialState(), fixture(0), 0);
  assert.equal(alone.receipt.reason, 'UNISSUED_QUERY_ID');
  const old = transition(anomaly().state, fixture(10_000), 11_000);
  assert.equal(old.receipt.reason, 'STALE_OR_FUTURE_CAMERA_OR_QUERY');
  const open = transition(anomaly().state, fixture(11_000), 11_000);
  const unsolicited = transition(open.state, fixture(12_000, { frameFingerprint: '0000000000000002' }), 12_000);
  assert.equal(unsolicited.receipt.windowEvidence, 'UNKNOWN');
  assert.equal(unsolicited.receipt.independentCameraObservationsCertified, false);
});

test('humidity confound never re-arms spent camera episode until stable baseline', () => {
  const q = anomaly();
  assert.equal(q.state.queriedEpisode, true);
  const steam = transition(q.state, thermo(15_000, 20, 60), 15_000);
  assert.equal(steam.receipt.thermal.status, 'HUMIDITY_CONFOUND');
  assert.equal(steam.state.queriedEpisode, true);
  const cooling = transition(steam.state, thermo(20_000, 19.5, 60), 20_000);
  assert.equal(cooling.receipt.proposals.length, 0);
  assert.equal(cooling.state.cameraProposals, 1);
  const stable = transition(cooling.state, thermo(25_000, 19.5, 60), 25_000);
  assert.equal(stable.receipt.thermal.status, 'STABLE_OR_WARMING');
  assert.equal(stable.state.queriedEpisode, true);
  let resumed = stable;
  for (const at of [35_000, 45_000, 55_000]) {
    resumed = transition(resumed.state, thermo(at, 19.5, 60), at);
  }
  assert.equal(resumed.state.queriedEpisode, false);
  const newAnomaly = transition(resumed.state, thermo(60_000, 18.5, 60), 60_000);
  assert.equal(newAnomaly.receipt.proposals.length, 1);
});

test('confirmed intentional airing cancels camera request and does not imply measured heat loss', () => {
  const q = anomaly();
  const human = transition(q.state, intent(11_000), 11_000);
  assert.equal(human.state.pendingCamera, false);
  assert.equal(human.state.pendingCameraAt, null);
  assert.equal(human.receipt.proposals.length, 0);
  assert.equal(human.receipt.energy.prospectiveScenarioIllustration.physicalUpperBound, false);
  assert.equal(human.receipt.energy.prospectiveScenarioIllustration.evidenceStatus, 'UNVERIFIED_ASSUMPTIONS_ONLY');
  const late = transition(human.state, fixture(12_000), 12_000);
  assert.equal(late.receipt.reason, 'UNISSUED_QUERY_ID');
  assert.equal(late.receipt.windowEvidence, 'UNKNOWN');
});

test('jittery Thermo input cannot cancel a valid pending query; no duplicate spending', () => {
  const first = anomaly();
  const jitter = transition(first.state, thermo(11_000, 20.9), 11_000);
  assert.equal(jitter.receipt.reason, 'THERMO_ACCEPTED_SLOPE_WINDOW_UNCHANGED');
  assert.equal(jitter.state.pendingQueryId, 1);
  const open = transition(jitter.state, fixture(11_500), 11_500);
  assert.equal(open.receipt.windowEvidence, 'SYNTHETIC_OPEN_ROI');
  assert.equal(open.state.cameraProposals, 1);
  assert.equal(open.state.pendingQueryId, null);
  const next = transition(open.state, thermo(20_000, 20), 20_000);
  assert.equal(next.state.cameraProposals, 1);
});

test('query ID cannot be forged or replayed; caller hex never persisted', () => {
  const initial = anomaly();
  const wrong = transition(initial.state, fixture(11_000, { queryId: 2 }), 11_000);
  assert.equal(wrong.receipt.reason, 'UNISSUED_QUERY_ID');
  const hex = 'ab'.repeat(16);
  const good = transition(initial.state, fixture(11_000, { frameFingerprint: hex }), 11_000);
  assert.equal(good.receipt.windowEvidence, 'SYNTHETIC_OPEN_ROI');
  assert.equal(JSON.stringify(good.state).includes(hex), false);
  assert.equal(JSON.stringify(good.receipt).includes(hex), false);
  const reused = transition(good.state, fixture(12_000, { queryId: 1, frameFingerprint: 'cd'.repeat(16) }), 12_000);
  assert.equal(reused.receipt.reason, 'UNISSUED_QUERY_ID');
  assert.equal(reused.receipt.windowEvidence, 'UNKNOWN');
});
