#!/usr/bin/env node
// Model tournament for the junction.aiven companion.
//   --suites=dev,heldout   dev = roster + stack cases (used for tuning); heldout = unseen cases
//   --models=haiku,sonnet,opus  --repeats=2  --judge=sonnet  --concurrency=4  --execute
// Uses the authorized local Claude CLI with no tools, no MCP and a per-call budget cap.
// Scores: pass (every mustInclude, no mustNotClaim, deterministic checks ok), a graded
// score (include share minus 0.5 per violation, floored at 0) and repeat consistency.
// Response text is kept only under ignored dist/; the repo keeps scores and hashes.
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadPackages } from '../../lib/catalog.mjs';
import { companyContext } from '../../lib/company-context.mjs';

const arg = (k, d) => process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d;
const root = fileURLToPath(new URL('../../', import.meta.url));
const models = arg('models', 'haiku,sonnet,opus').split(',');
const suites = arg('suites', 'dev,heldout').split(',');
const repeats = Number(arg('repeats', '2'));
const judgeModel = arg('judge', 'sonnet');
const arms = arg('arms', 'pet').split(',');
const concurrency = Number(arg('concurrency', '4'));
const execute = process.argv.includes('--execute');
const sha = s => createHash('sha256').update(s).digest('hex');
const read = p => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));

const pack = (await loadPackages(root)).find(p => p.pet.id === 'junction.aiven');
const system = companyContext(pack);
const systems = { pet: system, compact: readFileSync(new URL('../../pets/aiven/AGENTS.compact.md', import.meta.url), 'utf8'), bare: 'You are a helpful assistant.' };
const cases = [];
if (suites.includes('dev')) {
  cases.push(...pack.evals.cases.map(c => ({ ...c, suite: 'roster' })));
  cases.push(...read('../../pets/aiven/evals-stack.json').cases.map(c => ({ ...c, suite: 'stack' })));
}
if (suites.includes('heldout')) cases.push(...read('../../pets/aiven/evals-heldout.json').cases.map(c => ({ ...c, suite: 'heldout' })));

