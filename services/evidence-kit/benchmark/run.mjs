import {readFile, readdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {performance} from 'node:perf_hooks';
import {sha256, hashJson} from '../src/index.mjs';
import {dxfAdapter} from '../adapters/dxf.mjs';
import {csvAdapter} from '../adapters/csv.mjs';
import {measureRoom} from '../methods/drawing.mjs';
import {sumCells} from '../methods/table.mjs';
export async function benchmark() {
  const raw = await readFile(new URL('../fixtures/suite.json', import.meta.url)), suite = JSON.parse(raw);
  if (suite.schema !== 'evidence-kit.synthetic-suite/v1') throw new Error('Unsupported frozen suite.');
  const rows = [];
  for (const c of suite.cases) {
    const bytes = await readFile(new URL('../fixtures/' + c.file, import.meta.url));
    if (await sha256(bytes) !== suite.files[c.file]) throw new Error('Frozen fixture hash mismatch: ' + c.file);
    const start = performance.now();
    const adapter = c.adapter === 'dxf' ? dxfAdapter : csvAdapter;
    const dataset = await adapter.ingest(bytes, {filename: c.file, rights: {kind: 'synthetic', attribution: 'Evidence Kit CC0 fixtures'}});
    const ingested = performance.now();
    const claim = await (c.adapter === 'dxf' ? measureRoom : sumCells)(dataset, c.query);
    const ids = claim.refs.map(r => r.id).sort(), expectedIds = [...c.expected.ids].sort();
    const correct = claim.status === c.expected.status && claim.value === c.expected.value && JSON.stringify(ids) === JSON.stringify(expectedIds);
    rows.push({id: c.id, format: c.adapter, correct, status: claim.status, level: claim.level, value: claim.value,
      reason: claim.reason, sourceSha256: dataset.manifest().source.sha256, generation: dataset.manifest().generation,
      claimSha256: claim.claimSha256, ingestMs: ingested - start, methodMs: performance.now() - ingested, expected: c.expected});
  }
  const runtime = {};
  for (const directory of ['src', 'adapters', 'methods']) for (const name of (await readdir(new URL('../' + directory + '/', import.meta.url))).filter(n => n.endsWith('.mjs')).sort()) {
    runtime[directory + '/' + name] = await sha256(await readFile(new URL('../' + directory + '/' + name, import.meta.url)));
  }
  const answered = rows.filter(r => r.status === 'supported');
  return {schema: 'evidence-kit.benchmark/v1', corpus: 'authored-synthetic-mechanics-only', suiteSha256: await sha256(raw), evaluatorSha256: await sha256(await readFile(fileURLToPath(import.meta.url))), runtimeSha256: await hashJson(runtime), runtime,
    node: process.version, cases: rows.length, correctContracts: rows.filter(r => r.correct).length,
    supported: answered.length, abstained: rows.length - answered.length,
    coverage: answered.length / rows.length, exactWhenSupported: answered.length ? answered.filter(r => r.correct).length / answered.length : null,
    externalRequests: 0, modelCost: 0, baseline: 'no-comparable-baseline', realDataQualified: false, rows};
}
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const result = await benchmark();
  if (process.argv.includes('--check')) {
    const saved = JSON.parse(await readFile(new URL('./baseline.json', import.meta.url), 'utf8'));
    for (const key of ['suiteSha256','runtimeSha256','evaluatorSha256','cases','correctContracts','supported','abstained']) if (saved[key] !== result[key]) throw new Error('Frozen baseline differs at ' + key + '; qualify a new version explicitly.');
  }
  console.log(JSON.stringify(result, null, 2));
  if (result.correctContracts !== result.cases) process.exitCode = 1;
}
