#!/usr/bin/env node
// One workflow-fixed command per cell. Receipts are source-reported evidence,
// not provider attestations. Only the validated upload/ tree may be published.
import {constants} from 'node:fs';
import {appendFile, lstat, mkdir, mkdtemp, open, opendir, rename} from 'node:fs/promises';
import {spawn, execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {basename, dirname, extname, isAbsolute, join, parse, relative, resolve, sep} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';
import {canonicalJson, sha256} from '../../lib/artifact.mjs';
import {recordRun, validateRun} from '../../services/experiment-registry/registry.mjs';

const exec = promisify(execFile);
const COMMIT = /^[a-f0-9]{40}$/;
const SLUG = /^[a-z][a-z0-9._-]{0,63}$/;
const REPOSITORY = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const EXTENSIONS = new Set(['.json', '.jsonl', '.log', '.png', '.zip', '.trx', '.sha256']);
const RAW_FILES = new Set(['command-start.json', 'command.json', 'command.stdout.log', 'command.stderr.log']);
export const LIMITS = Object.freeze({
  logBytes: 4 * 1024 * 1024, fileBytes: 20 * 1024 * 1024,
  payloadBytes: 63 * 1024 * 1024, archiveBytes: 64 * 1024 * 1024,
  files: 128, entries: 256, depth: 5, jsonBytes: 256 * 1024,
});
const fail = code => {throw new Error(code);};
const bytes = value => Buffer.from(canonicalJson(value) + '\n');
const same = (a, b) => a.dev === b.dev && a.ino === b.ino && a.mode === b.mode &&
  a.size === b.size && a.mtimeNs === b.mtimeNs && a.ctimeNs === b.ctimeNs;
const inside = (root, path) => {const p = relative(root, path); return p !== '' && p !== '..' && !p.startsWith('..' + sep) && !isAbsolute(p);};
const safeRelative = value => typeof value === 'string' && value.length <= 512 &&
  !value.includes('\\') && value.split('/').every(part => SEGMENT.test(part) && part !== '.' && part !== '..');

async function chain(path, directory = false) {
  const absolute = resolve(path);
  let current = parse(absolute).root;
  const parts = absolute.slice(current.length).split(sep).filter(Boolean), snapshots = [];
  for (let i = -1; i < parts.length; i++) {
    if (i >= 0) current = join(current, parts[i]);
    const stat = await lstat(current, {bigint: true});
    if (stat.isSymbolicLink() || ((i < parts.length - 1 || directory) ? !stat.isDirectory() : !stat.isFile()))
      fail('UNSAFE_PATH');
    if (i === parts.length - 1 && !directory && stat.nlink !== 1n) fail('HARDLINK_REFUSED');
    snapshots.push([current, stat]);
  }
  return snapshots;
}
async function unchanged(snapshots) {
  for (const [path, stat] of snapshots) if (!same(stat, await lstat(path, {bigint: true}))) fail('FILE_CHANGED_DURING_READ');
}
async function ensureDirectory(path) {
  const absolute = resolve(path);
  let current = parse(absolute).root;
  for (const component of absolute.slice(current.length).split(sep).filter(Boolean)) {
    current = join(current, component);
    try {await mkdir(current, {mode: 0o700});} catch (error) {if (error.code !== 'EEXIST') throw error;}
    const stat = await lstat(current);
    if (!stat.isDirectory() || stat.isSymbolicLink()) fail('UNSAFE_DIRECTORY');
  }
  await chain(absolute, true);
}
async function boundedRead(path, limit) {
  const snapshots = await chain(path);
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const initial = await handle.stat({bigint: true});
    if (!same(initial, snapshots.at(-1)[1]) || initial.size > BigInt(limit)) fail('FILE_TOO_LARGE_OR_CHANGED');
    const buffer = Buffer.alloc(Number(initial.size) + 1);
    let length = 0;
    while (length < buffer.length) {
      const {bytesRead} = await handle.read(buffer, length, buffer.length - length, null);
      if (!bytesRead) break;
      length += bytesRead;
    }
    if (length !== Number(initial.size) || !same(initial, await handle.stat({bigint: true}))) fail('FILE_CHANGED_DURING_READ');
    await unchanged(snapshots);
    return buffer.subarray(0, length);
  } finally {await handle.close();}
}
async function optionalRead(path, limit = LIMITS.jsonBytes) {
  try {return await boundedRead(path, limit);} catch (error) {if (error.code === 'ENOENT') return null; throw error;}
}
async function exclusiveWrite(path, data) {
  await chain(dirname(path), true);
  const handle = await open(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try {await handle.writeFile(data); await handle.sync();} finally {await handle.close();}
}
const decode = data => JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(data));
const knownError = error => /^[A-Z_]{3,80}$/.test(error?.message || '') ? error.message :
  /^[A-Z0-9_]{2,30}$/.test(error?.code || '') ? error.code : 'UNAVAILABLE_OR_INVALID';

