import { CHANNELS, syntheticMeterDocument } from '../measurement.mjs';
import {
  BRIDGE_METHOD, PACKET_SCHEMA, EVIDENCE, LIMITS, createTelemetryIntake,
  exact, parseBoundedJSON, refuse,
} from './intake.mjs';

export const DEMO_ENROLLMENT = Object.freeze({
  streamId: 'stream-0000000000000001', clockId: 'clock-0000000000000001',
});

/** Reuse the existing positive/negative meter fixtures, not a second energy model.
 * Relabelling here is the intake's trust ceiling, NOT a measured-data assertion.
 */
export function demoReplay(variant) {
  if (!['positive', 'negative'].includes(variant)) refuse('DEMO_VARIANT');
  const doc = syntheticMeterDocument(variant);
  const { streamId, clockId } = DEMO_ENROLLMENT;
  return doc.channels.baseline.map((_, i) => {
    const atMs = doc.channels.baseline[i].endMs;
    const clock = { kind: 'monotonic-ms', id: clockId, atMs };
    return {
      receivedClock: { ...clock },
      packet: {
        schema: PACKET_SCHEMA, method: BRIDGE_METHOD, streamId, sequence: i + 1,
        clock, unit: 'mWh', channels: Object.fromEntries(CHANNELS.map((kind, channel) => [kind, {
          meterId: `meter-${String(channel + 1).padStart(16, '0')}`, clockId,
          ...doc.channels[kind][i], calibration: {
            checkedAtMs: doc.calibration[kind].checkedAtMs,
            validUntilMs: doc.calibration[kind].validUntilMs,
          },
        }])),
      },
    };
  }).map(row => JSON.stringify(row)).join('\n') + '\n';
}

/** Atomic operator replay: a failure returns no partial comparison or raw input.
 * recorded receivedClock is caller-supplied historical time, not wall-clock now.
 */
export function replayText(text, enrollment) {
  if (typeof text !== 'string' || text.length > LIMITS.replayBytes
    || new TextEncoder().encode(text).length > LIMITS.replayBytes) refuse('REPLAY_SIZE_OR_TYPE');
  const lines = text.split('\n');
  if (lines.at(-1) === '') lines.pop();
  if (lines.length < 2 || lines.length > LIMITS.packets) refuse('REPLAY_INTERVAL_COUNT');
  const intake = createTelemetryIntake(enrollment);
  for (const line of lines) {
    const row = parseBoundedJSON(line, LIMITS.packetBytes);
    exact(row, ['receivedClock', 'packet']);
    // Strict parsing ABOVE rejects duplicate keys even inside packet, before
    // JSON.stringify can normalize them. append independently checks its schema.
    intake.append(JSON.stringify(row.packet), row.receivedClock);
  }
  return {
    mode: 'OFFLINE_REPLAY', evidence: EVIDENCE, actuationAuthorized: false,
    physicalExecution: false, measuredEnvironmentalBenefit: false,
    comparison: intake.review(),
  };
}
