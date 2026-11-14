/**
 * TRAIN-only CRACI science feedback compiler.  Pure analysis; never submits
 * jobs, charges credits, updates a model, edits a PR, or promotes a policy.
 * The source-reported CRACI receipt and independent replay are bound by exact
 * original file hashes.  Neither is a provider-signed physics certificate.
 */
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat, open} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';

const SHA40 = /^[0-9a-f]{40}$/;
const SHA64 = /^[0-9a-f]{64}$/;
const MAX_JSON = 25 * 1024 * 1024;
const MAX_GZIP = 64 * 1024 * 1024;
const MAX_EXPANDED = 180 * 1024 * 1024;
function insist(x, message) { if (!x) throw new Error(message); }
const plain = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const list = (v, kind) => {insist(Array.isArray(v), `INVALID_${kind}`); return v;};
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (plain(value)) return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  insist(value === null || typeof value === 'string' || typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value)), 'INVALID_CANONICAL_VALUE');
  return JSON.stringify(value);
}
const digest = object => sha(Buffer.from(canonical(object)));
const bool = v => v === true || v === false;

async function checkedFile(path, expected, limit) {
  insist(typeof path === 'string' && path.length > 0 && SHA64.test(expected || ''), 'UNPINNED_FILE');
  const stat = await lstat(path);
  insist(stat.isFile() && !stat.isSymbolicLink() && stat.nlink === 1 && stat.size <= limit, 'UNSAFE_OR_OVERSIZED_EVIDENCE');
  const fd = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const bytes = await fd.readFile();
    insist(bytes.length === stat.size && sha(bytes) === expected, 'EVIDENCE_SHA_MISMATCH');
    return bytes;
  } finally {await fd.close();}
}

function parsed(bytes, label) {
  try {const data = JSON.parse(bytes.toString('utf8')); insist(plain(data), 'NOT_OBJECT'); return data;}
  catch {throw new Error(`INVALID_${label}_JSON`);}
}

function validateSource({training, manifest, qualification, replay, readout, receipt}, pins) {
  insist(pins.schema === 'junction.craci.learning-controller.v1.pinned-input' &&
    Number.isSafeInteger(pins.githubRun) && pins.githubRun>0 &&
    SHA40.test(pins.sourceSha) && SHA40.test(pins.harnessSha), 'INVALID_PIN_SET');
  insist(receipt.binding?.sourceSha === pins.sourceSha && receipt.binding?.harnessSha === pins.harnessSha &&
    receipt.binding?.runId === pins.receiptRunId &&
    typeof receipt.evidenceUrl === 'string' &&
    receipt.evidenceUrl.startsWith(`https://github.com/SalesSquad/junction-pets/actions/runs/${pins.githubRun}/`) &&
    pins.receiptRunId.startsWith(`craci.${pins.githubRun}.`) &&
    receipt.jobStatus === 'success' && receipt.evidenceLevel === 'source-reported' &&
    receipt.command?.exitCode === 0 && receipt.command?.state === 'completed' &&
    receipt.command?.output?.stdout?.truncated === false &&
    receipt.command?.output?.stderr?.truncated === false &&
    receipt.provenance?.after?.source?.verified === true && receipt.provenance?.after?.harness?.verified === true,
  'SOURCE_RECEIPT_UNQUALIFIED');
  insist(manifest.executed_head === pins.sourceSha && manifest.file_sha256?.['training.json'] === pins.sha256.training &&
    manifest.file_sha256?.['full_transitions.jsonl.gz'] === pins.sha256.transitions &&
    manifest.train_only === true && manifest.promotion_authorized === false &&
    manifest.dev_cal_test_ood_opened === false, 'SOURCE_MANIFEST_UNQUALIFIED');
  insist(training.executed_head === pins.sourceSha && training.training_only === true &&
    training.model_promotion_authorized === false && training.dev_cal_test_ood_opened === false &&
    training.no_dev_evaluation === true && training.actual_physics_engine === 'mujoco-3.3.7',
  'TRAINING_NOT_TRAIN_ONLY_OR_SOURCE_MISMATCH');
  insist(qualification.exact_source_sha === pins.sourceSha &&
    qualification.decision === 'valid_prospective_train_only_evidence' &&
    qualification.experiment_complete === true && qualification.producer_exit_code === 0 &&
    qualification.dev_cal_test_ood_opened === false && qualification.independentHoldout === false &&
    qualification.independent_full_trace_public_mask_replay === true &&
    bool(qualification.model_improvement_independently_verified) &&
    qualification.promotion_authorized === false &&
    qualification.dataset_sha256 === training.dataset_sha256 &&
    qualification.actual_real_option_transitions === training.actual_transition_count &&
    qualification.full_transition_archive_sha256 === pins.sha256.transitions,
  'QUALIFICATION_CONTRADICTS_SOURCE');
  insist(replay.claim_verified === true && replay.model_promotion_authorized === false &&
    replay.no_dev_cal_test_ood === true && replay.fully_replayed_positive_train_trials > 0,
  'POSITIVE_REPLAY_NOT_VERIFIED');
  insist(readout.executed_head === pins.sourceSha &&
    readout.dataset_sha256 === training.dataset_sha256 &&
    readout.prospective_train_only === true && readout.model_promotion_authorized === false &&
    readout.dev_cal_test_ood_opened === false && readout.science_gate === 'INDEPENDENT_REVIEW_REQUIRED_NO_PROMOTION',
  'READOUT_SOURCE_MISMATCH');
  insist(training.actual_trials === pins.expectedTrials &&
    training.actual_transition_count === pins.expectedTransitions &&
    qualification.trials === pins.expectedTrials, 'EPISODE_COUNT_MISMATCH');
}

