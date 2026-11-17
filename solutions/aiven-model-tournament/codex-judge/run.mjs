// Third, non-Claude judge: Codex CLI (ChatGPT login) with a typed output schema per case.
// Input: codex-judge.jsonl lines {id, nInclude, nNot, prompt} built from challenge-judge.mjs prompts.
// Usage (on a machine with an authenticated `codex`): node run.mjs <dir>
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
// Absolute, so the child (cwd = dir) and the parent agree on every schema/output path.
const dir = resolve(process.argv[2] ?? '.');
const items = readFileSync(`${dir}/codex-judge.jsonl`, 'utf8').trim().split('\n').map(l => JSON.parse(l));
mkdirSync(`${dir}/out`, { recursive: true });
const schemaFor = (ni, nn) => ({ type: 'object', additionalProperties: false, required: ['include', 'violations', 'note'], properties: {
  include: { type: 'array', items: { type: 'boolean' }, minItems: ni, maxItems: ni },
  violations: { type: 'array', items: { type: 'boolean' }, minItems: nn, maxItems: nn },
  note: { type: 'string' } } });
const run = it => new Promise(res => {
  const safe = it.id.replace(/[^a-z0-9-]/gi, '_'), out = `${dir}/out/${safe}.json`;
  if (existsSync(out)) return res();
  const sch = `${dir}/out/${safe}.schema.json`; writeFileSync(sch, JSON.stringify(schemaFor(it.nInclude, it.nNot)));
  const p = spawn('codex', ['exec', '--sandbox', 'read-only', '--skip-git-repo-check', '--output-schema', sch, '-o', out, it.prompt], { cwd: dir, stdio: ['ignore', 'ignore', 'ignore'] });
  const t = setTimeout(() => p.kill('SIGTERM'), 300000);
  p.on('close', () => { clearTimeout(t); res(); });
});
let next = 0;
await Promise.all(Array.from({ length: 4 }, async () => { while (next < items.length) await run(items[next++]); }));
// Verdicts keep booleans only; judge prose stays local.
const results = items.map(it => { try { const g = JSON.parse(readFileSync(`${dir}/out/${it.id.replace(/[^a-z0-9-]/gi, '_')}.json`, 'utf8')); return { id: it.id, pass: g.include.every(v => v === true) && !g.violations.some(v => v === true) }; } catch { return { id: it.id, pass: null }; } });
writeFileSync(`${dir}/verdicts.json`, JSON.stringify(results, null, 1));
console.log(JSON.stringify({ judged: results.filter(r => r.pass !== null).length, total: results.length }));
