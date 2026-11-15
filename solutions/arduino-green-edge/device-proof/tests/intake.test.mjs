import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { reviewMeterDocument } from '../../measurement.mjs';
import { createTelemetryIntake, IntakeError, LIMITS, parseBoundedJSON } from '../intake.mjs';
import { DEMO_ENROLLMENT, demoReplay, replayText } from '../replay.mjs';
import { runCli } from '../cli.mjs';

const rows = (variant = 'positive') => demoReplay(variant).trimEnd().split('\n').map(JSON.parse);
const create = () => createTelemetryIntake({ ...DEMO_ENROLLMENT });
const append = (intake, row) => intake.append(JSON.stringify(row.packet), row.receivedClock);
const refusal = (fn, code) => assert.throws(fn, error => error instanceof IntakeError && error.code === code);
function rejected(mutate, code, index = 0) {
  const intake = create(), fixtures = rows();
  for (let i = 0; i < index; i++) append(intake, fixtures[i]);
  const before = intake.snapshot(), row = structuredClone(fixtures[index]);
  mutate(row);
  refusal(() => append(intake, row), code);
  assert.deepEqual(intake.snapshot(), before, 'refusal must be atomic');
  append(intake, fixtures[index]); // The valid next packet still fits.
}
function interval(sequence, durationMs = 10000, mWh = 1, base = 0, calibrationEnd = 86400000) {
  const row = rows()[0];
  row.packet.sequence = sequence;
  const startMs = base + (sequence - 1) * durationMs, endMs = base + sequence * durationMs;
  row.packet.clock.atMs = row.receivedClock.atMs = endMs;
  for (const channel of Object.values(row.packet.channels)) {
    Object.assign(channel, { startMs, endMs, mWh, calibration: { checkedAtMs: base, validUntilMs: calibrationEnd } });
  }
  return row;
}

test('three positive packets transcode exactly into the existing reviewer contract', () => {
  const intake = create();
  for (const row of rows()) append(intake, row);
  const comparison = intake.review(), expected = reviewMeterDocument(intake.document());
  for (const [key, value] of Object.entries(expected)) assert.deepEqual(comparison[key], value);
  assert.deepEqual(comparison.totalsMWh, { baseline: 510, scenario: 270, device: 30 });
  assert.equal(comparison.netDifferenceMWh, 210);
  assert.equal(comparison.netDifferenceKWh, 0.000210);
});

test('negative and zero net differences remain signed, with device overhead included', () => {
  assert.equal(replayText(demoReplay('negative'), DEMO_ENROLLMENT).comparison.netDifferenceMWh, -135);
  const intake = create();
  for (const row of rows()) {
    row.packet.channels.baseline.mWh = 100;
    row.packet.channels.scenario.mWh = 90;
    row.packet.channels.device.mWh = 10;
    append(intake, row);
  }
  assert.equal(intake.review().netDifferenceMWh, 0);
});

test('one packet stages only: no incomplete meter document or comparison can escape', () => {
  const intake = create();
  refusal(() => intake.review(), 'NEED_TWO_INTERVALS');
  assert.equal(append(intake, rows()[0]).status, 'COLLECTING');
  refusal(() => intake.document(), 'NEED_TWO_INTERVALS');
  refusal(() => intake.review(), 'NEED_TWO_INTERVALS');
  assert.equal(append(intake, rows()[1]).status, 'READY_FOR_UNVERIFIED_REVIEW');
});

test('every accepted observation and result stays unverified and unauthorized', () => {
  const intake = create();
  for (const row of rows()) {
    const receipt = append(intake, row);
    assert.equal(receipt.evidence, 'USER_SUPPLIED_UNVERIFIED');
    assert.equal(receipt.actuationAuthorized, false);
    assert.equal(receipt.producerAuthenticated, false);
  }
  for (const value of [intake.review(), ...intake.snapshot()]) {
    assert.equal(value.evidence, 'USER_SUPPLIED_UNVERIFIED');
    assert.equal(value.actuationAuthorized, false);
    assert.equal(value.measuredEnvironmentalBenefit, false);
    assert.equal(value.physicalExecution, false);
  }
  assert.equal(intake.document().evidence, 'USER_SUPPLIED_UNVERIFIED');
  assert.match(intake.review().caveat, /unverified/);
});

