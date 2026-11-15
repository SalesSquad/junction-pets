#!/usr/bin/env node
/**
 * Sheet-context benchmark on official opening_design construction sheets (full dataset):
 * image-only vs image + text lines, N concurrent vision-model calls.
 *   STOA_VLM_KEY=... node bench/sheets.mjs [--mode both|text|image] [--concurrency 10]
 * Counts/areas scored per the sponsor rule; free-text answers with a lenient key-token check.
 */
import { writeFile, mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { CACHE, cached, loadQuestions } from '../raster/dataset.mjs';
import { isCorrect } from '../raster/score.mjs';
import { config } from '../raster/vlm.mjs';
import { askSheet, loadSheet } from '../sheet/sheet-qa.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const modes = (args.mode ?? 'both') === 'both' ? ['text', 'image'] : [args.mode];
// --text pdf (text layer) | ocr (local tiled OCR, text layer ignored) | sc (an external OCR binary
// given in SC_OCR_BIN, e.g. a ScreenshotContext-configured Vision pass; text layer ignored).
const textOpt = args.text ?? 'pdf';
const scOcr = async p => JSON.parse(execFileSync(process.env.SC_OCR_BIN, [p], { encoding: 'utf8', maxBuffer: 1 << 26 }));
const sheetOpts = textOpt === 'pdf' ? {} : textOpt === 'ocr' ? { textSource: 'ocr' } : { textSource: 'ocr', ocrFn: scOcr, label: 'external-ocr' };
const conc = Number(args.concurrency ?? 10);
const cfg = config();
const qs = (await loadQuestions('full')).filter(q => q.path.startsWith('data/opening_design/'));
const sheets = new Map();
for (const p of new Set(qs.map(q => q.path))) sheets.set(p, await loadSheet(await cached(p, 'full'), sheetOpts));

const norm = s => String(s).toLowerCase().replace(/[\s"”″'’′]/g, '').replace(/[–—]/g, '-');
/** Lenient text check: every number/code token of the truth appears in the answer. */
function textOk(truth, answer) {
  if (answer == null) return false;
  const keys = String(truth).match(/\d+(?:[-'"/ ]+\d+)*(?:\s*\d+\/\d+)?|[A-Z]{1,3}-?\d+(?:\/[A-Z]+-?\d+)?/g) ?? [norm(truth)];
  const a = norm(answer);
  return keys.every(k => a.includes(norm(k)));
}

const jobs = qs.flatMap(q => modes.map(mode => ({ q, mode })));
const out = []; let next = 0; const t0 = Date.now();
await Promise.all(Array.from({ length: conc }, async () => {
  while (next < jobs.length) {
    const { q, mode } = jobs[next++];
    const r = await askSheet(sheets.get(q.path), q.question, cfg, { withText: mode === 'text' });
    const correct = q.type === 'text' ? textOk(q.answer, r.answer) : isCorrect(q, r.answer);
    out.push({ mode, path: q.path, type: q.type, question: q.question, truth: q.answer, answer: r.answer, correct, evidence: r.evidence, call: r.call });
    process.stderr.write(correct ? '+' : '.');
  }
}));
process.stderr.write('\n');
const summary = {};
for (const mode of modes) {
  const rs = out.filter(r => r.mode === mode);
  const by = t => rs.filter(r => r.type === t);
  summary[mode] = { n: rs.length, correct: rs.filter(r => r.correct).length, accuracy: +(rs.filter(r => r.correct).length / rs.length).toFixed(3),
    byType: Object.fromEntries(['count', 'area', 'text'].map(t => [t, `${by(t).filter(r => r.correct).length}/${by(t).length}`])),
    withEvidence: rs.filter(r => r.evidence?.length).length, failedCalls: rs.filter(r => !r.call.ok).length,
    tokensPerQuestion: Math.round(rs.reduce((s, r) => s + (r.call.usage?.prompt ?? 0) + (r.call.usage?.completion ?? 0), 0) / rs.length) };
}
const report = { textSource: textOpt, sheets: [...sheets.values()].map(s => ({ path: s.path.split('/').pop(), lines: s.lines.length, source: s.source })), concurrency: conc, wallSeconds: Math.round((Date.now() - t0) / 1000), summary };
await mkdir(join(CACHE, 'reports'), { recursive: true });
const file = join(CACHE, 'reports', `sheets-${new Date().toISOString().replace(/[:.]/g, '')}.json`);
await writeFile(file, JSON.stringify({ report, rows: out }, null, 1));
console.log(JSON.stringify({ ...report, reportFile: file }, null, 1));
