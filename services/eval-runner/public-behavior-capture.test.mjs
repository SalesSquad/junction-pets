import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, readdir, rm, stat, mkdir, symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {loadPackages} from '../../lib/catalog.mjs';
import {capturePublicBehavior, parseCaptureOptions, preparePublicCapture,
  validateCaptureOptions, claudeCaptureArgs, parseClaudeCapture} from './public-behavior-capture.mjs';

const sha = 'a'.repeat(40);
const options = {sourceCommit: sha, pet: 'aiven', maxCases: 2};
const pack = (slug, ids = ['safe-one', 'safe-two']) => ({
  pet: {id: `junction.${slug}`, company: {slug}, artIndex: slug === 'aiven' ? 1 : 2, version: '0.1.0'},
  instructions: `Independent ${slug} instructions. ` + 'Public synthetic behavior only. '.repeat(25),
  story: 'Synthetic public test story.',
  evals: {schemaVersion: 1, petId: `junction.${slug}`, cases: ids.map(id => ({
    id, prompt: `Public synthetic question for ${id}.`,
    mustInclude: ['Identify missing evidence clearly'],
    mustNotClaim: ['Do not claim account access'],
  }))},
});
const packs = [pack('aiven'), pack('mariadb')];
const output = (text = 'I cannot confirm account access. Please provide a redacted plan for review.', extra = {}) =>
  JSON.stringify({is_error: false, result: text, total_cost_usd: 0.01, session_id: 'actual-cli-session-123',
    modelUsage: {'claude-model-provider-reported': {inputTokens: 10}}, ...extra});
const hash = value => createHash('sha256').update(value).digest('hex');

test('capture options are strict, bounded, offline by default and deny path traversal', () => {
  const parsed = parseCaptureOptions(['--source-commit', sha, '--pet', 'aiven']);
  assert.equal(parsed.execute, false);
  assert.equal(parsed.model, 'haiku');
  assert.equal(parsed.persona, 'pet');
  assert.equal(parsed.maxCases, 6);
  assert.equal(parsed.timeoutMs, 90_000);
  for (const args of [
    ['--source-commit', sha, '--execute', '--execute'],
    ['--source-commit', sha, '--output', '/tmp/leak'],
    ['--source-commit', sha, '--pet', '../ops'],
    ['--source-commit', sha, '--case', '../../private'],
    ['--source-commit', sha, '--max-cases', '205'],
    ['--source-commit', sha, '--max-cases', '0'],
    ['--source-commit', sha, '--max-cases', '1.5'],
    ['--source-commit', sha, '--timeout-ms', '99999999'],
    ['--source-commit', sha, '--max-budget-usd', 'NaN'],
    ['--source-commit', sha, '--model', '--execute'],
    ['--source-commit', sha, '--model', 'unverified-backend'],
    ['--source-commit', sha, '--persona', 'hidden-memory'],
    ['--source-commit', 'not-a-commit'],
  ]) assert.throws(() => parseCaptureOptions(args));
  assert.throws(() => validateCaptureOptions({...options, arbitraryTransport: 'shell'}), /INVALID_OPTIONS/);
  assert.throws(() => validateCaptureOptions({...options, execute: 'true'}), /INVALID_EXECUTE/);
});

test('freezes exact instruction/case/request hashes and does not leak rubric into model prompt', () => {
  const prepared = preparePublicCapture(packs, options);
  const item = prepared.cases[0];
  assert.equal(prepared.authoredCases, 4);
  assert.equal(prepared.source.commit, sha);
  assert.equal(item.instructionsSha256, hash(packs[0].instructions));
  assert.equal(JSON.parse(item.prompt).companionInstructions, packs[0].instructions);
  assert.equal(item.promptSha256, hash(item.prompt));
  assert.ok(!item.prompt.includes(item.mustInclude[0]));
  assert.equal(prepared.qualifiedPasses, 0);
  const changed = preparePublicCapture([{...packs[0], instructions: packs[0].instructions + ' changed'}, packs[1]], options);
  assert.notEqual(changed.planSha256, prepared.planSha256);
  assert.notEqual(changed.cases[0].requestSha256, item.requestSha256);
  assert.throws(() => preparePublicCapture(packs, {...options, caseId: 'junction.mariadb/safe-one'}), /CASE_NOT_IN_SELECTED_PET/);
});

test('all-company selection covers breadth before repeating a company', () => {
  const plan = preparePublicCapture(packs, {...options, pet: 'all', maxCases: 3});
  assert.deepEqual(plan.cases.map(item => item.id), [
    'junction.aiven/safe-one', 'junction.mariadb/safe-one', 'junction.aiven/safe-two',
  ]);
  assert.equal(plan.limits.concurrency, 1);
  assert.equal(plan.limits.maximumRequestedBatchBudgetUsd, 0.75);
});