test('snapshots, exported documents, enrollment and input cannot mutate accepted history', () => {
  const enrollment = { ...DEMO_ENROLLMENT }, intake = createTelemetryIntake(enrollment), fixture = rows();
  enrollment.streamId = 'other';
  for (const row of fixture) append(intake, row);
  fixture[0].packet.channels.baseline.mWh = 0;
  const snapshot = intake.snapshot();
  snapshot[0].packet.channels.baseline.mWh = 0;
  snapshot.pop();
  const doc = intake.document(); doc.channels.device[0].mWh = 1000000;
  assert.equal(intake.snapshot().length, 3);
  assert.equal(intake.review().netDifferenceMWh, 210);
  assert.deepEqual(Object.keys(intake).sort(), ['append', 'document', 'review', 'snapshot']);
  assert.equal(Object.isFrozen(intake), true);
});

test('a duplicate, rollback or skipped sequence is rejected without altering history', () => {
  for (const sequence of [1, 3, 0, Number.MAX_SAFE_INTEGER]) {
    rejected(row => { row.packet.sequence = sequence; }, sequence === 0 ? 'INTEGER_RANGE' : 'SEQUENCE', 1);
  }
  const intake = create(), row = rows()[0]; append(intake, row);
  refusal(() => append(intake, row), 'SEQUENCE');
  assert.equal(intake.snapshot().length, 1);
});

test('packet and host clocks cannot roll back, and packet clock must strictly increase', () => {
  for (const at of [9999, 10000]) rejected(row => { row.packet.clock.atMs = at; }, 'CLOCK_ORDER', 1);
  rejected(row => { row.receivedClock.atMs = 9999; }, 'CLOCK_ORDER', 1);
});

test('same host receive time is allowed for a fresh ordered offline batch', () => {
  const intake = create();
  for (const row of rows()) { row.receivedClock.atMs = 30000; append(intake, row); }
  assert.equal(intake.review().intervalCount, 3);
});

test('stale packet clock, stale interval end and future observations are rejected', () => {
  rejected(row => { row.receivedClock.atMs = 40001; }, 'STALE_OR_FUTURE');
  rejected(row => { row.packet.clock.atMs = row.receivedClock.atMs = 40001; }, 'STALE_OR_FUTURE');
  rejected(row => { row.packet.clock.atMs = 10001; }, 'STALE_OR_FUTURE');
  rejected(row => { row.packet.clock.atMs = 9999; }, 'STALE_OR_FUTURE');
});

test('freshness boundary is inclusive and never extrapolates missing time', () => {
  const intake = create(), fixture = rows();
  for (const row of fixture) { row.receivedClock.atMs += LIMITS.freshMs; append(intake, row); }
  assert.equal(intake.review().windowEndMs, 30000);
  assert.equal(intake.review().netDifferenceMWh, 210);
});

test('clock kind, session identity and per-channel clock mismatch all refuse', () => {
  for (const target of ['packet', 'receivedClock', 'channel']) {
    rejected(row => {
      if (target === 'channel') row.packet.channels.device.clockId = 'clock-0000000000000002';
      else (target === 'packet' ? row.packet.clock : row.receivedClock).id = 'clock-0000000000000002';
    }, 'TIME_BASE_MISMATCH');
  }
  rejected(row => { row.packet.clock.kind = 'unix-ms'; }, 'TIME_BASE_MISMATCH');
  rejected(row => { row.receivedClock.kind = 'unix-ms'; }, 'TIME_BASE_MISMATCH');
});

test('another stream cannot be appended', () => {
  rejected(row => { row.packet.streamId = 'stream-0000000000000002'; }, 'STREAM_MISMATCH');
});

test('all three energy channels are mandatory and only those channels are accepted', () => {
  for (const kind of ['baseline', 'scenario', 'device']) {
    rejected(row => { delete row.packet.channels[kind]; }, 'EXACT_FIELDS');
  }
  rejected(row => { row.packet.channels.occupants = {}; }, 'EXACT_FIELDS');
});

test('extra personal metadata at every schema level is rejected and never retained', () => {
  const secret = 'PRIVATE_PERSON_EMAIL@example.invalid';
  for (const target of ['packet', 'clock', 'channel', 'calibration', 'hostClock']) {
    const intake = create(), row = rows()[0];
    const value = { packet: row.packet, clock: row.packet.clock, channel: row.packet.channels.device,
      calibration: row.packet.channels.device.calibration, hostClock: row.receivedClock }[target];
    value.email = secret;
    assert.throws(() => append(intake, row), error => error.code === 'EXACT_FIELDS' && !error.message.includes(secret));
    assert.deepEqual(intake.snapshot(), []);
  }
});

