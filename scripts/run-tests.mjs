#!/usr/bin/env node
// Parallel test runner. Runs every test file Node's default discovery would find,
// in two phases:
//   1. all files in parallel (concurrency = CPU count, override with TEST_CONCURRENCY);
//   2. files marked `// test:serial` alone, one at a time, after phase 1 has finished.
// A file needs the marker when its code under test snapshots ancestor directories
// (for example `/tmp`) and rejects any change to them: parallel tests that create
// temporary directories legitimately change those ancestors.
// Usage: node scripts/run-tests.mjs [--list] [extra node --test flags]
import {globSync, readFileSync} from 'node:fs';
import {availableParallelism} from 'node:os';
import {spawnSync} from 'node:child_process';

const PATTERNS = [
  '**/*.test.{cjs,mjs,js,cts,mts,ts}', '**/*-test.{cjs,mjs,js,cts,mts,ts}', '**/*_test.{cjs,mjs,js,cts,mts,ts}',
  '**/test-*.{cjs,mjs,js,cts,mts,ts}', '**/test.{cjs,mjs,js,cts,mts,ts}', '**/test/**/*.{cjs,mjs,js,cts,mts,ts}'
];
const MARKER = /^\/\/ test:serial\b/m;

export function discover(cwd = process.cwd()) {
  const files = new Set();
  for (const pattern of PATTERNS) {
    for (const file of globSync(pattern, {cwd, exclude: p => /(^|\/)(node_modules|\.git)(\/|$)/.test(p)})) files.add(file);
  }
  const all = [...files].sort();
  const serial = all.filter(f => MARKER.test(readFileSync(f, 'utf8').slice(0, 4096)));
  return {parallel: all.filter(f => !serial.includes(f)), serial};
}

function run(files, concurrency, extra) {
  if (!files.length) return 0;
  const r = spawnSync(process.execPath, ['--test', `--test-concurrency=${concurrency}`, ...extra, ...files], {stdio: 'inherit'});
  return r.status ?? 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const {parallel, serial} = discover();
  if (args.includes('--list')) {
    console.log(JSON.stringify({parallel: parallel.length, serial}, null, 2));
    process.exit(0);
  }
  const concurrency = Number(process.env.TEST_CONCURRENCY) || availableParallelism();
  const a = run(parallel, concurrency, args);
  const b = run(serial, 1, args);
  process.exit(a || b);
}