function configuration(env) {
  const root = env.CRACI_RECEIPT_DIR, sourceRoot = env.CRACI_SOURCE_ROOT, harnessRoot = env.CRACI_HARNESS_ROOT;
  if (![root, sourceRoot, harnessRoot].every(value => typeof value === 'string' && isAbsolute(value))) fail('ABSOLUTE_ROOTS_REQUIRED');
  const config = {root: resolve(root), sourceRoot: resolve(sourceRoot), harnessRoot: resolve(harnessRoot)};
  if (config.root === parse(config.root).root || config.root === config.sourceRoot || config.root === config.harnessRoot ||
      inside(config.root, config.sourceRoot) || inside(config.root, config.harnessRoot)) fail('OUTPUT_ROOT_OVERLAPS_CHECKOUT');
  if (env.RUNNER_TEMP && !inside(resolve(env.RUNNER_TEMP), config.root)) fail('OUTPUT_OUTSIDE_RUNNER_TEMP');
  if (!SLUG.test(env.CRACI_WORKLOAD || '') || !SLUG.test(env.CRACI_CELL || '')) fail('INVALID_WORKLOAD_OR_CELL');
  if (!/^[0-9]{1,20}$/.test(env.GITHUB_RUN_ID || '') || !/^[0-9]{1,6}$/.test(env.GITHUB_RUN_ATTEMPT || '')) fail('INVALID_RUN_IDENTITY');
  const repository = env.GITHUB_REPOSITORY, sourceRepository = env.CRACI_SOURCE_REPOSITORY || repository;
  if (![repository, sourceRepository].every(value => typeof value === 'string' && value.length <= 120 && REPOSITORY.test(value))) fail('INVALID_REPOSITORY');
  let allowed;
  try {allowed = JSON.parse(env.CRACI_ALLOWED_SOURCE_CHANGES || '[]');} catch {fail('INVALID_SOURCE_ALLOWLIST');}
  if (!Array.isArray(allowed) || allowed.length > 8 || allowed.some(path => !safeRelative(path)) || new Set(allowed).size !== allowed.length)
    fail('INVALID_SOURCE_ALLOWLIST');
  const sourceSha = COMMIT.test(env.CRACI_SOURCE_SHA || '') ? env.CRACI_SOURCE_SHA : null;
  const harnessSha = COMMIT.test(env.CRACI_HARNESS_SHA || '') ? env.CRACI_HARNESS_SHA : null;
  const nextOwner = env.CRACI_NEXT_OWNER || 'Portfolio PR Recovery';
  if (nextOwner.length > 180 || /[\u0000-\u001f\u007f]/.test(nextOwner)) fail('INVALID_NEXT_OWNER');
  const runId = 'craci.' + env.GITHUB_RUN_ID + '.' + env.GITHUB_RUN_ATTEMPT + '.' +
    sha256(env.CRACI_WORKLOAD + ':' + env.CRACI_CELL).slice(0, 16);
  const binding = {runId, repository, sourceRepository, workload: env.CRACI_WORKLOAD, cell: env.CRACI_CELL,
    sourceSha, harnessSha, allowedSourceChanges: [...allowed].sort()};
  return {...config, ...binding, binding, nextOwner,
    evidenceUrl: 'https://github.com/' + repository + '/actions/runs/' + env.GITHUB_RUN_ID + '/attempts/' + env.GITHUB_RUN_ATTEMPT};
}

