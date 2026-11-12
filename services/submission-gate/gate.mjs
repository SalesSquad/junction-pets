import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { constants } from 'node:fs';
import { lstat, open, opendir } from 'node:fs/promises';
import { posix, relative, resolve, sep } from 'node:path';

const SOURCE_REPOSITORY = 'SalesSquad/junction-pets';
const SHA40 = /^[a-f0-9]{40}$/i;
const SHA256 = /^[a-f0-9]{64}$/i;
const SAFE_PATH = /^[A-Za-z0-9._/-]+$/;
const TEXT_EXT = /\.(?:css|html|js|json|mjs|md|py|rs|sql|toml|ts|tsx|txt|yaml|yml)$/i;
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const PUBLIC_ROOT_FILES = new Set(['README.md', 'LICENSE', 'NOTICE', 'COPYING', 'package.json', 'package-lock.json', 'catalog-contract.md']);
const PUBLIC_DOCS = new Set(['JUNCTION_SUBMISSION.md', 'BEHAVIOR_EVALS.md', 'INTER_PET_COLLABORATION.md', 'DEMO.md', 'PROVENANCE.md', 'OPEN_SOURCE.md', 'THIRD_PARTY_NOTICES.md']);
const PUBLIC_PET_FILES = new Set(['AGENTS.md', 'STORY.md', 'README.md', 'LICENSE', 'pet.json', 'evals.json']);
const PUBLIC_SERVICES = new Set(['council', 'dispatch-ledger', 'eval-runner', 'submission-gate']);
const PUBLIC_LIB_FILES = new Set(['pet-collaboration.mjs', 'behavior-eval.mjs', 'artifact.mjs']);
const FORBIDDEN_ROOTS = new Set([
  '.git', '.github', 'ops', 'plugins', 'private', 'internal',
  'chibi', 'chibi-runtime', 'chibi-marketplace', 'node_modules',
  '.codex', '.claude', '.ssh', 'dist'
]);
const FORBIDDEN_SEGMENTS = new Set([
  '.env', '.git', '.ssh', '.codex', '.claude', 'node_modules',
  'secrets', 'credentials', 'token', 'tokens', 'receipts',
  'passport', 'payments', 'billing', 'customer-data',
  'plugin-registrations', 'worktrees', 'chibi', 'chibi-runtime',
  'chibi-marketplace', 'private-chibi', 'account-records',
  'private', 'internal', 'auth', 'oauth', 'accounts', 'user-data',
  'customer-records', 'provider-private', 'host-secrets'
]);
const SECRET_PATTERNS = Object.freeze([
  ['private_key', /-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----/],
  ['openai_key', /\bsk-(?:proj-|live-)?[A-Za-z0-9_-]{24,}\b/],
  ['github_token', /\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}\b/],
  ['aws_access_key', /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/],
  ['slack_token', /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/],
  ['jwt', /\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\b/],
  ['credential_assignment', /\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password)\s*[:=]\s*[\"'][A-Za-z0-9_./+\-]{20,}[\"']/i]
]);

export class SubmissionGateError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'SubmissionGateError';
    this.code = code;
  }
}

function reject(code, message) {
  throw new SubmissionGateError(code, message);
}

export function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

export function assertSafePath(path) {
  if (typeof path !== 'string' || path.length < 1 || path.length > 512) {
    reject('INVALID_PATH', 'Submission file path must be a bounded relative string.');
  }
  if (!SAFE_PATH.test(path) || path.startsWith('/') || path.startsWith('./') ||
      path.includes('//') || path.includes('/./') || path.includes('/../') ||
      path.endsWith('/') || posix.normalize(path) !== path ||
      path.split('/').includes('..') || path.split('/').includes('.')) {
    reject('INVALID_PATH', 'Submission file path is not a normalized portable relative path.');
  }
  return path;
}

function isInPublicSourceScope(path) {
  const parts = path.split('/');
  if (parts.length === 1) return PUBLIC_ROOT_FILES.has(path);
  if (parts[0] === 'docs') return parts.length === 2 && PUBLIC_DOCS.has(parts[1]);
  if (parts[0] === 'pets') return parts.length === 3 && PUBLIC_PET_FILES.has(parts[2]);
  if (parts[0] === 'lib') return parts.length === 2 && PUBLIC_LIB_FILES.has(parts[1]);
  if (parts[0] === 'contracts') return parts[1] === 'pet-collaboration' && parts[2] === 'v1' && parts.length >= 4;
  if (parts[0] === 'services') return PUBLIC_SERVICES.has(parts[1]) && parts.length >= 3;
  if (parts[0] === 'apps') return (parts[1] === 'collaboration-demo' || parts[1] === 'catalog') && parts.length >= 3;
  if (parts[0] === 'tests') return parts.length >= 2;
  return false;
}

