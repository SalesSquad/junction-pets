import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, realpath, chmod, mkdir, writeFile, readFile, readdir, rm, symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {sha256} from '../../lib/artifact.mjs';
import {recordPolicy} from './registry.mjs';
import {importInbox} from './inbox.mjs';

async function fixture(t) {
  const base = await mkdtemp(join(await realpath(tmpdir()), 'inbox-test-'));
  t.after(() => rm(base, {recursive: true, force: true}));
  const options = {inbox: join(base, 'inbox'), receiptsRoot: join(base, 'receipts'), root: join(base, 'registry')};
  for (const path of Object.values(options)) await mkdir(path, {mode: 0o700});
  async function emit(name = '001.json', id = 'apple.run-one', change = () => {}) {
    const bytes = JSON.stringify({runId: id, exitCode: 0, signedStatement: 'synthetic-test-only'});
    const digest = sha256(bytes);
    const envelope = {schemaVersion: 1, run: {
      schemaVersion: 1, runId: id, projectId: 'apple', taskId: 'apple.check', kind: 'apple-check',
      capturedAt: '2026-11-14T01:00:00Z', status: 'succeeded',
      source: {repository: 'SalesSquad/junction-pets', commit: '6e0bfe058f9e8ba1779b641ffdaeb39a9366a332'},
      evidence: {level: 'local-receipt-unverified', ref: 'ops/experiments/README.md', receiptSha256: digest},
      dataset: null, evaluation: null, artifact: null, metrics: [], limitations: ['Synthetic importer fixture'], policySha256: null
    }, receipt: {path: `${id}.json`, sha256: digest, runId: id}};
    await writeFile(join(options.receiptsRoot, envelope.receipt.path), bytes);
    change(envelope);
    await writeFile(join(options.inbox, name), JSON.stringify(envelope), {mode: 0o600});
    return envelope;
  }
  return {...options, options, emit};
}

test('creates metadata only, retains original envelope, and replays idempotently', async t => {
  const f = await fixture(t); const e = await f.emit();
  const before = await readFile(join(f.inbox, '001.json'));
  assert.equal((await importInbox(f.options)).created, 1);
  assert.equal((await importInbox(f.options)).existing, 1);
  assert.deepEqual(JSON.parse(await readFile(join(f.root, 'runs', `${e.run.runId}.json`))), e.run);
  assert.deepEqual(await readdir(f.root), ['runs']);
  assert.deepEqual(await readFile(join(f.inbox, '001.json')), before);
});

test('dry run validates without writing and detects existing conflicts', async t => {
  const f = await fixture(t); await f.emit();
  assert.equal((await importInbox({...f.options, dryRun: true})).validated, 1);
  assert.deepEqual(await readdir(f.root), []);
  await importInbox(f.options);
  await f.emit('001.json', 'apple.run-one', e => {e.run.status = 'failed';});
  assert.equal((await importInbox({...f.options, dryRun: true})).failed, 1);
  assert.equal((await importInbox(f.options)).failed, 1);
});

test('rejects receipt tamper and disagreement with either declared digest', async t => {
  const f = await fixture(t); const e = await f.emit();
  await writeFile(join(f.receiptsRoot, e.receipt.path), JSON.stringify({runId: e.run.runId, signedStatement: 'changed'}));
  assert.equal((await importInbox(f.options)).failed, 1);
  await f.emit('001.json', 'apple.run-one', e => {e.receipt.sha256 = 'a'.repeat(64);});
  assert.equal((await importInbox(f.options)).failed, 1);
});

test('rejects changed envelope and receipt run IDs', async t => {
  const f = await fixture(t);
  await f.emit('001.json', 'apple.run-one', e => {e.run.runId = 'apple.other';});
  assert.equal((await importInbox(f.options)).failed, 1);
  const e = await f.emit();
  const bytes = JSON.stringify({runId: 'apple.other'});
  await writeFile(join(f.receiptsRoot, e.receipt.path), bytes);
  e.receipt.sha256 = e.run.evidence.receiptSha256 = sha256(bytes);
  await writeFile(join(f.inbox, '001.json'), JSON.stringify(e));
  assert.equal((await importInbox(f.options)).failed, 1);
});

test('rejects traversal, file symlinks and parent-directory symlinks', async t => {
  const f = await fixture(t); const e = await f.emit();
  await f.emit('001.json', 'apple.run-one', e => {e.receipt.path = '../outside.json';});
  assert.equal((await importInbox(f.options)).failed, 1);
  await f.emit();
  await symlink(join(f.receiptsRoot, e.receipt.path), join(f.receiptsRoot, 'link.json'));
  await f.emit('001.json', 'apple.run-one', e => {e.receipt.path = 'link.json';});
  assert.equal((await importInbox(f.options)).failed, 1);
  await symlink(f.receiptsRoot, join(f.receiptsRoot, 'parent'));
  await f.emit('001.json', 'apple.run-one', e => {e.receipt.path = `parent/${e.receipt.path}`;});
  assert.equal((await importInbox(f.options)).failed, 1);
  await f.emit();
  await rm(join(f.inbox, '001.json'));
  await symlink(join(f.receiptsRoot, e.receipt.path), join(f.inbox, '001.json'));
  assert.equal((await importInbox(f.options)).failed, 1);
});

