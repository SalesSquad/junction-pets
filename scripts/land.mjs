#!/usr/bin/env node
// One-command landing for a task branch:
//   checks clean tree → merges latest origin/main into the branch (no rebase, no force-push)
//   → npm run validate → parallel tests → push → PR (created if missing) → squash merge
//   pinned to the tested head → deletes the remote branch.
// Where the merge is refused (the cloud git proxy refuses merges), it prints the exact
// pinned command to run on a host whose gh may merge, for example the Mac mini.
// Usage: node scripts/land.mjs [--no-merge] [--skip-tests] [--title "..."]
// Output: one JSON receipt on stdout; progress goes to stderr.
import {execFileSync, spawnSync} from 'node:child_process';

const REPO = 'SalesSquad/junction-pets';
const args = process.argv.slice(2);
const flag = name => args.includes(`--${name}`);
const opt = name => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
const log = msg => process.stderr.write(`land: ${msg}\n`);
const git = (...a) => execFileSync('git', a, {encoding: 'utf8'}).trim();
const sh = (cmd, a) => spawnSync(cmd, a, {stdio: ['ignore', 'inherit', 'inherit']}).status;
const gh = a => spawnSync('gh', a, {encoding: 'utf8'});

const receipt = {repo: REPO, branch: null, head: null, base: null, validate: null, tests: null, pr: null, merged: false, merge_command: null};
function done(code, error) {
  if (error) receipt.error = error;
  process.stdout.write(JSON.stringify(receipt, null, 2) + '\n');
  process.exit(code);
}

receipt.branch = git('rev-parse', '--abbrev-ref', 'HEAD');
if (['main', 'HEAD'].includes(receipt.branch)) done(2, 'Run on a task branch, not main or a detached head.');
if (git('status', '--porcelain')) done(2, 'Working tree is not clean: commit or stash your own changes first.');

log('fetching origin/main');
git('fetch', '-q', 'origin', `+refs/heads/main:refs/remotes/origin/main`);
receipt.base = git('rev-parse', 'origin/main');
if (spawnSync('git', ['merge-base', '--is-ancestor', 'origin/main', 'HEAD']).status !== 0) {
  log('branch is behind main: merging origin/main (no rebase, no force-push)');
  if (sh('git', ['merge', '--no-edit', 'origin/main']) !== 0) {
    sh('git', ['merge', '--abort']);
    done(1, 'Merge conflict with origin/main: resolve by hand, then rerun.');
  }
}
receipt.head = git('rev-parse', 'HEAD');

log('npm run validate');
receipt.validate = sh('npm', ['run', '-s', 'validate']) === 0;
if (!receipt.validate) done(1, 'npm run validate failed.');
if (!flag('skip-tests')) {
  log('tests (parallel runner)');
  receipt.tests = sh(process.execPath, ['scripts/run-tests.mjs']) === 0 ? 'pass' : 'fail';
  if (receipt.tests !== 'pass') done(1, 'Tests failed.');
} else receipt.tests = 'skipped';

log('pushing');
if (sh('git', ['push', '-q', '-u', 'origin', receipt.branch]) !== 0) done(1, 'Push failed.');

let view = gh(['pr', 'view', receipt.branch, '--repo', REPO, '--json', 'number,state,url']);
if (view.status !== 0) {
  const title = opt('title') ?? git('log', '-1', '--format=%s');
  log('creating PR');
  const created = gh(['pr', 'create', '--repo', REPO, '--head', receipt.branch, '--base', 'main', '--title', title, '--body', 'Landed with scripts/land.mjs: validate and parallel tests passed on the pinned head.']);
  if (created.status !== 0) done(1, 'PR creation failed: ' + created.stderr.trim().slice(0, 300));
  view = gh(['pr', 'view', receipt.branch, '--repo', REPO, '--json', 'number,state,url']);
}
const pr = JSON.parse(view.stdout || '{}');
receipt.pr = pr.url ?? null;
const mergeArgs = ['pr', 'merge', String(pr.number), '--repo', REPO, '--squash', '--delete-branch', '--match-head-commit', receipt.head];
receipt.merge_command = ['gh', ...mergeArgs].join(' ');
if (flag('no-merge')) done(0);

log('merging (pinned to the tested head)');
const merged = gh(mergeArgs);
if (merged.status === 0) { receipt.merged = true; done(0); }
log('merge refused here; run merge_command on a host whose gh may merge');
done(3, merged.stderr.trim().slice(0, 300));
