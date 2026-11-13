import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, symlinkSync, chmodSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {EXPECTED_COMPANIES} from '../lib/catalog.mjs';
import {companyScopeSha256, parseDevelopmentProgress, readDevelopmentProgress, PROGRESS_LIMITS} from '../ops/development-progress.mjs';

const cli = fileURLToPath(new URL('../scripts/ops-development-progress.mjs', import.meta.url));
const git = (root, ...args) => execFileSync('git', ['-C', root, ...args], {encoding: 'utf8'}).trim();
const put = (root, path, text = 'synthetic\n') => { mkdirSync(dirname(join(root, path)), {recursive: true}); writeFileSync(join(root, path), text); };
const serial = value => JSON.stringify(value);
const pr = 'https://github.com/SalesSquad/junction-pets/pull/1';
const head = 'a'.repeat(40);
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'junction-continuity-'));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  git(root, 'init', '--quiet');
  git(root, 'config', 'user.name', 'Synthetic continuity test');
  git(root, 'config', 'user.email', 'synthetic@example.invalid');
  for (const company of EXPECTED_COMPANIES) {
    put(root, `pets/${company}/source.txt`, `${company}\n`);
    put(root, `plugins/junction-${company}/plugin.json`, '{}\n');
    put(root, `tests/pet-${company}.test.mjs`, '// synthetic\n');
  }
  put(root, 'README.md');
  git(root, 'add', '.');
  git(root, 'commit', '--quiet', '-m', 'Synthetic source fixture');
  const ledger = {
    schemaVersion: 1, repository: 'SalesSquad/junction-pets', observedAt: '2026-11-13T08:00:00.000Z',
    records: EXPECTED_COMPANIES.map(company => ({
      company, agentId: `junction-dev-${company}`, workId: `junction.${company}.synthetic`,
      branch: `codex/junction-${company}-synthetic`, source: {base: 'b'.repeat(40), head, tree: 'c'.repeat(40)},
      pr: {url: pr, mergeCommit: 'd'.repeat(40)}, integrationPr: null,
      executor: {kind: 'native', id: `synthetic-${company}-writer`, taskUrl: null},
      review: {reviewer: 'synthetic-independent-reviewer', head, verdict: 'pass', evidenceUrl: `${pr}#issuecomment-1`},
      checks: {focused: {passed: 3, total: 3}, full: {passed: 12, total: 12}, evidenceUrl: `${pr}#issuecomment-2`},
      writerState: 'released', nextAction: {state: 'proposed-not-started', owner: `junction-dev-${company}`, action: 'Inspect the synthetic follow-up proposal.'},
      scopeSha256: companyScopeSha256(root, company),
    })),
  };
  const save = () => put(root, 'ops/development-progress.json', serial(ledger));
  save();
  const run = (...args) => spawnSync(process.execPath, [cli, ...args], {cwd: root, encoding: 'utf8'});
  return {root, ledger, save, run};
}

test('CLI gives a small private summary, while --pet emits exactly one continuation record', t => {
  const {root, run} = fixture(t);
  const all = run();
  assert.equal(all.status, 0, all.stderr);
  const summary = JSON.parse(all.stdout);
  assert.equal(summary.summary.companies, 34);
  assert.equal(summary.summary.sourceMatched, 34);
  assert.equal(Object.hasOwn(summary, 'records'), false);
  assert.equal(Object.hasOwn(summary, 'record'), false);
  const selected = run('--pet', 'aiven');
  assert.equal(selected.status, 0, selected.stderr);
  const output = JSON.parse(selected.stdout);
  assert.equal(output.record.company, 'aiven');
  assert.equal(output.record.sourceCheck.state, 'source-matched');
  assert.equal(output.qualification.currentFullSuite, 'unverified');
  assert.equal(output.qualification.provenanceAuthenticated, false);
  assert.equal(output.qualification.provider, 'unverified');
  assert.equal(output.qualification.host, 'unverified');
  assert.equal(readDevelopmentProgress(root, {pet: 'aiven'}).records.length, 1);
  assert.equal(run('--check').status, 0);
  assert.equal(run('--check', '--pet', 'aiven').status, 0);
});

test('closed ledger schema rejects missing/duplicate/unknown companies and unknown fields at every level', t => {
  const {ledger, save, run} = fixture(t);
  const mutations = [
    x => x.records.pop(), x => { x.records[1] = structuredClone(x.records[0]); },
    x => { x.records[0].company = 'invented'; }, x => { x.extra = true; },
    ...['source', 'pr', 'executor', 'review', 'checks', 'nextAction'].map(key => x => { x.records[0][key].extra = true; }),
    x => { x.records[0].checks.focused.extra = true; }, x => { x.records[0].extra = true; },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(ledger); mutate(changed);
    assert.throws(() => parseDevelopmentProgress(serial(changed)), /Invalid development progress/);
  }
  ledger.records.pop(); save();
  assert.notEqual(run('--check').status, 0);
});

