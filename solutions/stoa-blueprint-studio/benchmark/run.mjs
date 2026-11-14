/** Source-isolated evaluation; references are authored separately, never from answers. */
import { createHash } from 'node:crypto';
import { open, readFile, realpath } from 'node:fs/promises';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { execFileSync } from 'node:child_process';
import { parseDxf, DXF_LIMITS } from '../src/dxf.mjs';
import { answerDrawing } from '../src/grounding.mjs';
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
export const PREVIEW_SHA = '4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d';
export const BASE = '79d998af372c26cb05907ad9a4aa8e0662caeaf8';
const here = dirname(fileURLToPath(import.meta.url));
const fail = message => { throw new Error(message); };
export async function tempPath(path) {
  const absolute = resolve(path);
  if (await realpath(dirname(absolute)) !== '/private/tmp') fail('Output must be directly under /private/tmp');
  return absolute;
}
export async function immutableJson(path, value) {
  const handle = await open(await tempPath(path), 'wx', 0o600);
  try { await handle.writeFile(JSON.stringify(value, null, 2) + '\n'); } finally { await handle.close(); }
}
export async function boundedRead(path, max) {
  const handle = await open(path, 'r');
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.size > max) fail('Input size/type exceeds limit');
    const bytes = Buffer.alloc(max + 1);
    let n = 0;
    while (n <= max) { const r = await handle.read(bytes, n, max + 1 - n, null); if (!r.bytesRead) break; n += r.bytesRead; }
    if (n > max) fail('Input exceeds limit');
    return bytes.subarray(0, n);
  } finally { await handle.close(); }
}
export function evaluate(bytes, suite, resolver = answerDrawing) {
  if (suite.status === 'NO_REAL_HELDOUT_SOURCE') fail('NO_REAL_HELDOUT_SOURCE: no real evaluation admitted');
  if (!['SYNTHETIC_MECHANICS_ONLY', 'SELF_AUDITED_DRAWING_NOT_SPONSOR_HELDOUT'].includes(suite.evidenceType)) fail('Unsupported evidence type');
  const hash = sha256(bytes);
  if (hash !== suite.source?.sha256 || !/^[a-f0-9]{64}$/.test(hash)) fail('Drawing SHA mismatch');
  if (hash === PREVIEW_SHA || suite.source.filename === 'site1102_bldg2242_floor10281.dxf') fail('Prior preview is excluded');
  if (!suite.source.license || !suite.source.attribution || !suite.source.archivePath) fail('Source/license metadata missing');
  if (suite.evidenceType !== 'SYNTHETIC_MECHANICS_ONLY' && (suite.source.license !== 'CC BY 4.0' || !/^junction-dataset-preview\/data\/swiss_dwellings\/site\d+_bldg\d+_floor\d+\.dxf$/.test(suite.source.archivePath))) fail('Unverified source/license');
  if (suite.evidenceType !== 'SYNTHETIC_MECHANICS_ONLY' && basename(suite.source.archivePath) !== suite.source.filename) fail('Selected source filename mismatch');
  const drawing = parseDxf(bytes.toString('utf8'), suite.source.filename); drawing.sha256 = hash;
  const questions = suite.questions;
  if (!Array.isArray(questions) || !questions.length || questions.length > 1000) fail('Invalid question denominator');
  if (!questions.some(q => q.expected?.status === 'supported') || !questions.some(q => q.expected?.status === 'abstained')) fail('Need supported and unanswerable cases');
  const ids = new Set();
  for (const q of questions) {
    if (!q.id || ids.has(q.id) || typeof q.question !== 'string' || !q.reference?.method || !q.reference?.sourceLocator) fail('Missing/duplicate question provenance');
    ids.add(q.id);
    const ex = q.expected;
    if (!['supported', 'abstained'].includes(ex?.status) || !Array.isArray(ex.regions)) fail('Invalid expected outcome');
    if (ex.status === 'supported' ? typeof ex.answer !== 'string' || !ex.regions.length : ex.answer !== null || ex.regions.length) fail('Missing expected answer/regions');
    const regionIds = new Set();
    for (const region of ex.regions) {
      const original = drawing.entities.find(e => e.id === region.id);
      if (!original || !isDeepStrictEqual(original, region) || regionIds.has(region.id)) fail('Fabricated or mismatched reference region');
      regionIds.add(region.id);
    }
  }
  const rows = questions.map(q => {
    const start = performance.now(); const result = resolver(drawing, q.question); const latencyMs = performance.now() - start;
    const ex = q.expected;
    const cited = Array.isArray(result?.evidence) ? result.evidence : [];
    const expectedIds = new Set(ex.regions.map(e => e.id)); const seen = new Set(); let tp = 0;
    const resolved = cited.map(c => {
      const original = drawing.entities.find(e => e.id === c.entityId);
      const valid = original && c.kind === original.type && c.layer === original.layer && result?.source?.sha256 === hash;
      if (valid && expectedIds.has(c.entityId) && !seen.has(c.entityId)) tp++;
      seen.add(c.entityId);
      return { citation: c, verifiedSourceEntity: valid ? original : null };
    });
    const provenance = result?.source?.sha256 === hash;
    const answerCorrect = provenance && result?.status === ex.status && result?.answer === ex.answer && (ex.status !== 'abstained' || cited.length === 0);
    return { id: q.id, question: q.question, expected: ex, reference: q.reference, result: result ?? null,
      answerCorrect, groundedCorrect: answerCorrect && tp === ex.regions.length && tp === cited.length,
      latencyMs, truePositiveRegions: tp, predictedRegions: cited.length, expectedRegions: ex.regions.length, resolved };
  });
  const total = rows.length, answered = rows.filter(r => r.result?.status === 'supported').length;
  const abstained = rows.filter(r => r.result?.status === 'abstained').length;
  const tp = rows.reduce((s,r) => s+r.truePositiveRegions,0), predicted = rows.reduce((s,r) => s+r.predictedRegions,0), expected = rows.reduce((s,r) => s+r.expectedRegions,0);
  const correct = rows.filter(r => r.answerCorrect).length, grounded = rows.filter(r => r.groundedCorrect).length;
  return { schemaVersion: 1, workId: 'J26-PF-STOA-M335-M3-20261114', evidenceType: suite.evidenceType,
    officialSponsorScore: null, createdAt: new Date().toISOString(), source: suite.source,
    suiteSha256: sha256(Buffer.from(JSON.stringify(suite))), engine: 'unchanged stoa grounding; deterministic; zero external calls',
    rubric: { accuracy: .25, verifiedRegion: .25, creativity: .25, lowInferenceCost: .25, aggregateScore: null },
    baseline: { comparable: false, reason: 'No independently executed comparable baseline; no performance advantage claimed' },
    metrics: { totalQuestions: total, expectedSupported: questions.filter(q=>q.expected.status==='supported').length,
      expectedAbstentions: questions.filter(q=>q.expected.status==='abstained').length, answered, abstained,
      missingResponses: total-answered-abstained, correct, groundedCorrect: grounded, accuracy: correct/total,
      groundedAccuracy: grounded/total, coverage: answered/total, abstentionRate: abstained/total,
      regionTruePositives: tp, predictedRegions: predicted, expectedRegions: expected,
      regionPrecision: predicted ? tp/predicted : null, regionRecall: expected ? tp/expected : null,
      meanResponseLatencyMs: rows.reduce((s,r)=>s+r.latencyMs,0)/total }, rows };
}
export async function run(args) {
  if (args.length !== 6 || args[0] !== '--drawing' || args[2] !== '--suite' || args[4] !== '--output') fail('Usage: --drawing FILE --suite JSON --output /private/tmp/result.json');
  const suiteBytes = await boundedRead(args[3], 1024*1024);
  const suite = JSON.parse(suiteBytes);
  if (suite.status === 'NO_REAL_HELDOUT_SOURCE') fail('NO_REAL_HELDOUT_SOURCE: no real evaluation admitted');
  const drawingPath = resolve(args[1]);
  if (await realpath(dirname(drawingPath)) !== '/private/tmp') fail('Drawing must be directly under /private/tmp');
  const bytes = await boundedRead(drawingPath, DXF_LIMITS.bytes);
  // Source pin catches accidental engine changes without modifying the application.
  const appFiles = ['dxf.mjs','grounding.mjs']; const appHashes = {};
  for (const name of appFiles) {
    const current = await readFile(resolve(here, '../src', name));
    const original = execFileSync('git', ['show', `${BASE}:solutions/stoa-blueprint-studio/src/${name}`], { cwd: here });
    if (sha256(current) !== sha256(original)) fail('Application source differs from pinned base');
    appHashes[name] = sha256(current);
  }
  const report = evaluate(bytes, suite);
  report.app = { baseCommit: BASE, files: appHashes, head: execFileSync('git',['rev-parse','HEAD'],{cwd:here,encoding:'utf8'}).trim(), node: process.version, platform: process.platform };
  report.benchmarkFiles = {};
  for (const name of ['run.mjs','fetch-holdout.mjs']) report.benchmarkFiles[name] = sha256(await readFile(resolve(here, name)));
  report.suiteFileSha256 = sha256(suiteBytes);
  await immutableJson(args[5], report);
  console.log(JSON.stringify({ output: resolve(args[5]), evidenceType: report.evidenceType, sourceSha256: report.source.sha256, metrics: report.metrics }));
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) run(process.argv.slice(2)).catch(e => { console.error(e.message); process.exitCode = 1; });
