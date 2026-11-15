"""Portable deterministic synthetic contract tests; NOT MuJoCo qualification."""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

import causal
import forensic
import protocol


class SyntheticContractEnv:
    """Tiny deterministic test double; never used for scientific outcomes."""
    def __init__(self,max_options=60,release_after=None,unsafe_on=None):
        self.max_options=max_options
        self.release_after=release_after
        self.unsafe_on=unsafe_on
        self.reset(123,False)

    def reset(self,seed,ood=False):
        self.seed=seed
        self.x=0.
        self.steps=self.physics_steps=self.contacts=self.dwell=0
        self.unsafe=self.done=False
        return self.observation()

    def observation(self):
        o=[0.]*18
        o[0]=self.x
        o[2]=self.x-.03
        o[7]=.15
        o[9]=1.
        o[10]=0. if self.release_after is not None and self.steps>=self.release_after else 1.
        o[11]=1.
        o[15]=float(not o[10])
        o[16]=.16
        return o

    def mask(self,obs=None):
        o=self.observation() if obs is None else obs
        return [0,1,1,1,1,1,1] if o[10] else [0,0,0,0,0,0,1]

    def step(self,action):
        if not self.mask()[action]:raise RuntimeError("SYNTHETIC_TEST_SHIELD_VIOLATION")
        if self.done:raise RuntimeError("SYNTHETIC_TEST_ALREADY_DONE")
        self.steps+=1
        self.physics_steps+=100
        movement={1:.06,2:.08,3:.02,4:.04,5:-.005,6:0.}[action]
        self.x+=movement
        self.contacts+=int(action in (1,2,3,4))
        self.unsafe=bool(action==self.unsafe_on)
        self.dwell=250 if abs(self.x-.16)<.02 and self.contacts else 0
        success=bool(self.dwell>=250 and not self.unsafe)
        self.done=bool(self.unsafe or success or action==6 or self.steps>=self.max_options)
        return self.observation(),movement,self.done,{
            "cost":int(self.unsafe),"success":success,"unsafe":self.unsafe,
            "error":abs(self.x-.16),"contacts":self.contacts}


def fake_original_trace(*actions,release_after=None):
    env=SyntheticContractEnv(release_after=release_after)
    env.reset(42,False)
    out=[]
    for a in actions:
        o=env.observation()
        mask=env.mask(o)
        n,r,done,info=env.step(a)
        out.append({"observation":o,"mask":mask,"action":a,
                    "next_observation":n,"cost":info["cost"],
                    "reward":float(r),"done":bool(done),
                    "success_info":bool(info["success"]),
                    "contacts_cumulative":info["contacts"],
                    "dwell_ticks_current":env.dwell,
                    "dwell_ticks_cumulative":env.dwell})
        if done:break
    return out


def factory(**kw):return SyntheticContractEnv(**kw)


def signature(e):return f"test-world-{e.seed}"


