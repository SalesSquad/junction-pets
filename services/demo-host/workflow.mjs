#!/usr/bin/env node
// Fixed public/synthetic developer demonstration; no Chibi host or account authority.
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {searchAivenPublicDocs, listAivenPinnedSources} from '../pet-adapters/aiven/adapter.mjs';
import {qualifiesLivePinnedResult} from '../pet-adapters/aiven/smoke-gates.mjs';
import {executeCapability} from '../pet-adapters/registry.mjs';
import {example} from '../../pets/mariadb/explain-example.mjs';
import {canonicalJson} from '../../lib/artifact.mjs';
import {buildPublicPrompt} from '../eval-runner/haiku-public-smoke.mjs';

const exec = promisify(execFile);
const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const SUMMARIES = [
  'Aiven guidance for observing Kafka consumer groups, including consumer lag.',
  'Aiven guidance for identifying and optimizing PostgreSQL slow queries, including pg_stat_statements.',
];
const QUERIES = ['Kafka consumer group lag', 'PostgreSQL slow queries indexes'];
const sha = value => createHash('sha256').update(value).digest('hex');
const fail = code => {throw Error(code);};
const exact = (value, fields) => value !== null && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));

export async function collectEvidence(search = searchAivenPublicDocs) {
  const docs = [];
  const pinned = listAivenPinnedSources();
  for (let i = 0; i < pinned.length; i++) {
    const response = await search(QUERIES[i], {timeoutMs: 5000});
    if (!qualifiesLivePinnedResult(response, pinned[i])) fail('PUBLIC_DOCS_NOT_VERIFIED');
    const doc = response.documents[0];
    docs.push({id: doc.id, title: doc.title, summary: doc.summary, url: doc.citation.url,
      sourceCommit: doc.provenance.sourceCommit, rawSha256: doc.provenance.contentSha256,
      verifiedThisRun: true});
  }
  const analysis = await executeCapability('mariadb.explain-evidence', {jsonText: JSON.stringify(example)});
  if (!analysis.ok) fail('SYNTHETIC_ANALYSIS_FAILED');
  return {docs, analysis};
}

export async function preparePrompt(evidence) {
  if (!exact(evidence, ['docs', 'analysis']) || !Array.isArray(evidence.docs) || evidence.docs.length !== 2) fail('INVALID_EVIDENCE');
  const pinned = listAivenPinnedSources();
  for (let i = 0; i < pinned.length; i++) {
    const d = evidence.docs[i], p = pinned[i];
    if (!exact(d, ['id', 'title', 'summary', 'url', 'sourceCommit', 'rawSha256', 'verifiedThisRun']) ||
        d.id !== p.id || d.title !== p.title || d.summary !== SUMMARIES[i] || d.url !== p.citationUrl ||
        d.sourceCommit !== p.sourceCommit || d.rawSha256 !== p.contentSha256 || d.verifiedThisRun !== true) fail('INVALID_EVIDENCE');
  }
  const expected = await executeCapability('mariadb.explain-evidence', {jsonText: JSON.stringify(example)});
  if (canonicalJson(evidence.analysis) !== canonicalJson(expected)) fail('INVALID_EVIDENCE');
  return buildPublicPrompt(evidence.docs) + '\nSynthetic MariaDB evidence, not a real database execution:\n' +
    JSON.stringify(expected.result) + '\nThe SQL engine for this supplied plan is MariaDB; its version is unknown. ' +
    'The Aiven sources above cover Kafka and PostgreSQL only. They are not evidence for MariaDB syntax or diagnostic commands. ' +
    'Keep estimated rows distinct from observed runtime. For the MariaDB next step, ask for the engine version and an already existing redacted runtime plan, if available. ' +
    'Propose the measurement needed to assess the estimate; do not prescribe diagnostic SQL, provide exact SQL, or ask anyone to execute a query. ' +
    'Keep any Kafka/PostgreSQL measurements separate from this MariaDB plan, and cite each source only for the engine and claims it actually supports.';
}