function checkTrace(training, gz, pins) {
  const expanded = gunzipSync(gz, {maxOutputLength: MAX_EXPANDED});
  const lines = expanded.toString('utf8').trimEnd().split('\n');
  insist(lines.length === training.actual_trials, 'RAW_EPISODE_COUNT_MISMATCH');
  const summary = new Map(training.trials.map(t => [`${t.seed}:${t.strategy}`, t]));
  insist(summary.size === training.actual_trials, 'DUPLICATE_EPISODE_SUMMARY');
  let count = 0;
  for (const line of lines) {
    const entry = parsed(Buffer.from(line), 'RAW_TRANSITION');
    const row = summary.get(`${entry.seed}:${entry.strategy}`);
    insist(row && Array.isArray(entry.transitions) && row.full_transition_count === entry.transitions.length,
      'FULL_TRACE_SUMMARY_CONFLICT');
    for (const t of entry.transitions) {
      insist(Number.isInteger(t.action) && t.action >= 0 && t.action < 7 &&
        Array.isArray(t.mask) && t.mask.length === 7 && t.mask.every(v => v === 0 || v === 1) &&
        t.mask[t.action] === 1 && Array.isArray(t.observation) && t.observation.length === 18 &&
        t.observation.every(v => typeof v === 'number' && Number.isFinite(v)) &&
        Array.isArray(t.next_observation) && t.next_observation.length === 18 &&
        t.next_observation.every(v => typeof v === 'number' && Number.isFinite(v)),
      'PUBLIC_ACTION_MASK_CONTRACT_VIOLATION');
    }
    count += entry.transitions.length;
    summary.delete(`${entry.seed}:${entry.strategy}`);
  }
  insist(summary.size === 0 && count === training.actual_transition_count && count === pins.expectedTransitions,
    'RAW_TRANSITION_COUNT_MISMATCH');
  return {episodes:lines.length,optionTransitions:count,allSevenActionMasksLegal:true,publicObservations18D:true};
}

