#!/usr/bin/env node
/**
 * CRACI Chaos Lab: bounded, deterministic synthetic fault-injection campaigns.
 *
 * Faults are applied to ephemeral models, not to npm packages, organization
 * settings, real tokens, remote registries, production services or runner hosts.
 * A separate chaos-probes.mjs runs isolated REAL local filesystem/process tests.
 */
import {strict as assert} from 'node:assert';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const sha = value => createHash('sha256').update(value).digest('hex');
const SOURCE = 'a'.repeat(40);
const LOCK = sha('synthetic-lockfile-pinned');
const STOP = Date.parse('2026-11-14T18:00:00Z');
const PROFILES = Object.freeze({
  provenance: ['source-drift', 'lock-drift', 'cache-poison', 'receipt-swap', 'artifact-tamper'],
  network: ['network-reset', 'unexpected-egress', 'lifecycle-fired', 'process-exit', 'process-hang'],
  control: ['duplicate-dispatch', 'unknown-ack', 'budget-overrun', 'deadline-crossed', 'credit-closed'],
  evidence: ['receipt-truncate', 'receipt-json-corrupt', 'receipt-byte-drift',
    'unverified-claim', 'secret-leak', 'artifact-missing', 'false-success'],
});
const BENIGN = ['clean', 'network-jitter-under-budget', 'artifact-list-reorder', 'verified-replay'];
const FAULTS = Object.values(PROFILES).flat();
const MIN_CASES = 400;
const MAX_CASES = 100000;

function rng(initial) {
  let x = (initial >>> 0) || 0x9e3779b9;
  return () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return (x >>> 0) / 0x100000000;
  };
}

function parseArgs(args) {
  const config = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!['--seed', '--cases', '--profile', '--output'].includes(args[i]) || !args[i + 1])
      throw new Error('Unexpected or incomplete argument');
    config[args[i].slice(2)] = args[i + 1];
  }
  for (const name of ['seed', 'cases']) {
    if (!/^\d{1,9}$/.test(config[name] || '')) throw new Error(`Invalid ${name}`);
    config[name] = Number(config[name]);
  }
  if (!Number.isInteger(config.seed) || config.seed < 1 || config.seed > 999999999 ||
      config.cases < MIN_CASES || config.cases > MAX_CASES || !PROFILES[config.profile] || !config.output)
    throw new Error('Invalid bounded chaos configuration');
  return config;
}

function pristine() {
  const receipt = {sourceCommit: SOURCE, result: 'pass', sourceVerified: true,
    jobConclusion: 'success', stageOutcome: 'success', evidence: 'synthetic'};
  const bytes = JSON.stringify(receipt);
  return {expectedCommit: SOURCE, checkedOutCommit: SOURCE,
    expectedLock: LOCK, observedLock: LOCK,
    cache: {sourceCommit: SOURCE, lockDigest: LOCK},
    lifecycleExecuted: false, outboundUnexpectedlySucceeded: false,
    networkResetRecovered: true, processExit: 0, processTimedOut: false,
    creditsOpen: true, now: STOP - 50 * 60000, jobBudgetMs: 16 * 60000,
    alreadyAttempted: false, unknownDispatchAck: false,
    reservedEur: 2, nextEur: 0.625, authorizedCapEur: 300,
    receiptBytes: bytes, receiptDigest: sha(bytes), artifactExists: true,
    artifactBytes: bytes, localSecret: 'SYNTHETIC_CANARY_DO_NOT_LOG',
    receipt, hookTrace: [],
  };
}

