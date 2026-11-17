import test from 'node:test';
import assert from 'node:assert/strict';
import {checkPlan, checkReceipt, inScope} from './run.mjs';

const sha = 'a'.repeat(40);
const lane = (id, owned) => ({id, objective: 'Do one bounded thing well.', owned_paths: owned});

test('plan: rejects overlapping owned paths, bad ids and short SHAs', () => {
  assert.throws(() => checkPlan({source: sha, lanes: [lane('one', ['pets/a/']), lane('two', ['pets/a/x.md'])]}), /overlaps/);
  assert.throws(() => checkPlan({source: sha, lanes: [lane('Bad Id', ['pets/a/'])]}), /bad or duplicate/);
  assert.throws(() => checkPlan({source: 'abc', lanes: [lane('one', ['pets/a/'])]}), /full commit SHA/);
  assert.throws(() => checkPlan({source: sha, lanes: [lane('one', ['../etc'])]}), /bad owned path/);
  const ok = checkPlan({source: sha, lanes: [lane('one', ['pets/a/']), lane('two', ['pets/b/'])]});
  assert.equal(ok.lanes[0].engine, 'claude');
});

test('scope: directory prefixes and exact files', () => {
  assert.ok(inScope('pets/a/guide.md', ['pets/a/']));
  assert.ok(!inScope('pets/ab/guide.md', ['pets/a/']));
  assert.ok(inScope('docs/x.md', ['docs/x.md']));
  assert.ok(!inScope('docs/x.md.bak', ['docs/x.md']));
  assert.ok(inScope('docs/x/y.md', ['docs/x']));
});

test('receipt: exact keys and types', () => {
  const good = {summary: 's', changed_paths: [], checks_run: [], risks: [], blocked: false, blocker: null};
  assert.deepEqual(checkReceipt(good), []);
  assert.ok(checkReceipt({...good, extra: 1}).length);
  assert.ok(checkReceipt({...good, blocker: 3}).length);
  assert.ok(checkReceipt(null).length);
});