test('unsafe method, action, GPIO, consent and claimed authenticity cannot grant effects', () => {
  for (const method of ['green_edge.set_output', 'exec', 'green_edge.sample']) {
    rejected(row => { row.packet.method = method; }, 'PROTOCOL');
  }
  for (const field of ['action', 'gpio', 'actuationAuthorized', 'optIn', 'evidence', 'signature']) {
    rejected(row => { row.packet[field] = true; }, 'EXACT_FIELDS');
  }
});

test('unknown schema, string numbers and unit conversions are refused', () => {
  for (const [field, value] of [['schema', 'green-edge.bridge-energy.v2'], ['unit', 'Wh']]) {
    rejected(row => { row.packet[field] = value; }, 'PROTOCOL');
  }
  rejected(row => { row.packet.channels.baseline.mWh = '170'; }, 'INTEGER_RANGE');
});

test('only bounded pseudonyms are accepted, never free text, email or path identifiers', () => {
  for (const id of ['name@example.invalid', '../meter', 'meter-0000000000000001\n', 'Alice', 'meter-000000000000000A']) {
    rejected(row => { row.packet.channels.device.meterId = id; }, 'PSEUDONYM');
  }
  refusal(() => createTelemetryIntake({ ...DEMO_ENROLLMENT, streamId: 'Alice' }), 'PSEUDONYM');
  refusal(() => createTelemetryIntake({ ...DEMO_ENROLLMENT, clockId: 'clock-1' }), 'PSEUDONYM');
});

test('one meter cannot stand in for another channel, or change after admission', () => {
  rejected(row => { row.packet.channels.device.meterId = row.packet.channels.baseline.meterId; }, 'METER_REUSE');
  rejected(row => { row.packet.channels.device.meterId = 'meter-0000000000000004'; }, 'METER_OR_CALIBRATION_CHANGED', 1);
});

test('calibration must be declared for each channel and cover the entire interval', () => {
  for (const kind of ['baseline', 'scenario', 'device']) {
    rejected(row => { delete row.packet.channels[kind].calibration; }, 'EXACT_FIELDS');
    rejected(row => { row.packet.channels[kind].calibration.checkedAtMs = 1; }, 'CALIBRATION_WINDOW');
    rejected(row => { row.packet.channels[kind].calibration.validUntilMs = 9999; }, 'CALIBRATION_WINDOW');
    rejected(row => { row.packet.channels[kind].calibration = { checkedAtMs: 10, validUntilMs: 10 }; }, 'CALIBRATION_WINDOW');
  }
});

test('calibration cannot be renewed, altered or silently swapped mid-stream', () => {
  rejected(row => { row.packet.channels.device.calibration.validUntilMs = 40000; }, 'METER_OR_CALIBRATION_CHANGED', 1);
  rejected(row => { row.packet.channels.device.calibration.checkedAtMs = 1; }, 'METER_OR_CALIBRATION_CHANGED', 1);
});

test('matched comparison boundaries are required on every channel', () => {
  for (const kind of ['scenario', 'device']) {
    rejected(row => { row.packet.channels[kind].startMs = 1; }, 'CHANNEL_ALIGNMENT');
    rejected(row => { row.packet.channels[kind].endMs = 9999; }, 'CHANNEL_ALIGNMENT');
  }
});

test('gaps, overlaps and duplicate intervals cannot be hidden behind a new sequence', () => {
  for (const start of [9999, 10001, 0]) {
    rejected(row => { for (const ch of Object.values(row.packet.channels)) ch.startMs = start; }, 'INTERVAL_GAP_OR_OVERLAP', 1);
  }
});

test('zero, reversed and overlong intervals are rejected', () => {
  for (const [startMs, endMs] of [[10000, 10000], [10001, 10000], [0, 3600001]]) {
    rejected(row => { Object.assign(row.packet.channels.baseline, { startMs, endMs }); }, 'DURATION');
  }
});

test('negative, fractional, null, unsafe and nonfinite energy or clocks cannot enter state', () => {
  for (const value of [-1, 0.25, null, Number.MAX_SAFE_INTEGER, NaN, Infinity]) {
    rejected(row => { row.packet.channels.baseline.mWh = value; }, 'INTEGER_RANGE');
  }
  for (const value of [-1, 0.25, null, Number.MAX_SAFE_INTEGER + 1]) {
    rejected(row => { row.packet.clock.atMs = value; }, 'INTEGER_RANGE');
  }
  const row = rows()[0], text = JSON.stringify(row.packet);
  for (const literal of ['1e309', '-0', '9007199254740993']) {
    refusal(() => create().append(text.replace('"mWh":170', `"mWh":${literal}`), row.receivedClock), 'INTEGER_RANGE');
  }
});