class V13SyntheticContractTest(unittest.TestCase):
    def test_reset_same_seed_exact_prefix_then_true_contract_goal(self):
        source=fake_original_trace(2,6)
        fork,kind=causal.frozen_first_fork(source,42)
        self.assertEqual((fork,kind),(1,"EARLY_LIVE_ABSTAIN"))
        result=causal.replay_actions(factory,signature,42,source,"test-world-42",fork,[2])
        self.assertTrue(result["actualGoalSuccess250Tick"])
        self.assertFalse(result["actualUnsafe"])
        self.assertEqual(result["actualDwellTicks"],250)
        self.assertEqual(result["actions"],[2,2])
        self.assertEqual(len(result["traceSha256"]),64)
        self.assertEqual(result["status"],"ORIGINAL_PHYSICS_TERMINAL")
        # A fake/constructor-injected environment can NEVER self-certify
        # physical MuJoCo qualification. Hosted independently replays it.
        self.assertFalse(result["newRealMuJoCoExecuted"])
        self.assertTrue(result["sourceOnlyUnattestedExecution"])
        self.assertTrue(result["physicsQualificationPending"])

    def test_bad_public_prefix_rejected_not_repaired(self):
        original=fake_original_trace(2,6)
        original[0]["observation"][0]=.999
        with self.assertRaisesRegex(ValueError,"RESEEDED_FIRST_PUBLIC_STATE_MISMATCH"):
            causal.replay_actions(factory,signature,42,original,"test-world-42",1,[2])

    def test_exact_world_hash_and_original_mask_fail_closed(self):
        original=fake_original_trace(2,6)
        with self.assertRaisesRegex(ValueError,"PAIRED_WORLD_HASH_CHANGED"):
            causal.replay_actions(factory,signature,42,original,"forged-world",1,[2])
        with self.assertRaisesRegex(ValueError,"SHIELD_LEGAL_ACTION_REQUIRED"):
            causal.replay_actions(factory,signature,42,original,"test-world-42",1,[0])

    def test_observed_live_false_is_irreversible_no_motor(self):
        original=fake_original_trace(2,6,release_after=1)
        result=causal.replay_actions(lambda **kw:factory(**kw,release_after=1),signature,
                                     42,original,"test-world-42",1,[2],tail=True)
        self.assertEqual(result["status"],"PUBLIC_LIVE_FALSE_MOTOR_DISABLED")
        self.assertEqual(result["actions"],[2])
        self.assertEqual(causal.supported_choices(result["lastPublicObservation18D"],
                         result["lastOriginalMask7"],result["actions"]),[])

    def test_physically_unsafe_intervention_remains_stop_evidence(self):
        original=fake_original_trace(2,6)
        result=causal.replay_actions(lambda **kw:factory(**kw,unsafe_on=4),signature,
                                     42,original,"test-world-42",1,[4],tail=True)
        self.assertTrue(result["actualUnsafe"])
        self.assertFalse(result["actualGoalSuccess250Tick"])
        self.assertEqual(result["status"],"ORIGINAL_PHYSICS_TERMINAL")
        self.assertEqual(result["trace"][-1]["cost"],1)

    def test_original_public_gate_no_future_hidden_parameters(self):
        o=[0.]*18;o[9]=1.;o[10]=1.;o[11]=1.;o[16]=.16
        self.assertEqual(causal.supported_choices(o,[0,0,0,1,1,1,1],[]),[3,4,5])
        self.assertEqual(causal.supported_choices(o,[0,0,0,1,1,1,1],[3,3]),[4,5,3])
        with self.assertRaisesRegex(ValueError,"PUBLIC18D"):
            causal.supported_choices(o+[123.],[0,0,0,1,1,1,1],[])
        with self.assertRaisesRegex(ValueError,"LIVE_FALSE"):
            bad=copy.deepcopy(o);bad[10]=0.
            causal.supported_choices(bad,[0,0,1,0,0,0,1],[])

    def test_pre_registered_budget_is_fixed(self):
        self.assertEqual(causal.MAX_DEPTH,3)
        self.assertEqual(causal.BEAM_WIDTH,2)
        self.assertEqual(causal.MAX_WORLD_BRANCHES,20)
        self.assertEqual(causal.MAX_TOTAL_BRANCHES,36*20)
        self.assertEqual(causal.MAX_ORIGINAL_OPTIONS,60)

    def test_lossless_callback_precedes_next_real_branch(self):
        source={"sourceSha":forensic.SOURCE_HEAD,
                "fullTransitionsSha256":forensic.RAW_SHAS["full_transitions.jsonl.gz"],
                "independentReplayQualified":True,
                "rows":{(42,forensic.ARM_V5):{"world_hash":"test-world-42"}},
                "traces":{(42,forensic.ARM_V5):fake_original_trace(2,6)}}
        journal=[]
        completed_options=[]
        with patch.object(forensic,"source_failure_diagnosis",
                          return_value={"v5FailedWorlds":[42]}):
            output=causal.run_budgeted_diagnostic(source,factory,signature,
                            on_branch=lambda b:journal.append(b),
                            on_step=lambda step:completed_options.append(step))
        self.assertEqual(output["status"],"TRAIN_ONLY_DIAGNOSTIC_COMPLETE")
        self.assertEqual(journal,output["rawBranches"])
        self.assertGreaterEqual(len(journal),2)
        self.assertEqual(output["worldResults"][0]["status"],"WITNESS")
        self.assertTrue(journal[-1]["actualGoalSuccess250Tick"])
        self.assertEqual(len(completed_options),sum(len(b["trace"]) for b in journal))
        self.assertEqual(completed_options[0]["phase"],"ORIGINAL_PREFIX")
        self.assertEqual(completed_options[-1]["phase"],"COUNTERFACTUAL")
        self.assertEqual(completed_options[-1]["branchId"],journal[-1]["branchId"])
        self.assertTrue(all(s["physicsQualificationPending"] for s in completed_options))

    def test_lossless_journal_failure_hard_stops_after_previous_receipt(self):
        source={"sourceSha":forensic.SOURCE_HEAD,
                "fullTransitionsSha256":forensic.RAW_SHAS["full_transitions.jsonl.gz"],
                "independentReplayQualified":True,
                "rows":{(42,forensic.ARM_V5):{"world_hash":"test-world-42"}},
                "traces":{(42,forensic.ARM_V5):fake_original_trace(2,6)}}
        journal=[]
        option_journal=[]
        def append_or_fail(branch):
            if journal:raise OSError("DURABLE_JOURNAL_UNAVAILABLE_STOP")
            journal.append(branch)
        with patch.object(forensic,"source_failure_diagnosis",
                          return_value={"v5FailedWorlds":[42]}):
            with self.assertRaisesRegex(OSError,"JOURNAL_UNAVAILABLE_STOP"):
                causal.run_budgeted_diagnostic(source,factory,signature,
                    on_branch=append_or_fail,
                    on_step=lambda event:option_journal.append(event))
        self.assertEqual(len(journal),1)
        self.assertEqual(journal[0]["actions"],[2])
        self.assertGreater(len(option_journal),len(journal))

    def test_journal_must_be_callable_if_supplied(self):
        with self.assertRaisesRegex(ValueError,"PREREGISTERED_FINITE"):
            causal.run_budgeted_diagnostic({},factory,signature,
                on_branch="unsafe",on_step=lambda event:None)

    def test_midbranch_timeout_preserves_complete_option_journal(self):
        original=fake_original_trace(2,3,6)
        step_journal=[]
        # No state mutation by the callback; a clean timeout AFTER one prefix
        # and one counterfactual option retains both complete physical steps.
        with patch.object(causal.time,"monotonic",side_effect=[0,0,2]):
            with self.assertRaisesRegex(TimeoutError,"DEADLINE"):
                causal.replay_actions(factory,signature,42,original,"test-world-42",1,
                   additional_actions=[3,3,3],deadline=1.,branch_id="partial-42",
                   on_step=lambda event:step_journal.append(event))
        self.assertEqual(len(step_journal),2)
        self.assertEqual([e["optionIndexZeroBased"] for e in step_journal],[0,1])
        self.assertEqual([e["phase"] for e in step_journal],
                         ["ORIGINAL_PREFIX","COUNTERFACTUAL"])
        self.assertEqual({e["branchId"] for e in step_journal},{"partial-42"})
        self.assertEqual([e["transition"]["action"] for e in step_journal],[2,3])

    def test_default_1200_second_internal_deadline_stops_and_preserves_partial(self):
        source={"sourceSha":forensic.SOURCE_HEAD,
                "fullTransitionsSha256":forensic.RAW_SHAS["full_transitions.jsonl.gz"],
                "independentReplayQualified":True,
                "rows":{(42,forensic.ARM_V5):{"world_hash":"test-world-42"}},
                "traces":{(42,forensic.ARM_V5):fake_original_trace(2,6)}}
        step_journal=[];branch_journal=[]
        # clock: internal deadline=1200, world precheck=600, first option=900,
        # next *branch* option=1300 >1200 => incomplete, first branch kept.
        clock=iter((0.,600.,900.,1300.))
        with patch.object(forensic,"source_failure_diagnosis",
                          return_value={"v5FailedWorlds":[42]}),\
             patch.object(causal.time,"monotonic",side_effect=lambda:next(clock)):
            output=causal.run_budgeted_diagnostic(source,factory,signature,
                      on_branch=branch_journal.append,on_step=step_journal.append)
        self.assertEqual(output["status"],"INCOMPLETE")
        self.assertEqual(output["hardStopReason"],"V13_FINITE_DEADLINE")
        self.assertFalse(output["allWorldsComplete"])
        self.assertEqual(len(branch_journal),1)
        self.assertEqual(len(step_journal),1)
        self.assertEqual(branch_journal,output["rawBranches"])
        self.assertTrue(step_journal[0]["sourceOnlyUnattestedExecution"])

    def test_new_future_seeds_under_original_guard_and_disjoint(self):
        self.assertEqual(protocol.FRESH_SCAN,(519024,519535))
        self.assertEqual(protocol.CONFIRM_SCAN,(519536,519999))
        self.assertLess(protocol.CONFIRM_SCAN[1],520000)
        self.assertEqual(protocol.FRESH_SCAN[1]-protocol.FRESH_SCAN[0]+1,512)
        self.assertEqual(protocol.CONFIRM_SCAN[1]-protocol.CONFIRM_SCAN[0]+1,464)
        plan=protocol.frozen_plan()
        first,last=protocol.FRESH_SCAN
        world_scan=[{"seed":s,"world_hash":f"future-world-{s}",
                     "observation":[0.,0.,0.,0.,0.,0.,0.,.15 if s%4==0 else .03,
                          0.,1.,1.,1.,1.,0.,0.,0.,.16,0.],
                     "mask":[0,1,1,1,1,1,1]} for s in range(first,last+1)]
        cohort=protocol.derive_public_cohort(world_scan,plan,"new_train")
        self.assertEqual(len(cohort),80)
        self.assertEqual(sum(w["publicNear"] for w in cohort),64)
        with self.assertRaisesRegex(ValueError,"MISSING_HANDPICKED"):
            protocol.derive_public_cohort(world_scan[:-1],plan,"new_train")
        fake=dict(plan,newTrainScanRangeInclusive=[520000,520511])
        with self.assertRaisesRegex(ValueError,"FORGED_OR_MUTATED"):
            protocol.derive_public_cohort(world_scan,fake,"new_train")


if __name__=="__main__":unittest.main()
