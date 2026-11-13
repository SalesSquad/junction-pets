import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {loadPackages} from '../lib/catalog.mjs';
import {sha256} from '../lib/artifact.mjs';
import {buildCaseManifest, verifyCaseManifest, assessSubmittedResponse, assessSubmissions} from '../lib/behavior-eval.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const packs = await loadPackages(root);
const SOURCE = 'a'.repeat(40); // Synthetic exact-shape SHA, never claimed as a real source commit.
const manifest = buildCaseManifest(packs, {sourceCommit: SOURCE});

function submissionFor(target, {response = 'A synthetic example with context and evidence.', kind = 'synthetic'} = {}) {
  const responseSha256 = sha256(response);
  return {
    schemaVersion: 1,
    caseId: target.id,
    caseSha256: target.caseSha256,
    sourceCommit: SOURCE,
    runId: 'controlled-fixture-001',
    execution: {kind, provider: kind === 'synthetic' ? 'synthetic' : 'example-model', model: 'fixture-only', invocationId: 'fixture-00001', completedAt: '2026-11-12T18:00:00Z'},
    response: {text: response, sha256: responseSha256},
    adjudication: {
      reviewerId: 'test-fixture-reviewer',
      method: 'human',
      reviewedAt: '2026-11-12T18:01:00Z',
      responseSha256,
      mustInclude: target.mustInclude.map(criterion => ({criterion, met: true, evidence: 'Fixture review only; criterion judged satisfied in synthetic data.'})),
      mustNotClaim: target.mustNotClaim.map(criterion => ({criterion, violated: false, evidence: 'Fixture review only; no prohibited claim in synthetic response.'})),
    },
  };
}

test('all 34 company packages expose 204 authored and zero executed cases', () => {
  assert.equal(packs.length, 34);
  assert.equal(manifest.cases.length, 204);
  assert.equal(manifest.authoredCases, 204);
  assert.equal(manifest.executedCases, 0);
  assert.equal(manifest.evidenceLevel, 'definitions-only');
  assert.equal(new Set(manifest.cases.map(item => item.id)).size, 204);
  assert.equal(new Set(manifest.cases.map(item => item.petSlug)).size, 34);
  for (const target of manifest.cases) {
    assert.match(target.caseSha256, /^[a-f0-9]{64}$/);
    assert.match(target.packageSha256, /^[a-f0-9]{64}$/);
    assert.ok(target.mustInclude.length && target.mustNotClaim.length);
  }
});

test('case manifest is deterministic regardless of filesystem enumeration order', () => {
  const reversed = buildCaseManifest([...packs].reverse(), {sourceCommit: SOURCE});
  assert.deepEqual(reversed, manifest);
  assert.deepEqual(verifyCaseManifest(manifest, packs, {expectedSourceCommit: SOURCE}), manifest);
});

test('unbound source manifests preserve absent verification', () => {
  const unbound = buildCaseManifest(packs);
  assert.equal(unbound.source.commit, null);
  assert.equal(unbound.executedCases, 0);
  assert.throws(() => assessSubmittedResponse(unbound, submissionFor(manifest.cases[0])), /Unbound or stale/);
});

test('source or rubric drift cannot reuse old case manifests', () => {
  assert.throws(() => verifyCaseManifest(manifest, packs, {expectedSourceCommit: 'b'.repeat(40)}), /Stale source/);
  const changed = structuredClone(manifest);
  changed.cases[0].prompt += ' Altered.';
  assert.throws(() => verifyCaseManifest(changed, packs), /no longer matches/);
  const sourceChanged = structuredClone(packs);
  sourceChanged[0].instructions += '\nUpdated runtime guidance.';
  assert.throws(() => verifyCaseManifest(manifest, sourceChanged), /no longer matches/);
});

test('a complete synthetic adjudication can only be a candidate, never qualified', () => {
  const result = assessSubmittedResponse(manifest, submissionFor(manifest.cases[0]));
  assert.equal(result.assessment, 'candidate-pass');
  assert.equal(result.synthetic, true);
  assert.equal(result.evidenceLevel, 'supplied-unverified');
  assert.equal(result.providerInvocationVerified, false);
  assert.equal(result.qualified, false);
});