/** Independent reconstruction of initial PUBLIC observed-world selection. */
export function verifyObservedSelection(training, contract) {
  insist(plain(contract) && Number.isInteger(contract.firstSeed) && contract.firstSeed>=0 &&
    Number.isInteger(contract.scanLimit) && contract.scanLimit>0 && contract.scanLimit<=4096 &&
    Number.isInteger(contract.nearTarget) && contract.nearTarget>0 &&
    Number.isInteger(contract.clearTarget) && contract.clearTarget>0 &&
    Number.isFinite(contract.nearAbsThreshold) && contract.nearAbsThreshold>0 &&
    contract.nearAbsThreshold<1, 'UNPINNED_PUBLIC_WORLD_SELECTION');
  const scan=list(training.selection_scan,'WORLD_SCAN');
  const cohort=list(training.cohort,'COHORT');
  insist(scan.length<=contract.scanLimit && scan.length>=contract.nearTarget+contract.clearTarget &&
    training.train_first_seed===contract.firstSeed &&
    training.selection_max_seeds===contract.scanLimit &&
    training.selected_near_count===contract.nearTarget &&
    training.selected_clear_count===contract.clearTarget,
  'WORLD_SELECTION_CONTRACT_CONTRADICTION');
  const near=[],clear=[];
  for(let i=0;i<scan.length;i++){
    const s=scan[i];
    insist(s.seed===contract.firstSeed+i && SHA64.test(s.world_hash||'') &&
      Number.isFinite(s.initial_observed_obstacle_y) &&
      s.initial_observed_obstacle_y>=-1 && s.initial_observed_obstacle_y<=1,
      'WORLD_SCAN_UNTRUSTED_ORDER_OR_OBSERVATION');
    const isNear=Math.abs(s.initial_observed_obstacle_y)<contract.nearAbsThreshold;
    if(isNear && near.length<contract.nearTarget)near.push(s);
    else if(!isNear && clear.length<contract.clearTarget)clear.push(s);
    if(near.length===contract.nearTarget && clear.length===contract.clearTarget){
      insist(i===scan.length-1,'WORLD_SCAN_CONTINUED_AFTER_COHORT_COMPLETE');break;
    }
  }
  insist(near.length===contract.nearTarget && clear.length===contract.clearTarget,
    'INCOMPLETE_WORLD_COHORT');
  const expected=[...near,...clear].sort((a,b)=>a.seed-b.seed);
  insist(expected.length===cohort.length && new Set(cohort.map(w=>w.seed)).size===cohort.length &&
    expected.every((w,i)=>{
      const x=cohort[i];return x.seed===w.seed && x.world_hash===w.world_hash &&
        x.initial_observed_obstacle_y===w.initial_observed_obstacle_y &&
        x.observed_corridor===(Math.abs(w.initial_observed_obstacle_y)<contract.nearAbsThreshold);
    }), 'SELECTED_COHORT_NOT_DERIVED_FROM_PUBLIC_SCAN');
  insist(JSON.stringify(near.map(w=>w.seed))===JSON.stringify(training.near_seeds) &&
    JSON.stringify(clear.map(w=>w.seed))===JSON.stringify(training.clear_seeds),
    'WORLD_GROUPS_NOT_DERIVED_FROM_OBSERVATIONS');
  return {scannedWorlds:scan.length,selectedNearWorlds:near.length,
    selectedClearWorlds:clear.length,selectionFromPublicInitialObservation:true};
}

/** Pin exact bytes first; external reviewers must still inspect original work. */
export async function loadQualifiedEvidence(paths, pins) {
  const required = ['training','transitions','manifest','qualification','replay','readout','receipt'];
  insist(plain(pins) && plain(pins.sha256) && required.every(k=>SHA64.test(pins.sha256[k]||'')),
    'MISSING_SOURCE_PIN');
  const loaded = await Promise.all(required.map(k=>checkedFile(paths[k],pins.sha256[k],
    k === 'transitions' ? MAX_GZIP : MAX_JSON)));
  const bytes = Object.fromEntries(required.map((key,i)=>[key,loaded[i]]));
  const objects = Object.fromEntries(required.filter(k=>k!=='transitions').map(k=>[k,parsed(bytes[k],k.toUpperCase())]));
  validateSource(objects,pins);
  const trace = checkTrace(objects.training,bytes.transitions,pins);
  return {...objects,trace,immutableSha256:{...pins.sha256}};
}

