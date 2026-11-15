"""Synthetic-only V14 contract tests. NEVER original MuJoCo qualification."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import cli
import core


def fake_obs(x=0.,live=1.):
    obs=[0.]*18
    obs[0]=x;obs[2]=x-.06;obs[6]=.2;obs[7]=.2
    obs[9]=1.;obs[10]=live;obs[11]=1.;obs[15]=1.-live;obs[16]=.16
    return obs


def fake_step(action,x0,x1,*,cost=0,goal=False,done=False,contacts=0):
    o=fake_obs(x0);n=fake_obs(x1)
    return {"observation":o,"mask":[1]*7,"action":action,
            "reward":x1-x0,"cost":cost,"done":done,
            "contacts_cumulative":contacts,"dwell_ticks_current":250 if goal else 0,
            "dwell_ticks_cumulative":250 if goal else 0,
            "success_info":goal,"next_observation":n}


def fake_bundle(*,complete=False,witness_seeds=()):
    worlds={seed:hashlib.sha256(f"world{seed}".encode()).hexdigest()
            for seed in range(518000,518048)}
    failed=list(range(518000,518036));wins=list(range(518036,518048))
    branches=[];events=[];world_results=[]
    for seed in failed if complete else [518006]:
        base=fake_step(1,0.,.02,contacts=10)
        for ordinal,action in enumerate((1,2,3) if complete else (2,)):
            goal=complete and seed in witness_seeds and action==2
            progress={1:.025,2:.070,3:.010}[action]
            second=fake_step(action,.02,.02+progress,goal=goal,
                             done=goal or not complete,
                             cost=0 if complete else 1,
                             contacts=100 if complete else 2013)
            # The real original source can have a branch with only prefix,
            # but here each synthetic branch has exactly one intervention.
            transitions=[base,second]
            idx=len(branches)
            bid=f"v13-seen-train-{seed}-{ordinal:02d}"
            branches.append({"seed":seed,"branch_id":idx,"source_prefix":1,
                             "actions":[1,action],"transitions":transitions})
            for i,t in enumerate(transitions):
                events.append({"branchId":bid,"seed":seed,
                  "optionIndexZeroBased":i,"sourceWorldHash":worlds[seed],
                  "phase":"ORIGINAL_PREFIX" if i==0 else "COUNTERFACTUAL",
                  "transition":t,"transitionSha256":core.sha_obj(t),
                  "sourceOnlyUnattestedExecution":True,
                  "physicsQualificationPending":True})
        if complete:
            goal=seed in witness_seeds
            real=branches[-2]["transitions"] if goal else None
            world_results.append({"seed":seed,"executedBudgetBranches":3,
              "status":"WITNESS" if goal else "NONE_REACHABLE_WITHIN_FINITE_BUDGET",
              "actual250TickWitnessTraceSha256":core.sha_obj(real) if goal else None})
    if not complete:
        # V13 unsafe branch need not have any independently qualified result.
        world_results=[]
    training={"sourceFailureDiagnosis":{"v5FailedWorlds":failed,
        "v5WinningWorlds":wins,
        "v5FailedEarlyLegalAbstainWorlds":failed[:26],
        "v5FailedLiveDropAtOption17Worlds":failed[26:]},
        "recorded_branches":len(branches),
        "durably_journaled_all_executed_option_events":len(events),
        "status":"COMPLETE_TRAIN_DIAGNOSTIC_ONLY" if complete else "INCOMPLETE_STOP",
        "worldResults":world_results,"allWorldsComplete":complete,
        "hardStopReason":None if complete else "V13_REAL_PHYSICS_UNSAFE"}
    proofs={"diagnostic-readout.json":{"world_results":world_results,
        "status":"COMPLETE_TRAIN_DIAGNOSTIC_ONLY"},
        "independent-qualification.json":{
          "all_36_seen_train_failure_worlds_physically_replayed":True,
          "all_raw_branches_independently_replayed":len(branches),
          "all_raw_original_physics_option_steps_replayed":2*len(branches),
          "any_unsafe_actual_cost":False},
        "early_stop.json":{"status":"INCOMPLETE_STOP",
                           "reason":"V13_REAL_PHYSICS_UNSAFE"}}
    return {"status":"COMPLETE_TRAIN_DIAGNOSTIC_ONLY" if complete else "INCOMPLETE_STOP",
       "v13ProductHead":core.ORIGINAL_V13_PRODUCT,
       "v13HarnessHead":"a"*40,"hostedRun":100,
       "outerZipSha256":"b"*64,"receiptRawSha256":"c"*64,
       "receipt":{"sourceVerified":True},
       "retention":{"original_sha256":{"training.json":"d"*64}},
       "training":training,"branches":branches,"events":events,
       "worlds":worlds,"proofs":proofs,"publicMask":lambda o:[1]*7}


class FeedbackV4Tests(unittest.TestCase):
    def test_incomplete_unsafe_is_a_hard_stop_no_training_or_claim(self):
        bundle=fake_bundle()
        result=core.compile_from_verified(bundle)
        self.assertEqual(result["decision"]["decision"],"HARD_STOP_UNSAFE_INCOMPLETE")
        self.assertEqual(result["manifest"]["status"],"UNQUALIFIED_PARTIAL_NO_TRAINING_DATA")
        self.assertEqual(result["manifest"]["trainingRowsCount"],0)
        self.assertIsNone(result["manifest"]["trainingRowsSha256"])
        self.assertIsNone(result["decision"]["nextSingleV14PolicyProposal"])
        self.assertIsNone(result["decision"]["seenTrainDiagnosticWitnessWorldCount"])
        unsafe=result["decision"]["safetyCounterexample"]
        self.assertEqual((unsafe["seed"],unsafe["optionIndexZeroBased"],unsafe["action"]),
                         (518006,1,2))
        self.assertIn("UNKNOWN",unsafe["unsafeMechanism"])
        self.assertEqual(result["manifest"]["sourceReportedDistinctSeenWorlds"],1)
        self.assertFalse(result["manifest"]["independentSafetyRateEstimable"])

    def test_complete_witness_compiles_one_candidate_but_never_promotes(self):
        bundle=fake_bundle(complete=True,witness_seeds=(518000,518001,518002))
        result=core.compile_from_verified(bundle)
        self.assertEqual(result["decision"]["decision"],
                         "SEEN_TRAIN_WITNESS_NEEDS_PROSPECTIVE")
        self.assertEqual(result["decision"]["seenTrainDiagnosticWitnessWorldCount"],3)
        proposed=result["decision"]["nextSingleV14PolicyProposal"]
        self.assertEqual(proposed["selectedOriginalOption"],2)
        self.assertEqual(proposed["fallback"],"frozen V5 unchanged")
        self.assertFalse(proposed["prospectiveActual250TickGainClaimed"])
        self.assertFalse(result["decision"]["modelPromotionAuthorized"])
        self.assertEqual(result["decision"]["nextTrainAll512PublicSeedSha256"],
                         core.sha_obj(list(range(519024,519536))))
        self.assertEqual(result["manifest"]["trainingRowsCount"],108)
        self.assertEqual(core.digest(result["rowsBytes"]),
                         result["manifest"]["trainingRowsSha256"])
        # Matched model uncertainty is counted in distinct worlds, NOT 108
        # branch rows, 216 option events, or all three pairwise action pairs.
        action2=next(r for r in result["decision"][
            "actionEvidenceWithDistinctWorldPairedBayesianUncertainty"] if r["action"]==2)
        self.assertEqual(action2["matchedWithinForkDistinctWorldCount"],26)
        self.assertEqual(action2["distinctInformativeWorlds"],26)
        self.assertLess(action2["conservativePosteriorOneSided95Lower"],
                        action2["posteriorMean"])

    def test_no_witness_remains_science_stop(self):
        result=core.compile_from_verified(fake_bundle(complete=True))
        self.assertEqual(result["decision"]["decision"],
                         "SCIENCE_STOP_NO_CAUSAL_ACTION_POLICY_SUPPORT")
        self.assertIsNone(result["decision"]["nextSingleV14PolicyProposal"])
        self.assertIsNone(result["decision"]["nextTrainFrozenPublicSeedScanInclusive"])

    def test_forged_full_physics_qualifier_fails_closed(self):
        bundle=fake_bundle(complete=True,witness_seeds=(518000,518001))
        bundle["proofs"]["independent-qualification.json"][
            "all_36_seen_train_failure_worlds_physically_replayed"]=False
        with self.assertRaisesRegex(core.EvidenceRejected,"INDEPENDENT_ORIGINAL_PHYSICS"):
            core.compile_from_verified(bundle)

    def test_corrupted_journal_event_hash_and_public_mask_rejected(self):
        bundle=fake_bundle()
        bundle["events"][-1]["transitionSha256"]="f"*64
        with self.assertRaisesRegex(core.EvidenceRejected,"DURABLE_ORIGINAL_STEP"):
            core.compile_from_verified(bundle)
        bundle=fake_bundle()
        bundle["branches"][0]["transitions"][0]["mask"]=[0]*7
        with self.assertRaisesRegex(core.EvidenceRejected,"SEVEN_SHIELD"):
            core.compile_from_verified(bundle)

    def test_unsafe_partial_cannot_masquer_as_complete(self):
        bundle=fake_bundle()
        bundle["status"]="COMPLETE_TRAIN_DIAGNOSTIC_ONLY"
        with self.assertRaises(core.EvidenceRejected):
            core.compile_from_verified(bundle)

    def test_paired_effect_credible_bound_small_n_is_conservative(self):
        p=core._beta_jeffreys_counts(2,0,0)
        self.assertEqual(p["distinctInformativeWorlds"],2)
        self.assertLessEqual(p["conservativePosteriorOneSided95Lower"],.5)
        p2=core._beta_jeffreys_counts(36,0,0)
        self.assertGreater(p2["posteriorMean"],.9)

    def test_hosted_sha_pin_mandatory_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact=Path(tmp)/"fake.zip"
            artifact.write_bytes(b"not a hosted artifact")
            with self.assertRaisesRegex(core.EvidenceRejected,"HOSTED_ARTIFACT_SHA_MISMATCH"):
                core.load_verified_hosted(artifact,"0"*64,"a"*40,100,Path(tmp))
            with self.assertRaisesRegex(core.EvidenceRejected,"EXTERNAL_IMMUTABLE"):
                core.load_verified_hosted(artifact,"bad","a"*40,100,Path(tmp))

    def test_output_is_new_immutable_and_source_hash_bound(self):
        result=core.compile_from_verified(fake_bundle())
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"result"
            cli.write_fresh(out,result)
            self.assertEqual(sorted(p.name for p in out.iterdir()),
                 ["next_training_decision.json","training_dataset_manifest.json"])
            decoded=json.loads((out/"next_training_decision.json").read_text())
            self.assertEqual(decoded["sourceLineageSha256"],
                             result["manifest"]["sourceLineageSha256"])
            with self.assertRaisesRegex(core.EvidenceRejected,"MUST_BE_NEW"):
                cli.write_fresh(out,result)


if __name__=="__main__":
    unittest.main()
