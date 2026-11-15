#!/usr/bin/env node
/**
 * Deterministic IFC route on official ifc_models preview questions (IFC paths and the floor-plan
 * PDFs rendered from those models). No model calls; models stay in the private cache.
 *   node bench/ifc.mjs [--model esplanades|molio|clinic|all] [--show-misses 20]
 */
import { access } from 'node:fs/promises';
import { cached, loadQuestions } from '../raster/dataset.mjs';
import { isCorrect, summarize } from '../raster/score.mjs';
import { readIfc } from '../src/ifc.mjs';
import { answerIfc, ifcSiblingOf } from '../src/ifc-qa.mjs';
import { PREFIX, openPreview } from '../raster/preview-zip.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const which = args.model ?? 'all';
const qs = (await loadQuestions()).filter(q => q.path.startsWith('data/ifc_models/') && (which === 'all' || q.path.includes(which)));
const zip = await openPreview();
const rows = [];
for (const model of [...new Set(qs.map(q => ifcSiblingOf(q.path)))]) {
  const mine = qs.filter(q => ifcSiblingOf(q.path) === model);
  if (!zip.entries.has(PREFIX + model)) { for (const q of mine) rows.push({ q, template: tmpl(q), status: 'no-model', correct: false }); continue; }
  const m = await readIfc(await cached(model));
  for (const q of mine) {
    const r = answerIfc(m, q.question) ?? { status: 'abstained', answer: null, explanation: 'unsupported' };
    rows.push({ q, template: tmpl(q), status: r.status, predicted: r.answer, why: r.explanation, correct: r.status === 'supported' && isCorrect(q, r.answer) });
  }
}
function tmpl(q) { return `${q.path.endsWith('.ifc') ? 'ifc' : 'pdf'}: ${q.question.replace(/'[^']*'|„[^“]*“/g, '<L>').replace(/\d+(\.\d+)?/g, '#').slice(0, 70)}`; }
const s = summarize(rows);
console.log(JSON.stringify({ model: which, n: s.n, correct: s.correct, accuracy: s.accuracy,
  answered: rows.filter(r => r.status === 'supported').length, noModel: rows.filter(r => r.status === 'no-model').length,
  perTemplate: s.perTemplate }, null, 1));
for (const r of rows.filter(r => !r.correct).slice(0, Number(args['show-misses'] ?? 0))) console.log(`- [${r.status}] ${r.q.question} | truth ${r.q.answer} | got ${r.predicted ?? '-'} | ${String(r.why ?? '').slice(0, 80)}`);