test('no-persona baseline uses same fixed case and excludes all companion instructions from model prompt', () => {
  const persona = preparePublicCapture(packs, options);
  const baseline = preparePublicCapture(packs, {...options, persona: 'none'});
  assert.equal(baseline.persona, 'none');
  assert.equal(baseline.cases[0].caseSha256, persona.cases[0].caseSha256);
  assert.equal(baseline.cases[0].instructionsSha256, persona.cases[0].instructionsSha256);
  assert.notEqual(baseline.cases[0].requestSha256, persona.cases[0].requestSha256);
  const prompt = JSON.parse(baseline.cases[0].prompt);
  assert.deepEqual(Object.keys(prompt), ['scenario']);
  assert.ok(!baseline.cases[0].prompt.includes(packs[0].instructions));
});

test('repository catalog freezes all 204 existing public/synthetic cases across all 34 companies', async () => {
  const repoPacks = await loadPackages(new URL('../../', import.meta.url).pathname);
  const plan = preparePublicCapture(repoPacks, {sourceCommit: sha, maxCases: 204});
  assert.equal(plan.cases.length, 204);
  assert.equal(new Set(plan.cases.map(item => item.petId)).size, 34);
  assert.equal(new Set(plan.cases.slice(0, 34).map(item => item.petId)).size, 34);
  assert.ok(plan.cases.every(item => /^[a-f0-9]{64}$/.test(item.caseSha256)));
});

test('Claude transport has no tool/MCP/browser rights or shell interpolation; aliases remain unverified', () => {
  const input = validateCaptureOptions({...options, model: 'fable'});
  const item = preparePublicCapture(packs, input).cases[0];
  const args = claudeCaptureArgs(item, input);
  for (const flag of ['--safe-mode', '--restricted', '--strict-mcp-config', '--no-chrome', '--no-session-persistence']) assert.ok(args.includes(flag));
  assert.equal(args[args.indexOf('--setting-sources') + 1], '');
  assert.equal(args[args.indexOf('--tools') + 1], '');
  assert.equal(args[args.indexOf('--permission-mode') + 1], 'dontAsk');
  assert.equal(args[args.indexOf('--model') + 1], 'fable');
  assert.equal(args.at(-1), item.prompt);
  assert.ok(!args.includes('--dangerously-skip-permissions'));
  const parsed = parseClaudeCapture(output(), input);
  assert.equal(parsed.exactBackendModelVerified, false);
  assert.deepEqual(parsed.backendModelsReported, ['claude-model-provider-reported']);
  assert.equal(parsed.invocationIdReported, 'actual-cli-session-123');
  assert.equal(parsed.response.sha256, hash(parsed.response.text));
});

test('malformed, oversized and provider-error outputs fail; overbudget response remains reviewable but stops batch', () => {
  const input = validateCaptureOptions(options);
  for (const raw of ['not-json', '{}', output('', {}), output('abc', {is_error: true}),
    output('x'.repeat(100_001)), output('abc', {total_cost_usd: -1}), output('abc', {total_cost_usd: 'cheap'})]) {
    assert.throws(() => parseClaudeCapture(raw, input), /PROVIDER_/);
  }
  const missing = parseClaudeCapture(JSON.stringify({is_error: false, result: 'Public answer.'}), input);
  assert.equal(missing.cliReportedCostUsd, null);
  assert.equal(missing.invocationIdReported, null);
  const over = parseClaudeCapture(output('Public overbudget answer.', {total_cost_usd: 0.26}), input);
  assert.equal(over.budgetExceededReported, true);
  assert.equal(over.response.text, 'Public overbudget answer.');
});

test('offline capture never checks provider or invokes transport or writes output', async () => {
  const result = await capturePublicBehavior(options, {
    root: '/path/that/does/not/exist', loadPacks: async () => packs,
    checkSource: () => {throw new Error('should not run');},
    invoke: () => {throw new Error('should not run');},
  });
  assert.equal(result.mode, 'offline-preview');
  assert.equal(result.modelResponseObserved, false);
  assert.equal(result.qualifiedPasses, 0);
  assert.equal(result.selectedCaseIds.length, 2);
});

test('source preflight rejects before model invocation or creating private run artifacts', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-capture-source-'));
  let calls = 0;
  try {
    await assert.rejects(capturePublicBehavior({...options, execute: true}, {root,
      loadPacks: async () => packs, checkSource: () => {throw new Error('SOURCE_CHECKOUT_NOT_CLEAN_OR_PINNED');},
      invoke: () => {calls++; return output();},
    }), /SOURCE_CHECKOUT_NOT_CLEAN_OR_PINNED/);
    assert.equal(calls, 0);
    assert.deepEqual(await readdir(root), []);
  } finally {await rm(root, {recursive: true, force: true});}
});