export function analyzePairedTraining(training, readout, {
  candidate='v8_hierarchical', baseline='frozen_v5',
  protectedControls=['frozen_v5','frozen_v6'],
  unsafeReferenceStrategies=['frozen_v5','frozen_v6','repeat_left'],
  readoutKeys={lost:'lost_frozen_v5_v6_safe_near_goal_seeds',novel:'novel_v8_safe_near_goal_seeds',unsafe:'v8_new_unsafe_vs_all_three_baselines_near_seeds'},
  selectionContract
}={}) {
  insist(plain(training) && Array.isArray(training.trials) && Array.isArray(training.near_seeds) &&
    Array.isArray(training.clear_seeds) && Array.isArray(training.strategies), 'INVALID_TRAINING_MATRIX');
  verifyObservedSelection(training,selectionContract);
  const near = new Set(training.near_seeds), clear = new Set(training.clear_seeds);
  insist(near.size === training.near_seeds.length && clear.size === training.clear_seeds.length &&
    [...near].every(s=>!clear.has(s)) && near.size+clear.size === training.cohort.length,
  'COHORT_PARTITION_INVALID');
  const arms = [...training.strategies];
  insist(new Set(arms).size===arms.length && arms.includes(candidate) && arms.includes(baseline) &&
    protectedControls.every(s=>arms.includes(s)) &&
    unsafeReferenceStrategies.every(s=>arms.includes(s)), 'MISSING_PAIRED_ARMS');
  const rows = new Map();const perStrategy = Object.fromEntries(arms.map(s=>[s,{worlds:0,goals:0,nearGoals:0,clearGoals:0,unsafe:0,nearReopenAfterAnySide:0,nearReopenAfterLateral25:0,nearLateral25:0,nearDwell:0}]));
  for(const trial of training.trials){
    insist(arms.includes(trial.strategy) && (near.has(trial.seed)||clear.has(trial.seed)) &&
      bool(trial.success) && bool(trial.unsafe) && plain(trial.stage_funnel) &&
      SHA64.test(trial.world_hash||'') && Number.isInteger(trial.full_transition_count) &&
      Number.isInteger(trial.forward_reopened_after_side) && trial.forward_reopened_after_side>=0,
      'INVALID_TRIAL_ROW');
    const key=`${trial.seed}:${trial.strategy}`;insist(!rows.has(key),'DUPLICATE_TRIAL_ROW');rows.set(key,trial);
    const m=perStrategy[trial.strategy], isNear=near.has(trial.seed);
    const win=trial.success && !trial.unsafe;
    m.worlds++;m.goals+=Number(win);m.unsafe+=Number(trial.unsafe);
    if(isNear){m.nearGoals+=Number(win);
      m.nearReopenAfterAnySide+=Number(!trial.unsafe && trial.forward_reopened_after_side>0);
      m.nearReopenAfterLateral25+=Number(!trial.unsafe && trial.stage_funnel.forward_reopen_after_lateral25===true);
      m.nearLateral25+=Number(!trial.unsafe && trial.stage_funnel.signed_lateral25_after_contact===true);
      m.nearDwell+=Number(!trial.unsafe && trial.stage_funnel.full_contact_lateral_reopen_goal_dwell===true);
    } else m.clearGoals+=Number(win);
  }
  for(const world of training.cohort){
    insist(near.has(world.seed)||clear.has(world.seed),'UNKNOWN_WORLD');
    for(const arm of arms){
      const row=rows.get(`${world.seed}:${arm}`);
      insist(row && row.world_hash===world.world_hash,'UNPAIRED_WORLD_OR_MISMATCHED_WORLD_HASH');
    }
  }
  insist(rows.size===training.cohort.length*arms.length &&
    arms.every(s=>perStrategy[s].worlds===training.cohort.length),'INCOMPLETE_PAIRED_MATRIX');

  const safe=(seed,strategy)=>{const r=rows.get(`${seed}:${strategy}`);return r.success&&!r.unsafe;};
  const baselineWins=training.cohort.filter(w=>safe(w.seed,baseline)).map(w=>w.seed);
  const candidateWins=training.cohort.filter(w=>safe(w.seed,candidate)).map(w=>w.seed);
  const lostFromBaseline=baselineWins.filter(s=>!safe(s,candidate));
  const novelVsBaseline=candidateWins.filter(s=>!safe(s,baseline));
  const preservedBaseline=baselineWins.filter(s=>safe(s,candidate));
  const frozenUnionNear=[...near].filter(seed=>protectedControls.some(c=>safe(seed,c))).sort((a,b)=>a-b);
  const candidateNearNovelVsFrozen=[...near].filter(seed=>safe(seed,candidate) &&
    !protectedControls.some(c=>safe(seed,c)));
  const unionNearLost=frozenUnionNear.filter(seed=>!safe(seed,candidate));
  const unsafeReadoutWorlds=training.cohort.filter(w=>near.has(w.seed) &&
    rows.get(`${w.seed}:${candidate}`).unsafe &&
    unsafeReferenceStrategies.every(c=>!rows.get(`${w.seed}:${c}`).unsafe)).map(w=>w.seed);
  const extraUnsafe=training.cohort.filter(w=>rows.get(`${w.seed}:${candidate}`).unsafe &&
    !rows.get(`${w.seed}:${baseline}`).unsafe).map(w=>w.seed);
  insist(['lost','novel','unsafe'].every(k=>typeof readoutKeys[k]==='string'&&readoutKeys[k].length<=100),
    'UNDECLARED_READOUT_FIELDS');
  insist(JSON.stringify([...unionNearLost].sort((a,b)=>a-b))===
    JSON.stringify(list(readout[readoutKeys.lost],'READOUT_LOSS').slice().sort((a,b)=>a-b)) &&
    JSON.stringify(candidateNearNovelVsFrozen.slice().sort((a,b)=>a-b))===
    JSON.stringify(list(readout[readoutKeys.novel],'READOUT_NOVEL').slice().sort((a,b)=>a-b)) &&
    JSON.stringify(unsafeReadoutWorlds.slice().sort((a,b)=>a-b))===
    JSON.stringify(list(readout[readoutKeys.unsafe],'READOUT_UNSAFE').slice().sort((a,b)=>a-b)),
  'PAIRED_READOUT_DISAGREES_WITH_RAW');
  const candidateGoalRegressed=lostFromBaseline.length>0;
  const safeRegression=extraUnsafe.length>0 || perStrategy[candidate].unsafe>0;
  const newGoalGain=novelVsBaseline.length>0;
  const verdict=safeRegression?'NO_GO_NEW_UNSAFE':candidateGoalRegressed?'NO_GO_LOST_FROZEN_GOALS':
    !newGoalGain?'NO_GO_NO_GOAL_GAIN':'REVIEW_ONLY_TRAIN_GAIN';
  return {
    strategyMetrics:perStrategy,
    paired:{baseline,candidate,worlds:training.cohort.length,nearWorlds:near.size,clearWorlds:clear.size,
      baselineSafeGoals:baselineWins.length,candidateSafeGoals:candidateWins.length,
      preservedBaselineGoalSeeds:preservedBaseline,lostBaselineGoalSeeds:lostFromBaseline,
      novelGoalSeedsVsBaseline:novelVsBaseline,nearLostFrozenUnionSeeds:unionNearLost,
      nearNovelGoalSeedsVsFrozen:candidateNearNovelVsFrozen,
      newlyUnsafeWorldSeeds:extraUnsafe,
      unsafeWithAllReadoutControlsSafeSeeds:unsafeReadoutWorlds},
    scienceVerdict:verdict,
    modelPromotionAuthorized:false,
    qualificationScope:'REAL_PAIRED_TRAIN_ONLY_NOT_DEV_TEST_OR_DEPLOYMENT'
  };
}