async function checkout(root, expected, allowed = []) {
  const out = {expectedCommit: expected, observedCommit: null, verified: false,
    basis: 'unverified', trackedChanges: [], diffSha256: null, overlays: [], reasons: []};
  try {
    await chain(root, true);
    const git = async args => (await exec('git', ['-C', root, ...args], {
      encoding: 'utf8', timeout: 15000, maxBuffer: 8 * 1024 * 1024,
    })).stdout;
    if (resolve((await git(['rev-parse', '--show-toplevel'])).trim()) !== root) fail('CHECKOUT_ROOT_MISMATCH');
    const observed = (await git(['rev-parse', 'HEAD'])).trim();
    if (COMMIT.test(observed)) out.observedCommit = observed;
    if (!COMMIT.test(expected || '') || observed !== expected) out.reasons.push('HEAD_MISMATCH_OR_MISSING_PIN');
    const changed = (await git(['diff', '--name-only', '-z', '--no-renames', 'HEAD', '--'])).split('\0').filter(Boolean);
    if (changed.length > 64 || changed.some(path => !safeRelative(path))) fail('INVALID_TRACKED_CHANGE_LIST');
    out.trackedChanges = changed.sort();
    if (changed.some(path => !allowed.includes(path))) out.reasons.push('UNEXPECTED_TRACKED_CHANGES');
    const diff = await git(['diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD', '--']);
    out.diffSha256 = sha256(diff);
    for (const path of changed.filter(path => allowed.includes(path))) {
      const content = await boundedRead(join(root, path), LIMITS.fileBytes);
      out.overlays.push({path, bytes: content.length, sha256: sha256(content)});
    }
    out.verified = out.reasons.length === 0;
    out.basis = out.verified ? changed.length ? 'commit-with-allowed-overlays' : 'clean-tracked-commit' : 'unverified';
  } catch (error) {out.reasons.push(knownError(error));}
  return out;
}
async function provenance(config) {
  const source = await checkout(config.sourceRoot, config.sourceSha, config.allowedSourceChanges);
  const harness = await checkout(config.harnessRoot, config.harnessSha);
  if (resolve(config.harnessRoot, 'scripts/craci/run-receipt.mjs') !== fileURLToPath(import.meta.url)) {
    harness.verified = false; harness.reasons.push('COLLECTOR_OUTSIDE_PINNED_HARNESS');
  }
  return {source, harness, verified: source.verified && harness.verified};
}

async function tee(stream, handle, output) {
  const stats = {observedBytes: 0, savedBytes: 0, truncated: false, captureError: null};
  try {
    for await (const chunk of stream) {
      const selected = chunk.subarray(0, Math.max(0, LIMITS.logBytes - stats.observedBytes));
      stats.observedBytes += chunk.length;
      if (selected.length) {
        try {await handle.writeFile(selected); stats.savedBytes += selected.length;}
        catch (error) {stats.captureError = knownError(error);}
        // Honor console backpressure too; a noisy child cannot queue unlimited logs.
        try {await new Promise((done, reject) => output.write(selected, error => error ? reject(error) : done()));}
        catch (error) {stats.captureError ||= knownError(error);}
      }
      if (stats.observedBytes > LIMITS.logBytes) stats.truncated = true;
    }
  } catch (error) {stats.captureError ||= knownError(error);}
  return stats;
}

