#!/usr/bin/env node
// Collects every challenger case that failed consensus in any stored run into a
// permanent regression suite (regression/aiven-regression.json). Case definitions
// come from the committed case files (calibrated version preferred); the suite keeps
// the failure count and which runs failed, so a later fix can be checked against it.
//   node collect-regressions.mjs [dist/evals/challenge-*.json ...]
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
const here = new URL('.', import.meta.url).pathname;
const caseFiles = [...readdirSync(here).filter(f => /^cases-.*\.json$/.test(f)), ...['round2', 'round3'].flatMap(d => existsSync(join(here, d)) ? readdirSync(join(here, d)).filter(f => /^cases-.*\.json$/.test(f)).map(f => join(d, f)) : [])];
const defs = {};
for (const f of caseFiles.sort((a, b) => a.includes('.cal.') - b.includes('.cal.'))) for (const c of JSON.parse(readFileSync(join(here, f), 'utf8')).cases) defs[c.id] = { ...c, sourceFile: f };
const runs = process.argv.slice(2).length ? process.argv.slice(2) : readdirSync(join(here, '../../dist/evals')).filter(f => f.startsWith('challenge-')).map(f => join(here, '../../dist/evals', f));
const fails = {};
for (const run of runs) {
  const d = JSON.parse(readFileSync(run, 'utf8'));
  for (const r of d.results ?? []) {
    if (r.error || !r.judges || !defs[r.case]) continue;
    const ok = Object.values(r.judges).every(j => j && j.pass) && Object.values(r.det ?? {}).every(Boolean);
    if (ok) continue;
    const f = fails[r.case] ??= { failures: 0, arms: new Set(), runs: new Set() };
    f.failures++; f.arms.add(`${r.model}/${r.arm}`); f.runs.add(run.split('/').pop());
  }
}
// Realistic-looking fake credentials are replaced consistently with obviously fake ones.
const defang = c => JSON.parse(JSON.stringify(c).replace(/AVNS_[A-Za-z0-9_-]{6,}/g, 'EXAMPLE-not-a-real-aiven-token'));
const cases = Object.entries(fails).sort((a, b) => b[1].failures - a[1].failures).map(([id, f]) => ({ ...defang(defs[id]), regression: { failures: f.failures, arms: [...f.arms].sort(), runs: [...f.runs].sort() } }));
writeFileSync(join(here, 'regression/aiven-regression.json'), JSON.stringify({ schemaVersion: 1, author: 'collected from stored challenger runs (cases written by challenger companions)', collectedAt: new Date().toISOString(), cases }, null, 2) + '\n');
console.log(JSON.stringify({ runs: runs.length, regressionCases: cases.length, top: cases.slice(0, 5).map(c => [c.id, c.regression.failures]) }));
