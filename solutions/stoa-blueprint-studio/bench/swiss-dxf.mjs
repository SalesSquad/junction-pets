#!/usr/bin/env node
/**
 * Deterministic DXF route on official Swiss Dwellings preview questions.
 * Questions name the PDF; the preview ships the same drawing as DXF (same stem).
 *   node bench/swiss-dxf.mjs --split dev|test|all [--dev 30 --test 35] [--lang en|all] [--show-misses 20]
 * No model calls. Drawings stay in the private cache, never in git.
 */
import { readFile } from 'node:fs/promises';
import { cached, loadQuestions, isEnglish, split } from '../raster/dataset.mjs';
import { isCorrect, summarize } from '../raster/score.mjs';
import { parseDxf } from '../src/dxf.mjs';
import { answerDrawing } from '../src/grounding.mjs';
import { answerDrawingV2 } from '../src/quantities.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const which = args.split ?? 'dev', lang = args.lang ?? 'all';
const all = (await loadQuestions()).filter(q => q.path.startsWith('data/swiss_dwellings/') && (lang === 'all' || isEnglish(q)));
const parts = split(all.map(q => q.path), { dev: Number(args.dev ?? 30), test: Number(args.test ?? 35) });
const files = which === 'all' ? [...parts.dev, ...parts.test] : parts[which];
const template = q => q.question.replace(/\d+(?:[.,]\d+)?/g, '#').replace(/«[^»]*»|"[^"]*"|„[^“]*“|‘[^’]*’/g, '<L>').slice(0, 80);

const rows = [];
for (const path of files) {
  const dxfPath = path.replace(/\.pdf$/i, '.dxf');
  let drawing;
  try { drawing = parseDxf(await readFile(await cached(dxfPath), 'utf8'), dxfPath.split('/').pop()); }
  catch (e) { for (const q of all.filter(x => x.path === path)) rows.push({ path, q, template: template(q), status: 'error', error: e.message, correct: false }); continue; }
  for (const q of all.filter(x => x.path === path)) {
    const r = (args.engine === 'v1' ? answerDrawing : answerDrawingV2)(drawing, q.question);
    rows.push({ path, q, template: template(q), status: r.status, predicted: r.answer, correct: r.status === 'supported' && isCorrect(q, r.answer), evidence: r.evidence?.length ?? 0, why: r.explanation });
  }
}
const s = summarize(rows);
const answered = rows.filter(r => r.status === 'supported');
console.log(JSON.stringify({
  split: which, drawings: files.length, n: s.n, correct: s.correct, accuracy: s.accuracy,
  answered: answered.length, precisionWhenAnswered: answered.length ? +(answered.filter(r => r.correct).length / answered.length).toFixed(3) : null,
  abstained: rows.filter(r => r.status === 'abstained').length, errors: rows.filter(r => r.status === 'error').length,
  perTemplate: Object.fromEntries(Object.entries(s.perTemplate).slice(0, 30)),
}, null, 1));
const k = Number(args['show-misses'] ?? 0);
if (k) for (const r of rows.filter(r => !r.correct).slice(0, k)) console.log(`- [${r.status}] ${r.q.question} | truth ${r.q.answer} | got ${r.predicted ?? '-'} | ${String(r.why ?? r.error).slice(0, 90)}`);
