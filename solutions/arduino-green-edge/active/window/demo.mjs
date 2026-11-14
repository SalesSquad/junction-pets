#!/usr/bin/env node
import { pathToFileURL } from 'node:url';
import { initialState, transition } from './core.mjs';

const thermo = (at, temperature, humidity = 45) => ({
  type: 'thermo', sample: { at, temperature, humidity },
});
const camera = (at, state, fingerprint) => ({ type: 'camera', fixture: {
  at, state, quality: 0.95, regionOfInterestOnly: true, storedFrames: false,
  frameFingerprint: fingerprint, queryId: 1,
} });

/** Reproducible virtual 90 seconds; neither sleep nor hardware access. */
export function runDemo() {
  let state = initialState();
  const events = [
    [0, 'Offline: no Thermo or camera', { type: 'tick' }],
    [10_000, 'First synthetic Thermo observation', thermo(10_000, 22)],
    [20_000, 'Stable synthetic room', thermo(20_000, 22)],
    [30_000, 'Authored open-window cooling scenario; kernel sees only T/RH', thermo(30_000, 21.5)],
    [31_000, 'Fresh OPEN synthetic ROI; advisory proposal only', camera(31_000, 'open', '0000000000000001')],
    [35_000, 'Knob: explicitly confirmed five-minute intentional airing',
      { type: 'intent', at: 35_000, confirmed: true, durationMs: 300_000 }],
    [40_000, 'Authored steam temperature/humidity confound', thermo(40_000, 24, 85)],
    [50_000, 'Cooling after steam; large RH change remains a confound', thermo(50_000, 23, 70)],
    [55_000, 'Lens fully occluded: UNKNOWN, never CLOSED', camera(55_000, 'occluded', '0000000000000002')],
    [90_000, 'End: no fresh sensor evidence; no environmental benefit measured', { type: 'tick' }],
  ];
  const trace = events.map(([now, scenario, event]) => {
    const result = transition(state, event, now);
    state = result.state;
    return { second: now / 1000, scenario, ...result.receipt };
  });
  return {
    schema: 'open-window.synthetic-demo.v1', labels: ['SYNTHETIC', 'HYPOTHETICAL'],
    durationSeconds: 90, source: 'Hand-authored fixtures; no real camera or board inference',
    trace, finalReceipt: trace.at(-1),
    unverified: ['REAL_UNO_Q', 'MODULINO_SENSOR_REVISION_AND_IO', 'USB_CAMERA_ROI_CAPTURE',
      'ON_DEVICE_CLASSIFIER', 'PHYSICAL_MCU_WATCHDOG', 'CALIBRATED_ENERGY',
      'CAUSAL_HEAT_LOSS_OR_ENVIRONMENTAL_BENEFIT', 'EXTERNAL_SUBMISSION'],
    priorOccupancyExperiment: 'NO_GO; no occupancy optimization or environmental benefit verified',
    correlatedFrames: 'Distinct fingerprints do not establish independent observations or causal heat loss',
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.stdout.write(`${JSON.stringify(runDemo(), null, 2)}\n`);
}

export default runDemo;
