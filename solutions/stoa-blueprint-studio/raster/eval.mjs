#!/usr/bin/env node
/**
 * Evaluate a raster strategy on official Stoa preview questions.
 *   STOA_VLM_KEY=... node raster/eval.mjs --strategy per-drawing --split test [--source cubicasa5k] [--lang en] [--limit 16] [--concurrency 4]
 * Writes a private JSON report to the cache directory (never to git) and prints a summary.
 */
import { execFileSync } from 'node:child_process';
import { stat, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { CACHE, cached, loadQuestions, isEnglish, split } from './dataset.mjs';
import { STRATEGIES } from './strategies.mjs';
import { config, imageDataUrl } from './vlm.mjs';
import { isCorrect, summarize } from './score.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const strategyName = args.strategy ?? 'per-drawing';
const strategy = STRATEGIES[strategyName];
if (!strategy) throw new Error(`Unknown strategy ${strategyName}`);
const source = args.source ?? 'cubicasa5k', which = args.split ?? 'dev', lang = args.lang ?? 'en';
const concurrency = Number(args.concurrency ?? 4);
const cfg = config();

const all = (await loadQuestions()).filter(q => q.path.startsWith(`data/${source}/`) && (lang === 'all' || isEnglish(q)));
const files = split(all.map(q => q.path), { dev: Number(args.dev ?? 8), test: Number(args.test ?? 16) })[which]
  .slice(0, Number(args.limit ?? 1e9));
const template = q => q.question.replace(/\d+(?:[.,]\d+)?/g, '#').replace(/«[^»]*»|"[^"]*"|„[^“]*“/g, '<L>').slice(0, 90);

async function prepare(path) {
  const original = await cached(path);
  let p = original;
  if ((await stat(p)).size > 3_000_000 && process.platform === 'darwin') {
    const small = p.replace(/\.\w+$/, '.2400.jpg');
    try { await stat(small); } catch { execFileSync('sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '85', '-Z', '2400', p, '--out', small], { stdio: 'ignore' }); }
    p = small;
  }
  // Optional upscaling of small plans so the vision encoder spends more tiles on dense symbols.
  const target = Number(args.upscale ?? 0);
  if (target && process.platform === 'darwin') {
    const img = await imageDataUrl(p);
    if (img.width && Math.max(img.width, img.height) < target) {
      const up = p.replace(/\.\w+$/, `.up${target}.png`);
      try { await stat(up); } catch { execFileSync('sips', ['-Z', String(target), p, '--out', up], { stdio: 'ignore' }); }
      const scaled = await imageDataUrl(up);
      return { ...scaled, path: original };
    }
  }
  return { ...(await imageDataUrl(p)), path: original };
}

const rows = []; const t0 = Date.now(); const queue = [...files];
await Promise.all(Array.from({ length: concurrency }, async () => {
  while (queue.length) {
    const path = queue.shift();
    const qs = all.filter(q => q.path === path);
    try {
      const drawing = await prepare(path);
      for (const r of await strategy(drawing, qs, cfg)) {
        rows.push({ path, question: r.q.question, template: template(r.q), type: r.q.type, truth: r.q.answer,
          predicted: r.predicted, stated: r.stated, correct: isCorrect(r.q, r.predicted),
          statedCorrect: r.stated === undefined ? undefined : isCorrect(r.q, r.stated),
          method: r.method, instances: r.instances, evidence: r.evidence, call: r.call });
      }
    } catch (e) {
      for (const q of qs) rows.push({ path, question: q.question, template: template(q), type: q.type, truth: q.answer, predicted: null, correct: false, error: String(e.message).slice(0, 200) });
    }
    process.stderr.write(`.`);
  }
}));
process.stderr.write('\n');

const calls = rows.map(r => r.call).filter(c => c && !c.shared);
const tokens = calls.reduce((a, c) => ({ prompt: a.prompt + (c.usage?.prompt ?? 0), completion: a.completion + (c.usage?.completion ?? 0) }), { prompt: 0, completion: 0 });
const report = {
  strategy: strategyName, model: cfg.model, source, split: which, lang, drawings: files.length,
  ...summarize(rows),
  statedAccuracy: rows.some(r => r.statedCorrect !== undefined) ? +(rows.filter(r => r.statedCorrect).length / rows.length).toFixed(3) : undefined,
  calls: calls.length, failedCalls: calls.filter(c => !c.ok).length, errors: rows.filter(r => r.error).length,
  // Share of positive answers whose markers/evidence regions match the stated count one-to-one.
  groundedShare: (() => {
    const pos = rows.filter(r => typeof r.predicted === 'number' && r.predicted > 0);
    const ok = pos.filter(r => (r.instances?.length ?? r.evidence?.length ?? -1) === r.predicted);
    return pos.length ? +(ok.length / pos.length).toFixed(3) : null;
  })(),
  tokens, tokensPerQuestion: rows.length ? Math.round((tokens.prompt + tokens.completion) / rows.length) : 0,
  wallSeconds: Math.round((Date.now() - t0) / 1000),
};
await mkdir(join(CACHE, 'reports'), { recursive: true });
const out = join(CACHE, 'reports', `${source}-${which}-${strategyName}-${new Date().toISOString().replace(/[:.]/g, '')}.json`);
await writeFile(out, JSON.stringify({ report, rows }, null, 1));
console.log(JSON.stringify({ ...report, reportFile: out }, null, 1));