function isPublicDirectoryPrefix(path) {
  const parts = path.split('/');
  if (parts.length === 1) return new Set(['docs', 'pets', 'lib', 'contracts', 'services', 'apps', 'tests']).has(parts[0]);
  if (parts[0] === 'pets') return parts.length === 2;
  if (parts[0] === 'services') return PUBLIC_SERVICES.has(parts[1]);
  if (parts[0] === 'contracts') return parts[1] === 'pet-collaboration' && (parts.length === 2 || parts[2] === 'v1');
  if (parts[0] === 'apps') return parts[1] === 'collaboration-demo' || parts[1] === 'catalog';
  if (parts[0] === 'tests') return true;
  return false;
}

export function isHardDenied(path, { directory = false } = {}) {
  assertSafePath(path);
  const lower = path.toLowerCase();
  const segments = lower.split('/');
  if (FORBIDDEN_ROOTS.has(segments[0]) ||
      segments.some((part) => FORBIDDEN_SEGMENTS.has(part)) ||
      segments.some((part) => part.startsWith('.env'))) return true;
  if (segments[0] === 'apps' && segments[1] === 'mission-control') return true;
  if (lower.includes('plugin-registration') ||
      lower.includes('oauth-secret') ||
      lower.includes('chibi-private') ||
      lower.includes('secret-hub')) return true;
  if (/\.(?:db|sqlite|sqlite3|pem|key|p12|pfx|p8|mobileprovision|keystore|jks|env)$/i.test(lower)) {
    return true;
  }
  return directory ? !isPublicDirectoryPrefix(path) : !isInPublicSourceScope(path);
}

export function inspectText(bytes, path) {
  if (bytes.length > MAX_FILE_BYTES) reject('TOO_LARGE', 'Submission file exceeds 2 MiB: ' + path);
  if (!TEXT_EXT.test(path) && !/(^|\/)(?:LICENSE|NOTICE|COPYING)$/i.test(path)) {
    reject('UNREVIEWED_BINARY', 'Only reviewed UTF-8 source/text is accepted: ' + path);
  }
  let value;
  try {
    value = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    reject('INVALID_TEXT', 'Submission file must be UTF-8: ' + path);
  }
  if (value.includes('\u0000')) reject('INVALID_TEXT', 'NUL is not permitted in submission text.');
  if (value.startsWith('version https://git-lfs.github.com/spec/v1')) {
    reject('LFS_POINTER', 'Git LFS pointer is not the actual reviewed file.');
  }
  for (const [code, regex] of SECRET_PATTERNS) {
    if (regex.test(value)) reject('SECRET_MATCH', 'Potential ' + code + ' found in ' + path);
  }
}

export function validateAllowlist(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input) ||
      input.schemaVersion !== 1 || input.sourceRepository !== SOURCE_REPOSITORY ||
      !SHA40.test(input.sourceRevision) || !Array.isArray(input.files) ||
      input.files.length === 0 || input.files.length > 2000) {
    reject('INVALID_ALLOWLIST', 'Expected a non-empty versioned SalesSquad/junction-pets allowlist with a 40-character source commit.');
  }
  const seen = new Set();
  const paths = [];
  for (const row of input.files) {
    if (!row || typeof row !== 'object' || Array.isArray(row) ||
        Object.keys(row).sort().join(',') !== 'path,sha256' ||
        typeof row.path !== 'string' || typeof row.sha256 !== 'string' ||
        !SHA256.test(row.sha256)) {
      reject('INVALID_ALLOWLIST', 'Each allowlist entry needs only path and 64-character sha256.');
    }
    const path = assertSafePath(row.path);
    const caseFold = path.toLowerCase();
    if (seen.has(caseFold)) reject('DUPLICATE_PATH', 'Duplicate or case-fold collision in allowlist.');
    if (isHardDenied(path)) reject('HARD_DENY', 'Private or internal path cannot be allowlisted: ' + path);
    seen.add(caseFold);
    paths.push({ path, sha256: row.sha256.toLowerCase() });
  }
  paths.sort((a, b) => a.path.localeCompare(b.path, 'en'));
  return {
    schemaVersion: 1,
    sourceRepository: SOURCE_REPOSITORY,
    sourceRevision: input.sourceRevision.toLowerCase(),
    files: paths
  };
}

async function scanTree(root, dir, prefix, found, budget) {
  const directory = await opendir(dir);
  for await (const row of directory) {
    budget.entries += 1;
    if (budget.entries > budget.maximum) reject('TOO_MANY_ENTRIES', 'Proposed export has too many directory entries.');
    const rel = prefix ? prefix + '/' + row.name : row.name;
    assertSafePath(rel);
    const absolute = resolve(dir, row.name);
    const st = await lstat(absolute);
    if (st.isSymbolicLink()) reject('SYMLINK', 'Symlink is forbidden in proposed export: ' + rel);
    if (isHardDenied(rel, { directory: st.isDirectory() })) {
      reject('HARD_DENY', 'Private or internal path in proposed export: ' + rel);
    }
    if (st.isDirectory()) {
      await scanTree(root, absolute, rel, found, budget);
      continue;
    }
    if (!st.isFile()) reject('UNSUPPORTED_ENTRY', 'Unsupported non-file entry in proposed export.');
    if (st.size > MAX_FILE_BYTES) reject('TOO_LARGE', 'Submission file exceeds 2 MiB: ' + rel);
    if (relative(root, absolute).startsWith('..' + sep)) {
      reject('PATH_ESCAPE', 'Resolved export path escaped the submission root.');
    }
    found.push({ path: rel, absolute });
  }
}