test('bounded high totals remain exact; the 97th packet cannot overflow the log', () => {
  const intake = create();
  for (let sequence = 1; sequence <= LIMITS.packets; sequence++) append(intake, interval(sequence, 1, LIMITS.intervalMWh));
  assert.equal(intake.review().totalsMWh.baseline, 96000000000);
  assert.equal(intake.review().netDifferenceMWh, -96000000000);
  const before = intake.snapshot();
  refusal(() => append(intake, interval(97, 1)), 'CAPACITY');
  assert.deepEqual(intake.snapshot(), before);
});

test('fraction/exponent encodings cannot exploit IEEE-754 rounding or underflow', () => {
  const row = rows()[0], text = JSON.stringify(row.packet);
  for (const literal of ['170.0000000000000000001', '1e-9999', '1e2', '170.0', '-0']) {
    refusal(() => create().append(text.replace('"mWh":170', `"mWh":${literal}`), row.receivedClock), 'INTEGER_RANGE');
    refusal(() => replayText(demoReplay('positive').replace('"mWh":170', `"mWh":${literal}`), DEMO_ENROLLMENT), 'INTEGER_RANGE');
  }
  refusal(() => create().append(text.replace('"atMs":10000', '"atMs":9007199254740991.1'), row.receivedClock), 'INTEGER_RANGE');
});

test('a comparison may cover exactly one day, never a twenty-fifth hour', () => {
  const intake = create();
  for (let sequence = 1; sequence <= 24; sequence++) append(intake, interval(sequence, 3600000, 1, 0, 90000000));
  assert.equal(intake.review().windowEndMs, 86400000);
  refusal(() => append(intake, interval(25, 3600000, 1, 0, 90000000)), 'TOTAL_DURATION');
  assert.equal(intake.snapshot().length, 24);
});

test('safe-integer endpoint boundary works without timestamp addition overflow', () => {
  const intake = create(), base = Number.MAX_SAFE_INTEGER - 2;
  append(intake, interval(1, 1, 0, base, Number.MAX_SAFE_INTEGER));
  append(intake, interval(2, 1, 0, base, Number.MAX_SAFE_INTEGER));
  assert.equal(intake.review().windowEndMs, Number.MAX_SAFE_INTEGER);
  assert.equal(intake.review().netDifferenceMWh, 0);
});

test('duplicate JSON keys, including escaped keys, are rejected before normalization', () => {
  const row = rows()[0], text = JSON.stringify(row.packet);
  for (const key of ['sequence', '\\u0073equence']) {
    refusal(() => create().append(text.replace('"sequence":1', `"sequence":99,"${key}":1`), row.receivedClock), 'DUPLICATE_JSON_KEY');
  }
  refusal(() => parseBoundedJSON('{"channels":{"device":{},"device":{}}}'), 'DUPLICATE_JSON_KEY');
});

test('prototype pollution keys are rejected without touching Object.prototype', () => {
  for (const key of ['__proto__', 'constructor', 'prototype', '\\u005f_proto__']) {
    refusal(() => parseBoundedJSON(`{"${key}":{"polluted":true}}`), 'FORBIDDEN_JSON_KEY');
  }
  assert.equal({}.polluted, undefined);
});

test('malformed JSON, arrays, trailing content and excessive nesting fail closed', () => {
  for (const text of ['', 'null junk', '{"a":1,}', '{"a":01}', '{"a":"\n"}', '[]', '{"a":undefined}', '{"a":true}{}']) {
    assert.throws(() => parseBoundedJSON(text), IntakeError);
  }
  refusal(() => parseBoundedJSON('{"a":'.repeat(7) + '0' + '}'.repeat(7)), 'JSON_COMPLEXITY');
  refusal(() => parseBoundedJSON('{' + Array.from({ length: 128 }, (_, i) => `"a${i}":0`).join(',') + '}'), 'JSON_COMPLEXITY');
});

test('byte bounds account for UTF-8, and the parser cannot be configured unbounded', () => {
  for (const text of [' '.repeat(LIMITS.packetBytes + 1), 'é'.repeat(LIMITS.packetBytes / 2 + 1)]) {
    refusal(() => parseBoundedJSON(text), 'INPUT_SIZE_OR_TYPE');
  }
  assert.equal(parseBoundedJSON(' '.repeat(LIMITS.packetBytes - 2) + '{}') instanceof Object, true);
  for (const size of [Infinity, LIMITS.replayBytes + 1, -1]) refusal(() => parseBoundedJSON('{}', size), 'INPUT_SIZE_OR_TYPE');
});

