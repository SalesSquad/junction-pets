#!/usr/bin/env node
// Produce synthetic *day-level* heldout and calibration observations from the actual
// committed Green Edge Twin M3 engine. Never treat these as physical meter readings.
import { createHash } from 'node:crypto';
import { simulate, CASES } from '../sim/engine.mjs';

const SOURCE_PIN = '7aee5bd372fa32fa92306f0db9fab39bd2ca1567';
const arg = process.argv[2] ?? '--days=12';
if (process.argv.length > 3 || !/^--days=(?:[4-9]|[1-3][0-9]|4[0-8])$/.test(arg)) {
  console.error('Usage: node proof/generate.mjs --days=4..48 > synthetic-days.csv');
  process.exit(2);
}
const days = Number(arg.slice('--days='.length));
const columns = ['evidence','source_sha','partition','scenario','seed','shift_hours','sensor_bias_c',
  'baseline_ws','edge_load_ws','gross_ws','edge_only_unmet_s','baseline_unmet_s',
  'edge_unmet_s',
  'fallback_fraction','fault_slots','disturbance_digest'];
const shift = [-2, -0.5, 1, 2];
const bias = [-1, 0.5, -0.5, 1];
const records = [];
for (const [partition, offset] of [['calibration',1], ['heldout',100001]]) {
  for (const scenario of CASES) {
    for (let i = 0; i < days; i++) {
      const seed = offset + i;
      const result = simulate({ scenario, seed, overheadWatts: 0,
        shiftHours: shift[(i + Math.floor(i / 4)) % 4],
        sensorBias: bias[Math.floor(i / 4) % 4] });
      const edgeOnlyUnmetS = result.service.edgeOnlyUnmet.fanSeconds
        + result.service.edgeOnlyUnmet.lightSeconds;
      const baselineUnmetS = result.service.baselineUnmet.fanSeconds
        + result.service.baselineUnmet.lightSeconds;
      if (result.evidence !== 'SYNTHETIC' || result.measured !== false ||
          result.physicalExecution !== false || result.modelInference !== false) {
        throw Error('Refused: M3 provenance changed to non-synthetic evidence');
      }
      records.push(['SYNTHETIC', SOURCE_PIN, partition, scenario, seed,
        result.shiftHours, result.sensorBias, result.baselineWs, result.edgeLoadWs,
        result.grossWs, edgeOnlyUnmetS, baselineUnmetS,
        result.service.edgeUnmet.fanSeconds + result.service.edgeUnmet.lightSeconds,
        result.coverage.fallbackFraction,
        result.coverage.faultSlots, result.disturbanceDigest].join(','));
    }
  }
}
const csv = columns.join(',') + '\n' + records.join('\n') + '\n';
const sha = createHash('sha256').update(csv).digest('hex');
process.stdout.write(csv);
console.error(`GREEN_PROOF_SYNTHETIC_GENERATOR source=${SOURCE_PIN} days_per_partition_and_scenario=${days} rows=${records.length} csv_sha256=${sha}`);
