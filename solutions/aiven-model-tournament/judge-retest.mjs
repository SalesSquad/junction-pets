#!/usr/bin/env node
// Test-retest reliability of the judges on a stored injection run: re-grades every stored
// answer once more and compares with the stored verdicts. No new model answers.
//   node judge-retest.mjs --run=dist/evals/injection-X.json --cases=injection-cases-v2.json
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { judgePrompt } from './challenge-judge.mjs';
import { composeTurn } from '../../services/aiven-platform/untrusted.mjs';
import { auditedInjected, wilson } from './scoring.mjs';
const arg = (k, d) => process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d;
const run = JSON.parse(readFileSync(arg('run'), 'utf8'));
const cases = Object.fromEntries(JSON.parse(readFileSync(arg('cases'), 'utf8')).cases.map(c => [c.id, { ...c, injected: auditedInjected(c) }]));
const judges = arg('judges', 'opus,sonnet').split(',');
const claude = (model, prompt) => new Promise(res => { const p = spawn('claude', ['-p', prompt, '--model', model, '--max-budget-usd', '1', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence'], { cwd: '/tmp', stdio: ['ignore', 'pipe', 'ignore'] }); let o = ''; p.stdout.on('data', d => { o += d; }); p.on('close', () => { try { const d = JSON.parse(o); res({ text: d.result, cost: d.total_cost_usd ?? 0 }); } catch { res({}); } }); });
const items = run.results.filter(r => !r.error && cases[r.case]).map(r => ({ r, resp: run.raw.find(x => x.m === r.m && x.arm === r.arm && x.case === r.case && x.rep === r.rep)?.response })).filter(x => x.resp);
let next = 0, cost = 0; const out = [];
await Promise.all(Array.from({ length: Number(arg('concurrency', '10')) }, async () => { while (next < items.length) { const { r, resp } = items[next++], c = cases[r.case]; const again = {};
  for (const j of judges) for (let i = 0; i < 2 && again[j] === undefined; i++) { const a = await claude(j, judgePrompt({ ...c, prompt: composeTurn(c.user_request, c.attachments) }, resp)); cost += a.cost ?? 0; try { const g = JSON.parse((a.text ?? '').replace(/^```json\s*|```\s*$/g, '').trim()); if (Array.isArray(g.include)) again[j] = g.include.every(Boolean) && !g.violations.some(Boolean); } catch {} }
  out.push({ case: r.case, det: Object.values(r.det).every(Boolean), first: r.judges, again }); } }));
const ok = out.filter(x => judges.every(j => typeof x.first[j] === 'boolean' && typeof x.again[j] === 'boolean'));
const pass = f => ok.filter(x => x.det && f(x)).length;
const rate = k => ({ rate: +(k / ok.length).toFixed(3), ci95: wilson(k, ok.length) });
const report = { run: arg('run'), answers: ok.length, costUsd: +cost.toFixed(2),
  retestAgreement: Object.fromEntries(judges.map(j => [j, +(ok.filter(x => x.first[j] === x.again[j]).length / ok.length).toFixed(3)])),
  consensusFirst: rate(pass(x => judges.every(j => x.first[j]))), consensusRetest: rate(pass(x => judges.every(j => x.again[j]))),
  consensusBothSamples: rate(pass(x => judges.every(j => x.first[j] && x.again[j]))),
  majorityOfFour: rate(pass(x => judges.flatMap(j => [x.first[j], x.again[j]]).filter(Boolean).length >= 3)) };
console.log(JSON.stringify(report, null, 2));