export function claudeArgs(prompt) {
  return ['--safe-mode', '--restricted', '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
    '--no-session-persistence', '--no-chrome', '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
    '--model', 'haiku', '--max-budget-usd', '0.25', '--output-format', 'json', '-p', prompt];
}

export async function invokeModel(evidence, invoke = null) {
  const prompt = await preparePrompt(evidence);
  const cwd = await mkdtemp(join(tmpdir(), 'junction-aiven-public-'));
  let stdout;
  try {
    stdout = invoke ? await invoke(claudeArgs(prompt), cwd) :
      (await exec('claude', claudeArgs(prompt), {cwd, timeout: 90000, maxBuffer: 500000, killSignal: 'SIGTERM',
        env: Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('PG') && key !== 'JUNCTION_DEMO_DATABASE_URL'))})).stdout;
  } catch {fail('CLAUDE_CLI_FAILED');}
  finally {await rm(cwd, {recursive: true, force: true});}
  let response;
  try {response = JSON.parse(stdout);} catch {fail('MODEL_RESPONSE_INVALID');}
  if (response?.is_error !== false || typeof response.result !== 'string' || response.result.length < 30 ||
      Buffer.byteLength(response.result) > 20000 || !response.result.isWellFormed()) fail('MODEL_RESPONSE_INVALID');
  const cost = response.total_cost_usd;
  if (typeof cost !== 'number' || !Number.isFinite(cost) || cost < 0 || cost > 0.25) fail('MODEL_COST_UNVERIFIED_OR_OVER_CAP');
  return {kind: 'public-synthetic-developer-demo', response: response.result,
    promptSha256: sha(prompt), responseSha256: sha(response.result), cliReportedCostUsd: cost,
    requestedModelAlias: 'haiku', exactBackendModelVerified: false,
    modelResponseObserved: !invoke, evidenceLevel: invoke ? 'synthetic-test-only' : 'local-cli-observed-unverified',
    docs: evidence.docs, analysis: evidence.analysis.result,
    chibiHostVerified: false, providerInvocationVerified: false, signedReceiptVerified: false};
}

async function checkSource(sourceCommit) {
  if (!/^[a-f0-9]{40}$/.test(sourceCommit ?? '')) fail('INVALID_SOURCE_COMMIT');
  const git = async (...args) => (await exec('git', ['-C', ROOT, ...args], {timeout: 10000, maxBuffer: 100000})).stdout.trim();
  const [head, status, origin] = await Promise.all([git('rev-parse', 'HEAD'), git('status', '--porcelain=v1', '--untracked-files=all'), git('remote', 'get-url', 'origin')]);
  if (head !== sourceCommit || status) fail('SOURCE_NOT_CLEAN_OR_PINNED');
  if (!['https://github.com/SalesSquad/junction-pets.git', 'git@github.com:SalesSquad/junction-pets.git'].includes(origin)) fail('SOURCE_ORIGIN_MISMATCH');
}

async function main(args) {
  if (args.length !== 4 || args[0] !== '--stage' || !['evidence', 'model'].includes(args[1]) || args[2] !== '--source-commit') fail('INVALID_OPTIONS');
  await checkSource(args[3]);
  if (args[1] === 'evidence') return collectEvidence();
  let input = ''; for await (const chunk of process.stdin) {input += chunk; if (Buffer.byteLength(input) > 65000) fail('INPUT_TOO_LARGE');}
  let evidence; try {evidence = JSON.parse(input);} catch {fail('INVALID_EVIDENCE');}
  await checkSource(args[3]);
  return invokeModel(evidence);
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).then(value => console.log(JSON.stringify(value)), () => {
    console.error(JSON.stringify({error: 'PUBLIC_WORKFLOW_STAGE_FAILED'})); process.exitCode = 1;
  });
}
