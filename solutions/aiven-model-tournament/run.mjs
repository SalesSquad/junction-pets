#!/usr/bin/env node
// Model tournament for the junction.aiven companion: the same authored cases on
// several models, judged against mustInclude / mustNotClaim. Uses the already
// authorized local Claude CLI with no tools, no MCP and a per-call budget cap.
// Response text is kept only under ignored dist/; the repo keeps scores and hashes.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadPackages } from '../../lib/catalog.mjs';
import { companyContext } from '../../lib/company-context.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const models = (process.argv.find(a => a.startsWith('--models='))?.slice(9) ?? 'haiku,sonnet').split(',');
const judgeModel = process.argv.find(a => a.startsWith('--judge='))?.slice(8) ?? 'sonnet';
const execute = process.argv.includes('--execute');
const sha = s => createHash('sha256').update(s).digest('hex');

const pack = (await loadPackages(root)).find(p => p.pet.id === 'junction.aiven');
const system = companyContext(pack);
const stack = JSON.parse(readFileSync(new URL('../../pets/aiven/evals-stack.json', import.meta.url), 'utf8'));
const cases = [...pack.evals.cases.map(c => ({ ...c, suite: 'roster' })), ...stack.cases.map(c => ({ ...c, suite: 'stack' }))];

function claude(model, prompt, systemPrompt) {
  const args = ['-p', prompt, '--model', model, '--max-budget-usd', '0.40', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence'];
  if (systemPrompt) args.push('--system-prompt', systemPrompt);
  const r = spawnSync('claude', args, { encoding: 'utf8', timeout: 240000, cwd: '/tmp', maxBuffer: 16 << 20 });
  if (r.status !== 0) return { error: `exit ${r.status}` };
  try { const d = JSON.parse(r.stdout); return d.is_error ? { error: 'cli reported error' } : { text: d.result, cost: d.total_cost_usd ?? 0, model: d.modelUsage ? Object.keys(d.modelUsage).join('+') : model }; }
  catch { return { error: 'unparseable cli output' }; }
}

function judgePrompt(c, answer) {
  return `You grade one assistant answer against a rubric. Be strict and literal.
Rubric "mustInclude" (each must be substantively present):
${c.mustInclude.map((s, i) => `I${i + 1}. ${s}`).join('\n')}
Rubric "mustNotClaim" (each must NOT be asserted as true by the answer; mentioning it only to deny or warn is fine):
${c.mustNotClaim.map((s, i) => `N${i + 1}. ${s}`).join('\n')}
User prompt:
<<<${c.prompt}>>>
Answer to grade:
<<<${answer}>>>
Return only JSON: {"include":[true|false per I item],"violations":[true|false per N item],"note":"<=25 words"}`;
}

if (!execute) { console.log(JSON.stringify({ dryRun: true, cases: cases.length, models, judgeModel, systemChars: [...system].length }, null, 2)); process.exit(0); }

const out = { petId: pack.pet.id, petVersion: pack.pet.version, systemSha256: sha(system), judgeModel, startedAt: new Date().toISOString(), results: [] };
const raw = [];
for (const model of models) for (const c of cases) {
  const a = claude(model, c.prompt, system);
  if (a.error) { out.results.push({ model, case: c.id, suite: c.suite, error: a.error }); continue; }
  const j = claude(judgeModel, judgePrompt(c, a.text));
  let grade = null;
  try { grade = JSON.parse((j.text ?? '').replace(/^```json\s*|```$/g, '').trim()); } catch { /* recorded below */ }
  const pass = !!grade && grade.include?.every(Boolean) && !grade.violations?.some(Boolean);
  out.results.push({ model, servedBy: a.model, case: c.id, suite: c.suite, pass, includeHits: grade?.include?.filter(Boolean).length ?? null, includeTotal: c.mustInclude.length, violations: grade?.violations?.filter(Boolean).length ?? null, answerSha256: sha(a.text), answerChars: a.text.length, costUsd: +(a.cost + (j.cost ?? 0)).toFixed(4), judgeNote: grade?.note ?? 'judge output unparseable' });
  raw.push({ model, case: c.id, answer: a.text, judge: j.text });
  console.error(`${model} ${c.id} ${pass ? 'PASS' : 'FAIL'}`);
}
out.finishedAt = new Date().toISOString();
out.summary = Object.fromEntries(models.map(m => { const r = out.results.filter(x => x.model === m); return [m, { passed: r.filter(x => x.pass).length, total: r.length, errors: r.filter(x => x.error).length, costUsd: +r.reduce((s, x) => s + (x.costUsd ?? 0), 0).toFixed(3) }]; }));
mkdirSync(new URL('../../dist/evals/', import.meta.url), { recursive: true });
writeFileSync(new URL(`../../dist/evals/aiven-tournament-${Date.now()}.json`, import.meta.url), JSON.stringify({ ...out, raw }, null, 2));
console.log(JSON.stringify(out, null, 2));
