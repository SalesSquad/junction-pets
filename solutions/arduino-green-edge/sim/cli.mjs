#!/usr/bin/env node
import { simulate, stress } from './engine.mjs';

// Dependency-free, bounded JSON interface. All output is explicitly synthetic.
const usage = 'node sim/cli.mjs winter 4 [--seed=1] [--seeds=12] [--trace]';
try {
  const args = process.argv.slice(2);
  if (args.length > 5) throw new Error(usage);
  const [scenario = 'winter', watts = '4', ...flags] = args;
  let seed = 1, seeds, trace = false;
  const seen = new Set();
  const numeric = value => {
    if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) throw new Error('Expected a non-negative decimal');
    return Number(value);
  };
  for (const flag of flags) {
    const key = flag.split('=')[0];
    if (seen.has(key)) throw new Error(`Duplicate flag: ${key}`);
    seen.add(key);
    if (flag === '--trace') trace = true;
    else if (flag.startsWith('--seed=')) seed = numeric(flag.slice(7));
    else if (flag.startsWith('--seeds=')) seeds = numeric(flag.slice(8));
    else throw new Error(usage);
  }
  if (trace && seeds !== undefined) throw new Error('--trace is single-day only');
  const options = { scenario, overheadWatts: numeric(watts), seed, trace };
  const result = seeds === undefined ? simulate(options) : stress({ ...options, seeds });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
} catch (error) {
  process.stderr.write(`${JSON.stringify({ error: error.message, evidence: 'SYNTHETIC', usage })}\n`);
  process.exitCode = 1;
}
