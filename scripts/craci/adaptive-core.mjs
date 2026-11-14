/**
 * Advisory CRACI experiment selector. It never dispatches or grants spend.
 * Existing workflow authority, GitHub checkout pins and CRACI policy stay in force.
 */
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {readFile, open, mkdir, lstat} from 'node:fs/promises';
import {dirname} from 'node:path';
import {WINDOW_END, WORKLOADS} from './plan.mjs';

const SHA40 = /^[a-f0-9]{40}$/;
const SHA64 = /^[a-f0-9]{64}$/;
const ID = /^[a-z][a-z0-9._-]{2,79}$/;
const MAX_CANDIDATES = 256;
const MAX_RECEIPTS = 10000;
const MAX_BYTES = 4 * 1024 * 1024;
const STATUS = new Set(['reserved', 'queued', 'running', 'passed', 'failed', 'cancelled', 'rejected']);
const ACTIVE = new Set(['reserved', 'queued', 'running']);

function requireThat(condition, code) {if (!condition) throw new Error(code);}
function plain(value) {return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;}
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (plain(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  if (value === null || typeof value === 'string' || typeof value === 'boolean' ||
      (typeof value === 'number' && Number.isFinite(value))) return JSON.stringify(value);
  throw new Error('UNSUPPORTED_CANONICAL_VALUE');
}
export function sha256(value) {return createHash('sha256').update(value).digest('hex');}
export function digest(value) {return sha256(canonical(value));}
const money = value => Number.isFinite(value) && value >= 0 && value <= 1000 &&
  Math.abs(Math.round(value * 100) - value * 100) < 1e-7;
const probability = value => Number.isFinite(value) && value >= 0 && value <= 1;
const parseDate = value => {const epoch = Date.parse(value);
  requireThat(typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value) &&
    Number.isFinite(epoch) && new Date(epoch).toISOString().replace('.000Z', 'Z') === value.replace(/\.0+Z$/, 'Z'),
    'INVALID_UTC_TIMESTAMP');
  return epoch;};

export function tupleOf(candidate) {
  return {repository: 'SalesSquad/junction-pets', workload: candidate.workload,
    cell: candidate.cell, sourceSha: candidate.sourceSha, harnessSha: candidate.harnessSha,
    scenarioDigest: candidate.scenarioDigest, seed: candidate.seed};
}

function validatedCandidate(candidate, manifest) {
  requireThat(plain(candidate), 'INVALID_CANDIDATE');
  requireThat(ID.test(candidate.id || '') && ID.test(candidate.cell || '') && ID.test(candidate.group || ''), 'INVALID_EXPERIMENT_ID');
  requireThat(WORKLOADS.includes(candidate.workload) && SHA40.test(candidate.sourceSha || '') &&
    candidate.harnessSha === manifest.harnessSha && SHA64.test(candidate.scenarioDigest || ''), 'UNPINNED_EXPERIMENT');
  requireThat(Number.isSafeInteger(candidate.seed) && candidate.seed >= 0 && candidate.seed <= 2147483647, 'INVALID_EXPERIMENT_SEED');
  requireThat(Number.isInteger(candidate.jobs) && candidate.jobs >= 1 && candidate.jobs <= 8 &&
    money(candidate.worstCaseEur) && candidate.worstCaseEur > 0, 'INVALID_EXPERIMENT_RESERVATION');
  requireThat(plain(candidate.value) && ['uncertainty','disagreement','safetyRisk','novelty'].every(key =>
    probability(candidate.value[key])), 'INVALID_INFORMATION_VALUE');
  requireThat(typeof candidate.hypothesis === 'string' && candidate.hypothesis.length >= 12 &&
    candidate.hypothesis.length <= 400, 'HYPOTHESIS_REQUIRED');
  return {...candidate, tupleDigest: digest(tupleOf(candidate))};
}

