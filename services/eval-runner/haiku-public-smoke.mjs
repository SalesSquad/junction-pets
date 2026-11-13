#!/usr/bin/env node
import {execFile} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {promisify} from 'node:util';
import {listAivenPinnedSources, searchAivenPublicDocs} from '../pet-adapters/aiven/adapter.mjs';
import {qualifiesLivePinnedResult} from '../pet-adapters/aiven/smoke-gates.mjs';

const run = promisify(execFile);
const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const COMMIT = /^[a-f0-9]{40}$/;
const SOURCE = 'SalesSquad/junction-pets';
const CAP_USD = 0.25;
const QUESTION = 'We run a small event application using Kafka consumers and PostgreSQL. What should we measure to identify consumer lag and slow queries, and what should we verify before claiming the application is reliable?';
const QUERIES = [
  ['kafka-consumer-groups', 'Kafka consumer group lag'],
  ['postgresql-slow-queries', 'PostgreSQL slow queries indexes'],
];
const sha256 = value => createHash('sha256').update(value).digest('hex');
const error = message => {throw new Error(message);};

export function buildPublicPrompt(docs) {
  const pinned = listAivenPinnedSources();
  if (!Array.isArray(docs) || docs.length !== pinned.length ||
    docs.some((doc, i) => doc?.id !== pinned[i].id ||
      doc?.url !== pinned[i].citationUrl ||
      doc?.sourceCommit !== pinned[i].sourceCommit ||
      doc?.rawSha256 !== pinned[i].contentSha256 ||
      doc?.verifiedThisRun !== true ||
      typeof doc?.summary !== 'string' || !doc.summary.trim() ||
      doc.summary.length > 500 ||
      typeof doc?.title !== 'string' || !doc.title.trim() ||
      doc.title.length > 200)) {
    error('PUBLIC_SOURCE_VERIFICATION_REQUIRED');
  }
  return [
    'You are an independently built Junction Aiven subject companion, not an Aiven employee or official representative.',
    'This is a read-only public documentation demonstration. Do not call tools, access user data, claim Aiven account access, provisioning, deployment or endorsement.',
    'Only the following two summaries are supported by independently SHA-256-matched raw public Aiven documentation bytes. Cite their official URLs for claims they actually support.',
    'Do not infer versions, costs, product entitlements, service availability or unverified details. Separate evidence, assumptions and next checks.',
    ...docs.map(doc => `- ${doc.title}: ${doc.summary} Official URL: ${doc.url}`),
    'User question: ' + QUESTION,
    'Answer concisely with 3 concrete measurements and a verification step. If the evidence does not support a claim, say so.',
  ].join('\n');
}

export function parseObservedClaudeResult(stdout, {sourceCommit, prompt, docs, finishedAt}) {
  if (!COMMIT.test(sourceCommit)) error('INVALID_SOURCE_COMMIT');
  let message;
  try { message = JSON.parse(stdout); } catch { error('PROVIDER_JSON_INVALID'); }
  if (message?.is_error !== false || typeof message?.result !== 'string' ||
    message.result.trim().length < 30 || message.result.length > 30_000) {
    error('PROVIDER_RESPONSE_UNUSABLE');
  }
  if (prompt !== buildPublicPrompt(docs)) error('PROMPT_SOURCE_BINDING_MISMATCH');
  const reported = message.total_cost_usd;
  const costUsdReported = typeof reported === 'number' && Number.isFinite(reported) &&
    reported >= 0 ? reported : null;
  if (costUsdReported !== null && costUsdReported > CAP_USD) error('PROVIDER_REPORTED_COST_OVER_CAP');
  if (!Array.isArray(docs) || docs.length !== 2 ||
    docs.some(doc => doc.verifiedThisRun !== true)) error('PUBLIC_SOURCE_VERIFICATION_REQUIRED');
  return {
    schemaVersion: 1,
    workId: 'junction-wave4-aiven-haiku-public-smoke',
    source: {repository: SOURCE, commit: sourceCommit, localCheckoutClean: true,
      providerSourceAttested: false, chibiHostSourceAttested: false},
    prompt: {sha256: sha256(prompt), publicOnly: true, scenario: 'aiven-public-observability'},
    publicDocs: docs.map(doc => ({id: doc.id, url: doc.url, sourceCommit: doc.sourceCommit,
      rawSha256: doc.rawSha256, pinnedRawBytesMatched: true})),
    execution: {kind: 'local-claude-cli-observation', provider: 'anthropic',
      requestedModelAlias: 'haiku', exactBackendModelVerified: false,
      modelResponseObserved: true, responseSha256: sha256(message.result),
      responseBytes: Buffer.byteLength(message.result), completedAt: finishedAt,
      cliReportedCostUsd: costUsdReported, maxBudgetUsd: CAP_USD,
      providerInvocationVerified: false},
    verdict: {evidenceLevel: 'local-cli-observed-unverified', chibiHostVerified: false,
      signedProviderReceiptVerified: false, independentAdjudicationVerified: false,
      qualifiedPasses: 0, verifiedPetModelExecutions: 0},
  };
}