test('violating a prohibited claim fails despite all positive criteria being marked met', () => {
  const data = submissionFor(manifest.cases[0]);
  data.adjudication.mustNotClaim[0].violated = true;
  data.adjudication.mustNotClaim[0].evidence = 'Synthetic reviewer found a purported operation with no authorized tool evidence.';
  const result = assessSubmittedResponse(manifest, data);
  assert.equal(result.assessment, 'fail');
  assert.deepEqual(result.violatedSafetyCriteria, [manifest.cases[0].mustNotClaim[0]]);
  assert.equal(result.qualified, false);
});

test('missing explicit per-criterion safety adjudication rejects the transcript', () => {
  const data = submissionFor(manifest.cases[0]);
  data.adjudication.mustNotClaim.pop();
  assert.throws(() => assessSubmittedResponse(manifest, data), /Missing mustNotClaim adjudications/);
});

test('response edits, changed source and changed rubrics invalidate submitted reviews', () => {
  const target = manifest.cases[0];
  const data = submissionFor(target);
  data.response.text += ' Edited without re-review.';
  assert.throws(() => assessSubmittedResponse(manifest, data), /Response SHA mismatch/);
  data.response.sha256 = sha256(data.response.text);
  assert.throws(() => assessSubmittedResponse(manifest, data), /Adjudication is not bound/);
  const changedSource = submissionFor(target);
  changedSource.sourceCommit = 'b'.repeat(40);
  assert.throws(() => assessSubmittedResponse(manifest, changedSource), /Unbound or stale/);
  const changedCase = submissionFor(target);
  changedCase.caseSha256 = '0'.repeat(64);
  assert.throws(() => assessSubmittedResponse(manifest, changedCase), /Stale or forged/);
});

test('reordered and unexplained semantic verdicts are rejected', () => {
  const target = manifest.cases[0];
  const changed = submissionFor(target);
  changed.adjudication.mustInclude.reverse();
  assert.throws(() => assessSubmittedResponse(manifest, changed), /Changed or reordered/);
  const empty = submissionFor(target);
  empty.adjudication.mustInclude[0].evidence = 'ok';
  assert.throws(() => assessSubmittedResponse(manifest, empty), /Invalid adjudication evidence/);
  const provider = submissionFor(target);
  provider.execution.provider = 'openai';
  assert.throws(() => assessSubmittedResponse(manifest, provider), /Synthetic execution cannot claim provider work/);
});

test('submitted model transcripts are still self-reported and not provider-qualified', () => {
  const data = submissionFor(manifest.cases[0], {kind: 'model-response'});
  const assessed = assessSubmissions(manifest, [data]);
  assert.equal(assessed.reviewCandidates, 1);
  assert.equal(assessed.modelExecutionsVerified, 0);
  assert.equal(assessed.qualifiedPasses, 0);
  assert.equal(assessed.assessments[0].synthetic, false);
});

test('an adjudication cannot precede the response or hide a synthetic provider', () => {
  const data = submissionFor(manifest.cases[0]);
  data.adjudication.reviewedAt = '2026-11-12T17:59:59Z';
  assert.throws(() => assessSubmittedResponse(manifest, data), /predates execution/);
  const fake = submissionFor(manifest.cases[0], {kind: 'model-response'});
  fake.execution.provider = 'synthetic';
  assert.throws(() => assessSubmittedResponse(manifest, fake), /non-synthetic provider/);
});

test('duplicate case responses in a batch cannot conceal conflicting reviews', () => {
  const data = submissionFor(manifest.cases[0]);
  assert.throws(() => assessSubmissions(manifest, [data, data]), /Duplicate case response/);
});

test('an unknown fake case and a missing reviewer are rejected', () => {
  const data = submissionFor(manifest.cases[0]);
  data.caseId = 'junction.ghost/never-ran';
  assert.throws(() => assessSubmittedResponse(manifest, data), /Unknown evaluation case/);
  const missingReviewer = submissionFor(manifest.cases[0]);
  delete missingReviewer.adjudication.reviewerId;
  assert.throws(() => assessSubmittedResponse(manifest, missingReviewer), /Invalid reviewer ID/);
});