export function recommendNextCycle(verified, observation, {candidateCommit,candidateWeightsSha,nextSeedStart=515000}={}) {
  insist(SHA40.test(candidateCommit||'') && SHA64.test(candidateWeightsSha||'') &&
    Number.isInteger(nextSeedStart) && nextSeedStart>=515000 && nextSeedStart+511<=2147483647,
    'NEXT_CANDIDATE_NOT_SOURCE_PINNED');
  const pastSeeds=new Set(verified.training.cohort.map(w=>w.seed));
  insist([...pastSeeds].every(s=>s<nextSeedStart), 'TRAIN_SEED_LEAKAGE');
  const seeds=Array.from({length:512},(_,i)=>nextSeedStart+i);
  const p=observation.paired;
  const nearTeacherSeeds=p.nearLostFrozenUnionSeeds;
  const stage3Bottleneck=observation.strategyMetrics[p.candidate].nearReopenAfterAnySide>0 &&
    observation.strategyMetrics[p.candidate].nearGoals===0;
  return {
    schema:'junction.craci.learning-controller.v1.next-cycle-advisory',
    sourceEvidence:{sourceCommit:verified.training.executed_head,trainingSha256:verified.immutableSha256.training,
      transitionArchiveSha256:verified.immutableSha256.transitions,
      qualifiedRunId:verified.receipt.binding.runId,level:'source-reported-plus-independent-source-replay'},
    failureSignal:{verdict:observation.scienceVerdict,
      lostBaselineGoalWorlds:p.lostBaselineGoalSeeds.length,
      nearLostFrozenGoalWorlds:nearTeacherSeeds.length,
      candidateForwardReopenedNearWorlds:observation.strategyMetrics[p.candidate].nearReopenAfterAnySide,
      candidateStrictLateral25ThenReopen:observation.strategyMetrics[p.candidate].nearReopenAfterLateral25,
      candidateSafeNearGoals:observation.strategyMetrics[p.candidate].nearGoals,
      failureHypothesis:stage3Bottleneck?'goal_completion_after_safe_reopening':'goal_preservation_and_masked_control'},
    observedTeacherSelection:{seedIds:nearTeacherSeeds,source:'original same-world frozen V5/V6 winning TRAIN observations',
      labels:'only actual observed actions of successful frozen controls; NOT counterfactual action labels',
      candidateFailureRowsMayChangeSamplingWeights:true},
    proposedProspective:{candidateCommit,candidateWeightsSha,nextTrainSeedStart:nextSeedStart,
      seedScanRangeInclusive:[nextSeedStart,nextSeedStart+511],seedScanSha256:digest(seeds),
      initialObservationOnlySelection:{nearWorldsTarget:128,clearWorldsTarget:32,
        noClaimsAboutFutureWorldClassification:true},
      pairedStrategies:['frozen_v5','frozen_v6','repeat_left','v8_hierarchical','v10_candidate'],
      maxEpisodesIfWorldTargetsMet:800,
      rawCapturePreflight:{summaryCaptureLimitBytes:19*1024*1024,
        nextActualSummaryBytes:'unknown_until_generated',
        mustUseReviewedLosslessChunkingIfOverLimit:true,
        mustVerifyExactRawEpisodeCountAndTransitionTotalsAfterReassembly:true,
        noSilentTruncationOrLossyFiltering:true},
      mustPreserveExactWorldPairing:true,
      prereqs:['independent code review','source-pinned CRACI workflow','fresh provider credit meter','owner-approved admission under active window'],
      noHeldoutDevTestOod:true,
      dispatchAuthorized:false},
    nextLearningCriterion:'Preserve every frozen-V5 goal world, reduce newly unsafe worlds to zero, and gain at least one truly new paired safe goal before independent model review.',
    modelPromotionAuthorized:false,
    automaticallyTrainModel:false,
    automaticallyDispatch:false,
    qualifiedFutureGain:false
  };
}