export function validateManifest(manifest, now = new Date()) {
  requireThat(plain(manifest) && manifest.schema === 'craci-adaptive-v1' &&
    manifest.repository === 'SalesSquad/junction-pets' && SHA40.test(manifest.harnessSha || ''), 'INVALID_MANIFEST_SOURCE');
  requireThat(manifest.creditWindowOpen === true && manifest.dispatchAuthorized === false,
    'ADVISORY_ONLY_CREDIT_CLOSED_OR_DISPATCH_ENABLED');
  const nowMs = new Date(now).getTime();
  const deadline = parseDate(manifest.deadlineUtc), campaignStop = parseDate(manifest.campaignHardStopUtc);
  requireThat(Number.isFinite(nowMs) && deadline <= Date.parse(WINDOW_END) &&
    campaignStop <= deadline && nowMs < campaignStop && nowMs < deadline &&
    nowMs < Date.parse(WINDOW_END), 'CRACI_WINDOW_CLOSED');
  requireThat(Number.isInteger(manifest.maxParallel) && manifest.maxParallel > 0 && manifest.maxParallel <= 8 &&
    Number.isInteger(manifest.maxJobs) && manifest.maxJobs > 0 && manifest.maxJobs <= 64, 'INVALID_MATRIX_CAP');
  requireThat(money(manifest.creditRemainingEur) && money(manifest.campaignRemainingEur), 'INVALID_BUDGET');
  requireThat(typeof manifest.meterReference === 'string' && manifest.meterReference.length > 8 &&
    manifest.meterReference.length <= 500 && typeof manifest.meterObservedAtUtc === 'string' &&
    nowMs - parseDate(manifest.meterObservedAtUtc) <= 30 * 60_000 &&
    parseDate(manifest.meterObservedAtUtc) <= nowMs, 'STALE_OR_MISSING_CREDIT_METER');
  requireThat(Array.isArray(manifest.candidates) && manifest.candidates.length <= MAX_CANDIDATES, 'TOO_MANY_CANDIDATES');
  const ids = new Set(), tuples = new Set();
  const candidates = manifest.candidates.map(value => validatedCandidate(value, manifest));
  // These two campaigns have their own *immutable* 14 Nov 20:00 Helsinki stop.
  // A caller cannot extend it by supplying a later campaignHardStopUtc.
  if (candidates.some(c => c.workload === 'immune-tournament' || c.workload === 'chaos-lab'))
    requireThat(campaignStop <= Date.parse('2026-11-14T18:00:00Z'), 'IMMUNE_CHAOS_HARD_STOP_EXCEEDED');
  for (const candidate of candidates) {
    requireThat(!ids.has(candidate.id) && !tuples.has(candidate.tupleDigest), 'DUPLICATE_EXPERIMENT');
    ids.add(candidate.id); tuples.add(candidate.tupleDigest);
  }
  return candidates;
}

export function receiptHash(sequence, prevHash, event) {return digest({sequence, prevHash, event});}

export function verifyReceiptLog(text) {
  requireThat(typeof text === 'string' && Buffer.byteLength(text) <= MAX_BYTES, 'OVERSIZED_RECEIPT_LOG');
  requireThat(text === '' || text.endsWith('\n'), 'TRUNCATED_RECEIPT_LOG');
  const lines = text === '' ? [] : text.trimEnd().split('\n');
  requireThat(lines.length <= MAX_RECEIPTS, 'TOO_MANY_RECEIPTS');
  const events = []; let head = '0'.repeat(64);
  for (let i = 0; i < lines.length; i++) {
    let receipt;
    try {receipt = JSON.parse(lines[i]);} catch {throw new Error('INVALID_RECEIPT_JSON');}
    requireThat(plain(receipt) && receipt.sequence === i + 1 && receipt.prevHash === head &&
      SHA64.test(receipt.hash || '') && plain(receipt.event) &&
      receipt.hash === receiptHash(receipt.sequence, receipt.prevHash, receipt.event), 'RECEIPT_CHAIN_BROKEN');
    const event = receipt.event;
    requireThat(SHA64.test(event.tupleDigest || '') && SHA40.test(event.sourceSha || '') &&
      SHA40.test(event.harnessSha || '') && STATUS.has(event.status) && money(event.reservedEur) &&
      Number.isInteger(event.jobs) && event.jobs >= 1 && event.jobs <= 8 &&
      typeof event.whenUtc === 'string' && Number.isFinite(Date.parse(event.whenUtc)), 'INVALID_RECEIPT_EVENT');
    if (event.status === 'passed') requireThat(/^https:\/\/github\.com\/SalesSquad\/junction-pets\/actions\/runs\/\d+/.test(event.githubRunUrl || ''), 'PASS_WITHOUT_GITHUB_EVIDENCE');
    events.push(event); head = receipt.hash;
  }
  return {events, head, count: events.length};
}

