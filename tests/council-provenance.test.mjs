import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyCouncilProvenance } from '../scripts/check-council-provenance.mjs';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PINNED = {
  prototypeCommit: '8531f3cfb364121314c014e8ec8a72d84c82388e',
  workflowBlob: 'db5755c00080aff6fa0e7aee76685d6f42de265d',
  serviceBlob: '1427a7761bf7e766901955485701d8168a1909b5',
  foundationCommit: 'fcb5ef8bf731b72fd557f3c326adbc58f18da8f7',
  licenseSha256: 'b4831843132a1942db41e3efc2714d27ad598425b7bd8176afcbe14d1cb53c18'
};

async function makeFixture() {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-council-provenance-'));
  await mkdir(resolve(root, 'services/council'), { recursive: true });
  await cp(resolve(REPO, 'services/council/upstream-provenance.json'), resolve(root, 'services/council/upstream-provenance.json'));
  await cp(resolve(REPO, 'services/council/README.md'), resolve(root, 'services/council/README.md'));
  await cp(resolve(REPO, 'services/council/LICENSE-UPSTREAM'), resolve(root, 'services/council/LICENSE-UPSTREAM'));
  return root;
}

test('pinned upstream refs and MIT notice remain stable', async () => {
  const manifest = JSON.parse(await readFile(resolve(REPO, 'services/council/upstream-provenance.json'), 'utf8'));
  assert.equal(manifest.prototype.commit, PINNED.prototypeCommit);
  assert.equal(manifest.prototype.files.find(file => file.path === 'workflow.py')?.blobSha, PINNED.workflowBlob);
  assert.equal(manifest.prototype.files.find(file => file.path === 'service.py')?.blobSha, PINNED.serviceBlob);
  assert.equal(manifest.foundation.commit, PINNED.foundationCommit);
  assert.equal(manifest.license.sha256, PINNED.licenseSha256);

  const result = await verifyCouncilProvenance(REPO);
  assert.equal(result.status, 'pass');
  assert.equal(result.scope, 'local-record-consistency-only');
  assert.equal(result.prototypeFiles, 2);
});

test('fails when README provenance references drift', async t => {
  const root = await makeFixture();
  t.after(() => rm(root, { recursive: true, force: true }));
  const path = resolve(root, 'services/council/README.md');
  const readme = await readFile(path, 'utf8');
  await writeFile(path, readme.replace(PINNED.workflowBlob, '0'.repeat(40)));
  await assert.rejects(verifyCouncilProvenance(root), /README is missing the pinned blob ref for workflow\.py/);
});

test('fails when the upstream MIT notice changes', async t => {
  const root = await makeFixture();
  t.after(() => rm(root, { recursive: true, force: true }));
  const path = resolve(root, 'services/council/LICENSE-UPSTREAM');
  await writeFile(path, (await readFile(path, 'utf8')) + 'changed\n');
  await assert.rejects(verifyCouncilProvenance(root), /local upstream license does not match its pinned MIT SHA-256/);
});

test('rejects an unreviewed license path from the manifest', async t => {
  const root = await makeFixture();
  t.after(() => rm(root, { recursive: true, force: true }));
  const path = resolve(root, 'services/council/upstream-provenance.json');
  const manifest = JSON.parse(await readFile(path, 'utf8'));
  manifest.license.localPath = '../../outside.txt';
  await writeFile(path, JSON.stringify(manifest, null, 2) + '\n');
  await assert.rejects(verifyCouncilProvenance(root), /license paths must match the reviewed source and local notice/);
});
