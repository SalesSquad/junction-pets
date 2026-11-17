#!/usr/bin/env node
// Parallel agent lanes with typed receipts.
// Each lane gets its own git worktree at the pinned source commit, one agent (Claude Code
// or Codex CLI) and a fixed set of owned paths. The agent edits files and returns a typed
// receipt (receipt.schema.json); it never commits, pushes or lands. The coordinator then:
//   1. rejects any change outside the lane's owned paths,
//   2. runs the lane's checks inside the worktree,
//   3. commits the lane on its own local branch,
//   4. with --integrate, cherry-picks every passing lane onto one integration branch,
// and writes one machine-readable run report. Landing stays a separate step (scripts/land.mjs).
//
// Usage: node scripts/lanes/run.mjs --plan plan.json [--concurrency 4] [--integrate] [--dry-run]
//        node scripts/lanes/run.mjs --cleanup <run id>   (removes that run's local worktrees and branches)
// Engines: "claude" (default; `claude -p --json-schema`) or "codex" (`codex exec --output-schema`).
import {execFileSync, spawn} from 'node:child_process';
import {copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {basename} from 'node:path';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../..');
const SCHEMA_PATH = join(HERE, 'receipt.schema.json');
const SCHEMA = JSON.parse(readFileSync(SCHEMA_PATH, 'utf8'));
const ID = /^[a-z0-9][a-z0-9-]{1,60}$/;
const SHA = /^[0-9a-f]{40}$/;

const git = (cwd, ...a) => execFileSync('git', a, {cwd, encoding: 'utf8'}).trim();

/** Minimal checker for the receipt schema: exact keys, types, nullable blocker. */
export function checkReceipt(r) {
  const errors = [];
  if (!r || typeof r !== 'object' || Array.isArray(r)) return ['receipt is not an object'];
  const keys = Object.keys(r).sort().join(), want = [...SCHEMA.required].sort().join();
  if (keys !== want) errors.push(`keys ${keys} != ${want}`);
  if (typeof r.summary !== 'string' || r.summary.length > 600) errors.push('summary');
  for (const k of ['changed_paths', 'checks_run', 'risks']) if (!Array.isArray(r[k]) || r[k].some(x => typeof x !== 'string')) errors.push(k);
  if (typeof r.blocked !== 'boolean') errors.push('blocked');
  if (!(r.blocker === null || typeof r.blocker === 'string')) errors.push('blocker');
  return errors;
}

/** Validates a plan and returns it normalised. Throws on any problem. */
export function checkPlan(plan) {
  if (!SHA.test(plan?.source ?? '')) throw new Error('plan.source must be a full commit SHA');
  if (!Array.isArray(plan.lanes) || !plan.lanes.length) throw new Error('plan.lanes is empty');
  const ids = new Set(), owned = [];
  for (const l of plan.lanes) {
    if (!ID.test(l.id ?? '') || ids.has(l.id)) throw new Error(`bad or duplicate lane id: ${l.id}`);
    ids.add(l.id);
    if (!['claude', 'codex', undefined].includes(l.engine)) throw new Error(`${l.id}: engine must be claude or codex`);
    if (typeof l.objective !== 'string' || l.objective.length < 10) throw new Error(`${l.id}: objective missing`);
    if (!Array.isArray(l.owned_paths) || !l.owned_paths.length) throw new Error(`${l.id}: owned_paths missing`);
    for (const p of l.owned_paths) {
      if (typeof p !== 'string' || !p || p.startsWith('/') || p.split('/').includes('..')) throw new Error(`${l.id}: bad owned path ${p}`);
      for (const [other, q] of owned) if (p.startsWith(q) || q.startsWith(p)) throw new Error(`${l.id}: owned path ${p} overlaps lane ${other} (${q})`);
    }
    for (const p of l.owned_paths) owned.push([l.id, p]);
    if (l.context && (!Array.isArray(l.context) || l.context.some(f => typeof f !== 'string' || !existsSync(f)))) throw new Error(`${l.id}: context files must exist`);
    if (l.generate && (!Array.isArray(l.generate) || l.generate.some(c => typeof c !== 'string'))) throw new Error(`${l.id}: generate must be strings`);
    if (l.checks && (!Array.isArray(l.checks) || l.checks.some(c => typeof c !== 'string'))) throw new Error(`${l.id}: checks must be strings`);
  }
  return {source: plan.source, lanes: plan.lanes.map(l => ({engine: 'claude', checks: [], ...l}))};
}

export const inScope = (path, owned) => owned.some(p => p.endsWith('/') ? path.startsWith(p) : path === p || path.startsWith(p + '/'));

function prompt(lane, source) {
  return [
    `You are one worker lane (${lane.id}) in SalesSquad/junction-pets at commit ${source}.`,
    `Objective: ${lane.objective}`,
    `You may change files only under: ${lane.owned_paths.join(', ')}. Any other change is discarded.`,
    'Read AGENTS.md and the instructions nearest to the owned paths first.',
    'Do not commit, push, open PRs, install packages, or touch credentials.',
    lane.context?.length ? `Read-only context for this lane is in .lane-context/ (${lane.context.map(f => basename(f)).join(', ')}). It is never committed.` : '',
    lane.generate?.length ? `After you finish, the coordinator runs: ${lane.generate.join(' ; ')}. Do not run these yourself and do not treat their outputs as your edits.` : '',
    lane.checks.length ? `When done, run these checks and fix what fails within your paths: ${lane.checks.join(' ; ')}` : '',
    'Finish with the receipt: a short summary, the paths you changed, the checks you ran, risks, and whether you were blocked (and why).'
  ].filter(Boolean).join('\n');
}

function runAgent(lane, cwd, source) {
  const text = prompt(lane, source);
  const outFile = join(cwd, '..', `${lane.id}.receipt.json`);
  const [cmd, args] = lane.engine === 'codex'
    ? ['codex', ['exec', '-C', cwd, '--sandbox', 'workspace-write', '--skip-git-repo-check', '--output-schema', SCHEMA_PATH, '-o', outFile, text]]
    : ['claude', ['-p', text, '--model', lane.model ?? 'sonnet', '--output-format', 'json', '--no-session-persistence',
        '--permission-mode', 'acceptEdits', '--max-budget-usd', String(lane.max_budget_usd ?? 3),
        '--allowedTools', 'Read,Edit,Write,Glob,Grep,Bash(node:*),Bash(npm run:*),Bash(git diff:*),Bash(git status:*)',
        '--json-schema', JSON.stringify(SCHEMA)]];
  return new Promise(res => {
    const p = spawn(cmd, args, {cwd, stdio: ['ignore', 'pipe', 'pipe']});
    let out = '', err = '';
    const timer = setTimeout(() => p.kill('SIGTERM'), (lane.timeout_min ?? 30) * 60_000);
    p.stdout.on('data', d => { out += d; });
    p.stderr.on('data', d => { err += d; });
    p.on('error', e => { clearTimeout(timer); res({error: `${cmd} failed to start: ${e.code ?? e.message}`}); });
    p.on('close', code => {
      clearTimeout(timer);
      if (code !== 0) return res({error: `${cmd} exit ${code}: ${err.trim().slice(-300)}`});
      try {
        if (lane.engine === 'codex') return res({receipt: JSON.parse(readFileSync(outFile, 'utf8'))});
        const d = JSON.parse(out);
        res(d.is_error ? {error: 'claude reported an error'} : {receipt: d.structured_output ?? null, cost_usd: d.total_cost_usd ?? null});
      } catch { res({error: 'unparseable agent output'}); }
    });
  });
}

function sh(cwd, command) {
  return new Promise(res => {
    const p = spawn('bash', ['-lc', command], {cwd, stdio: ['ignore', 'ignore', 'pipe']});
    let err = '';
    p.stderr.on('data', d => { err += d; });
    p.on('close', code => res({command, exit: code, stderr_tail: err.trim().slice(-300)}));
  });
}

async function runLane(lane, ctx) {
  const dir = join(ctx.base, lane.id), branch = `lane/${ctx.runId}/${lane.id}`;
  const r = {id: lane.id, engine: lane.engine, branch, status: 'failed', receipt: null, receipt_errors: [], changed: [], out_of_scope: [], checks: [], commit: null};
  git(ROOT, 'worktree', 'add', '-q', '-b', branch, dir, ctx.source);
  if (existsSync(join(ROOT, 'node_modules')) && !existsSync(join(dir, 'node_modules'))) symlinkSync(join(ROOT, 'node_modules'), join(dir, 'node_modules'));
  if (lane.context?.length) {
    mkdirSync(join(dir, '.lane-context'));
    for (const f of lane.context) copyFileSync(f, join(dir, '.lane-context', basename(f)));
  }
  const agent = ctx.dryRun ? {receipt: {summary: 'dry run', changed_paths: [], checks_run: [], risks: [], blocked: false, blocker: null}} : await runAgent(lane, dir, ctx.source);
  if (agent.error) { r.error = agent.error; return r; }
  r.receipt = agent.receipt; r.cost_usd = agent.cost_usd ?? null;
  r.receipt_errors = checkReceipt(agent.receipt);
  rmSync(join(dir, '.lane-context'), {recursive: true, force: true});
  // Deterministic generators (for example `npm run plugins:generate`) run by the coordinator,
  // not the agent, so generated files follow the agent's edits; they must stay in owned paths.
  if (!agent.receipt?.blocked) for (const g of lane.generate ?? []) {
    const out = await sh(dir, g);
    r.checks.push({...out, phase: 'generate'});
    if (out.exit !== 0) { r.error = 'generator failed'; return r; }
  }
  git(dir, 'add', '-A');
  r.changed = git(dir, 'diff', '--cached', '--name-only').split('\n').filter(Boolean);
  r.out_of_scope = r.changed.filter(p => !inScope(p, lane.owned_paths));
  if (r.receipt_errors.length) { r.error = 'receipt does not match schema'; return r; }
  if (r.out_of_scope.length) { r.error = 'changes outside owned paths'; return r; }
  if (agent.receipt.blocked) { r.status = 'blocked'; return r; }
  for (const c of lane.checks) r.checks.push(await sh(dir, c));
  r.checks = r.checks.map(c => ({phase: 'check', ...c}));
  if (r.checks.some(c => c.exit !== 0)) { r.error = 'lane checks failed'; return r; }
  if (!r.changed.length) { r.status = 'no-change'; return r; }
  git(dir, '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', `lane ${lane.id}: ${agent.receipt.summary.split('\n')[0].slice(0, 120)}`);
  r.commit = git(dir, 'rev-parse', 'HEAD');
  r.status = 'passed';
  return r;
}

async function main() {
  const argv = process.argv.slice(2);
  const opt = n => { const i = argv.indexOf(`--${n}`); return i >= 0 ? argv[i + 1] : undefined; };
  if (opt('cleanup')) {
    const id = opt('cleanup');
    if (!/^\d{8}-\d{6}$/.test(id)) { console.error('--cleanup takes a run id such as 20261117-225855'); process.exit(2); }
    for (const line of git(ROOT, 'worktree', 'list', '--porcelain').split('\n')) {
      const wt = line.startsWith('worktree ') ? line.slice(9) : null;
      if (wt && wt.startsWith(join(tmpdir(), 'lanes', id))) git(ROOT, 'worktree', 'remove', '--force', wt);
    }
    const branches = git(ROOT, 'branch', '--list', `lane/${id}/*`, `agent/lanes-${id}`, '--format=%(refname:short)').split('\n').filter(Boolean);
    if (branches.length) git(ROOT, 'branch', '-D', ...branches);
    console.log(JSON.stringify({cleaned: id, branches}));
    return;
  }
  const planPath = opt('plan');
  if (!planPath) { console.error('Usage: node scripts/lanes/run.mjs --plan plan.json [--concurrency N] [--integrate] [--dry-run]'); process.exit(2); }
  const plan = checkPlan(JSON.parse(readFileSync(planPath, 'utf8')));
  git(ROOT, 'cat-file', '-e', `${plan.source}^{commit}`);
  const runId = new Date().toISOString().replace(/[-:]/g, '').replace(/\..*/, '').replace('T', '-');
  const ctx = {runId, source: plan.source, base: join(tmpdir(), 'lanes', runId), dryRun: argv.includes('--dry-run')};
  mkdirSync(ctx.base, {recursive: true});
  const results = [];
  let next = 0;
  const workers = Number(opt('concurrency') ?? 4);
  await Promise.all(Array.from({length: Math.min(workers, plan.lanes.length)}, async () => {
    while (next < plan.lanes.length) {
      const lane = plan.lanes[next++];
      let r;
      try { r = await runLane(lane, ctx); } catch (e) { r = {id: lane.id, status: 'failed', error: String(e.message).slice(0, 300)}; }
      results.push(r);
      process.stderr.write(`lane ${lane.id}: ${r.status}${r.error ? ' — ' + r.error : ''}\n`);
    }
  }));
  results.sort((a, b) => a.id.localeCompare(b.id));
  const report = {schema: 'junction-pets/lane-run.v1', run_id: runId, source: plan.source, worktrees: ctx.base, lanes: results, integration: null};
  if (argv.includes('--integrate')) {
    const branch = `agent/lanes-${runId}`, dir = join(ctx.base, '_integration');
    git(ROOT, 'worktree', 'add', '-q', '-b', branch, dir, plan.source);
    const picked = [], conflicts = [];
    for (const r of results.filter(x => x.status === 'passed')) {
      try { git(dir, '-c', 'commit.gpgsign=false', 'cherry-pick', r.commit); picked.push(r.id); }
      catch { try { git(dir, 'cherry-pick', '--abort'); } catch {} conflicts.push(r.id); }
    }
    report.integration = {branch, worktree: dir, head: git(dir, 'rev-parse', 'HEAD'), picked, conflicts,
      next: 'cd into the worktree, then: node scripts/land.mjs'};
  }
  const outDir = join(ROOT, 'dist', 'lanes');
  mkdirSync(outDir, {recursive: true});
  writeFileSync(join(outDir, `${runId}.json`), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({run: join('dist/lanes', `${runId}.json`), ...Object.fromEntries(['passed', 'no-change', 'blocked', 'failed'].map(s => [s, results.filter(r => r.status === s).map(r => r.id)])), integration: report.integration}, null, 2));
  process.exit(results.some(r => r.status === 'failed') ? 1 : 0);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