export async function runCommand(argv, env = process.env) {
  if (!Array.isArray(argv) || !argv.length || argv.length > 100 || argv.some(arg => typeof arg !== 'string' || arg.includes('\0') || arg.length > 8192))
    fail('FIXED_COMMAND_REQUIRED');
  const config = configuration(env);
  await ensureDirectory(config.root);
  if (await optionalRead(join(config.root, 'command-start.json'))) fail('COMMAND_ALREADY_STARTED');
  try {await lstat(join(config.root, 'upload')); fail('OUTPUT_ALREADY_FINALIZED');} catch (error) {if (error.code !== 'ENOENT') throw error;}
  const before = await provenance(config);
  const startedAt = new Date().toISOString(), started = performance.now();
  const start = {schemaVersion: 1, binding: config.binding, startedAt, provenance: before,
    command: {executable: basename(argv[0]), argumentCount: argv.length - 1, argvSha256: sha256(canonicalJson(argv))}};
  await exclusiveWrite(join(config.root, 'command-start.json'), bytes(start));
  const result = {schemaVersion: 1, binding: config.binding, startSha256: sha256(bytes(start)),
    startedAt, finishedAt: null, wallSeconds: null, state: 'blocked', exitCode: null, signal: null,
    wrapperExitCode: 2, output: null, reason: null};
  if (!before.verified) result.reason = 'CHECKOUT_PROVENANCE_NOT_VERIFIED';
  else {
    const handles = await Promise.all(['stdout', 'stderr'].map(name => open(join(config.root, 'command.' + name + '.log'),
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600)));
    let child, spawnError = null;
    const listeners = new Map();
    try {
      child = spawn(argv[0], argv.slice(1), {env, stdio: ['ignore', 'pipe', 'pipe'], detached: process.platform !== 'win32'});
      for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) {
        const forward = () => {
          try {
            if (child.pid && process.platform !== 'win32') process.kill(-child.pid, signal);
            else child.kill(signal);
          } catch (error) {if (error.code !== 'ESRCH') spawnError ||= error;}
        };
        listeners.set(signal, forward); process.on(signal, forward);
      }
      const ended = new Promise(done => {
        child.once('error', error => {spawnError = error;});
        child.once('close', (exitCode, signal) => done({exitCode, signal}));
      });
      const [termination, stdout, stderr] = await Promise.all([
        ended, tee(child.stdout, handles[0], process.stdout), tee(child.stderr, handles[1], process.stderr),
      ]);
      result.output = {stdout, stderr};
      result.state = spawnError ? 'spawn-error' : 'completed';
      result.reason = spawnError ? knownError(spawnError) : null;
      result.exitCode = spawnError ? null : termination.exitCode;
      result.signal = termination.signal;
      result.wrapperExitCode = termination.signal ? null : spawnError ? 2 :
        termination.exitCode !== 0 ? termination.exitCode : stdout.captureError || stderr.captureError ? 2 : 0;
    } finally {
      for (const [signal, listener] of listeners) process.off(signal, listener);
      await Promise.all(handles.map(handle => handle.close()));
    }
  }
  result.finishedAt = new Date().toISOString();
  result.wallSeconds = Math.round((performance.now() - started) * 1000) / 1000;
  try {await exclusiveWrite(join(config.root, 'command.json'), bytes(result));}
  catch (error) {
    // Evidence failure must not replace an already observed child failure.
    if (!result.signal && !(Number.isInteger(result.exitCode) && result.exitCode !== 0)) throw error;
    result.receiptWriteError = knownError(error);
    console.error(JSON.stringify({status: 'incomplete', error: result.receiptWriteError, childExitCode: result.exitCode, childSignal: result.signal}));
  }
  return result;
}

