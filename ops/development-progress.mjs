// Private, read-only historical continuity. No provider, dispatch or attestation authority.
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {lstatSync, realpathSync, openSync, closeSync, fstatSync, readSync, constants} from 'node:fs';
import {join, resolve} from 'node:path';
import {EXPECTED_COMPANIES} from '../lib/catalog.mjs';

export const PROGRESS_LIMITS = Object.freeze({ledgerBytes: 262144, files: 256, fileBytes: 1048576, scopeBytes: 8388608});
const repository = 'SalesSquad/junction-pets';
const sha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9/_][A-Za-z0-9._:/-]{0,159}$/.test(value);
const receiptUrl = value => typeof value === 'string' && /^https:\/\/github\.com\/SalesSquad\/junction-pets\/pull\/[1-9][0-9]*(?:#(?:issuecomment-|pullrequestreview-|discussion_r)[0-9]+)?$/.test(value);
const taskUrl = value => typeof value === 'string' && /^https:\/\/chatgpt\.com\/(?:local\/[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}|codex\/tasks\/task_[a-z0-9_]{8,100})$/.test(value);
const requireValue = (condition, reason) => { if (!condition) throw new Error(`Invalid development progress: ${reason}`); };
function shape(value, keys) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join('|') === keys.split(' ').sort().join('|'), 'unknown or missing fields');
}
function count(value) {
  shape(value, 'passed total');
  requireValue(Number.isSafeInteger(value.total) && value.total > 0 && value.total <= 1000000 &&
    Number.isSafeInteger(value.passed) && value.passed >= 0 && value.passed <= value.total, 'original test counts');
}

