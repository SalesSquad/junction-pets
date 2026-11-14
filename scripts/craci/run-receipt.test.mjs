import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync, spawnSync} from 'node:child_process';
import {copyFile, link, mkdir, mkdtemp, open, readFile, readdir, rm, symlink, writeFile, appendFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {LIMITS} from './run-receipt.mjs';
import {validateRun} from '../../services/experiment-registry/registry.mjs';

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const hash = value => createHash('sha256').update(value).digest('hex');
const json = async path => JSON.parse(await readFile(path, 'utf8'));
function git(root, args) {
  return execFileSync('git', ['-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', '-C', root, ...args],
    {encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).trim();
}
async function commit(root) {
  git(root, ['init', '--quiet', '--initial-branch=main']);
  git(root, ['add', '.']);
  git(root, ['-c', 'user.name=Synthetic Receipt Test', '-c', 'user.email=receipt@example.invalid', 'commit', '--quiet', '-m', 'synthetic source']);
  return git(root, ['rev-parse', 'HEAD']);
}
async function fixture(t) {
  const base = await mkdtemp(join(tmpdir(), 'craci-receipt-test-'));
  t.after(() => rm(base, {recursive: true, force: true}));
  const source = join(base, 'source'), harness = join(base, 'harness'), evidence = join(base, 'evidence');
  await mkdir(source); await mkdir(harness);
  await writeFile(join(source, 'fixture.json'), '{"synthetic":true}\n');
  await writeFile(join(source, 'global.json'), '{"sdk":{"version":"9.0.100"}}\n');
  for (const path of ['scripts/craci/run-receipt.mjs', 'services/experiment-registry/registry.mjs', 'lib/artifact.mjs']) {
    await mkdir(dirname(join(harness, path)), {recursive: true});
    await copyFile(join(repository, path), join(harness, path));
  }
  const sourceSha = await commit(source), harnessSha = await commit(harness);
  return {base, source, harness, evidence, sourceSha, harnessSha,
    script: join(harness, 'scripts/craci/run-receipt.mjs'),
    env: {...process.env, RUNNER_TEMP: base, CRACI_RECEIPT_DIR: evidence,
      CRACI_SOURCE_ROOT: source, CRACI_SOURCE_SHA: sourceSha,
      CRACI_HARNESS_ROOT: harness, CRACI_HARNESS_SHA: harnessSha,
      CRACI_SOURCE_REPOSITORY: 'SalesSquad/junction-pets', GITHUB_REPOSITORY: 'SalesSquad/junction-pets',
      GITHUB_RUN_ID: '123456789', GITHUB_RUN_ATTEMPT: '1', GITHUB_OUTPUT: join(base, 'step-output'),
      CRACI_WORKLOAD: 'synthetic-test', CRACI_CELL: 'fixture-cell', CRACI_NEXT_OWNER: 'synthetic-owner',
      CRACI_ALLOWED_SOURCE_CHANGES: '[]', CRACI_JOB_STATUS: 'success', CRACI_STAGE_OUTCOME: 'success'}};
}
function invoke(f, operation, code) {
  return spawnSync(process.execPath, [f.script, operation, ...(code === undefined ? [] : ['--', process.execPath, '-e', code])],
    {env: f.env, cwd: f.source, encoding: 'utf8', timeout: 20000, maxBuffer: 16 * 1024 * 1024});
}
async function published(f) {
  const root = join(f.evidence, 'upload'), receipt = await json(join(root, 'receipt.json'));
  const manifest = await json(join(root, 'manifest.json'));
  const run = await json(join(root, receipt.registry.path));
  validateRun(run);
  assert.equal(run.evidence.receiptSha256, hash(await readFile(join(root, 'receipt.json'))));
  assert.equal(receipt.manifest.sha256, hash(await readFile(join(root, 'manifest.json'))));
  for (const file of manifest.files) {
    const contents = await readFile(join(root, file.path));
    assert.equal(contents.length, file.bytes); assert.equal(hash(contents), file.sha256);
  }
  return {root, receipt, manifest, run};
}

test('child exit 42 survives capture/finalize; receipts are immutable and registry-bound', async t => {
  const f = await fixture(t);
  const run = invoke(f, 'run', "process.stdout.write('synthetic out\\n');process.stderr.write('synthetic err\\n');process.exitCode=42;");
  assert.equal(run.status, 42, run.stderr); assert.equal(run.signal, null);
  assert.match(run.stdout, /synthetic out/); assert.match(run.stderr, /synthetic err/);
  f.env.CRACI_JOB_STATUS = 'failure'; f.env.CRACI_STAGE_OUTCOME = 'failure';
  assert.equal(invoke(f, 'finalize').status, 1);
  const first = await published(f);
  assert.equal(first.receipt.status, 'failed'); assert.equal(first.run.status, 'failed');
  assert.equal(first.receipt.command.exitCode, 42); assert.equal(first.receipt.command.signal, null);
  assert.equal(first.receipt.sourceVerified, true); assert.equal(first.receipt.harnessVerified, true);
  assert.equal(first.run.kind, 'synthetic-test'); assert.equal(first.run.evidence.level, 'source-reported');
  assert.equal(first.receipt.cost.actual, null); assert.equal(first.receipt.cost.estimate, null);
  assert.equal(first.receipt.nextOwner, 'synthetic-owner');
  assert.ok(first.receipt.command.wallSeconds >= 0); assert.equal(first.run.metrics[0].unit, 'seconds');
  const preserved = await readFile(join(first.root, 'receipt.json'));
  assert.equal(invoke(f, 'finalize').status, 1, 'Identical failure finalization must be idempotent');
  assert.deepEqual(await readFile(join(first.root, 'receipt.json')), preserved);
  await appendFile(join(f.evidence, 'command.stdout.log'), 'changed evidence\n');
  assert.equal(invoke(f, 'finalize').status, 2);
  assert.deepEqual(await readFile(join(first.root, 'receipt.json')), preserved);
  assert.match(await readFile(f.env.GITHUB_OUTPUT, 'utf8'), /upload_ready=false\n$/);
});

test('child SIGTERM is returned as the same signal and retained as a failed command', async t => {
  const f = await fixture(t);
  const run = invoke(f, 'run', "process.kill(process.pid,'SIGTERM')");
  assert.equal(run.status, null); assert.equal(run.signal, 'SIGTERM');
  f.env.CRACI_JOB_STATUS = 'failure'; f.env.CRACI_STAGE_OUTCOME = 'failure';
  assert.equal(invoke(f, 'finalize').status, 1);
  const {receipt, run: record} = await published(f);
  assert.equal(receipt.status, 'failed'); assert.equal(receipt.command.signal, 'SIGTERM');
  assert.equal(receipt.command.exitCode, null); assert.equal(record.status, 'failed');
});

test('wallSeconds agrees with independent command timestamps for a bounded delay', async t => {
  const f = await fixture(t);
  assert.equal(invoke(f, 'run', "setTimeout(() => process.stdout.write('synthetic timing sample\\n'), 150)").status, 0);
  const command = await json(join(f.evidence, 'command.json'));
  const timestampSeconds = (Date.parse(command.finishedAt) - Date.parse(command.startedAt)) / 1000;
  assert.ok(timestampSeconds >= 0.15, 'The child must execute its actual delayed workload');
  t.diagnostic('wallSeconds=' + command.wallSeconds + '; independent timestamp seconds=' + timestampSeconds);
  assert.ok(Math.abs(command.wallSeconds - timestampSeconds) <= 0.1,
    'The seconds metric must agree with independently recorded UTC endpoints within 100 ms');
  assert.equal(invoke(f, 'finalize').status, 0);
  const {receipt, run} = await published(f);
  assert.equal(receipt.command.wallSeconds, command.wallSeconds);
  assert.equal(run.metrics[0].unit, 'seconds');
  assert.equal(run.metrics[0].value, command.wallSeconds);
});

test('setup failure without checkout/command produces incomplete evidence, never zero cost or success', async t => {
  const f = await fixture(t);
  f.env.CRACI_SOURCE_ROOT = join(f.base, 'checkout-never-created');
  f.env.CRACI_JOB_STATUS = 'failure'; f.env.CRACI_STAGE_OUTCOME = 'skipped';
  assert.equal(invoke(f, 'finalize').status, 1);
  const {receipt, run} = await published(f);
  assert.equal(receipt.status, 'incomplete'); assert.equal(receipt.command, null);
  assert.equal(receipt.sourceVerified, false); assert.equal(receipt.provenance.after.source.observedCommit, null);
  assert.equal(run.source.commit, f.sourceSha, 'Only the explicitly requested pin is retained');
  assert.ok(run.limitations.some(value => value.includes('source verification failed')));
  assert.deepEqual(run.metrics, []); assert.equal(receipt.cost.actual, null);
  assert.ok(receipt.issues.includes('COMMAND_EVIDENCE_MISSING'));
});

test('wrong source pin and dirty harness block execution before any child effect', async t => {
  for (const variant of ['wrong-source', 'dirty-harness']) {
    await t.test(variant, async sub => {
      const f = await fixture(sub), marker = join(f.base, 'child-must-not-run');
      if (variant === 'wrong-source') f.env.CRACI_SOURCE_SHA = 'f'.repeat(40);
      else await appendFile(join(f.harness, 'lib/artifact.mjs'), '\n// synthetic tracked modification\n');
      const command = "require('node:fs').writeFileSync(" + JSON.stringify(marker) + ",'ran')";
      assert.equal(invoke(f, 'run', command).status, 2);
      await assert.rejects(readFile(marker), {code: 'ENOENT'});
      f.env.CRACI_JOB_STATUS = 'failure'; f.env.CRACI_STAGE_OUTCOME = 'failure';
      assert.equal(invoke(f, 'finalize').status, 1);
      const {receipt, run} = await published(f);
      assert.equal(receipt.status, 'incomplete'); assert.equal(receipt.command.state, 'blocked');
      assert.equal(run.status, 'incomplete');
    });
  }
});

test('explicit global.json overlays are hashed before and after; unexpected child edits invalidate provenance', async t => {
  const f = await fixture(t);
  f.env.CRACI_ALLOWED_SOURCE_CHANGES = '["global.json"]';
  await writeFile(join(f.source, 'global.json'), '{"sdk":{"version":"9.0.200"}}\n');
  assert.equal(invoke(f, 'run', "require('node:fs').writeFileSync('global.json','{\"sdk\":{\"version\":\"9.0.300\"}}\\n')").status, 0);
  assert.equal(invoke(f, 'finalize').status, 0);
  const {receipt} = await published(f);
  assert.equal(receipt.sourceVerified, true);
  assert.equal(receipt.provenance.after.source.basis, 'commit-with-allowed-overlays');
  const before = receipt.provenance.before.source, after = receipt.provenance.after.source;
  assert.notEqual(before.diffSha256, after.diffSha256);
  assert.notEqual(before.overlays[0].sha256, after.overlays[0].sha256);
  assert.equal(after.overlays[0].sha256, hash(await readFile(join(f.source, 'global.json'))));
  const altered = await fixture(t);
  assert.equal(invoke(altered, 'run', "require('node:fs').writeFileSync('fixture.json','{\"changed\":true}\\n')").status, 0);
  assert.equal(invoke(altered, 'finalize').status, 1);
  const invalid = await published(altered);
  assert.equal(invalid.receipt.status, 'incomplete'); assert.equal(invalid.receipt.sourceVerified, false);
  assert.ok(invalid.receipt.provenance.after.source.reasons.includes('UNEXPECTED_TRACKED_CHANGES'));
});

test('symlinks, hardlinks, unapproved files and oversized files never enter published staging', async t => {
  const f = await fixture(t);
  assert.equal(invoke(f, 'run', "process.stdout.write('synthetic safe log\\n')").status, 0);
  const artifacts = join(f.evidence, 'artifacts');
  await mkdir(artifacts);
  await writeFile(join(artifacts, 'safe.json'), '{"synthetic":true}\n');
  const outside = join(f.base, 'private-synthetic.txt');
  await writeFile(outside, 'DO_NOT_PUBLISH_SYNTHETIC_SECRET');
  await symlink(outside, join(artifacts, 'linked.json'));
  await symlink(f.base, join(artifacts, 'linked-directory'));
  await link(outside, join(artifacts, 'hardlinked.log'));
  await writeFile(join(artifacts, 'credentials.env'), 'DO_NOT_PUBLISH_SYNTHETIC_ENV');
  const huge = await open(join(artifacts, 'too-large.zip'), 'wx');
  await huge.truncate(LIMITS.fileBytes + 1); await huge.close();
  assert.equal(invoke(f, 'finalize').status, 1);
  const {receipt, manifest, root} = await published(f);
  assert.equal(receipt.status, 'incomplete'); assert.equal(manifest.complete, false);
  assert.deepEqual(await readdir(join(root, 'artifacts')), ['safe.json']);
  assert.ok(manifest.rejected.some(item => item.code === 'HARDLINK_REFUSED'));
  assert.ok(manifest.rejected.some(item => item.code === 'NONREGULAR_ARTIFACT'));
  assert.ok(manifest.rejected.some(item => item.code === 'ARTIFACT_NOT_WHITELISTED'));
  assert.ok(manifest.rejected.some(item => item.code === 'ARTIFACT_SIZE_OR_COUNT_LIMIT'));
  for (const file of manifest.files) assert.doesNotMatch(await readFile(join(root, file.path), 'utf8'), /DO_NOT_PUBLISH/);
  assert.match(await readFile(f.env.GITHUB_OUTPUT, 'utf8'), /upload_ready=true\n$/);
  assert.equal(await readFile(outside, 'utf8'), 'DO_NOT_PUBLISH_SYNTHETIC_SECRET', 'Raw source is preserved');
});

test('unexpected existing upload directory is not published or overwritten', async t => {
  const f = await fixture(t);
  assert.equal(invoke(f, 'run', 'process.exitCode=0').status, 0);
  await mkdir(join(f.evidence, 'upload'));
  await writeFile(join(f.evidence, 'upload', 'untrusted.json'), '{"mustNotUpload":true}\n');
  assert.equal(invoke(f, 'finalize').status, 2);
  assert.match(await readFile(f.env.GITHUB_OUTPUT, 'utf8'), /upload_ready=false\n$/);
  assert.deepEqual(await readdir(join(f.evidence, 'upload')), ['untrusted.json']);
});

test('a missing captured log cannot become a succeeded receipt', async t => {
  const f = await fixture(t);
  assert.equal(invoke(f, 'run', "process.stdout.write('synthetic result\\n')").status, 0);
  await rm(join(f.evidence, 'command.stderr.log'));
  assert.equal(invoke(f, 'finalize').status, 1);
  const {receipt, run} = await published(f);
  assert.equal(receipt.command.exitCode, 0);
  assert.equal(receipt.status, 'incomplete'); assert.equal(run.status, 'incomplete');
  assert.ok(receipt.issues.includes('COMMAND_LOG_EVIDENCE_MISSING_OR_INVALID'));
});

test('log capture is bounded and explicit, while the child exit result remains authoritative', async t => {
  const f = await fixture(t);
  const outputSize = LIMITS.logBytes + 4096;
  const result = invoke(f, 'run', "process.stdout.write(Buffer.alloc(" + outputSize + ",120));process.stderr.write(Buffer.alloc(" + outputSize + ",121));");
  assert.equal(result.status, 0, result.error?.message);
  assert.equal(Buffer.byteLength(result.stdout), LIMITS.logBytes);
  assert.equal(Buffer.byteLength(result.stderr), LIMITS.logBytes);
  assert.equal(invoke(f, 'finalize').status, 0);
  const {receipt} = await published(f);
  for (const name of ['stdout', 'stderr']) {
    assert.equal(receipt.command.output[name].observedBytes, outputSize);
    assert.equal(receipt.command.output[name].savedBytes, LIMITS.logBytes);
    assert.equal(receipt.command.output[name].truncated, true);
  }
});
