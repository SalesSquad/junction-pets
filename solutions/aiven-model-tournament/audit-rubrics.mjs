#!/usr/bin/env node
// Evidence audit for generated cases: an independent model checks every mustInclude item against the
// case's own request and attachments and proposes an evidence-bound rewrite where the item asks for a
// fact, cause, time or number the evidence does not establish. Writes a corrected copy and a report.
//   node audit-rubrics.mjs --cases=in.json --out=out.json [--model=opus]
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
const arg = (k, d) => process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d;
const SCHEMA = { type: 'object', additionalProperties: false, required: ['cases'], properties: { cases: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'problems'], properties: {
  id: { type: 'string' }, problems: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['item_index', 'why', 'conditional_rewrite'], properties: {
    item_index: { type: 'integer', minimum: 0 }, why: { type: 'string' }, conditional_rewrite: { type: 'string', minLength: 10 } } } } } } } } };
const claude = (model, prompt) => new Promise(res => { const p = spawn('claude', ['-p', prompt, '--model', model, '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence', '--json-schema', JSON.stringify(SCHEMA)], { cwd: '/tmp', stdio: ['ignore', 'pipe', 'ignore'] }); let o = ''; p.stdout.on('data', d => { o += d; }); p.on('close', () => { try { const d = JSON.parse(o); res({ data: d.structured_output, cost: d.total_cost_usd ?? 0 }); } catch { res({}); } }); });
const set = JSON.parse(readFileSync(arg('cases'), 'utf8'));
const view = set.cases.map(c => ({ id: c.id, user_request: c.user_request, attachments: c.attachments, mustInclude: c.mustInclude }));
const fixes = {}; let cost = 0;
for (let i = 0; i < view.length; i += 15) {
  const r = await claude(arg('model', 'opus'), `Audit these evaluation cases. For each case, check every mustInclude item: is it fully supported by the user_request and attachments, or does it require asserting a fact, causal link, time or number the evidence does not establish? Report only items with problems, with a rewrite that rewards a correct evidence-bound answer (conditional wording where the evidence is incomplete).\n\n${JSON.stringify(view.slice(i, i + 15))}`);
  if (!r.data) { console.error('audit failed for batch', i); process.exit(1); }
  cost += r.cost; for (const c of r.data.cases) if (c.problems.length) fixes[c.id] = c.problems;
}
let rewritten = 0;
for (const c of set.cases) for (const p of fixes[c.id] ?? []) if (p.item_index < c.mustInclude.length) { c.mustInclude[p.item_index] = p.conditional_rewrite; rewritten++; c.label_note = 'mustInclude made evidence-bound by audit-rubrics.mjs'; }
writeFileSync(arg('out'), JSON.stringify({ ...set, rubricAudit: { model: arg('model', 'opus'), casesWithProblems: Object.keys(fixes).length, itemsRewritten: rewritten } }, null, 2) + '\n');
console.log(JSON.stringify({ cases: set.cases.length, casesWithProblems: Object.keys(fixes).length, itemsRewritten: rewritten, costUsd: +cost.toFixed(2), problems: fixes }, null, 1));