/** Fault injection occurs at named lifecycle hooks; the detector never sees a fault label. */
function inject(world, fault) {
  const actions = {
    'source-drift': ['after-checkout', () => { world.checkedOutCommit = 'b'.repeat(40); }],
    'lock-drift': ['after-checkout', () => { world.observedLock = sha('different-lock'); }],
    'cache-poison': ['after-install', () => { world.cache.sourceCommit = 'b'.repeat(40); }],
    'receipt-swap': ['after-receipt', () => { world.receipt.sourceCommit = 'b'.repeat(40); world.receiptBytes = JSON.stringify(world.receipt); world.receiptDigest = sha(world.receiptBytes); world.artifactBytes = world.receiptBytes; }],
    'artifact-tamper': ['after-artifact', () => { world.artifactBytes += '\\nCORRUPTED'; }],
    'network-reset': ['after-install', () => { world.networkResetRecovered = false; }],
    'unexpected-egress': ['after-install', () => { world.outboundUnexpectedlySucceeded = true; }],
    'lifecycle-fired': ['after-install', () => { world.lifecycleExecuted = true; }],
    'process-exit': ['after-execute', () => { world.processExit = 99; }],
    'process-hang': ['after-execute', () => { world.processTimedOut = true; }],
    'duplicate-dispatch': ['before-admit', () => { world.alreadyAttempted = true; }],
    'unknown-ack': ['before-admit', () => { world.unknownDispatchAck = true; }],
    'budget-overrun': ['before-admit', () => { world.reservedEur = 299.75; }],
    'deadline-crossed': ['before-admit', () => { world.now = STOP - 10 * 60000; }],
    'credit-closed': ['before-admit', () => { world.creditsOpen = false; }],
    'receipt-truncate': ['after-receipt', () => { world.receiptBytes = world.receiptBytes.slice(0, 30); world.artifactBytes = world.receiptBytes; }],
    'receipt-json-corrupt': ['after-receipt', () => { world.receiptBytes = '{not-json'; world.receiptDigest = sha(world.receiptBytes); world.artifactBytes = world.receiptBytes; }],
    'receipt-byte-drift': ['after-receipt', () => { world.receiptBytes += ' '; }],
    'unverified-claim': ['after-receipt', () => { world.receipt.sourceVerified = false; world.receiptBytes = JSON.stringify(world.receipt); world.receiptDigest = sha(world.receiptBytes); world.artifactBytes = world.receiptBytes; }],
    'secret-leak': ['after-receipt', () => { world.receipt.debug = world.localSecret; world.receiptBytes = JSON.stringify(world.receipt); world.receiptDigest = sha(world.receiptBytes); world.artifactBytes = world.receiptBytes; }],
    'artifact-missing': ['after-artifact', () => { world.artifactExists = false; }],
    'false-success': ['after-receipt', () => { world.receipt.stageOutcome = 'failure'; world.receiptBytes = JSON.stringify(world.receipt); world.receiptDigest = sha(world.receiptBytes); world.artifactBytes = world.receiptBytes; }],
    clean: ['before-admit', () => {}],
    'network-jitter-under-budget': ['after-install', () => { world.jobBudgetMs -= 500; }],
    'artifact-list-reorder': ['after-artifact', () => { world.hookTrace.reverse(); }],
    'verified-replay': ['before-admit', () => { world.hookTrace.push('verified-read-only-replay'); }],
  };
  const [hook, apply] = actions[fault] || [];
  if (!hook) throw new Error(`Unsupported fault: ${fault}`);
  return {hook, apply};
}