test('raw JS object packets and getter-bearing host configuration are never executed', () => {
  let called = false;
  const payload = { get schema() { called = true; return 'evil'; } };
  refusal(() => create().append(payload, rows()[0].receivedClock), 'INPUT_SIZE_OR_TYPE');
  const hostClock = { ...rows()[0].receivedClock, get atMs() { called = true; return 10000; } };
  refusal(() => create().append(JSON.stringify(rows()[0].packet), hostClock), 'EXACT_FIELDS');
  assert.equal(called, false);
});

test('replay is deterministic, supports CRLF and rejects blank or incomplete streams', () => {
  const text = demoReplay('positive');
  assert.deepEqual(replayText(text, DEMO_ENROLLMENT), replayText(text.replaceAll('\n', '\r\n'), DEMO_ENROLLMENT));
  assert.deepEqual(replayText(text, DEMO_ENROLLMENT), replayText(text, DEMO_ENROLLMENT));
  refusal(() => replayText(text.split('\n')[0], DEMO_ENROLLMENT), 'REPLAY_INTERVAL_COUNT');
  assert.throws(() => replayText(text + '\n', DEMO_ENROLLMENT), IntakeError);
});

test('replay refuses an invalid late packet, unknown wrapper metadata and hidden duplicates', () => {
  const fixture = rows(); fixture[2].packet.channels.device.mWh = -1;
  refusal(() => replayText(fixture.map(JSON.stringify).join('\n'), DEMO_ENROLLMENT), 'INTEGER_RANGE');
  const extra = rows(); extra[0].name = 'PRIVATE_NAME';
  refusal(() => replayText(extra.map(JSON.stringify).join('\n'), DEMO_ENROLLMENT), 'EXACT_FIELDS');
  refusal(() => replayText(demoReplay('positive').replace('"sequence":1', '"sequence":0,"sequence":1'), DEMO_ENROLLMENT), 'DUPLICATE_JSON_KEY');
});

test('replay bounds whole input, individual lines and packet count', () => {
  refusal(() => replayText(' '.repeat(LIMITS.replayBytes + 1), DEMO_ENROLLMENT), 'REPLAY_SIZE_OR_TYPE');
  refusal(() => replayText((' '.repeat(LIMITS.packetBytes + 1) + '\n').repeat(2), DEMO_ENROLLMENT), 'INPUT_SIZE_OR_TYPE');
  const line = demoReplay('positive').split('\n')[0];
  refusal(() => replayText((line + '\n').repeat(97), DEMO_ENROLLMENT), 'REPLAY_INTERVAL_COUNT');
});

test('operator CLI positive and negative demos use the same unverified comparison path', async () => {
  for (const [variant, net] of [['positive', 210], ['negative', -135]]) {
    const result = await runCli(['demo', variant]);
    assert.equal(result.source, 'DEMO_FIXTURE_NOT_HARDWARE');
    assert.equal(result.comparison.netDifferenceMWh, net);
    assert.equal(result.evidence, 'USER_SUPPLIED_UNVERIFIED');
    assert.equal(result.actuationAuthorized, false);
    const fixture = await runCli(['fixture', variant]);
    assert.deepEqual(result.comparison, replayText(fixture, DEMO_ENROLLMENT).comparison);
  }
});

test('operator CLI replays a local file and rejects directories, unreadable and non-JSON files safely', async () => {
  const path = fileURLToPath(new URL('./fixtures/positive.ndjson', import.meta.url));
  const result = await runCli(['replay', path, DEMO_ENROLLMENT.streamId, DEMO_ENROLLMENT.clockId]);
  assert.equal(result.source, 'LOCAL_USER_FILE');
  assert.equal(result.comparison.netDifferenceMWh, 210);
  for (const input of [fileURLToPath(new URL('.', import.meta.url)), path + '.missing', fileURLToPath(import.meta.url)]) {
    await assert.rejects(runCli(['replay', input, DEMO_ENROLLMENT.streamId, DEMO_ENROLLMENT.clockId]), error => {
      assert.equal(error instanceof IntakeError, true);
      assert.equal(error.message.includes(input), false);
      return true;
    });
  }
});

test('operator CLI rejects extra flags, unsafe commands and invalid demo names', async () => {
  for (const args of [[], ['demo', 'other'], ['demo', 'positive', '--actuate'], ['exec', 'positive'], ['replay', '/dev/null']]) {
    await assert.rejects(runCli(args), error => error.code === 'CLI_ARGUMENTS');
  }
});