async function readBoundedRegular(path) {
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const st = await handle.stat();
    if (!st.isFile()) reject('UNSUPPORTED_ENTRY', 'Export entry stopped being a regular file.');
    if (st.size > MAX_FILE_BYTES) reject('TOO_LARGE', 'Submission file exceeds 2 MiB: ' + path);
    const bytes = Buffer.allocUnsafe(MAX_FILE_BYTES + 1);
    let total = 0;
    while (total < bytes.length) {
      const { bytesRead } = await handle.read(bytes, total, bytes.length - total, total);
      if (bytesRead === 0) break;
      total += bytesRead;
    }
    if (total > MAX_FILE_BYTES) reject('TOO_LARGE', 'Submission file grew past 2 MiB during scan.');
    return bytes.subarray(0, total);
  } finally {
    await handle.close();
  }
}

function git(repo, args, asText = false) {
  try {
    return execFileSync('git', ['-C', repo, ...args], {
      encoding: asText ? 'utf8' : undefined,
      maxBuffer: 16 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe']
    });
  } catch {
    reject('SOURCE_UNVERIFIED', 'Cannot verify the pinned source revision and tracked files.');
  }
}

function checkSource(repo, sourceRevision) {
  const origin = git(repo, ['remote', 'get-url', 'origin'], true).trim();
  if (origin !== 'https://github.com/SalesSquad/junction-pets.git' &&
      origin !== 'git@github.com:SalesSquad/junction-pets.git') {
    reject('SOURCE_ORIGIN', 'Source checkout origin is not the expected Junction repository.');
  }
  const current = git(repo, ['rev-parse', 'HEAD'], true).trim().toLowerCase();
  if (current !== sourceRevision) {
    reject('STALE_SOURCE', 'The source checkout HEAD does not match the allowlist commit.');
  }
  const dirty = git(repo, ['status', '--porcelain'], true).trim();
  if (dirty) {
    reject('DIRTY_SOURCE', 'Source checkout contains uncommitted/untracked changes.');
  }
}

function gitBlob(repo, revision, path) {
  const result = git(repo, ['ls-tree', '-z', revision, '--', path]);
  const line = result.toString('utf8').replace(/\0$/, '');
  const match = /^(100644|100755) blob [a-f0-9]{40}\t([^\0]+)$/.exec(line);
  if (!match || match[2] !== path) {
    reject('SOURCE_NOT_REGULAR_FILE', 'Allowlisted path is not a regular tracked source file: ' + path);
  }
  return git(repo, ['show', revision + ':' + path]);
}

export async function verifySubmission({ treeDir, sourceRepo, allowlist }) {
  if (!treeDir || !sourceRepo) reject('ARGUMENTS', 'Both treeDir and sourceRepo are required.');
  const config = validateAllowlist(allowlist);
  const root = resolve(treeDir);
  const st = await lstat(root);
  if (!st.isDirectory() || st.isSymbolicLink()) reject('INVALID_ROOT', 'The submission root must be a real directory.');
  checkSource(resolve(sourceRepo), config.sourceRevision);
  const found = [];
  await scanTree(root, root, '', found, {
    entries: 0,
    maximum: Math.min(10000, config.files.length * 8 + 32)
  });
  if (found.length !== config.files.length) {
    reject('UNEXPECTED_FILES', 'The proposed export file count differs from its exact allowlist.');
  }
  found.sort((a, b) => a.path.localeCompare(b.path, 'en'));
  const files = [];
  for (let i = 0; i < found.length; i++) {
    const row = found[i];
    const expected = config.files[i];
    if (row.path !== expected.path) {
      reject('UNEXPECTED_FILES', 'Proposed export contains a path not in the exact allowlist.');
    }
    const bytes = await readBoundedRegular(row.absolute);
    inspectText(bytes, row.path);
    const hash = sha256(bytes);
    if (hash !== expected.sha256) {
      reject('HASH_MISMATCH', 'Proposed export does not match the reviewed file digest: ' + row.path);
    }
    const sourceBytes = gitBlob(resolve(sourceRepo), config.sourceRevision, row.path);
    if (sha256(sourceBytes) !== hash) {
      reject('SOURCE_MISMATCH', 'Proposed export differs from pinned Git source: ' + row.path);
    }
    files.push({ path: row.path, bytes: bytes.length, sha256: hash });
  }
  return {
    schemaVersion: 1,
    sourceRepository: SOURCE_REPOSITORY,
    sourceRevision: config.sourceRevision,
    allowlistSha256: sha256(Buffer.from(JSON.stringify(config))),
    fileCount: files.length,
    files,
    check: 'exact-source-bytes-with-heuristic-secret-screen',
    status: 'reviewable-not-published',
    caveat: 'Requires separate human/legal/brand review; this is not release or submission authorization.'
  };
}