test('captured private text and digest receipts persist for independent scoring; synthetic transport stays labeled', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-capture-results-'));
  let active = 0, peak = 0;
  try {
    const result = await capturePublicBehavior({...options, execute: true}, {root, loadPacks: async () => packs,
      checkSource: async () => {}, invoke: async (args, {cwd}) => {
        assert.ok(!cwd.startsWith(root));
        assert.deepEqual(await readdir(cwd), []);
        active++; peak = Math.max(peak, active); await Promise.resolve(); active--; return output();
      },
    });
    assert.equal(peak, 1);
    assert.equal(result.capturedResponses, 2);
    assert.equal(result.failedAttempts, 0);
    assert.equal(result.providerInvocationsVerified, 0);
    assert.equal(result.independentAdjudicationVerified, false);
    assert.equal(result.evidenceLevel, 'synthetic-test-only');
    assert.equal(result.localCheckoutVerified, false);
    assert.equal(result.qualifiedPasses, 0);
    assert.equal((await stat(result.directory)).mode & 0o777, 0o700);
    const raw = await readFile(resolve(result.directory, 'case-001.json'), 'utf8');
    const first = JSON.parse(raw);
    assert.equal(first.execution.kind, 'synthetic');
    assert.equal(first.execution.provider, 'synthetic');
    assert.equal(first.response.sha256, hash(first.response.text));
    assert.equal(first.adjudication, null);
    assert.equal(hash(raw), result.recordDigests[0].sha256);
    assert.equal((await stat(resolve(result.directory, 'case-001.json'))).mode & 0o777, 0o600);
    assert.ok(!JSON.stringify(result).includes(first.response.text));
    const another = await capturePublicBehavior({...options, execute: true}, {root, loadPacks: async () => packs,
      checkSource: async () => {}, invoke: async () => output(),
    });
    assert.notEqual(another.directory, result.directory);
    assert.equal((await readdir(resolve(root, 'dist/evals/public-behavior'))).length, 2);
  } finally {await rm(root, {recursive: true, force: true});}
});

test('CLI failure retains sanitized failed attempt, marks remaining cases unattempted, no automatic retry', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-capture-failure-'));
  let calls = 0;
  try {
    const result = await capturePublicBehavior({...options, execute: true}, {root,
      loadPacks: async () => packs, checkSource: async () => {}, invoke: async () => {calls++; throw new Error('private-provider-stderr');},
    });
    assert.equal(calls, 1);
    assert.equal(result.failedAttempts, 1);
    assert.equal(result.attemptedCases, 1);
    assert.equal(result.notAttemptedCaseIds.length, 1);
    const raw = await readFile(resolve(result.directory, 'case-001.json'), 'utf8');
    assert.ok(!raw.includes('private-provider-stderr'));
    assert.equal(JSON.parse(raw).failureCode, 'PROVIDER_CLI_FAILED');
  } finally {await rm(root, {recursive: true, force: true});}
});

test('source drift after first response is retained as failure and prevents further invocation', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-capture-drift-'));
  let loads = 0, calls = 0;
  try {
    const changed = [{...packs[0], instructions: packs[0].instructions + 'mutation'}, packs[1]];
    const result = await capturePublicBehavior({...options, execute: true}, {root,
      loadPacks: async () => ++loads <= 2 ? packs : changed, checkSource: async () => {},
      invoke: async () => {calls++; return output();},
    });
    assert.equal(calls, 1);
    assert.equal(result.capturedResponses, 1);
    assert.equal(result.failedAttempts, 1);
    assert.equal(JSON.parse(await readFile(resolve(result.directory, 'case-002.json'), 'utf8')).failureCode, 'SOURCE_PLAN_CHANGED');
  } finally {await rm(root, {recursive: true, force: true});}
});

test('reported budget excess retains response and stops following invocations', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-capture-budget-'));
  let calls = 0;
  try {
    const result = await capturePublicBehavior({...options, execute: true}, {root, loadPacks: async () => packs,
      checkSource: async () => {}, invoke: async () => {calls++; return output('Review this exact public response.', {total_cost_usd: 0.5});},
    });
    assert.equal(calls, 1);
    assert.equal(result.capturedResponses, 1);
    assert.equal(result.failedAttempts, 1);
    const record = JSON.parse(await readFile(resolve(result.directory, 'case-001.json'), 'utf8'));
    assert.equal(record.status, 'budget-exceeded');
    assert.equal(record.response.text, 'Review this exact public response.');
  } finally {await rm(root, {recursive: true, force: true});}
});

test('fixed output destination rejects a symlink escaping repository root before provider invocation', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'junction-capture-link-'));
  const outside = await mkdtemp(resolve(tmpdir(), 'junction-capture-outside-'));
  let calls = 0;
  try {
    await mkdir(resolve(root, 'dist/evals'), {recursive: true});
    await symlink(outside, resolve(root, 'dist/evals/public-behavior'));
    await assert.rejects(capturePublicBehavior({...options, execute: true}, {root, loadPacks: async () => packs,
      checkSource: async () => {}, invoke: async () => {calls++; return output();},
    }), /OUTPUT_PATH_ESCAPE/);
    assert.equal(calls, 0);
    assert.deepEqual(await readdir(outside), []);
  } finally {await rm(root, {recursive: true, force: true}); await rm(outside, {recursive: true, force: true});}
});
