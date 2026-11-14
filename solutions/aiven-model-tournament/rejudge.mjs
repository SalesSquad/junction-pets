#!/usr/bin/env node
// Re-grades stored responses (dist/evals/challenge-*.json raw) with the current judge
// prompt and given case files, to measure judge agreement without new answers.
//   node rejudge.mjs --run=dist/evals/challenge-X.json --cases=a.cal.json,b.cal.json --judges=opus,sonnet
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { judgePrompt } from './challenge-judge.mjs';
const arg = (k, d) => process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d;
const run = JSON.parse(readFileSync(arg('run'), 'utf8'));
const cases = Object.fromEntries(arg('cases').split(',').flatMap(f => JSON.parse(readFileSync(f, 'utf8')).cases).map(c => [c.id, c]));
const judges = arg('judges', 'opus,sonnet').split(',');
const claude = (model, prompt) => new Promise(res => { const p = spawn('claude', ['-p', prompt, '--model', model, '--max-budget-usd', '1', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence'], { cwd: '/tmp', stdio: ['ignore', 'pipe', 'ignore'] }); let o = ''; p.stdout.on('data', d => { o += d; }); p.on('close', () => { try { const d = JSON.parse(o); res({ text: d.result, cost: d.total_cost_usd }); } catch { res({}); } }); });
const items = run.raw.filter(r => r.response && cases[r.case]).map(r => ({ ...r, det: run.results.find(x => x.model === r.model && x.arm === r.arm && x.case === r.case && x.rep === r.rep)?.det }));
const out = []; let next = 0, cost = 0;
await Promise.all(Array.from({ length: 10 }, async () => { while (next < items.length) { const it = items[next++], c = cases[it.case]; const per = {};
  for (const j of judges) { for (let i = 0; i < 2 && !per[j]; i++) { const r = await claude(j, judgePrompt(c, it.response)); cost += r.cost ?? 0; try { const g = JSON.parse((r.text ?? '').replace(/^```json\s*|```\s*$/g, '').trim()); if (Array.isArray(g.include)) per[j] = g.include.every(Boolean) && !g.violations.some(Boolean) && Object.values(it.det ?? {}).every(Boolean); } catch {} } }
  out.push({ arm: it.arm, case: it.case, per }); } }));
const both = out.filter(r => judges.every(j => r.per[j] !== undefined));
const agree = both.filter(r => new Set(judges.map(j => r.per[j])).size === 1).length;
const byArm = Object.fromEntries(Object.entries(Object.groupBy(both, r => r.arm)).map(([a, g]) => [a, { consensus: +(g.filter(r => judges.every(j => r.per[j])).length / g.length).toFixed(3), ...Object.fromEntries(judges.map(j => [j, +(g.filter(r => r.per[j]).length / g.length).toFixed(3)])) }]));
console.log(JSON.stringify({ graded: both.length, judgeAgreement: +(agree / both.length).toFixed(3), byArm, costUsd: +cost.toFixed(2) }, null, 2));
