// Offline consistency of invented declarations only. No I/O, tools or authority.
const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const ID = /^[a-z0-9][a-z0-9-]{0,79}$/;
const LABEL = /^fictional-[a-z0-9][a-z0-9.-]{0,79}$/;
function requireValue(ok, message) { if (!ok) throw new TypeError(message); }
function fields(value, keys, name) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value), `${name} must be an object`);
  requireValue(Object.keys(value).length === keys.length && keys.every(k => Object.hasOwn(value, k)), `${name} fields must be exactly ${keys.join(', ')}`);
}
function list(value, min, max, name) {
  requireValue(Array.isArray(value) && value.length >= min && value.length <= max, `${name} must contain ${min}..${max} items`);
}
function matches(value, pattern, name) { requireValue(typeof value === 'string' && !/[\u0000-\u001f\u007f]/.test(value) && pattern.test(value), `invalid ${name}`); }
function command(value) { requireValue(typeof value === 'string' && value.trim().length > 0 && value.length <= 512 && !/[\u0000-\u001f\u007f]/.test(value), 'invalid inert command'); }
function count(value, max, name) { requireValue(value === null || Number.isSafeInteger(value) && value >= 0 && value <= max, `invalid ${name}`); }
function paths(value, max, directories, name) {
  list(value, 1, max, name);
  const seen = new Set();
  for (const p of value) {
    requireValue(typeof p === 'string' && p.length <= 240 && !/[\u0000-\u001f\u007f]/.test(p) && /^[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*\/?$/.test(p) &&
      !p.split('/').some(x => x === '.' || x === '..') && (directories || !p.endsWith('/')), 'invalid repository path');
    requireValue(!seen.has(p), `duplicate ${name}`); seen.add(p);
  }
}

/** Parse <=32 KiB JSON text; check consistency, never authenticate test receipts. */
export function verifySyntheticHandoff(text) {
  requireValue(typeof text === 'string' && Buffer.byteLength(text, 'utf8') <= 32768, 'expected at most 32768 UTF-8 bytes of JSON text');
  let data;
  try { data = JSON.parse(text); } catch { throw new TypeError('invalid JSON text'); }
  fields(data, ['schemaVersion', 'kind', 'repository', 'workId', 'headSha', 'authorId', 'ownedPaths', 'changedPaths', 'acceptance', 'receipts', 'review'], 'handoff');
  requireValue(data.schemaVersion === 1 && data.kind === 'synthetic-coding-handoff', 'unsupported handoff version or kind');
  matches(data.repository, /^fictional\/[a-z0-9][a-z0-9-]{0,63}$/, 'fictional repository');
  matches(data.workId, LABEL, 'fictional work ID'); matches(data.authorId, LABEL, 'fictional author ID');
  matches(data.headSha, SHA, 'exact source SHA');
  paths(data.ownedPaths, 32, true, 'owned paths'); paths(data.changedPaths, 64, false, 'changed paths');
  list(data.acceptance, 1, 16, 'acceptance'); list(data.receipts, 0, 16, 'receipts');
  const acceptance = new Map();
  for (const check of data.acceptance) {
    fields(check, ['id', 'command'], 'acceptance check'); matches(check.id, ID, 'check ID'); command(check.command);
    requireValue(!acceptance.has(check.id), 'duplicate acceptance ID'); acceptance.set(check.id, check);
  }
  const receipts = new Map();
  for (const receipt of data.receipts) {
    fields(receipt, ['checkId', 'headSha', 'command', 'exitCode', 'tests', 'originalLog'], 'receipt');
    matches(receipt.checkId, ID, 'receipt check ID'); matches(receipt.headSha, SHA, 'receipt source SHA'); command(receipt.command);
    count(receipt.exitCode, 255, 'exit code');
    fields(receipt.tests, ['passed', 'failed'], 'tests');
    count(receipt.tests.passed, 1000000, 'passed count'); count(receipt.tests.failed, 1000000, 'failed count');
    if (receipt.originalLog !== null) {
      fields(receipt.originalLog, ['label', 'sha256'], 'original log');
      matches(receipt.originalLog.label, LABEL, 'fictional log label'); matches(receipt.originalLog.sha256, DIGEST, 'log digest');
    }
    requireValue(acceptance.has(receipt.checkId), 'unrequested receipt');
    requireValue(!receipts.has(receipt.checkId), 'duplicate receipt'); receipts.set(receipt.checkId, receipt);
  }
  if (data.review !== null) {
    fields(data.review, ['reviewerId', 'headSha', 'verdict'], 'review');
    matches(data.review.reviewerId, LABEL, 'fictional reviewer ID'); matches(data.review.headSha, SHA, 'review source SHA');
    requireValue(['approved', 'changes-requested', 'unknown'].includes(data.review.verdict), 'invalid review verdict');
  }
  const findings = [];
  const add = (code, subject) => findings.push({code, subject});
  for (const path of data.changedPaths) {
    if (!data.ownedPaths.some(owned => owned.endsWith('/') ? path.startsWith(owned) : path === owned)) add('out-of-scope-path', path);
  }
  for (const check of data.acceptance) {
    const receipt = receipts.get(check.id);
    if (!receipt) { add('missing-receipt', check.id); continue; }
    if (receipt.headSha !== data.headSha) add('receipt-source-mismatch', check.id);
    if (receipt.command !== check.command) add('receipt-command-mismatch', check.id);
    if (receipt.exitCode === null || receipt.tests.passed === null || receipt.tests.failed === null) add('unknown-check-result', check.id);
    if ((receipt.exitCode !== null && receipt.exitCode !== 0) || receipt.tests.failed > 0) add('failed-check', check.id);
    if (receipt.tests.passed === 0 && receipt.tests.failed === 0) add('no-tests-executed', check.id);
    if (receipt.originalLog === null) add('missing-original-log', check.id);
  }
  if (data.review === null) add('missing-review', 'review');
  else {
    if (data.review.reviewerId === data.authorId) add('self-review', 'review');
    if (data.review.headSha !== data.headSha) add('review-source-mismatch', 'review');
    if (data.review.verdict !== 'approved') add('review-not-approved', 'review');
  }
  return {schemaVersion: 1, kind: 'synthetic-handoff-report', repository: data.repository, workId: data.workId, headSha: data.headSha,
    status: findings.length ? 'needs-review' : 'consistent-declarations', findings,
    boundary: {synthetic: true, receiptAuthenticated: false, ciVerified: false, mergeAuthorized: false, codingPermissionGranted: false}};
}