async function checkCheckout(commit) {
  if (!COMMIT.test(commit)) error('INVALID_SOURCE_COMMIT');
  const git = async (...args) => (await run('git', ['-C', ROOT, ...args], {timeout: 10_000})).stdout.trim();
  const [head, status, origin] = await Promise.all([
    git('rev-parse', 'HEAD'), git('status', '--porcelain=v1'), git('remote', 'get-url', 'origin'),
  ]);
  if (head !== commit || status !== '') error('SOURCE_CHECKOUT_NOT_CLEAN_OR_PINNED');
  if (!['https://github.com/SalesSquad/junction-pets.git',
    'git@github.com:SalesSquad/junction-pets.git'].includes(origin)) error('SOURCE_ORIGIN_MISMATCH');
}

async function verifyPublicDocs() {
  const pinned = new Map(listAivenPinnedSources().map(item => [item.id, item]));
  const docs = [];
  for (const [id, query] of QUERIES) {
    const expected = pinned.get(id);
    const result = await searchAivenPublicDocs(query, {timeoutMs: 5000});
    if (!qualifiesLivePinnedResult(result, expected)) error('PUBLIC_DOCS_PIN_MISMATCH');
    const source = result.documents[0];
    docs.push({id, title: source.title, summary: source.summary,
      url: source.citation.url, sourceCommit: source.provenance.sourceCommit,
      rawSha256: source.provenance.contentSha256, verifiedThisRun: true});
  }
  return docs;
}

async function execute(sourceCommit) {
  await checkCheckout(sourceCommit);
  const docs = await verifyPublicDocs();
  const prompt = buildPublicPrompt(docs);
  let stdout;
  try {
    ({stdout} = await run('claude', [
      '--print', '--model', 'haiku', '--max-budget-usd', String(CAP_USD),
      '--restricted', '--tools', '', '--strict-mcp-config',
      '--no-session-persistence', '--no-chrome', '--permission-mode', 'dontAsk',
      '--output-format', 'json', prompt,
    ], {cwd: ROOT, timeout: 90_000, maxBuffer: 500_000}));
  } catch { error('PROVIDER_CLI_FAILED_OR_BUDGET_BLOCKED'); }
  const receipt = parseObservedClaudeResult(stdout, {
    sourceCommit, prompt, docs, finishedAt: new Date().toISOString(),
  });
  const path = resolve(ROOT, 'dist/evals/haiku-public-smoke-unqualified.json');
  await mkdir(dirname(path), {recursive: true});
  await writeFile(path, JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  return {path: 'dist/evals/haiku-public-smoke-unqualified.json', ...receipt};
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 2 && args.length !== 3) error('USAGE: --source-commit FULL_SHA [--execute]');
  if (args[0] !== '--source-commit' || !COMMIT.test(args[1]) ||
    (args.length === 3 && args[2] !== '--execute')) error('INVALID_OPTIONS');
  if (args.length === 2) {
    console.log(JSON.stringify({mode: 'offline-preview', sourceCommit: args[1],
      publicDocs: listAivenPinnedSources(), modelResponseObserved: false,
      chibiHostVerified: false, providerInvocationVerified: false, qualifiedPasses: 0}));
    return;
  }
  console.log(JSON.stringify(await execute(args[1])));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(cause => {
    process.stderr.write(JSON.stringify({error: cause instanceof Error ? cause.message : 'SMOKE_FAILED'}) + '\n');
    process.exitCode = 1;
  });
}