/** The append lock is local only: never treat this as a distributed CRACI mutex. */
export async function appendReceipt(logPath, event, {expectedHead} = {}) {
  requireThat(plain(event), 'INVALID_RECEIPT_EVENT');
  const root = dirname(logPath);
  await mkdir(root, {recursive: true, mode: 0o700});
  const lockPath = `${logPath}.lock`;
  const lock = await open(lockPath, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
  try {
    // Verify a preexisting file is an ordinary file, not a symlink.
    let current = '';
    try {const st = await lstat(logPath);requireThat(st.isFile() && !st.isSymbolicLink() && st.nlink === 1, 'UNSAFE_RECEIPT_PATH');
      current = await readFile(logPath, 'utf8');}
    catch (err) {if (err.code !== 'ENOENT') throw err;}
    const checked = verifyReceiptLog(current);
    if (expectedHead !== undefined) requireThat(checked.head === expectedHead, 'RECEIPT_HEAD_CHANGED');
    // Run validation on a candidate line before writing anything.
    const next = {sequence: checked.count + 1, prevHash: checked.head, event};
    next.hash = receiptHash(next.sequence, next.prevHash, event);
    verifyReceiptLog(current + JSON.stringify(next) + '\n');
    const fd = await open(logPath, constants.O_APPEND | constants.O_CREAT | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
    try {await fd.writeFile(JSON.stringify(next) + '\n'); await fd.sync();} finally {await fd.close();}
    return next;
  } finally {await lock.close(); await import('node:fs/promises').then(fs => fs.unlink(lockPath));}
}

/** Only decide which evidence gaps merit *admission review*. Does not dispatch. */
export function selectExperiments(manifest, receiptsText = '', {now = new Date()} = {}) {
  const candidates = validateManifest(manifest, now);
  const history = verifyReceiptLog(receiptsText);
  const latest = new Map(), everPassed = new Set(), everFailed = new Set();
  for (const event of history.events) {
    latest.set(event.tupleDigest, event);
    if (event.status === 'passed') everPassed.add(event.tupleDigest);
    if (event.status === 'failed') everFailed.add(event.tupleDigest);
  }
  const excluded = [], eligible = [];
  let activeReserve = 0, activeJobs = 0;
  for (const entry of latest.values()) if (ACTIVE.has(entry.status)) {
    activeReserve += entry.reservedEur;
    activeJobs += entry.jobs;
  }
  const ceiling = Math.max(0, Math.min(manifest.creditRemainingEur, manifest.campaignRemainingEur) - activeReserve);
  // This result represents one simultaneous wave, not an unbounded queue.
  // In particular an 8-cell candidate cannot fit a 4-cell maxParallel window.
  const jobsLeft = Math.max(0, Math.min(manifest.maxJobs - activeJobs,
    manifest.maxParallel - activeJobs));
  for (const candidate of candidates) {
    const prior = latest.get(candidate.tupleDigest);
    if (prior && (prior.sourceSha !== candidate.sourceSha || prior.harnessSha !== candidate.harnessSha))
      throw new Error('RECEIPT_SOURCE_BINDING_CONFLICT');
    if (everPassed.has(candidate.tupleDigest) || (prior && ACTIVE.has(prior.status))) {
      excluded.push({id: candidate.id, reason: everPassed.has(candidate.tupleDigest) ? 'unchanged_green_tuple' : 'already_reserved_or_running'}); continue;
    }
    if (everFailed.has(candidate.tupleDigest)) {
      // Repetition is only useful when the test case/repair changes (and therefore its digest changes).
      excluded.push({id: candidate.id, reason: 'unchanged_failed_tuple_requires_new_hypothesis'});continue;
    }
    const v = candidate.value;
    const merit = 1.4 * v.uncertainty + 1.1 * v.disagreement + 1.6 * v.safetyRisk + 0.6 * v.novelty;
    eligible.push({...candidate, merit, score: merit / Math.sqrt(candidate.worstCaseEur)});
  }
  eligible.sort((a,b) => b.score - a.score || a.id.localeCompare(b.id));
  const selected = [];const groups = new Map();let reserve = 0, count = 0;
  while (eligible.length > 0) {
    eligible.sort((a,b) => b.score / (1 + (groups.get(b.group) || 0)) - a.score / (1 + (groups.get(a.group) || 0)) || a.id.localeCompare(b.id));
    const candidate = eligible.shift();
    if (reserve + candidate.worstCaseEur > ceiling + 1e-8 || count + candidate.jobs > jobsLeft) {
      excluded.push({id:candidate.id,reason:'budget_or_job_cap'});continue;
    }
    selected.push({id:candidate.id, tupleDigest:candidate.tupleDigest, workload:candidate.workload,
      cell:candidate.cell, sourceSha:candidate.sourceSha, harnessSha:candidate.harnessSha,
      scenarioDigest:candidate.scenarioDigest, seed:candidate.seed, jobs:candidate.jobs,
      worstCaseEur:candidate.worstCaseEur, score:Number(candidate.score.toFixed(6)),
      hypothesis:candidate.hypothesis});
    reserve += candidate.worstCaseEur;count += candidate.jobs;
    groups.set(candidate.group,(groups.get(candidate.group)||0)+1);
  }
  return {schema:'craci-adaptive-plan-v1', repository:manifest.repository,harnessSha:manifest.harnessSha,
    issuedAtUtc:new Date(now).toISOString(),deadlineUtc:manifest.deadlineUtc,
    campaignHardStopUtc:manifest.campaignHardStopUtc,
    evidenceLogHead:history.head,budgetBasis:'operator-provided-meter-not-provider-verified',
    meterReference:manifest.meterReference, alreadyActiveReservedEur:Number(activeReserve.toFixed(2)),
    additionalReservedEur:Number(reserve.toFixed(2)), availableEur:Number(ceiling.toFixed(2)),
    selected, excluded, maxParallel:manifest.maxParallel,
    inferencePolicy:'exploration_only; prospective_locked_holdout_or_anytime_valid_sequence_required_for_claims',
    dispatchAuthorized:false, reason:'shadow_plan_only_no_second_dispatcher_or_distributed_reservation_lock'};
}