async function collect(root) {
  const files = [], rejected = [];
  let total = 0, entries = 0;
  const reject = (code, path) => rejected.push({code, pathSha256: sha256(path)});
  async function walk(directory, prefix = '', depth = 0) {
    if (depth > LIMITS.depth) {reject('DIRECTORY_DEPTH_LIMIT', prefix); return;}
    try {await chain(directory, true);} catch (error) {reject(knownError(error), prefix); return;}
    const names = [];
    for await (const entry of await opendir(directory)) {
      if (++entries > LIMITS.entries) {reject('ENTRY_LIMIT', prefix); break;}
      names.push(entry.name);
    }
    for (const name of names.sort()) {
      const path = prefix ? prefix + '/' + name : name;
      if (!prefix && ['upload'].includes(name)) continue;
      if (!safeRelative(path)) {reject('UNSAFE_ARTIFACT_NAME', path); continue;}
      const absolute = join(directory, name);
      const stat = await lstat(absolute);
      if (stat.isSymbolicLink() || (!stat.isFile() && !stat.isDirectory())) {reject('NONREGULAR_ARTIFACT', path); continue;}
      if (stat.isDirectory()) {
        if ((!prefix && name !== 'artifacts') || (prefix && !prefix.startsWith('artifacts'))) reject('UNEXPECTED_DIRECTORY', path);
        else await walk(absolute, path, depth + 1);
        continue;
      }
      if ((!prefix && !RAW_FILES.has(name)) || (prefix && !EXTENSIONS.has(extname(name).toLowerCase()))) {
        reject('ARTIFACT_NOT_WHITELISTED', path); continue;
      }
      if (files.length >= LIMITS.files || stat.size > LIMITS.fileBytes || total + stat.size > LIMITS.payloadBytes) {
        reject('ARTIFACT_SIZE_OR_COUNT_LIMIT', path); continue;
      }
      try {
        const data = await boundedRead(absolute, Math.min(LIMITS.fileBytes, LIMITS.payloadBytes - total));
        total += data.length;
        files.push({path, bytes: data.length, sha256: sha256(data), data});
      } catch (error) {reject(knownError(error), path);}
    }
  }
  await walk(root);
  return {files, rejected, bytes: total};
}

async function previousUpload(config) {
  try {await lstat(join(config.root, 'upload'));} catch (error) {if (error.code === 'ENOENT') return null; throw error;}
  await chain(join(config.root, 'upload'), true);
  const previous = await optionalRead(join(config.root, 'upload', 'receipt.json'));
  if (!previous) fail('UNEXPECTED_UPLOAD_DIRECTORY');
  return decode(previous);
}
async function verifyPublished(root, expectedFiles) {
  const found = [];
  let entries = 0;
  async function walk(directory, prefix = '', depth = 0) {
    if (depth > LIMITS.depth + 2) fail('UNSAFE_PUBLISHED_PATH');
    await chain(directory, true);
    for await (const entry of await opendir(directory)) {
      if (++entries > LIMITS.entries + 10 || found.length > LIMITS.files + 10) fail('UNEXPECTED_PUBLISHED_FILE');
      const path = prefix ? prefix + '/' + entry.name : entry.name;
      if (!safeRelative(path) || entry.isSymbolicLink()) fail('UNSAFE_PUBLISHED_PATH');
      if (entry.isDirectory()) await walk(join(directory, entry.name), path, depth + 1);
      else {
        const expected = expectedFiles.get(path);
        if (!expected) fail('UNEXPECTED_PUBLISHED_FILE');
        const actual = await boundedRead(join(directory, entry.name), LIMITS.fileBytes);
        if (!actual.equals(expected)) fail('IMMUTABLE_UPLOAD_CONFLICT');
        found.push(path);
      }
    }
  }
  await walk(root);
  if (found.length !== expectedFiles.size) fail('MISSING_PUBLISHED_FILE');
}
async function outputFlag(env, ready) {
  if (env.GITHUB_OUTPUT) await appendFile(env.GITHUB_OUTPUT, 'upload_ready=' + String(ready) + '\n');
}