test('historical finite tasks cannot assert running workers, provider readiness or self-reviewed evidence', t => {
  const {ledger} = fixture(t);
  const mutations = [
    x => { x.writerState = 'running'; }, x => { x.nextAction.state = 'running'; },
    x => { x.executor.ready = true; }, x => { x.executor.kind = 'native'; x.executor.taskUrl = 'https://chatgpt.com/local/123'; },
    x => { x.executor.kind = 'codex-cloud'; }, x => { x.executor.kind = 'other-provider'; },
    x => { x.review.head = 'e'.repeat(40); }, x => { x.review.reviewer = x.executor.id; },
    x => { x.review.verdict = 'approved'; }, x => { x.checks.full.passed = 13; },
    x => { x.agentId = 'another-owner'; }, x => { x.source.head = 'main'; },
    x => { x.branch += '/../../main'; }, x => { x.checks.evidenceUrl = `${pr}?token=secret`; },
    x => { x.review.evidenceUrl = 'https://other.invalid/receipt'; },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(ledger); mutate(changed.records[0]);
    assert.throws(() => parseDevelopmentProgress(serial(changed)), /Invalid development progress/);
  }
  const cloud = structuredClone(ledger);
  cloud.records[0].executor = {kind: 'codex-cloud', id: 'synthetic-task-id', taskUrl: 'https://chatgpt.com/codex/tasks/task_e_0123456789abcdef'};
  assert.equal(parseDevelopmentProgress(serial(cloud)).records[0].executor.kind, 'codex-cloud');
});

test('strict UTC calendar, bounded JSON text, hashes and original counts have no coercion', t => {
  const {ledger} = fixture(t);
  for (const observedAt of ['2026-02-30T08:00:00.000Z', '2026-11-13T08:00:00Z', '2026-11-13T10:00:00.000+02:00', null]) {
    assert.throws(() => parseDevelopmentProgress(serial({...ledger, observedAt})), /Invalid development progress/);
  }
  for (const value of ['{', 'null', '[]', ' '.repeat(PROGRESS_LIMITS.ledgerBytes + 1), ledger]) {
    assert.throws(() => parseDevelopmentProgress(value), /Invalid development progress/);
  }
  for (const mutate of [x => { x.scopeSha256 = 'f'.repeat(63); }, x => { x.checks.focused.total = '3'; }, x => { x.checks.full.total = Infinity; }, x => { x.nextAction.action = ''; }]) {
    const changed = structuredClone(ledger); mutate(changed.records[0]);
    assert.throws(() => parseDevelopmentProgress(serial(changed)), /Invalid development progress/);
  }
  const copy = parseDevelopmentProgress(serial(ledger));
  copy.records[0].checks.full.total++;
  assert.equal(parseDevelopmentProgress(serial(ledger)).records[0].checks.full.total, 12);
  assert.equal(parseDevelopmentProgress(serial(ledger).replace('"schemaVersion":1', '"schemaVersion":0,"schemaVersion":1')).schemaVersion, 1);
});

test('actual changed bytes make evidence stale without refreshing historical counts or digest', t => {
  const {root, ledger, run} = fixture(t);
  const old = ledger.records.find(record => record.company === 'aiven');
  put(root, 'pets/aiven/source.txt', 'changed source\n');
  const result = run('--pet', 'aiven', '--check');
  assert.equal(result.status, 1);
  const record = JSON.parse(result.stdout).record;
  assert.equal(record.sourceCheck.state, 'stale');
  assert.equal(record.scopeSha256, old.scopeSha256);
  assert.deepEqual(record.checks, old.checks);
  assert.notEqual(record.sourceCheck.actualSha256, old.scopeSha256);
  assert.deepEqual(JSON.parse(readFileSync(join(root, 'ops/development-progress.json'))), ledger);
});

test('tracked added/deleted/renamed files and executable mode enter the scope digest', t => {
  const {root, run} = fixture(t);
  const original = companyScopeSha256(root, 'aiven');
  put(root, 'pets/aiven/added.txt'); git(root, 'add', 'pets/aiven/added.txt');
  assert.notEqual(companyScopeSha256(root, 'aiven'), original);
  assert.equal(run('--pet', 'aiven', '--check').status, 1);
  git(root, 'rm', '--cached', 'pets/aiven/added.txt');
  assert.equal(companyScopeSha256(root, 'aiven'), original);
  git(root, 'mv', 'pets/aiven/source.txt', 'pets/aiven/renamed.txt');
  assert.notEqual(companyScopeSha256(root, 'aiven'), original);
  git(root, 'mv', 'pets/aiven/renamed.txt', 'pets/aiven/source.txt');
  chmodSync(join(root, 'pets/aiven/source.txt'), 0o755);
  assert.notEqual(companyScopeSha256(root, 'aiven'), original);
  chmodSync(join(root, 'pets/aiven/source.txt'), 0o644);
  git(root, 'rm', 'pets/aiven/source.txt');
  assert.equal(run('--pet', 'aiven', '--check').status, 1);
});

