#!/usr/bin/env node
// Objective tournament: code-scored Aiven tasks, randomised per seed, each model run
// twice: with the junction.aiven companion guidance ("pet") and without it ("bare").
//   --models=haiku,sonnet,opus --arms=pet,compact,bare --tier=basic|hard|all --seeds=3 --concurrency=6 --execute
// Arms: pet = full AGENTS.md company context; compact = pets/aiven/AGENTS.compact.md; bare = generic assistant.
// The same seeds are used for every model and arm, so arms differ only by guidance.
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadPackages } from '../../lib/catalog.mjs';
import { companyContext } from '../../lib/company-context.mjs';
import { TASKS, HARD_TASKS, rng, lastJson } from './tasks.mjs';

const arg = (k, d) => process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d;
const tier = arg('tier', 'all'), arms = arg('arms', 'pet,compact,bare').split(',');
const TASKSET = { ...(tier !== 'hard' ? TASKS : {}), ...(tier !== 'basic' ? HARD_TASKS : {}) };
const models = arg('models', 'haiku,sonnet,opus').split(','), seeds = Number(arg('seeds', '3')), concurrency = Number(arg('concurrency', '6'));
const sha = s => createHash('sha256').update(s).digest('hex');
const root = fileURLToPath(new URL('../../', import.meta.url));
const pack = (await loadPackages(root)).find(p => p.pet.id === 'junction.aiven');
const petSystem = companyContext(pack);
const bareSystem = 'You are a helpful assistant.';
const compactSystem = readFileSync(new URL('../../pets/aiven/AGENTS.compact.md', import.meta.url), 'utf8');
const systems = { pet: petSystem, compact: compactSystem, bare: bareSystem };

function claude(model, prompt, system) {
  const args = ['-p', prompt, '--model', model, '--max-budget-usd', '0.60', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence', '--system-prompt', system];
  return new Promise(res => {
    const p = spawn('claude', args, { cwd: '/tmp', stdio: ['ignore', 'pipe', 'ignore'] });
    let out = ''; const t = setTimeout(() => p.kill('SIGTERM'), 300000);
    p.stdout.on('data', d => { out += d; });
    p.on('close', code => { clearTimeout(t); if (code !== 0) return res({ error: `exit ${code}` });
      try { const d = JSON.parse(out); res(d.is_error ? { error: 'cli error' } : { text: d.result ?? '', cost: d.total_cost_usd ?? 0 }); } catch { res({ error: 'unparseable cli output' }); } });
  });
}

const jobs = [];
for (const model of models) for (const arm of arms) for (const [task, gen] of Object.entries(TASKSET)) for (let s = 1; s <= seeds; s++) jobs.push({ model, arm, task, seed: 1000 + s, gen });
if (!process.argv.includes('--execute')) { console.log(JSON.stringify({ dryRun: true, tier, arms, tasks: Object.keys(TASKSET), compactChars: [...compactSystem].length, models, seeds, calls: jobs.length, petSystemChars: [...petSystem].length }, null, 2)); process.exit(0); }

const results = []; let next = 0; const started = new Date().toISOString();
await Promise.all(Array.from({ length: concurrency }, async () => {
  while (next < jobs.length) {
    const j = jobs[next++]; const t = j.gen(rng(j.seed));
    const a = await claude(j.model, t.prompt, systems[j.arm]);
    let r;
    if (a.error) r = { error: a.error };
    else { const parsed = lastJson(a.text); r = { parsed: !!parsed, score: parsed ? +Math.min(1, Math.max(0, t.score(parsed, a.text))).toFixed(3) : 0, costUsd: +a.cost.toFixed(4), answerSha256: sha(a.text) }; }
    results.push({ model: j.model, arm: j.arm, task: j.task, seed: j.seed, ...r });
    console.error(`${j.model}/${j.arm} ${j.task}#${j.seed} ${r.error ?? r.score}`);
  }
}));
const ok = results.filter(r => !r.error);
const agg = xs => ({ n: xs.length, meanScore: +(xs.reduce((a, x) => a + x.score, 0) / (xs.length || 1)).toFixed(3), perfect: +(xs.filter(x => x.score === 1).length / (xs.length || 1)).toFixed(3), costUsd: +xs.reduce((a, x) => a + x.costUsd, 0).toFixed(3) });
const summary = {}, byTask = {};
for (const m of models) for (const arm of arms) {
  summary[`${m}/${arm}`] = agg(ok.filter(r => r.model === m && r.arm === arm));
  for (const task of Object.keys(TASKSET)) byTask[`${task} ${m}/${arm}`] = agg(ok.filter(r => r.model === m && r.arm === arm && r.task === task)).meanScore;
}
const out = { petId: pack.pet.id, petVersion: pack.pet.version, petSystemSha256: sha(petSystem), compactSystemSha256: sha(compactSystem), tier, arms, seeds, startedAt: started, finishedAt: new Date().toISOString(), errors: results.length - ok.length, summary, byTask, results };
mkdirSync(new URL('../../dist/evals/', import.meta.url), { recursive: true });
writeFileSync(new URL(`../../dist/evals/aiven-objective-${Date.now()}.json`, import.meta.url), JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 2));
