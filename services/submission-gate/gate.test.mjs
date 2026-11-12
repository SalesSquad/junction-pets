import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { assertSafePath, isHardDenied, sha256, validateAllowlist, verifySubmission } from './gate.mjs';

async function fixture(path = 'pets/aiven/pet.json', content = '{"id":"junction-aiven"}\n') {
  const outer = await mkdtemp(join(tmpdir(), 'junction-submission-gate-'));
  const repo = join(outer, 'repo');
  const stage = join(outer, 'stage');
  await mkdir(repo);
  await mkdir(stage);
  const sourceFile = join(repo, path);
  const stagedFile = join(stage, path);
  await mkdir(dirname(sourceFile), { recursive: true });
  await mkdir(dirname(stagedFile), { recursive: true });
  await writeFile(sourceFile, content);
  await writeFile(stagedFile, content);
  const run = (...args) => execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8' }).trim();
  run('init', '-q');
  run('config', 'user.email', 'synthetic@example.invalid');
  run('config', 'user.name', 'Synthetic Test');
  run('remote', 'add', 'origin', 'https://github.com/SalesSquad/junction-pets.git');
  run('add', '.');
  run('commit', '-q', '-m', 'synthetic source');
  const sourceRevision = run('rev-parse', 'HEAD');
  const allowlist = {
    schemaVersion: 1,
    sourceRepository: 'SalesSquad/junction-pets',
    sourceRevision,
    files: [{ path, sha256: sha256(Buffer.from(content)) }]
  };
  return { outer, repo, stage, path, sourceFile, stagedFile, sourceRevision, allowlist };
}

function blocked(code) {
  return (error) => error?.code === code;
}

test('passes exact reviewed source bytes and labels result not published', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  const result = await verifySubmission({ treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist });
  assert.equal(result.sourceRevision, f.sourceRevision);
  assert.equal(result.status, 'reviewable-not-published');
  assert.equal(result.fileCount, 1);
  assert.equal(result.files[0].sha256, f.allowlist.files[0].sha256);
});

test('extra files are rejected even if they appear harmless', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await writeFile(join(f.stage, 'README.md'), 'unexpected\n');
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('UNEXPECTED_FILES'));
});

test('ops and private plugin registrations are never allowlisted', async (t) => {
  const f = await fixture('ops/plugin-registrations/aiven.json', '{"private":true}\n');
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  assert.equal(isHardDenied('ops/plugin-registrations/aiven.json'), true);
  assert.throws(() => validateAllowlist(f.allowlist), blocked('HARD_DENY'));
});

test('internal mission control and nested private paths fail even if explicitly allowlisted', () => {
  assert.equal(isHardDenied('apps/mission-control/app.js'), true);
  assert.equal(isHardDenied('chibi/src/runtime.rs'), true);
  assert.equal(isHardDenied('services/chibi/src/runtime.rs'), true);
  assert.equal(isHardDenied('services/private-host/auth.json'), true);
  assert.equal(isHardDenied('services/fleet-control/state.mjs'), true);
  assert.equal(isHardDenied('services/council/private/customer.json'), true);
  assert.equal(isHardDenied('pets/aiven/owner-data.json'), true);
  assert.equal(isHardDenied('pets/aiven/notes/secret.txt'), true);
  assert.equal(isHardDenied('private/passport/session.json'), true);
  assert.equal(isHardDenied('services/council/workflow.py'), false);
  assert.equal(isHardDenied('contracts/pet-collaboration/v1/envelope.json'), false);
  assert.equal(isHardDenied('pets/aiven/pet.json'), false);
});

test('unknown nested service scope fails the explicit allowlist override', async (t) => {
  const f = await fixture('services/private-host/secret.txt', 'not actually public\n');
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('HARD_DENY'));
});

test('a symlink that could escape the public tree is rejected', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await symlink('/etc/hosts', join(f.stage, 'linked.md'));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('SYMLINK'));
});

test('secret-looking provider tokens fail even if Git and SHA match', async (t) => {
  const secret = 'sk-proj-' + 'A'.repeat(30);
  const f = await fixture('README.md', 'Example fixture secret: ' + secret + '\n');
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('SECRET_MATCH'));
});

test('unreviewed long credential assignments fail even with source digest match', async (t) => {
  const f = await fixture('README.md', 'client_secret = "' + 'z'.repeat(32) + '"\n');
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('SECRET_MATCH'));
});

test('changed staged bytes cannot pass the reviewed digest', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await writeFile(f.stagedFile, '{"id":"other"}\n');
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('HASH_MISMATCH'));
});

test('approved staged digest cannot override a different pinned Git blob', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  const replacement = '{"id":"other"}\n';
  await writeFile(f.stagedFile, replacement);
  f.allowlist.files[0].sha256 = sha256(Buffer.from(replacement));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('SOURCE_MISMATCH'));
});

test('source checkout must be clean, not a working draft', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await writeFile(join(f.repo, 'untracked.md'), 'local-only\n');
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('DIRTY_SOURCE'));
});

test('an unrelated Git origin cannot masquerade as the submission source', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  execFileSync('git', ['-C', f.repo, 'remote', 'set-url', 'origin', 'https://github.com/SalesSquad/chibi.git']);
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('SOURCE_ORIGIN'));
});

test('source revision mismatch invalidates earlier review receipts', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  f.allowlist.sourceRevision = '0'.repeat(40);
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('STALE_SOURCE'));
});

test('path traversal and allowlist case-fold collisions fail', () => {
  assert.throws(() => assertSafePath('../ops/a.json'), blocked('INVALID_PATH'));
  assert.throws(() => assertSafePath('pets\\aiven\\pet.json'), blocked('INVALID_PATH'));
  const base = {
    schemaVersion: 1,
    sourceRepository: 'SalesSquad/junction-pets',
    sourceRevision: 'a'.repeat(40),
    files: [
      { path: 'README.md', sha256: 'a'.repeat(64) },
      { path: 'readme.md', sha256: 'a'.repeat(64) }
    ]
  };
  assert.throws(() => validateAllowlist(base), blocked('DUPLICATE_PATH'));
});

test('a 2MiB+ staged artifact is rejected by metadata before content loading', async (t) => {
  const f = await fixture('README.md', 'small\n');
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await writeFile(f.stagedFile, 'x'.repeat(2 * 1024 * 1024 + 1));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('TOO_LARGE'));
});

test('directory fanout is bounded before untrusted tree enumeration grows unbounded', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await mkdir(join(f.stage, 'tests'));
  for (let i = 0; i < 60; i++) {
    await mkdir(join(f.stage, 'tests', 'extra-' + String(i).padStart(2, '0')));
  }
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('TOO_MANY_ENTRIES'));
});

test('submission root symlinks are rejected', async (t) => {
  const f = await fixture();
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  const alias = join(f.outer, 'alias');
  await symlink(f.stage, alias);
  await assert.rejects(verifySubmission({
    treeDir: alias, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('INVALID_ROOT'));
});

test('binary payloads and oversized text remain unreviewed by default', async (t) => {
  const f = await fixture('README.md', 'valid text\n');
  t.after(() => rm(f.outer, { recursive: true, force: true }));
  await writeFile(f.stagedFile, Buffer.from([0x00, 0xff]));
  f.allowlist.files[0].sha256 = sha256(await readFile(f.stagedFile));
  await assert.rejects(verifySubmission({
    treeDir: f.stage, sourceRepo: f.repo, allowlist: f.allowlist
  }), blocked('INVALID_TEXT'));
});