export async function compileCycle(paths,pins, options) {
  const verified=await loadQualifiedEvidence(paths,pins);
  const observation=analyzePairedTraining(verified.training,verified.readout,{
    candidate:pins.candidateStrategy,baseline:pins.baselineStrategy,
    protectedControls:pins.protectedControls,unsafeReferenceStrategies:pins.unsafeReferenceStrategies,
    readoutKeys:pins.readoutKeys,selectionContract:pins.selectionContract});
  const next=recommendNextCycle(verified,observation,options);
  return {
    schema:'junction.craci.learning-controller.v1.evidence-cycle',workId:'J26-CRACI-SELF-IMPROVING-LOOP-20261114',
    input:{githubRun:pins.githubRun,sourceSha:pins.sourceSha,harnessSha:pins.harnessSha,
      rawSha256:{...verified.immutableSha256},datasetSha256:verified.training.dataset_sha256,
      sourceReportedReceiptRunId:pins.receiptRunId},
    originalEvidenceRecheck:{...verified.trace,
      ...verifyObservedSelection(verified.training,pins.selectionContract),
      sourceReceiptState:'success-but-source-reported',
      independentQualification:'TRAIN-only positive replay, no held-out certification'},
    observation,next,
    activationState:'ADVISORY_NO_DISPATCH_NO_MODEL_PROMOTION',
    note:'Deterministic feedback from historical real MuJoCo TRAIN bytes. This compiler does not execute a new training or physics experiment.'
  };
}