export async function finalizeReceipt(env = process.env) {
  const config = configuration(env);
  await ensureDirectory(config.root);
  const previous = await previousUpload(config);
  const current = await provenance(config);
  const payload = await collect(config.root);
  const issues = [];
  let start = null, command = null;
  try {
    const startBytes = await optionalRead(join(config.root, 'command-start.json'));
    const commandBytes = await optionalRead(join(config.root, 'command.json'));
    start = startBytes ? decode(startBytes) : null;
    command = commandBytes ? decode(commandBytes) : null;
    if (!start || !command) issues.push('COMMAND_EVIDENCE_MISSING');
    else if (canonicalJson(start.binding) !== canonicalJson(config.binding) ||
      canonicalJson(command.binding) !== canonicalJson(config.binding) || command.startSha256 !== sha256(startBytes))
      issues.push('COMMAND_BINDING_MISMATCH');
  } catch {issues.push('COMMAND_EVIDENCE_INVALID');}
  if (!current.verified || (start && !start.provenance?.verified)) issues.push('SOURCE_OR_HARNESS_UNVERIFIED');
  if (command && command.state !== 'completed') issues.push('COMMAND_DID_NOT_COMPLETE');
  if (command?.state === 'completed' && !['stdout', 'stderr'].every(name => {
    const stats = command.output?.[name];
    const file = payload.files.find(item => item.path === 'command.' + name + '.log');
    return stats && file && Number.isSafeInteger(stats.observedBytes) && stats.observedBytes >= 0 &&
      Number.isSafeInteger(stats.savedBytes) && stats.savedBytes >= 0 && stats.savedBytes <= LIMITS.logBytes &&
      stats.observedBytes >= stats.savedBytes && stats.savedBytes === file.bytes &&
      typeof stats.truncated === 'boolean' && (stats.captureError || stats.truncated === (stats.observedBytes > LIMITS.logBytes));
  })) issues.push('COMMAND_LOG_EVIDENCE_MISSING_OR_INVALID');
  if (command?.output && Object.values(command.output).some(value => value.captureError)) issues.push('LOG_CAPTURE_INCOMPLETE');
  if (payload.rejected.length) issues.push('ARTIFACT_COLLECTION_INCOMPLETE');
  const jobStatus = env.CRACI_JOB_STATUS || 'unknown', stageOutcome = env.CRACI_STAGE_OUTCOME || 'unknown';
  if (!['success', 'failure', 'cancelled', 'skipped'].includes(jobStatus) ||
      !['success', 'failure', 'cancelled', 'skipped'].includes(stageOutcome)) issues.push('JOB_OR_STAGE_OUTCOME_UNKNOWN');
  if (['cancelled', 'skipped'].includes(jobStatus) || ['cancelled', 'skipped'].includes(stageOutcome)) issues.push('JOB_OR_STAGE_NOT_COMPLETED');
  const failed = command?.signal || (Number.isInteger(command?.exitCode) && command.exitCode !== 0) ||
    command?.wrapperExitCode !== 0 || jobStatus === 'failure' || stageOutcome === 'failure';
  if (command && command.state === 'completed' && !command.signal && !Number.isInteger(command.exitCode)) issues.push('COMMAND_EXIT_UNKNOWN');
  const status = issues.length ? 'incomplete' : failed ? 'failed' : 'succeeded';
  const manifest = {schemaVersion: 1, runId: config.runId, complete: payload.rejected.length === 0,
    limits: LIMITS, totalPayloadBytes: payload.bytes, files: payload.files.map(({data, ...file}) => file), rejected: payload.rejected};
  const manifestBytes = bytes(manifest), manifestSha256 = sha256(manifestBytes);
  const sourceCommit = COMMIT.test(current.source.observedCommit || '') ? current.source.observedCommit :
    COMMIT.test(config.sourceSha || '') ? config.sourceSha : null;
  const receipt = {schemaVersion: 1, runId: config.runId, kind: 'synthetic-test', evidenceLevel: 'source-reported',
    capturedAt: previous?.capturedAt || new Date().toISOString(), binding: config.binding, status,
    jobStatus, stageOutcome, sourceVerified: current.source.verified, harnessVerified: current.harness.verified,
    provenance: {before: start?.provenance || null, after: current},
    command, issues, manifest: {path: 'manifest.json', sha256: manifestSha256},
    cost: {actual: null, estimate: null, currency: 'EUR', reason: 'No authenticated job-level billing or priced resource measurement supplied.'},
    nextOwner: config.nextOwner, evidenceUrl: config.evidenceUrl,
    registry: {path: sourceCommit ? 'registry/runs/' + config.runId + '.json' : null,
      status: sourceCommit ? 'recorded' : 'blocked-no-valid-source-commit'},
    providerAttestationVerified: false, sponsorIntegrationVerified: false,
    limitations: ['Source-reported execution evidence; no provider attestation.',
      'Wall time measures the wrapped command only; setup and queue time are excluded.',
      'Only tracked checkout changes are inspected; private and untracked files are not collected.']};
  if (!sourceCommit && !receipt.issues.includes('NO_VALID_SOURCE_COMMIT')) {
    receipt.status = 'incomplete'; receipt.issues.push('NO_VALID_SOURCE_COMMIT');
  }
  const receiptBytes = bytes(receipt);
  if (receiptBytes.length > LIMITS.jsonBytes || manifestBytes.length > LIMITS.jsonBytes) fail('RECEIPT_METADATA_TOO_LARGE');
  const run = sourceCommit ? {
    schemaVersion: 1, runId: config.runId, projectId: 'junction-pets', taskId: 'craci.' + config.workload,
    kind: 'synthetic-test', capturedAt: receipt.capturedAt, status: receipt.status,
    source: {repository: config.sourceRepository, commit: sourceCommit},
    evidence: {level: 'source-reported', ref: config.evidenceUrl, receiptSha256: sha256(receiptBytes)},
    dataset: null, evaluation: null, artifact: {type: 'report', sha256: manifestSha256},
    metrics: Number.isFinite(command?.wallSeconds) && command.wallSeconds >= 0 ?
      [{id: 'command-wall-seconds', value: command.wallSeconds, unit: 'seconds', direction: 'lower', samples: 1}] : [],
    limitations: [...receipt.limitations,
      ...(!current.source.verified ? ['Source commit is observed or requested only; source verification failed.'] : []),
      ...(current.source.trackedChanges.length ? ['Source includes explicitly allowed tracked overlays; see receipt digests.'] : []),
      ...(!current.harness.verified ? ['Harness checkout was not verified.'] : []),
      ...receipt.issues.map(issue => 'Receipt limitation: ' + issue)],
    policySha256: null,
  } : null;
  if (run) validateRun(run);
  const expectedFiles = new Map(payload.files.map(file => [file.path, file.data]));
  expectedFiles.set('manifest.json', manifestBytes); expectedFiles.set('receipt.json', receiptBytes);
  if (run) expectedFiles.set(receipt.registry.path, bytes(run));
  if (previous) {
    if (canonicalJson(previous) !== canonicalJson(receipt)) fail('IMMUTABLE_RECEIPT_CONFLICT');
    await verifyPublished(join(config.root, 'upload'), expectedFiles);
  } else {
    const staging = await mkdtemp(join(config.root, '.receipt-stage-'));
    for (const [path, content] of expectedFiles) {
      if (path.startsWith('registry/')) continue; // Existing registry API owns its record format and persistence.
      await ensureDirectory(dirname(join(staging, path)));
      await exclusiveWrite(join(staging, path), content);
    }
    if (run) await recordRun(join(staging, 'registry'), run);
    await verifyPublished(staging, expectedFiles);
    await rename(staging, join(config.root, 'upload'));
  }
  await outputFlag(env, true);
  return {runId: config.runId, status: receipt.status, uploadReady: true,
    files: expectedFiles.size, receipt: 'upload/receipt.json', registryRecorded: Boolean(run)};
}

async function main() {
  const [operation, ...args] = process.argv.slice(2);
  if (operation === 'run') {
    if (args.shift() !== '--') fail('COMMAND_SEPARATOR_REQUIRED');
    const result = await runCommand(args);
    if (result.signal) {
      process.kill(process.pid, result.signal);
      return;
    }
    process.exitCode = result.wrapperExitCode;
  } else if (operation === 'finalize' && !args.length) {
    const result = await finalizeReceipt();
    console.log(JSON.stringify(result));
    process.exitCode = result.status === 'succeeded' ? 0 : 1;
  } else fail('USE_RUN_OR_FINALIZE');
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(async error => {
    if (process.argv[2] === 'finalize') await outputFlag(process.env, false).catch(() => {});
    console.error(JSON.stringify({status: 'incomplete', error: knownError(error), uploadReady: false}));
    process.exitCode = 2;
  });
}