test('missing tracked bytes are unverified; another company is neither read nor blocked by --pet', t => {
  const {root, run} = fixture(t);
  rmSync(join(root, 'pets/hostinger/source.txt'));
  const output = run('--pet', 'hostinger', '--check');
  assert.equal(output.status, 1);
  assert.equal(JSON.parse(output.stdout).record.sourceCheck.state, 'unverified');
  assert.equal(run('--pet', 'aiven', '--check').status, 0);
  assert.equal(run('--check').status, 1);
});

test('tracked symlinks, replaced parent directories and malformed Git paths are refused', t => {
  const {root, run} = fixture(t);
  const target = join(root, 'private-untracked.txt');
  writeFileSync(target, 'must never be read');
  rmSync(join(root, 'pets/aiven/source.txt'));
  symlinkSync(target, join(root, 'pets/aiven/source.txt'));
  assert.throws(() => companyScopeSha256(root, 'aiven'), /symlink|regular/i);
  git(root, 'add', 'pets/aiven/source.txt');
  assert.equal(run('--pet', 'aiven', '--check').status, 1);
  rmSync(join(root, 'pets/aiven'), {recursive: true});
  symlinkSync(join(root, 'pets/hostinger'), join(root, 'pets/aiven'));
  assert.throws(() => companyScopeSha256(root, 'aiven'), /symlink|mode/i);
  rmSync(join(root, 'pets/meta'), {recursive: true});
  symlinkSync(join(root, 'pets/hostinger'), join(root, 'pets/meta'));
  assert.throws(() => companyScopeSha256(root, 'meta'), /symlink/i);
  put(root, 'pets/mariadb/bad\nname.txt'); git(root, 'add', 'pets/mariadb');
  assert.throws(() => companyScopeSha256(root, 'mariadb'), /path/i);
});

test('unrelated tracked and arbitrary untracked content never enters the source digest', t => {
  const {root, run} = fixture(t);
  const original = companyScopeSha256(root, 'aiven');
  put(root, 'README.md', 'unrelated dirty source\n');
  put(root, 'pets/hostinger/source.txt', 'other company change\n');
  symlinkSync('/does/not/exist', join(root, 'pets/aiven/untracked-secret'));
  put(root, 'pets/aiven/untracked-huge.txt', 'x'.repeat(PROGRESS_LIMITS.fileBytes + 1));
  assert.equal(companyScopeSha256(root, 'aiven'), original);
  assert.equal(run('--pet', 'aiven', '--check').status, 0);
  assert.equal(JSON.parse(run('--pet', 'aiven').stdout).qualification.remote, 'unverified');
});

test('scope hashing is deterministic with path/mode/byte framing and finite file/count limits', t => {
  const {root} = fixture(t);
  const files = [['pets/aiven/source.txt', 'aiven\n'], ['plugins/junction-aiven/plugin.json', '{}\n'], ['tests/pet-aiven.test.mjs', '// synthetic\n']];
  const expected = createHash('sha256').update('junction-company-scope-v1\0aiven\0');
  for (const [path, text] of files.sort(([a], [b]) => a < b ? -1 : 1)) expected.update([path, '100644', Buffer.byteLength(text), ''].join('\0')).update(text);
  assert.equal(companyScopeSha256(root, 'aiven'), expected.digest('hex'));
  put(root, 'pets/aiven/source.txt', 'x'.repeat(PROGRESS_LIMITS.fileBytes + 1));
  assert.throws(() => companyScopeSha256(root, 'aiven'), /limit|large/i);
  for (let i = 0; i < PROGRESS_LIMITS.files; i++) put(root, `pets/mariadb/file-${i}.txt`);
  git(root, 'add', 'pets/mariadb');
  assert.throws(() => companyScopeSha256(root, 'mariadb'), /limit|many/i);
  for (let i = 0; i < PROGRESS_LIMITS.scopeBytes / PROGRESS_LIMITS.fileBytes; i++) put(root, `pets/meta/large-${i}.txt`, 'x'.repeat(PROGRESS_LIMITS.fileBytes));
  git(root, 'add', 'pets/meta');
  assert.throws(() => companyScopeSha256(root, 'meta'), /limit/i);
  assert.throws(() => companyScopeSha256(root, '../aiven'), /company/i);
});

test('CLI rejects unknown/repeated arguments and missing/malformed/symlink ledger safely', t => {
  const {root, run} = fixture(t);
  for (const args of [['--pet'], ['--pet', '../aiven'], ['--pet', 'aiven', '--pet', 'meta'], ['--check', '--check'], ['--dispatch'], ['--root', root]]) {
    assert.equal(run(...args).status, 1);
  }
  put(root, 'ops/development-progress.json', '{');
  assert.equal(run('--check').status, 1);
  rmSync(join(root, 'ops/development-progress.json'));
  assert.equal(run().status, 1);
  symlinkSync(join(root, 'README.md'), join(root, 'ops/development-progress.json'));
  assert.equal(run().status, 1);
});
