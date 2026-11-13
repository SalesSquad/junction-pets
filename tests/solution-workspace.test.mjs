import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, readFile, rm} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createSolution, checkSolutions, briefSolution, validateSolution} from '../scripts/solution-workspace.mjs';

const sha = 'a'.repeat(40);
const agent = {id: 'junction.meta', company: {slug: 'meta'}, capabilities: [{id: 'sdk-check'}]};
async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'solution-workspace-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  await mkdir(path.join(root, 'pets', 'meta'), {recursive: true});
  await mkdir(path.join(root, 'solutions'));
  await writeFile(path.join(root, 'pets', 'meta', 'pet.json'), JSON.stringify(agent));
  return root;
}

test('new solution can be discovered and handed to a developer without the original chat', async (t) => {
  const root = await fixture(t);
  await createSolution(root, {id: 'find-verify', agent: 'meta', challenge: 'meta', baseCommit: sha});
  const solutions = await checkSolutions(root);
  assert.equal(solutions.length, 1);
  const brief = await briefSolution(root, 'find-verify');
  assert.ok(brief.readFirst.includes('pets/meta/CHALLENGE_RESEARCH.md'));
  assert.ok(brief.readFirst.includes('solutions/find-verify/PROGRESS.md'));
  assert.match(brief.execution, /no worker or runtime/);
  const instructions = await readFile(path.join(root, 'solutions/find-verify/AGENTS.md'), 'utf8');
  assert.match(instructions, /solutions\/find-verify\//);
  assert.match(instructions, /explicit integrator ownership/);
});

test('a product may exist without a selected competition', async (t) => {
  const root = await fixture(t);
  const value = await createSolution(root, {id: 'new-product', agent: 'meta', baseCommit: sha});
  assert.deepEqual(value.challengeSlugs, []);
  assert.match(await readFile(path.join(root, 'solutions/new-product/README.md'), 'utf8'), /no competition selected/);
});

test('repeated scaffolding preserves all existing product work', async (t) => {
  const root = await fixture(t);
  const args = {id: 'find-verify', agent: 'meta', baseCommit: sha};
  await createSolution(root, args);
  const file = path.join(root, 'solutions/find-verify/README.md');
  await writeFile(file, 'valuable user changes');
  await assert.rejects(createSolution(root, args), /EEXIST/);
  assert.equal(await readFile(file, 'utf8'), 'valuable user changes');
});

test('unsafe IDs and unknown agents/challenges cannot create a workspace', async (t) => {
  const root = await fixture(t);
  for (const id of ['../escape', '/tmp/escape', 'Upper', 'bad\nname']) {
    await assert.rejects(createSolution(root, {id, agent: 'meta', baseCommit: sha}));
  }
  await assert.rejects(createSolution(root, {id: 'unknown', agent: 'missing', baseCommit: sha}), /Unknown agent/);
  await assert.rejects(createSolution(root, {id: 'unknown', agent: 'meta', challenge: 'missing', baseCommit: sha}), /Unknown challenge/);
  assert.deepEqual(await checkSolutions(root), []);
});

test('capability composition must refer to a selected, actually declared capability', async (t) => {
  const root = await fixture(t);
  const value = await createSolution(root, {id: 'composition', agent: 'meta', baseCommit: sha});
  value.capabilityUses = [{agentId: 'junction.meta', capabilityId: 'sdk-check', purpose: 'Check SDK assumptions', status: 'planned'}];
  validateSolution(value, [agent]);
  const bad = structuredClone(value);
  bad.capabilityUses[0].capabilityId = 'imaginary-live-camera';
  assert.throws(() => validateSolution(bad, [agent]), /Unknown or unselected/);
  const escalation = structuredClone(value);
  escalation.capabilityUses[0].status = 'authorized';
  assert.throws(() => validateSolution(escalation, [agent]), /not execution receipts/);
  const duplicate = structuredClone(value);
  duplicate.capabilityUses.push(duplicate.capabilityUses[0]);
  assert.throws(() => validateSolution(duplicate, [agent]), /Duplicate capability/);
});

test('a workspace cannot silently claim shared source or change its directory identity', async (t) => {
  const root = await fixture(t);
  const value = await createSolution(root, {id: 'bounded', agent: 'meta', baseCommit: sha});
  assert.throws(() => validateSolution({...value, ownedPaths: ['services/']}, [agent]), /ownership/);
  assert.throws(() => validateSolution({...value, id: 'different'}, [agent], 'bounded'), /identity/);
  assert.throws(() => validateSolution({...value, baseCommit: 'main'}, [agent]), /exact base commit/);
  value.unrecognizedAuthority = true;
  assert.throws(() => validateSolution(value, [agent]), /Unexpected/);
});
