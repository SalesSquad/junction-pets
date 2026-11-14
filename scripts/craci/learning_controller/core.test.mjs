import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzePairedTraining, recommendNextCycle, canonical, sha} from './core.mjs';

const WORLD_SHA='a'.repeat(64);
const ARMS=['frozen_v5','frozen_v6','repeat_left','v8_hierarchical'];
const selectionContract={firstSeed:1,scanLimit:3,nearTarget:2,clearTarget:1,nearAbsThreshold:.122};
const analyze=(training,readout)=>analyzePairedTraining(training,readout,{selectionContract});
function fixture({promoteV8=false,unsafeV8=false}={}) {
  const worlds=[{seed:1,world_hash:WORLD_SHA,initial_observed_obstacle_y:.04,observed_corridor:true},
    {seed:2,world_hash:WORLD_SHA,initial_observed_obstacle_y:.09,observed_corridor:true},
    {seed:3,world_hash:WORLD_SHA,initial_observed_obstacle_y:.16,observed_corridor:false}];
  const success={frozen_v5:[1,3],frozen_v6:[3],repeat_left:[],v8_hierarchical:promoteV8?[1,2,3]:[3]};
  const trials=worlds.flatMap(w=>ARMS.map(strategy=>({
    seed:w.seed,world_hash:WORLD_SHA,strategy,
    success:success[strategy].includes(w.seed),unsafe:unsafeV8&&strategy==='v8_hierarchical'&&w.seed===2,
    full_transition_count:1,forward_reopened_after_side:strategy==='v8_hierarchical'?1:0,
    stage_funnel:{signed_lateral25_after_contact:false,forward_reopen_after_lateral25:false,full_contact_lateral_reopen_goal_dwell:false}
  })));
  const training={cohort:worlds,selection_scan:worlds.map(w=>({seed:w.seed,world_hash:w.world_hash,
    initial_observed_obstacle_y:w.initial_observed_obstacle_y})),
    train_first_seed:1,selection_max_seeds:3,selected_near_count:2,selected_clear_count:1,
    trials,strategies:ARMS,near_seeds:[1,2],clear_seeds:[3],
    executed_head:'a'.repeat(40)};
  const readout={lost_frozen_v5_v6_safe_near_goal_seeds:promoteV8?[]:[1],
    novel_v8_safe_near_goal_seeds:promoteV8?[2]:[],
    v8_new_unsafe_vs_all_three_baselines_near_seeds:unsafeV8?[2]:[]};
  return {training,readout};
}

test('real paired contracts: losing frozen goals prevents promotion',()=>{
  const {training,readout}=fixture();
  const x=analyze(training,readout);
  assert.equal(x.scienceVerdict,'NO_GO_LOST_FROZEN_GOALS');
  assert.equal(x.paired.baselineSafeGoals,2);
  assert.equal(x.paired.candidateSafeGoals,1);
  assert.deepEqual(x.paired.nearLostFrozenUnionSeeds,[1]);
  assert.deepEqual(x.paired.lostBaselineGoalSeeds,[1]);
  assert.equal(x.modelPromotionAuthorized,false);
});

test('candidate gains in unchanged paired worlds remain reviewer-only',()=>{
  const {training,readout}=fixture({promoteV8:true});
  const x=analyze(training,readout);
  assert.equal(x.scienceVerdict,'REVIEW_ONLY_TRAIN_GAIN');
  assert.deepEqual(x.paired.novelGoalSeedsVsBaseline,[2]);
  assert.equal(x.modelPromotionAuthorized,false);
});

test('new unsafe event is a STOP even if goal score improved',()=>{
  const {training,readout}=fixture({promoteV8:true,unsafeV8:true});
  readout.novel_v8_safe_near_goal_seeds=[];
  const x=analyze(training,readout);
  assert.equal(x.scienceVerdict,'NO_GO_NEW_UNSAFE');
  assert.deepEqual(x.paired.newlyUnsafeWorldSeeds,[2]);
});