function inspect(world, {disabledGate = null, injections = []} = {}) {
  // Order is intentional: no work should begin after the admission hook rejects.
  const failures = [];
  const check = (condition, code) => { if (code !== disabledGate && !condition) failures.push(code); };
  const hook = (name, run) => {
    // Apply only faults whose scheduled hook is reached. An earlier rejection
    // prevents later stages from executing (unlike a pre-mutated world).
    for (const injection of injections) if (injection.hook === name) injection.apply();
    world.hookTrace.push(name);
    run();
  };
  hook('before-admit', () => {
    check(world.creditsOpen, 'CREDIT_CLOSED');
    check(world.now + world.jobBudgetMs < STOP, 'DEADLINE_GUARD');
    check(world.reservedEur + world.nextEur <= world.authorizedCapEur, 'BUDGET_GUARD');
    check(!world.alreadyAttempted && !world.unknownDispatchAck, 'DISPATCH_AMBIGUOUS');
  });
  if (failures.length) return failures;
  hook('after-checkout', () => {
    check(world.expectedCommit === world.checkedOutCommit, 'SOURCE_PIN');
    check(world.expectedLock === world.observedLock, 'LOCK_PIN');
  });
  if (failures.length) return failures;
  hook('after-install', () => {
    check(world.cache.sourceCommit === world.expectedCommit &&
          world.cache.lockDigest === world.expectedLock, 'CACHE_PROVENANCE');
    check(!world.lifecycleExecuted, 'LIFECYCLE_EXECUTED');
    check(!world.outboundUnexpectedlySucceeded, 'UNEXPECTED_EGRESS');
    check(world.networkResetRecovered, 'NETWORK_RESET');
  });
  if (failures.length) return failures;
  hook('after-execute', () => {
    check(world.processExit === 0, 'PROCESS_FAILED');
    check(!world.processTimedOut, 'PROCESS_TIMEOUT');
  });
  if (failures.length) return failures;
  hook('after-receipt', () => {
    check(sha(world.receiptBytes) === world.receiptDigest, 'RECEIPT_DIGEST');
    let receipt;
    try { receipt = JSON.parse(world.receiptBytes); } catch { check(false,'RECEIPT_PARSE'); }
    if (receipt) {
      check(receipt.sourceCommit === world.expectedCommit, 'RECEIPT_SOURCE');
      check(receipt.result === 'pass' && receipt.sourceVerified === true &&
          receipt.jobConclusion === 'success' && receipt.stageOutcome === 'success', 'RECEIPT_CLAIM');
      check(!world.receiptBytes.includes(world.localSecret), 'SECRET_MARKER');
    }
  });
  if (failures.length) return failures;
  hook('after-artifact', () => {
    check(world.artifactExists && world.artifactBytes.length > 0, 'ARTIFACT_MISSING');
    check(sha(world.artifactBytes) === world.receiptDigest, 'ARTIFACT_DIGEST');
  });
  return failures;
}

function flawedBaseline(world) {
  // Deliberately weak comparator, never used for accepting the real job.
  return world.processExit === 0 && world.receipt?.result === 'pass';
}

// Independent fixture oracle: all named adversarial faults invalidate a PASS.
// This oracle is a *synthetic specification*, not a measure of CRACI's detector.
function oracle(faults) { return faults.every(f => BENIGN.includes(f)); }

function evaluate(faults) {
  const specimen = pristine();
  const patches = faults.map(f => ({fault:f, ...inject(specimen,f)}));
  const failures = inspect(specimen,{injections:patches});
  return {accepted:failures.length === 0, baselineAccepted:flawedBaseline(specimen), failures};
}

/** Mutation testing: if a single protection is deleted, a matching probe MUST fail green. */
export function mutationAudit() {
  const critical = Object.entries({
    CREDIT_CLOSED:'credit-closed', DEADLINE_GUARD:'deadline-crossed',
    BUDGET_GUARD:'budget-overrun', DISPATCH_AMBIGUOUS:'duplicate-dispatch',
    SOURCE_PIN:'source-drift', LOCK_PIN:'lock-drift',
    CACHE_PROVENANCE:'cache-poison', LIFECYCLE_EXECUTED:'lifecycle-fired',
    UNEXPECTED_EGRESS:'unexpected-egress', NETWORK_RESET:'network-reset',
    PROCESS_FAILED:'process-exit', PROCESS_TIMEOUT:'process-hang',
    RECEIPT_DIGEST:'receipt-byte-drift', RECEIPT_PARSE:'receipt-json-corrupt',
    RECEIPT_SOURCE:'receipt-swap', RECEIPT_CLAIM:'unverified-claim',
    SECRET_MARKER:'secret-leak', ARTIFACT_MISSING:'artifact-missing',
    ARTIFACT_DIGEST:'artifact-tamper',
  });
  const findings = critical.map(([disabledGate, fault]) => {
    const clean = pristine(), weak = pristine();
    const normal = inspect(clean,{injections:[inject(clean,fault)]});
    const mutated = inspect(weak,{disabledGate,injections:[inject(weak,fault)]});
    return {disabledGate,fault,
      detectedByNormal:normal.length > 0,
      killed:normal.length > 0 && mutated.length === 0};
  });
  const killed = findings.filter(f=>f.killed).length;
  return {total:findings.length,killed,score:killed/findings.length,
    surviving:findings.filter(f=>!f.killed)};
}

