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
import { ARCHIVES, openPreview } from '../raster/preview-zip.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const which = args.model ?? 'all';
const source = args.archive ?? 'preview';            // 'full' = the 10 GB dataset
// Models the rules were developed on; --exclude-seen yes gives a held-out run.
const SEEN = ['bsc-esplanades_1807-ep-ar-v18', 'bsc-molio_molio-with-uris', 'bsc-clinic_clinic-plumbing'];
const qs = (await loadQuestions(source)).filter(q => q.path.startsWith('data/ifc_models/') && (which === 'all' || q.path.includes(which))
  && !(args['exclude-seen'] && SEEN.some(s => ifcSiblingOf(q.path).includes(s))));
// --half dev|test splits the unseen models deterministically (salted SHA-256 of the model path).
import('node:crypto');
const { createHash } = await import('node:crypto');
const half = m => (parseInt(createHash('sha256').update(`stoa-ifc-split-v1|${m}`).digest('hex').slice(0, 8), 16) % 2 ? 'test' : 'dev');
if (args.half) for (let i = qs.length - 1; i >= 0; i--) if (half(ifcSiblingOf(qs[i].path)) !== args.half) qs.splice(i, 1);
const zip = await openPreview(ARCHIVES[source].url, ARCHIVES[source].prefix);
const models = [...new Set(qs.map(q => ifcSiblingOf(q.path)))].filter(m => zip.has(m));
// Prefetch models with bounded parallelism (byte ranges, CRC-checked, private cache).
for (let i = 0; i < models.length; i += 6) await Promise.all(models.slice(i, i + 6).map(m => cached(m, source)));
const rows = [];
for (const model of [...new Set(qs.map(q => ifcSiblingOf(q.path)))]) {
  const mine = qs.filter(q => ifcSiblingOf(q.path) === model);
  if (!zip.has(model)) { for (const q of mine) rows.push({ q, template: tmpl(q), status: 'no-model', correct: false }); continue; }
  const m = await readIfc(await cached(model, source));
  for (const q of mine) {
    const r = answerIfc(m, q.question) ?? { status: 'abstained', answer: null, explanation: 'unsupported' };
    rows.push({ q, template: tmpl(q), status: r.status, predicted: r.answer, why: r.explanation, correct: r.status === 'supported' && isCorrect(q, r.answer) });
  }
}
function tmpl(q) { return `${q.path.endsWith('.ifc') ? 'ifc' : 'pdf'}: ${q.question.replace(/'[^']*'|„[^“]*“/g, '<L>').replace(/\d+(\.\d+)?/g, '#').slice(0, 70)}`; }
const s = summarize(rows);
console.log(JSON.stringify({ archive: source, heldOut: Boolean(args['exclude-seen']), half: args.half ?? 'all', models: models.length, model: which, n: s.n, correct: s.correct, accuracy: s.accuracy,
  answered: rows.filter(r => r.status === 'supported').length, noModel: rows.filter(r => r.status === 'no-model').length,
  perTemplate: s.perTemplate }, null, 1));
for (const r of rows.filter(r => !r.correct).slice(0, Number(args['show-misses'] ?? 0))) console.log(`- [${r.status}] ${r.q.question} | truth ${r.q.answer} | got ${r.predicted ?? '-'} | ${String(r.why ?? '').slice(0, 80)}`);
