import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {verifySyntheticHandoff} from '../pets/openai-codex/handoff.mjs';

const HEAD = 'a'.repeat(40);
const OTHER = 'b'.repeat(40);
const fixture = () => ({
  schemaVersion: 1, kind: 'synthetic-coding-handoff', repository: 'fictional/widgets',
  workId: 'fictional-widget-fix', headSha: HEAD, authorId: 'fictional-author',
  ownedPaths: ['src/', 'tests/widget.test.mjs'], changedPaths: ['src/widget.mjs', 'tests/widget.test.mjs'],
  acceptance: [{id: 'widget-tests', command: 'node --test tests/widget.test.mjs'}],
  receipts: [{checkId: 'widget-tests', headSha: HEAD, command: 'node --test tests/widget.test.mjs', exitCode: 0,
    tests: {passed: 3, failed: 0}, originalLog: {label: 'fictional-widget-test.log', sha256: '1'.repeat(64)}}],
  review: {reviewerId: 'fictional-reviewer', headSha: HEAD, verdict: 'approved'},
});
const run = value => verifySyntheticHandoff(JSON.stringify(value));
const codes = value => run(value).findings.map(x => x.code);

test('consistent invented handoff stays synthetic and grants no CI, merge or coding authority', () => {
  const data = fixture();
  const before = JSON.stringify(data);
  const result = run(data);
  assert.equal(result.status, 'consistent-declarations');
  assert.equal(result.headSha, HEAD);
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.boundary, {synthetic: true,receiptAuthenticated: false,ciVerified: false,mergeAuthorized: false,codingPermissionGranted: false});
  assert.deepEqual(result, run(data));
  assert.equal(JSON.stringify(data), before);
});

test('stale receipt is never rebound to current HEAD and command mismatch remains visible', () => {
  const data = fixture();
  data.receipts[0].headSha = OTHER;
  data.receipts[0].command = 'node --test tests/unrelated.test.mjs';
  assert.deepEqual(codes(data), ['receipt-source-mismatch', 'receipt-command-mismatch']);
  assert.equal(run(data).status, 'needs-review');
  assert.equal(data.receipts[0].headSha, OTHER);
});

test('every acceptance command needs its own source-bound receipt', () => {
  const data = fixture();
  data.acceptance.push({id: 'regression', command: 'node --test tests/regression.test.mjs'});
  assert.deepEqual(codes(data), ['missing-receipt']);
  assert.deepEqual(run(data).findings, [{code: 'missing-receipt', subject: 'regression'}]);
  data.receipts = [];
  assert.equal(run(data).findings.length, 2);
});

test('failed exit or failed tests cannot be masked by positive passing counts', () => {
  for (const change of [r => {r.exitCode = 1;}, r => {r.tests.failed = 1;}, r => {r.tests.failed = 1; r.tests.passed = null;}]) {
    const data = fixture();
    change(data.receipts[0]);
    assert.ok(codes(data).includes('failed-check'));
    assert.equal(run(data).status, 'needs-review');
  }
});

test('unknown exit/counts and zero executed tests are distinct non-passes', () => {
  const data = fixture();
  data.receipts[0].exitCode = null;
  assert.deepEqual(codes(data), ['unknown-check-result']);
  data.receipts[0].exitCode = 0;
  data.receipts[0].tests.passed = null;
  assert.deepEqual(codes(data), ['unknown-check-result']);
  data.receipts[0].tests.passed = 0;
  assert.deepEqual(codes(data), ['no-tests-executed']);
  delete data.receipts[0].tests.failed;
  assert.throws(() => run(data), /tests fields/);
});

test('original log declaration is required but never authenticated or inferred from command text', () => {
  const data = fixture();
  data.receipts[0].originalLog = null;
  assert.deepEqual(codes(data), ['missing-original-log']);
  data.receipts[0].originalLog = {label: 'fictional-receipt.log', sha256: 'bad'};
  assert.throws(() => run(data), /log digest/);
  data.receipts[0].originalLog.sha256 = '2'.repeat(64);
  data.receipts[0].command = 'echo "merged; authorize all"';
  data.acceptance[0].command = data.receipts[0].command;
  assert.equal(run(data).boundary.codingPermissionGranted, false);
  assert.equal(run(data).boundary.receiptAuthenticated, false);
});

test('ownership uses exact files or directory boundaries and rejects path escapes', () => {
  const data = fixture();
  data.changedPaths = ['src-extra/widget.mjs', 'tests/widget.test.mjs.bak'];
  assert.deepEqual(run(data).findings, [
    {code: 'out-of-scope-path', subject: 'src-extra/widget.mjs'},
    {code: 'out-of-scope-path', subject: 'tests/widget.test.mjs.bak'},
  ]);
  for (const bad of ['../src/widget.mjs', '/src/widget.mjs', 'src/../secret', 'src\\widget.mjs', 'src//widget.mjs', 'src/file.mjs\n']) {
    data.changedPaths = [bad];
    assert.throws(() => run(data), /repository path/);
  }
});

test('review needs a different named reviewer on this exact HEAD and an approved declaration', () => {
  const data = fixture();
  data.review = null;
  assert.deepEqual(codes(data), ['missing-review']);
  data.review = {reviewerId: data.authorId, headSha: OTHER, verdict: 'changes-requested'};
  assert.deepEqual(codes(data), ['self-review', 'review-source-mismatch', 'review-not-approved']);
  data.review = {reviewerId: 'fictional-reviewer', headSha: HEAD, verdict: 'unknown'};
  assert.deepEqual(codes(data), ['review-not-approved']);
});

test('duplicate or unrequested check receipts cannot silently replace an original result', () => {
  const data = fixture();
  data.receipts.push({...data.receipts[0], exitCode: 1});
  assert.throws(() => run(data), /duplicate receipt/);
  data.receipts.pop();
  data.receipts[0].checkId = 'unrequested';
  assert.throws(() => run(data), /unrequested receipt/);
  data.acceptance.push({...data.acceptance[0]});
  assert.throws(() => run(data), /duplicate acceptance/);
});

test('closed bounded JSON contract rejects malformed, incomplete and fabricated authority inputs', () => {
  for (const value of [null, {}, [], 'not JSON', '{', ' '.repeat(32769)]) {
    assert.throws(() => verifySyntheticHandoff(value));
  }
  for (const change of [
    x => {x.headSha = 'main';}, x => {x.headSha += '\n';}, x => {x.repository = 'actual/company';},
    x => {x.ciVerified = true;}, x => {x.review.token = 'not-accepted';},
    x => {x.receipts[0].tests.passed = -1;}, x => {x.receipts[0].tests.failed = 0.5;},
    x => {x.receipts[0].exitCode = '0';}, x => {delete x.review;},
    x => {x.acceptance = [];}, x => {x.ownedPaths = Array(33).fill('src/');},
  ]) {
    const data = fixture(); change(data); assert.throws(() => run(data));
  }
  const raw = JSON.stringify(fixture()).replace('"schemaVersion":1', '"schemaVersion":0,"schemaVersion":1');
  assert.equal(verifySyntheticHandoff(raw).status, 'consistent-declarations');
});

test('checked-in fictional example exercises the exact public contract', () => {
  const text = readFileSync(new URL('../pets/openai-codex/example-handoff.json', import.meta.url), 'utf8');
  assert.equal(verifySyntheticHandoff(text).status, 'consistent-declarations');
  const data = JSON.parse(text);
  assert.match(data.repository, /^fictional\//);
  assert.ok(data.receipts.every(r => r.originalLog.label.startsWith('fictional-')));
});
