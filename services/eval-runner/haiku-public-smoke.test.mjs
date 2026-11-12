import test from 'node:test';
import assert from 'node:assert/strict';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
import {buildPublicPrompt, parseObservedClaudeResult} from './haiku-public-smoke.mjs';
import {listAivenPinnedSources} from '../pet-adapters/aiven/adapter.mjs';

const run = promisify(execFile);
const SOURCE_SHA = 'a'.repeat(40);
const pinned = listAivenPinnedSources();
const docs = pinned.map((item, index) => ({
  id: item.id, title: item.title,
  summary: index ? 'Official PostgreSQL slow query guidance.' : 'Official Kafka consumer lag guidance.',
  url: item.citationUrl, sourceCommit: item.sourceCommit,
  rawSha256: item.contentSha256, verifiedThisRun: true,
}));
const prompt = buildPublicPrompt(docs);
const observed = JSON.stringify({is_error: false,
  result: 'Watch consumer lag and slow queries. Verify the metrics on a real authorized system.',
  total_cost_usd: 0.01});
const options = {sourceCommit: SOURCE_SHA, prompt, docs, finishedAt: '2026-11-12T21:00:00.000Z'};

test('only exact two public sources form the bounded Aiven prompt', () => {
  assert.match(prompt, /independently built Junction Aiven/);
  assert.match(prompt, /not an Aiven employee/);
  for (const item of pinned) assert.ok(prompt.includes(item.citationUrl));
  assert.match(prompt, /Do not call tools/);
  assert.throws(() => buildPublicPrompt(docs.slice(0, 1)), /PUBLIC_SOURCE_VERIFICATION_REQUIRED/);
  assert.throws(() => buildPublicPrompt(docs.map(d => ({...d, verifiedThisRun: false}))),
    /PUBLIC_SOURCE_VERIFICATION_REQUIRED/);
});

test('observed CLI response remains fully UNQUALIFIED', () => {
  const result = parseObservedClaudeResult(observed, options);
  assert.equal(result.source.commit, SOURCE_SHA);
  assert.equal(result.source.providerSourceAttested, false);
  assert.equal(result.execution.modelResponseObserved, true);
  assert.equal(result.execution.requestedModelAlias, 'haiku');
  assert.equal(result.execution.providerInvocationVerified, false);
  assert.equal(result.verdict.qualifiedPasses, 0);
  assert.equal(result.verdict.verifiedPetModelExecutions, 0);
  assert.equal(result.verdict.chibiHostVerified, false);
  assert.equal(result.verdict.signedProviderReceiptVerified, false);
  assert.equal(result.verdict.evidenceLevel, 'local-cli-observed-unverified');
  assert.equal(result.publicDocs.length, 2);
  assert.ok(result.execution.responseSha256.match(/^[a-f0-9]{64}$/));
  assert.ok(!JSON.stringify(result).includes('Watch consumer lag'));
});

test('invalid provider JSON, error result and empty text fail closed', () => {
  for (const bad of [
    'not-json', '{}', JSON.stringify({is_error: true, result: 'This is a long enough error response.'}),
    JSON.stringify({result: ''}), JSON.stringify({result: 'not enough'}),
  ]) assert.throws(() => parseObservedClaudeResult(bad, options), /PROVIDER_/);
});

test('provider-reported over-budget cost rejected; missing cost remains unknown', () => {
  const excessive = JSON.stringify({is_error: false, result: 'A sufficiently long realistic reply for testing.', total_cost_usd: 0.26});
  assert.throws(() => parseObservedClaudeResult(excessive, options), /PROVIDER_REPORTED_COST_OVER_CAP/);
  const missing = parseObservedClaudeResult(JSON.stringify({
    is_error: false, result: 'A sufficiently long realistic reply for testing.',
  }), options);
  assert.equal(missing.execution.cliReportedCostUsd, null);
  assert.equal(missing.execution.qualifiedPasses, undefined);
  assert.equal(missing.verdict.qualifiedPasses, 0);
});

test('source hash and two-document public proof are mandatory', () => {
  assert.throws(() => parseObservedClaudeResult(observed, {...options, sourceCommit: 'not-a-sha'}),
    /INVALID_SOURCE_COMMIT/);
  assert.throws(() => parseObservedClaudeResult(observed, {...options, docs: []}),
    /PUBLIC_SOURCE_VERIFICATION_REQUIRED/);
  assert.throws(() => parseObservedClaudeResult(observed, {...options, docs:
    docs.map(d => ({...d, verifiedThisRun: false}))}), /PUBLIC_SOURCE_VERIFICATION_REQUIRED/);
});

test('CLI defaults to offline preview and cannot invoke provider', async () => {
  const {stdout, stderr} = await run(process.execPath, [
    new URL('./haiku-public-smoke.mjs', import.meta.url).pathname,
    '--source-commit', SOURCE_SHA,
  ], {timeout: 10_000});
  assert.equal(stderr, '');
  const result = JSON.parse(stdout);
  assert.equal(result.mode, 'offline-preview');
  assert.equal(result.modelResponseObserved, false);
  assert.equal(result.providerInvocationVerified, false);
  assert.equal(result.chibiHostVerified, false);
  assert.equal(result.qualifiedPasses, 0);
  assert.equal(result.publicDocs.length, 2);
  assert.ok(result.publicDocs.every(d => d.bytesVerifiedThisRun === false));
});