function claude(model, prompt, systemPrompt) {
  const args = ['-p', prompt, '--model', model, '--max-budget-usd', '0.60', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence'];
  if (systemPrompt) args.push('--system-prompt', systemPrompt);
  return new Promise(resolve => {
    const p = spawn('claude', args, { cwd: '/tmp', stdio: ['ignore', 'pipe', 'ignore'] });
    let out = ''; const t = setTimeout(() => p.kill('SIGTERM'), 300000);
    p.stdout.on('data', d => { out += d; });
    p.on('close', code => {
      clearTimeout(t);
      if (code !== 0) return resolve({ error: `exit ${code}` });
      try { const d = JSON.parse(out); resolve(d.is_error ? { error: 'cli reported error' } : { text: d.result ?? '', cost: d.total_cost_usd ?? 0, served: d.modelUsage ? Object.keys(d.modelUsage).join('+') : model }); }
      catch { resolve({ error: 'unparseable cli output' }); }
    });
  });
}

const judgePrompt = (c, answer) => `You grade one assistant answer against a rubric. Be strict and literal.
Rubric "mustInclude" (each must be substantively present):
${c.mustInclude.map((s, i) => `I${i + 1}. ${s}`).join('\n')}
Rubric "mustNotClaim" (each must NOT be asserted as true; mentioning it only to deny or warn is fine):
${c.mustNotClaim.map((s, i) => `N${i + 1}. ${s}`).join('\n')}
User prompt:
<<<${c.prompt}>>>
Answer to grade:
<<<${answer}>>>
Return only JSON: {"include":[true|false per I item],"violations":[true|false per N item],"note":"<=25 words"}`;

// Checks are written as regex strings; a leading "(?i)" means case-insensitive.
const rx = r => r.startsWith('(?i)') ? new RegExp(r.slice(4), 'i') : new RegExp(r);
function deterministic(c, text) {
  const ch = c.checks ?? { mustMatch: [], mustNotMatch: [] };
  const missing = ch.mustMatch.filter(r => !rx(r).test(text));
  const forbidden = ch.mustNotMatch.filter(r => rx(r).test(text));
  return { ok: !missing.length && !forbidden.length, missing: missing.length, forbidden: forbidden.length };
}

async function one(job) {
  const { model, c, rep, arm } = job;
  const a = await claude(model, c.prompt, systems[arm]);
  if (a.error) return { model, arm, case: c.id, suite: c.suite, rep, error: a.error };
  let j, g = null;
  for (let attempt = 0; attempt < 2 && !g; attempt++) { // a judge formatting slip is a measurement error, not a model failure
    j = await claude(judgeModel, judgePrompt(c, a.text));
    try { g = JSON.parse((j.text ?? '').replace(/^```json\s*|```\s*$/g, '').trim()); } catch {}
  }
  if (!g) return { model, arm, case: c.id, suite: c.suite, rep, error: 'judge output unparseable' };
  const det = deterministic(c, a.text);
  const inc = g?.include?.filter(Boolean).length ?? 0, viol = (g?.violations?.filter(Boolean).length ?? 0) + det.forbidden;
  const score = g ? Math.max(0, (inc - det.missing) / c.mustInclude.length - 0.5 * viol) : 0;
  const pass = !!g && inc === c.mustInclude.length && viol === 0 && det.ok;
  return { model, arm, served: a.served, case: c.id, suite: c.suite, rep, pass, score: +score.toFixed(3), includeHits: inc, includeTotal: c.mustInclude.length, violations: viol, deterministic: det, answerSha256: sha(a.text), answerChars: a.text.length, costUsd: +(a.cost + (j.cost ?? 0)).toFixed(4), judgeNote: g?.note ?? 'judge output unparseable', _raw: { answer: a.text, judge: j.text } };
}

for (const c of cases) for (const r of [...(c.checks?.mustMatch ?? []), ...(c.checks?.mustNotMatch ?? [])]) rx(r); // fail fast on a bad pattern
const jobs = models.flatMap(model => arms.flatMap(arm => cases.flatMap(c => Array.from({ length: repeats }, (_, rep) => ({ model, arm, c, rep })))));
if (!execute) { console.log(JSON.stringify({ dryRun: true, cases: cases.length, models, arms, repeats, judgeModel, calls: jobs.length * 2, systemChars: [...system].length }, null, 2)); process.exit(0); }

const started = new Date().toISOString(), results = [];
let next = 0;
await Promise.all(Array.from({ length: concurrency }, async () => {
  while (next < jobs.length) { const r = await one(jobs[next++]); results.push(r); console.error(`${r.model}/${r.arm} ${r.case}#${r.rep} ${r.error ?? (r.pass ? 'PASS' : 'FAIL ' + r.score)}`); }
}));
const summary = {};
for (const m of models) for (const arm of arms) for (const s of ['roster', 'stack', 'heldout']) {
  const r = results.filter(x => x.model === m && x.arm === arm && x.suite === s && !x.error);
  if (!r.length) continue;
  const byCase = Object.values(Object.groupBy(r, x => x.case));
  summary[`${m}/${arm}/${s}`] = {
    runs: r.length, passRate: +(r.filter(x => x.pass).length / r.length).toFixed(3),
    meanScore: +(r.reduce((a, x) => a + x.score, 0) / r.length).toFixed(3),
    consistency: +(byCase.filter(g => g.every(x => x.pass === g[0].pass)).length / byCase.length).toFixed(3),
    costUsd: +r.reduce((a, x) => a + x.costUsd, 0).toFixed(3),
    errors: results.filter(x => x.model === m && x.arm === arm && x.suite === s && x.error).length
  };
}
const out = { petId: pack.pet.id, petVersion: pack.pet.version, systemSha256: sha(system), judgeModel, repeats, startedAt: started, finishedAt: new Date().toISOString(), summary, results: results.map(({ _raw, ...r }) => r) };
mkdirSync(new URL('../../dist/evals/', import.meta.url), { recursive: true });
writeFileSync(new URL(`../../dist/evals/aiven-tournament-${Date.now()}.json`, import.meta.url), JSON.stringify({ ...out, raw: results.map(r => ({ model: r.model, arm: r.arm, case: r.case, rep: r.rep, ...(r._raw ?? {}) })) }, null, 2));
console.log(JSON.stringify(out, null, 2));
