import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {evaluateLedger} from './ledger.mjs';

const template = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url), 'utf8'));
const fresh = () => structuredClone(template);
const fakeLogSha = 'a'.repeat(64);

test('pinned official source and synthetic outcomes remain explicit, not accepted', () => {
  const out = evaluateLedger(fresh());
  assert.equal(out.source.headSha, '9df83c38409c8bfad0517aebffe48211eda4a5b4');
  assert.equal(out.metrics.refused, 2);
  assert.equal(out.reviewer.outcome, 'AWAITING_HUMAN');
  assert.deepEqual(out.refusals[0].reasons, ['SYNTHETIC_ONLY']);
  assert.deepEqual(out.refusals[1].reasons, ['NON_DISCRIMINATING_CHECK', 'SYNTHETIC_ONLY']);
  assert.equal(out.boundaries.checksExecutedHere, false);
});

test('base and head both PASS never support a fix, even with a declared log', () => {
  const v = fresh();
  v.checks[1].evidenceClass = 'self-reported-run';
  v.checks[1].logSha256 = fakeLogSha;
  const out = evaluateLedger(v);
  assert.ok(out.refusals.find(x => x.claimId === 'C-FALSE-ASSURANCE').reasons.includes('NON_DISCRIMINATING_CHECK'));
});

test('stale check SHA is refused; accepting cannot bypass the refusal', () => {
  const v = fresh();
  v.checks[0].baseSha = 'b'.repeat(40);
  v.reviewer.decision = 'accept';
  const out = evaluateLedger(v);
  assert.ok(out.refusals[0].reasons.includes('STALE_SOURCE_SHA'));
  assert.equal(out.reviewer.outcome, 'UNSUPPORTED_ACCEPTANCE_REFUSED');
});

test('missing check reference is refused', () => {
  const v = fresh();
  v.claims[0].checkIds = ['ABSENT'];
  assert.deepEqual(evaluateLedger(v).refusals[0].reasons, ['MISSING_CHECK']);
});

test('wrong requirement is refused', () => {
  const v = fresh();
  v.checks[0].requirementId = 'OTHER';
  assert.ok(evaluateLedger(v).refusals[0].reasons.includes('WRONG_REQUIREMENT'));
});

test('self-reported evidence needs a log hash and remains human-reviewable', () => {
  const v = fresh();
  v.claims = [v.claims[0]];
  v.checks = [v.checks[0]];
  v.checks[0].evidenceClass = 'self-reported-run';
  assert.deepEqual(evaluateLedger(v).refusals[0].reasons, ['MISSING_LOG_DIGEST']);
  v.checks[0].logSha256 = fakeLogSha;
  const out = evaluateLedger(v);
  assert.equal(out.claims[0].status, 'READY_FOR_HUMAN');
  assert.equal(out.metrics.refused, 0);
  assert.equal(out.boundaries.receiptSignaturesVerified, false);
});

test('named human decision is recorded only for reviewable declarations, not externally authorized', () => {
  const v = fresh();
  v.claims = [v.claims[0]];
  v.checks = [v.checks[0]];
  v.checks[0].evidenceClass = 'self-reported-run';
  v.checks[0].logSha256 = fakeLogSha;
  v.reviewer.decision = 'accept';
  const out = evaluateLedger(v);
  assert.equal(out.reviewer.outcome, 'HUMAN_ACCEPTANCE_RECORDED_UNAUTHENTICATED');
  assert.equal(out.boundaries.codeChangeApproved, false);
  v.reviewer.name = null;
  assert.equal(evaluateLedger(v).reviewer.outcome, 'REVIEWER_ID_MISSING');
});

test('invalid and ambiguous structures are rejected, not silently coerced', () => {
  const v = fresh();
  v.checks[0].extra = 'ignore me';
  assert.throws(() => evaluateLedger(v), /shape/);
  const q = fresh();
  q.claims.push(structuredClone(q.claims[0]));
  assert.throws(() => evaluateLedger(q), /Duplicate/);
  const r = fresh();
  r.sample.headSha = r.sample.baseSha;
  assert.throws(() => evaluateLedger(r), /Same base/);
});
