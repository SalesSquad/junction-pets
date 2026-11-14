import { createDay, scheduledAction, ASSUMPTIONS } from '../sim/engine.mjs';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

export const SOURCE = 'eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4';
export const FEATURES = ['time_sin', 'time_cos', 'temperature_c', 'rh_percent', 'connected', 'age_seconds'];
export const HEADER = ['day_id', 'partition', 'scenario', 'seed', 'second', ...FEATURES, 'target_occupied'];
export const PARTITIONS = ['train', 'validation', 'calibration', 'test'];
const here = dirname(fileURLToPath(import.meta.url));
export const sha = value => createHash('sha256').update(value).digest('hex');
export function sourceHashes() {
  return Object.fromEntries(['sim/engine.mjs', 'core.mjs'].map(path => {
    const bytes = readFileSync(resolve(here, '..', path));
    const pinned = execFileSync('git', ['show', `${SOURCE}:solutions/arduino-green-edge/${path}`], { cwd: here });
    if (!bytes.equals(pinned)) throw new Error(`Source differs from pin: ${path}`);
    return [path, sha(bytes)];
  }));
}
export function plan(days = 4, seed = 1729) {
  if (!Number.isInteger(days) || days < 4 || days > 48) throw new RangeError('days: integer 4..48 per scenario/partition');
  if (!Number.isInteger(seed) || seed < 0 || seed > 0xffffffff - 1000) throw new RangeError('seed: integer 0..4294966295');
  let index = 0;
  return PARTITIONS.flatMap(partition => (partition === 'test' ? ['winter', 'summer', 'evening', 'fault'] : ['winter', 'summer', 'evening']).flatMap(scenario =>
    Array.from({ length: days }, (_, day) => ({ day_id: `${partition}-${scenario}-${day}`, partition, scenario, seed: seed + index++ }))));
}
export function features(row) {
  const angle = row.second / 86400 * 2 * Math.PI;
  return [Math.sin(angle), Math.cos(angle), row.sample.temperature, row.sample.humidity, Number(row.sample.connected),
    (ASSUMPTIONS.epochMs + row.second * 1000 - row.sample.at) / 1000];
}
export function csvDay(day) {
  return createDay(day).filter(row => row.second % 60 === 0).map(row =>
    [...['day_id', 'partition', 'scenario', 'seed'].map(k => day[k]), row.second, ...features(row), Number(row.truth.occupancy > 0)].join(',')).join('\n') + '\n';
}
function args(argv) {
  const out = {};
  for (const arg of argv) {
    const match = /^--(days|seed|out|evaluation)=(.+)$/.exec(arg);
    if (!match || Object.hasOwn(out, match[1])) throw new Error(`Unknown/duplicate argument: ${arg}`);
    out[match[1]] = match[2];
  }
  return out;
}
export function main(argv) {
  const options = args(argv);
  const sources = sourceHashes();
  if (options.evaluation) {
    if (Object.keys(options).length !== 1) throw new Error('evaluation accepts only a dataset manifest');
    const manifest = JSON.parse(readFileSync(options.evaluation, 'utf8'));
    if (manifest.source_commit !== SOURCE || JSON.stringify(manifest.sources) !== JSON.stringify(sources) ||
        JSON.stringify(manifest.days) !== JSON.stringify(plan(manifest.days_per_scenario, manifest.seed))) throw new Error('Invalid source/day plan');
    // This stream is ONLY for comparative evaluator scoring and query-time camera calls.
    for (const day of manifest.days.filter(d => d.partition === 'test')) {
      for (const variant of ['nominal', 'drift', 'correlated_false_empty', 'untrusted_camera']) {
        const shiftHours = variant === 'drift' ? 2 : 0;
        const sensorBias = variant === 'drift' ? 2 : 0;
        const rows = createDay({ ...day, shiftHours, sensorBias }).map(row => ({ ...row,
          cheap: features(row), baseline: scheduledAction(row.second, day.scenario) }));
        process.stdout.write(JSON.stringify({ day, variant, rows }) + '\n');
      }
    }
    return;
  }
  const days = Number(options.days ?? 4), seed = Number(options.seed ?? 1729);
  const daysPlan = plan(days, seed);
  if (!options.out) throw new Error('Required --out=directory');
  mkdirSync(options.out, { recursive: true });
  const files = {};
  for (const partition of PARTITIONS) {
    const csv = HEADER.join(',') + '\n' + daysPlan.filter(d => d.partition === partition).map(csvDay).join('');
    writeFileSync(resolve(options.out, `${partition}.csv`), csv);
    files[partition] = { sha256: sha(csv), rows: daysPlan.filter(d => d.partition === partition).length * 1440 };
  }
  const manifest = { schema: 'green-edge.active.dataset.v1', evidence: 'SYNTHETIC/OFFBOARD', source_commit: SOURCE, sources,
    exporter_sha256: sha(readFileSync(fileURLToPath(import.meta.url))), days_per_scenario: days, seed, features: FEATURES,
    label: 'target_occupied', decision_seconds: 60, original_seconds: 10, days: daysPlan, files,
    normalization: 'float32; fit train only in train_gpu.py; no pretrained model', fault_train: false };
  writeFileSync(resolve(options.out, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  process.stderr.write(JSON.stringify({ files, source_commit: SOURCE }) + '\n');
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(process.argv.slice(2)); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
