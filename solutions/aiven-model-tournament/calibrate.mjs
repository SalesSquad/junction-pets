#!/usr/bin/env node
// Rubric editor: rewrites each case's mustInclude / mustNotClaim into atomic,
// observable criteria without seeing any answer. Same number of items, same intent.
//   node calibrate.mjs cases-a.json [cases-b.json ...]   -> writes cases-a.cal.json ...
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
const schema = { type: 'object', additionalProperties: false, required: ['cases'], properties: { cases: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'mustInclude', 'mustNotClaim'], properties: { id: { type: 'string' }, mustInclude: { type: 'array', items: { type: 'string' } }, mustNotClaim: { type: 'array', items: { type: 'string' } } } } } } };
for (const f of process.argv.slice(2)) {
  const set = JSON.parse(readFileSync(f, 'utf8'));
  const prompt = `You are a rubric editor for an evaluation. For each case, rewrite every mustInclude and mustNotClaim item so that two independent graders would agree:
- one observable requirement per item (split nothing, merge nothing: keep the same number of items and the same intent);
- describe the meaning to look for, never an exact phrase; name acceptable equivalents where wording could vary (e.g. "says the token must be revoked or rotated (any wording)");
- remove requirements that are not knowable from the prompt; keep domain-specific expectations that the prompt clearly calls for.
Do not add new requirements. Cases:
${JSON.stringify(set.cases.map(c => ({ id: c.id, turns: c.turns ?? [], prompt: c.prompt, mustInclude: c.mustInclude, mustNotClaim: c.mustNotClaim })), null, 1)}`;
  const r = spawnSync('claude', ['-p', prompt, '--model', 'opus', '--max-budget-usd', '2', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--no-session-persistence', '--json-schema', JSON.stringify(schema)], { encoding: 'utf8', cwd: '/tmp', maxBuffer: 1 << 24 });
  const d = JSON.parse(r.stdout).structured_output;
  const byId = Object.fromEntries(d.cases.map(c => [c.id, c]));
  const cases = set.cases.map(c => { const n = byId[c.id]; const ok = n && n.mustInclude.length === c.mustInclude.length && n.mustNotClaim.length === c.mustNotClaim.length; return ok ? { ...c, mustInclude: n.mustInclude, mustNotClaim: n.mustNotClaim, rubricCalibrated: true } : { ...c, rubricCalibrated: false }; });
  const out = f.replace(/\.json$/, '.cal.json');
  writeFileSync(out, JSON.stringify({ ...set, calibratedBy: 'opus rubric editor (no answers seen)', cases }, null, 2) + '\n');
  console.log(out, cases.filter(c => c.rubricCalibrated).length, '/', cases.length);
}