export async function chaosCampaign({seed, cases, profile}) {
  const next = rng(seed), pool = PROFILES[profile];
  if (!pool) throw new Error('Unknown chaos profile');
  const counts = Object.fromEntries([...FAULTS, ...BENIGN].map(f=>[f,0]));
  const outcomes = {acceptedControl:0, detectedInjected:0, missedInjected:0,
    rejectedControl:0, baselineMissedInjected:0, baselineRejectedControl:0,
    pairs:0, distinctPairs:0};
  const seenPairs = new Set(), observedRejects = new Set(), firstFailures = {};
  const corpusHash = createHash('sha256');
  for (let i=0; i<cases; i++) {
    const primary = i%8 === 0 ? BENIGN[Math.floor(i/8)%BENIGN.length] : pool[i%pool.length];
    const faults = [primary];
    // Combinatorial injection spans profile boundaries without creating real faults.
    if (i%11 === 0 && i > 0) {
      const other = FAULTS[Math.floor(next()*FAULTS.length)];
      if (!faults.includes(other)) {
        faults.push(other); outcomes.pairs++;
        seenPairs.add([...faults].sort().join('+'));
      }
    }
    const expected = oracle(faults), result = evaluate(faults);
    // Hash every generated case and observed hook result, not just totals.
    // This is replay evidence, not a cryptographic signature of CRACI runtime.
    corpusHash.update(JSON.stringify({i,faults,expected,accepted:result.accepted,
      failures:result.failures})+'\n');
    for (const name of faults) counts[name]++;
    if (expected) {
      if (result.accepted) outcomes.acceptedControl++;
      else outcomes.rejectedControl++;
      if (!result.baselineAccepted) outcomes.baselineRejectedControl++;
    } else {
      if (!result.accepted) outcomes.detectedInjected++;
      else outcomes.missedInjected++;
      if (result.baselineAccepted) outcomes.baselineMissedInjected++;
      for (const name of faults) if (!BENIGN.includes(name) && !result.accepted) observedRejects.add(name);
    }
    if (expected !== result.accepted && Object.keys(firstFailures).length < 6)
      firstFailures[i] = {faults,expected,actual:result};
  }
  outcomes.distinctPairs = seenPairs.size;
  assert.equal(outcomes.missedInjected,0,'Unsafe fault escaped a hook');
  assert.equal(outcomes.rejectedControl,0,'Benign control rejected');
  assert.equal(outcomes.detectedInjected+outcomes.acceptedControl,cases);
  for (const fault of pool) assert(observedRejects.has(fault),`Uncovered fault: ${fault}`);
  assert(outcomes.distinctPairs > 0,'Combinatorial coverage missing');
  const mutations = mutationAudit();
  assert.equal(mutations.killed,mutations.total,'At least one deleted protection survived');
  const corpus = corpusHash.digest('hex');
  return {schemaVersion:1,workId:'CRACI-CHAOS-20261114',profile,seed,cases,
    claim:'Synthetic failure-hook evaluation, not production or CRACI enforcement qualification',
    sourceCommit:process.env.CRACI_SOURCE_SHA||null,
    actualCostEur:null,deterministicCorpusDigestSha256:corpus,
    metrics:{...outcomes,mutationKills:mutations.killed,mutationTotal:mutations.total,
      zeroMissUpper95IfZero:outcomes.detectedInjected?
      Number((3/outcomes.detectedInjected).toFixed(7)):null},
    faults:counts, counterexamples:firstFailures,
    bounds:['No real secrets, malware, production traffic, runner crashes or destructive resource load',
      'CRACI egress/SBOM and GitHub artifact receipts require separate provider evidence',
      'Synthetic fixture verdicts are not live detection or resilience rates']};
}

async function main() {
  const config = parseArgs(process.argv.slice(2));
  const report = await chaosCampaign(config);
  const output = resolve(config.output);
  await mkdir(dirname(output),{recursive:true});
  await writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({profile:report.profile,seed:report.seed,cases:report.cases,
    metrics:report.metrics,corpusDigestSha256:report.deterministicCorpusDigestSha256}));
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
