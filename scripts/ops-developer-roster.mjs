#!/usr/bin/env node
/**
 * Emit a 34-company / 102-role developer continuity PLAN, not live Cloud tasks.
 *
 * Usage:
 *   node scripts/ops-developer-roster.mjs
 *   node scripts/ops-developer-roster.mjs --requested-concurrency 2
 *
 * Requires a clean local HEAD. The original manifests and package catalog are
 * validated before the plan is emitted. Provider readiness, distributed leases,
 * developer authorization and actual capacity must be checked by a trusted executor.
 */
import {fileURLToPath} from 'node:url';
import {EXPECTED_COMPANIES,loadPackages} from '../lib/catalog.mjs';
import {loadEnvironmentManifests,localSourceCommit,validateRegistry} from '../ops/registry.mjs';
import {buildDeveloperRoster} from '../ops/developer-roster.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));

function parseCli(argv) {
  if (argv.length === 0) return {requestedConcurrency: 0};
  if (argv.length !== 2 || argv[0] !== '--requested-concurrency' ||
    !/^(0|[1-9][0-9]?)$/.test(argv[1])) {
    throw new Error('Usage: node scripts/ops-developer-roster.mjs [--requested-concurrency 0..34]');
  }
  const requestedConcurrency = Number(argv[1]);
  if (requestedConcurrency > 34) throw new Error('Requested concurrency must be 0..34');
  return {requestedConcurrency};
}

try {
  const options = parseCli(process.argv.slice(2));
  const sourceCommit = localSourceCommit(root);
  if (!sourceCommit) throw new Error('Dirty or unverified local HEAD; roster refuses source-ambiguous output');
  const [packs, manifests] = await Promise.all([
    loadPackages(root), loadEnvironmentManifests(root)
  ]);
  validateRegistry(packs, manifests);
  const roster = buildDeveloperRoster(manifests, {
    expectedCompanies: EXPECTED_COMPANIES,
    sourceCommit,
    generatedAt: new Date(),
    requestedConcurrency: options.requestedConcurrency
  });
  console.log(JSON.stringify(roster, null, 2));
} catch (error) {
  console.error('DEVELOPER ROSTER BLOCKED: ' + error.message);
  process.exitCode = 1;
}