/** Standard JSON.parse semantics (duplicate object members use the last value). */
export function parseDevelopmentProgress(text) {
  requireValue(typeof text === 'string' && Buffer.byteLength(text) <= PROGRESS_LIMITS.ledgerBytes, 'bounded JSON text required');
  let ledger;
  try { ledger = JSON.parse(text); } catch { throw new Error('Invalid development progress: JSON syntax'); }
  shape(ledger, 'schemaVersion repository observedAt records');
  requireValue(ledger.schemaVersion === 1 && ledger.repository === repository, 'schema or repository');
  requireValue(typeof ledger.observedAt === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(ledger.observedAt) &&
    Number.isFinite(Date.parse(ledger.observedAt)) && new Date(ledger.observedAt).toISOString() === ledger.observedAt, 'strict UTC observedAt');
  requireValue(Array.isArray(ledger.records) && ledger.records.length === EXPECTED_COMPANIES.length, 'exactly 34 companies required');
  const seen = new Set();
  for (const record of ledger.records) {
    shape(record, 'company agentId workId branch source pr integrationPr executor review checks writerState nextAction scopeSha256');
    const company = record.company;
    requireValue(EXPECTED_COMPANIES.includes(company) && !seen.has(company), 'unknown or duplicate company');
    seen.add(company);
    requireValue(record.agentId === `junction-dev-${company}` && typeof record.workId === 'string' &&
      new RegExp(`^junction\\.${company}\\.[a-z0-9][a-z0-9.-]{0,95}$`).test(record.workId), 'logical owner or work ID');
    requireValue(typeof record.branch === 'string' && /^codex\/[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$/.test(record.branch) &&
      !record.branch.includes('..') && !record.branch.split('/').some(part => !part || part.startsWith('.') || part.endsWith('.') || part.endsWith('.lock')), 'task branch');
    shape(record.source, 'base head tree');
    requireValue(Object.values(record.source).every(sha), 'reviewed source base/head/tree');
    shape(record.pr, 'url mergeCommit');
    requireValue(receiptUrl(record.pr.url) && (record.pr.mergeCommit === null || sha(record.pr.mergeCommit)) &&
      (record.integrationPr === null || receiptUrl(record.integrationPr)), 'PR or merge evidence');
    shape(record.executor, 'kind id taskUrl');
    requireValue(identifier(record.executor.id) && ((record.executor.kind === 'native' && record.executor.taskUrl === null) ||
      (record.executor.kind === 'codex-cloud' && taskUrl(record.executor.taskUrl))), 'actual executor kind/id/task URL');
    shape(record.review, 'reviewer head verdict evidenceUrl');
    requireValue(identifier(record.review.reviewer) && record.review.reviewer !== record.executor.id &&
      record.review.head === record.source.head && record.review.verdict === 'pass' && receiptUrl(record.review.evidenceUrl), 'independent reviewed HEAD claim');
    shape(record.checks, 'focused full evidenceUrl');
    count(record.checks.focused); count(record.checks.full);
    requireValue(receiptUrl(record.checks.evidenceUrl) || taskUrl(record.checks.evidenceUrl), 'original check evidence URL');
    requireValue(record.writerState === 'released', 'finite writer must be released');
    shape(record.nextAction, 'state owner action');
    requireValue(record.nextAction.state === 'proposed-not-started' && identifier(record.nextAction.owner) &&
      typeof record.nextAction.action === 'string' && record.nextAction.action.trim().length > 0 &&
      record.nextAction.action.length <= 600 && !/[\x00-\x1f\x7f]/.test(record.nextAction.action), 'one proposed next action');
    requireValue(typeof record.scopeSha256 === 'string' && /^[a-f0-9]{64}$/.test(record.scopeSha256), 'scope SHA-256');
  }
  return ledger;
}

// Check every path component and refuse symlinks, including the known ledger path.
// Bounded FD reads avoid following a replaced final symlink or unbounded file growth.
function boundedFile(root, path, limit) {
  let current = root;
  const parts = path.split('/');
  for (const [index, part] of parts.entries()) {
    current = join(current, part);
    const stat = lstatSync(current);
    if (stat.isSymbolicLink() || (index < parts.length - 1 && !stat.isDirectory())) throw new Error('Source symlink or non-directory refused');
  }
  const fd = openSync(current, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = fstatSync(fd);
    if (!before.isFile()) throw new Error('Source must be a regular file');
    if (before.size > limit) throw new Error('Source byte limit exceeded');
    const buffer = Buffer.alloc(limit + 1);
    let size = 0, read;
    while (size < buffer.length && (read = readSync(fd, buffer, size, buffer.length - size, null)) !== 0) size += read;
    const after = fstatSync(fd), pathStat = lstatSync(current);
    if (size > limit) throw new Error('Source byte limit exceeded');
    if (pathStat.isSymbolicLink() || pathStat.ino !== before.ino || pathStat.dev !== before.dev || after.size !== size ||
      before.size !== size || before.mtimeMs !== after.mtimeMs || before.mode !== after.mode) throw new Error('Source changed while reading; retry from a stable checkout');
    return {bytes: buffer.subarray(0, size), mode: before.mode & 0o111 ? '100755' : '100644'};
  } finally { closeSync(fd); }
}
const git = (root, args) => execFileSync('git', ['-C', root, ...args], {encoding: 'utf8', maxBuffer: 1048576, timeout: 10000, stdio: ['ignore', 'pipe', 'pipe']});

/** Hash tracked scope paths and actual file modes/bytes, not an asserted Git SHA. */
export function companyScopeSha256(root, company) {
  requireValue(EXPECTED_COMPANIES.includes(company), 'unknown company');
  root = realpathSync(resolve(root));
  if (realpathSync(git(root, ['rev-parse', '--show-toplevel']).trim()) !== root) throw new Error('Source root must be the Git toplevel');
  const prefixes = [`pets/${company}/`, `plugins/junction-${company}/`], testPath = `tests/pet-${company}.test.mjs`;
  const raw = git(root, ['ls-files', '--stage', '-z', '--', ...prefixes, testPath]);
  const entries = raw.split('\0').filter(Boolean);
  if (!entries.length || entries.length > PROGRESS_LIMITS.files) throw new Error('Missing source or tracked file count limit exceeded');
  const paths = entries.map(entry => {
    const match = /^(100644|100755) [a-f0-9]{40} 0\t([^\0]+)$/.exec(entry);
    if (!match) throw new Error('Unsupported Git mode, symlink or unmerged index');
    const path = match[2];
    if (path.length > 240 || !/^[A-Za-z0-9._/-]+$/.test(path) || path.split('/').some(part => !part || ['.', '..', '.git'].includes(part)) ||
      !(prefixes.some(prefix => path.startsWith(prefix)) || path === testPath)) throw new Error('Malformed tracked scope path');
    return path;
  }).sort();
  if (new Set(paths).size !== paths.length || !paths.includes(testPath) || prefixes.some(prefix => !paths.some(path => path.startsWith(prefix)))) throw new Error('Duplicate or missing tracked company scope');
  const digest = createHash('sha256').update(`junction-company-scope-v1\0${company}\0`);
  let total = 0;
  for (const path of paths) {
    const {bytes, mode} = boundedFile(root, path, Math.min(PROGRESS_LIMITS.fileBytes, PROGRESS_LIMITS.scopeBytes - total));
    total += bytes.length;
    digest.update([path, mode, bytes.length, ''].join('\0')).update(bytes);
  }
  if (git(root, ['ls-files', '--stage', '-z', '--', ...prefixes, testPath]) !== raw) throw new Error('Git index changed while reading; retry');
  return digest.digest('hex');
}

export function readDevelopmentProgress(root, {pet = null} = {}) {
  requireValue(pet === null || EXPECTED_COMPANIES.includes(pet), 'unknown company');
  root = realpathSync(resolve(root));
  const ledger = parseDevelopmentProgress(boundedFile(root, 'ops/development-progress.json', PROGRESS_LIMITS.ledgerBytes).bytes.toString('utf8'));
  const records = ledger.records.filter(record => pet === null || record.company === pet).map(record => {
    let sourceCheck;
    try {
      const actualSha256 = companyScopeSha256(root, record.company);
      sourceCheck = {state: actualSha256 === record.scopeSha256 ? 'source-matched' : 'stale', actualSha256, reason: null};
    } catch (error) { sourceCheck = {state: 'unverified', actualSha256: null, reason: error.message}; }
    return {...record, sourceCheck};
  });
  return {
    repository, observedAt: ledger.observedAt,
    summary: {companies: records.length, sourceMatched: records.filter(record => record.sourceCheck.state === 'source-matched').length,
      stale: records.filter(record => record.sourceCheck.state === 'stale').map(record => record.company),
      unverified: records.filter(record => record.sourceCheck.state === 'unverified').map(record => record.company),
      writerState: 'released', nextActions: 'proposed-not-started'},
    qualification: {scope: 'local-tracked-company-bytes-only', currentFullSuite: 'unverified', remote: 'unverified', provider: 'unverified', host: 'unverified', provenanceAuthenticated: false},
    records,
  };
}