test('baseline-safe world unsafe regression is caught even when secondary control unsafe',()=>{
  const {training,readout}=fixture();
  // Candidate and V6 are both unsafe on near world #2; readout's ALL-three-safe
  // subset is empty. V5 is unsafe elsewhere, so aggregate counts alone cannot
  // show the paired regression of V5-safe world #2.
  const v6=training.trials.find(t=>t.seed===2&&t.strategy==='frozen_v6');v6.unsafe=true;
  const v5=training.trials.find(t=>t.seed===3&&t.strategy==='frozen_v5');v5.unsafe=true;
  const candidate=training.trials.find(t=>t.seed===2&&t.strategy==='v8_hierarchical');candidate.unsafe=true;
  // Source readout pairwise loss reflects the changed world #3 and still #1.
  readout.lost_frozen_v5_v6_safe_near_goal_seeds=[1];
  readout.v8_new_unsafe_vs_all_three_baselines_near_seeds=[];
  const x=analyze(training,readout);
  assert.deepEqual(x.paired.newlyUnsafeWorldSeeds,[2]);
  assert.deepEqual(x.paired.unsafeWithAllReadoutControlsSafeSeeds,[]);
  assert.equal(x.strategyMetrics.frozen_v5.unsafe,1);
  assert.equal(x.strategyMetrics.v8_hierarchical.unsafe,1);
  assert.equal(x.scienceVerdict,'NO_GO_NEW_UNSAFE');
});

test('unpaired, altered-world, or contradictory readout never silently passes',()=>{
  const {training,readout}=fixture();
  training.trials[0].world_hash='b'.repeat(64);
  assert.throws(()=>analyze(training,readout),/UNPAIRED_WORLD/);
  training.trials[0].world_hash=WORLD_SHA;
  readout.lost_frozen_v5_v6_safe_near_goal_seeds=[];
  assert.throws(()=>analyze(training,readout),/PAIRED_READOUT_DISAGREES/);
  readout.lost_frozen_v5_v6_safe_near_goal_seeds=[1];
  training.trials.pop();
  assert.throws(()=>analyze(training,readout),/UNPAIRED_WORLD/);
});

test('tampered initial-observation near/clear selection is rejected before scoring',()=>{
  const {training,readout}=fixture();
  training.selection_scan[1].initial_observed_obstacle_y=.16;
  assert.throws(()=>analyze(training,readout),/WORLD_SELECTION|SELECTED_COHORT|INCOMPLETE_WORLD_COHORT/);
  training.selection_scan[1].initial_observed_obstacle_y=.09;
  training.cohort[1].world_hash='c'.repeat(64);
  assert.throws(()=>analyze(training,readout),/SELECTED_COHORT_NOT_DERIVED/);
});

test('next cycle is reproducible, disjoint, advisory and source-pinned',()=>{
  const {training,readout}=fixture();
  const obs=analyze(training,readout);
  const verified={training,receipt:{binding:{runId:'source.reported.run'}},
    immutableSha256:{training:'1'.repeat(64),transitions:'2'.repeat(64)}};
  const opts={candidateCommit:'3'.repeat(40),candidateWeightsSha:'4'.repeat(64),nextSeedStart:515000};
  const p=recommendNextCycle(verified,obs,opts);
  const q=recommendNextCycle(verified,obs,opts);
  assert.equal(canonical(p),canonical(q));
  assert.equal(p.failureSignal.verdict,'NO_GO_LOST_FROZEN_GOALS');
  assert.equal(p.proposedProspective.seedScanRangeInclusive[0],515000);
  assert.equal(p.proposedProspective.maxEpisodesIfWorldTargetsMet,800);
  assert.equal(p.proposedProspective.dispatchAuthorized,false);
  assert.equal(p.modelPromotionAuthorized,false);
  assert.throws(()=>recommendNextCycle(verified,obs,{...opts,nextSeedStart:2}),/NEXT_CANDIDATE_NOT_SOURCE_PINNED/);
  assert.match(sha(Buffer.from(canonical(p.proposedProspective))),/^[a-f0-9]{64}$/);
});