test('rejects missing, oversized, invalid JSON and non-regular receipt files', async t => {
  const f = await fixture(t); let e = await f.emit();
  await rm(join(f.receiptsRoot, e.receipt.path));
  assert.equal((await importInbox(f.options)).failed, 1);
  e = await f.emit();
  await writeFile(join(f.receiptsRoot, e.receipt.path), Buffer.alloc(4 * 1024 * 1024 + 1));
  assert.equal((await importInbox(f.options)).failed, 1);
  await f.emit();
  await writeFile(join(f.inbox, '001.json'), '{invalid');
  assert.equal((await importInbox(f.options)).failed, 1);
  await writeFile(join(f.inbox, '001.json'), Buffer.alloc(256 * 1024 + 1));
  assert.equal((await importInbox(f.options)).failed, 1);
  e = await f.emit(); await rm(join(f.receiptsRoot, e.receipt.path));
  await mkdir(join(f.receiptsRoot, e.receipt.path));
  assert.equal((await importInbox(f.options)).failed, 1);
});

test('rejects bad run schema and unsupported envelope fields without leaking them', async t => {
  const f = await fixture(t);
  await f.emit('001.json', 'apple.run-one', e => {e.run.privateRaw = 'SECRET-CONTENT';});
  const result = await importInbox(f.options);
  assert.equal(result.failed, 1);
  assert.ok(!JSON.stringify(result).includes('SECRET'));
  assert.ok(!JSON.stringify(result).includes(f.inbox));
});

test('aggregates mixed items in lexical order with bounded batch and nonzero failure', async t => {
  const f = await fixture(t);
  await f.emit('003.json', 'apple.run-three'); await f.emit('001.json');
  await writeFile(join(f.inbox, '002.json'), '{}');
  const first = await importInbox({...f.options, limit: 2});
  assert.equal(first.created, 0); assert.equal(first.failed, 1); assert.equal(first.exitCode, 1);
  assert.deepEqual(first.items, []); // Refuse silent starvation when the inbox exceeds its bound.
  const all = await importInbox(f.options);
  assert.equal(all.existing, 0); assert.equal(all.created, 2); assert.equal(all.failed, 1);
  const replay = await importInbox(f.options);
  assert.equal(replay.existing, 2); assert.equal(replay.created, 0); assert.equal(replay.failed, 1);
});

test('requires explicit receipts authority and sanitizes CLI errors', async t => {
  const f = await fixture(t); await f.emit();
  assert.equal((await importInbox({...f.options, receiptsRoot: undefined})).exitCode, 1);
  const cli = spawnSync(process.execPath, ['services/experiment-registry/inbox.mjs', '--inbox', f.inbox, '--root', f.root], {encoding: 'utf8'});
  assert.equal(cli.status, 1); assert.ok(!cli.stdout.includes(f.inbox)); assert.equal(cli.stderr, '');
});

test('model runs require preregistration and remain not-compared with exit 2', async t => {
  const f = await fixture(t);
  const h = 'a'.repeat(64);
  const policy = {schemaVersion: 1, policyId: 'apple.policy', taskId: 'apple.check', evaluationKind: 'vision-test', sampleSetSha256: h, protocolSha256: h, frozenAt: '2026-11-13T00:00:00Z', minSamples: 1, allowedEvidenceLevels: ['local-receipt-unverified'], metrics: [
    {id: 'accuracy', unit: 'rate', direction: 'higher', role: 'primary', minimumImprovement: 0, maxRegression: 0},
    {id: 'error-rate', unit: 'rate', direction: 'lower', role: 'safety', minimumImprovement: 0, maxRegression: 0}
  ]};
  const {canonicalJson} = await import('../../lib/artifact.mjs');
  await f.emit('001.json', 'apple.run-one', e => Object.assign(e.run, {
    kind: 'model-evaluation', policySha256: sha256(canonicalJson(policy)),
    dataset: {sha256: h, sampleSetSha256: h, split: 'holdout', sampleCount: 1, origin: 'synthetic'},
    evaluation: {kind: 'vision-test', protocolSha256: h, independentHoldout: true},
    artifact: {type: 'model-checkpoint', sha256: h},
    metrics: [{id: 'accuracy', value: 1, unit: 'rate', direction: 'higher', samples: 1}]
  }));
  assert.equal((await importInbox(f.options)).failed, 1);
  assert.equal((await importInbox({...f.options, dryRun: true})).failed, 1);
  await recordPolicy(f.root, policy);
  const dry = await importInbox({...f.options, dryRun: true});
  assert.equal(dry.exitCode, 2); assert.equal(dry.items[0].admission, 'not-compared');
  const saved = await importInbox(f.options);
  assert.equal(saved.created, 1); assert.equal(saved.exitCode, 2);
  assert.equal(saved.providerAttestationVerified, false);
});


test('rejects permissive inbox, symlinked approved roots, and null existing records', async t => {
  const f = await fixture(t); await f.emit();
  await chmod(f.inbox, 0o755);
  assert.equal((await importInbox(f.options)).exitCode, 1);
  await chmod(f.inbox, 0o700);
  const alias = join(f.root, 'receipt-alias');
  await symlink(f.receiptsRoot, alias);
  assert.equal((await importInbox({...f.options, receiptsRoot: alias})).exitCode, 1);
  await mkdir(join(f.root, 'runs'));
  await writeFile(join(f.root, 'runs', 'apple.run-one.json'), 'null');
  assert.equal((await importInbox({...f.options, dryRun: true})).failed, 1);
  assert.equal((await importInbox(f.options)).failed, 1);
});
