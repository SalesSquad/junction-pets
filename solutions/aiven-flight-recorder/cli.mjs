#!/usr/bin/env node
// node cli.mjs            -> offline, deterministic (no external service)
// node cli.mjs --live     -> Aiven for Kafka + Aiven for PostgreSQL (env config)
import { runBaseline, runFlightRecorder, compare, DEFAULTS } from './core.mjs';
import { memoryAdapter } from './memory.mjs';

const live = process.argv.includes('--live');
const started = new Date().toISOString();
const baseline = runBaseline(DEFAULTS);
let adapter;
if (live) {
  const { liveAdapter, liveConfigFromEnv } = await import('./live.mjs');
  adapter = liveAdapter(liveConfigFromEnv());
} else adapter = memoryAdapter();
const t0 = Date.now();
const recorder = await runFlightRecorder(adapter, DEFAULTS);
await adapter.close?.();
console.log(JSON.stringify({ started, scenario: DEFAULTS, ms: Date.now() - t0, topic: adapter.topic ?? null, ...compare(baseline, recorder) }, null, 2));
