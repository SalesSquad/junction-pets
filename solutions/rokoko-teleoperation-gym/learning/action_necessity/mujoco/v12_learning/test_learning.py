"""Focused portable source/model/safety contract tests; no hosted physics."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import fit
import policy
import protocol

HERE=Path(__file__).resolve().parent
CHECKPOINT=HERE/"frozen-real-train-v10-v11-final"


def obs(distance=.2,obstacle=0.):
    o=[0.]*18
    o[16]=distance
    o[7]=obstacle
    o[9]=1.
    o[10]=1.
    o[15]=1.
    return o


def mask(*actions):
    return [int(k in actions) for k in range(7)]


class V12ActualEvidenceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=policy.load_frozen_model(CHECKPOINT/"model.json")
        cls.plan=protocol.verified_plan(CHECKPOINT/"next-train-plan.json")

    def test_real_source_only_model_exact_pins_and_world_disjoint_splits(self):
        self.assertEqual(self.model["sourceOriginalRealMuJoCoTrials"],1600)
        self.assertEqual(self.model["sourceOriginalRealOptionTransitions"],73561)
        self.assertEqual(self.model["worldDisjointSplits"],{
            "fit":185,"calibration":65,"diagnostic":70})
        splits=self.model["sourceWorldSplitKeys"]
        sets={name:set(ids) for name,ids in splits.items()}
        self.assertEqual(len(set.union(*sets.values())),320)
        self.assertFalse(sets["fit"] & sets["calibration"])
        self.assertFalse(sets["fit"] & sets["diagnostic"])
        self.assertFalse(sets["calibration"] & sets["diagnostic"])
        import hashlib
        for name,ids in splits.items():
            digest=hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest()
            self.assertEqual(digest,self.model["sourceWorldSplitSeedSha256"][name])

    def test_action4_legal_but_untrained_from_one_world(self):
        counts=self.model["sourceActualExecutedActionCounts"]
        self.assertEqual(sum(c["executed"][4] for c in counts.values()),3)
        self.assertEqual(sum(c["legal"][4] for c in counts.values()),48800)
        self.assertEqual(sum(r[4] for r in self.model["sourceDistinctWorldsPerAction"].values()),1)
        self.assertFalse(self.model["models"]["4"]["supported"])
        with self.assertRaisesRegex(policy.V12ContractStop,"UNSUPPORTED_ACTION"):
            policy.model_score(obs(),mask(4,6),None,4,self.model,0)

    def test_action0_diagnostic_failure_not_relaxed(self):
        align=self.model["models"]["0"]
        self.assertFalse(align["supported"])
        self.assertEqual(sum(x["executed"][0] for x in self.model["sourceActualExecutedActionCounts"].values()),947)
        self.assertLess(align["diagnosticPositionCoverage"],.90)
        self.assertLess(align["diagnosticWorldMaxPositionCoverage"],.90)
        self.assertTrue(all(self.model["models"][str(a)]["supported"] for a in (1,2,3,5)))

    def test_world_max_calibration_and_original_250tick_dwell(self):
        for a in (1,2,3,5):
            d=self.model["models"][str(a)]
            self.assertGreaterEqual(d["diagnosticWorldMaxPositionCoverage"],.9)
            self.assertGreaterEqual(d["sourceDistinctWorldsBySplit"]["diagnostic"],8)
        step={"observation":obs(),"next_observation":obs(),"mask":mask(6),
              "dwell_ticks_current":259,"cost":0}
        self.assertEqual(fit.target_from_executed_transition(step)[5],1.)
        self.assertEqual(step["dwell_ticks_current"],259)

    def test_frozen_gate_original_v5_winners_unaffected(self):
        witnesses=self.model["frozenV5WinningTrajectoryGateNoninterference"]
        self.assertEqual([witnesses[r]["realV5SafeGoalWorlds"] for r in ("v10","v11")],
                         [37,18])
        self.assertEqual([witnesses[r]["firedOnV5OriginalWinningWorlds"] for r in ("v10","v11")],
                         [0,0])

    def test_public_mask_fail_closed_and_wrong_sha(self):
        with self.assertRaisesRegex(policy.V12ContractStop,"ORIGINAL_SHIELD"):
            policy.checked_action(4,mask(6))
        with self.assertRaisesRegex(policy.V12ContractStop,"PUBLIC18D"):
            policy.public_abi(obs()+[4.],mask(6))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"candidate.json"
            path.write_bytes((CHECKPOINT/"model.json").read_bytes()+b" ")
            with self.assertRaisesRegex(policy.V12ContractStop,"MODEL_SHA"):
                policy.load_frozen_model(path)

    def test_v5_first_bounded_rescue_and_forward_restore(self):
        creations=[]
        def baseline_factory():
            creations.append(True)
            return lambda o,m:6 if m[6] else next(i for i,allowed in enumerate(m) if allowed)
        candidate=policy.policy_factory(baseline_factory,CHECKPOINT/"model.json")()
        sideways=candidate(obs(),mask(3,4,5,6))
        self.assertIn(sideways,(3,5))
        self.assertNotEqual(sideways,4)
        self.assertEqual(candidate.rescue_rounds,1)
        self.assertEqual(candidate(obs(),mask(1,3,4,5,6)),6)
        self.assertEqual(len(creations),2)
        self.assertFalse(candidate.rescue_active)
        for _ in range(12):
            self.assertIn(candidate(obs(),mask(3,4,5,6)),(3,5,6))
        self.assertLessEqual(candidate.rescue_rounds,1)
        self.assertLessEqual(candidate.rescue_options,8)
        self.assertNotIn(4,[sideways,*[0]])

    def test_untrained_right_probe_only_once_no_auto_promotion(self):
        factory=lambda: (lambda o,m:6)
        explorer=policy.right4_train_only_factory(factory,CHECKPOINT/"model.json")()
        self.assertEqual(explorer(obs(),mask(3,4,6)),4)
        self.assertEqual(explorer(obs(),mask(3,4,6)),6)
        self.assertTrue(explorer.used)
        self.assertEqual(explorer.mode_history[0],"UNTRAINED_RIGHT4_EXPLORATION_ONLY")
        self.assertFalse(self.plan["rightSideAction4ExplorationOnly"]["modelSupported"])
        self.assertFalse(self.plan["modelPromotionAuthorized"])

    def test_full512_public_initial_scan_derivation_and_fail_closed(self):
        scans=[]
        for s in range(518000,518512):
            scans.append({"seed":s,"observation":obs(obstacle=0. if s%3 else .13),
                          "mask":mask(3,4,6),"world_hash":f"verified-world-{s}"})
        cohort=protocol.derive_cohort(scans,self.plan,"pilot")
        self.assertEqual(len(cohort),48)
        self.assertEqual(sum(w["observed_corridor"] for w in cohort),40)
        self.assertEqual(sum(not w["observed_corridor"] for w in cohort),8)
        with self.assertRaisesRegex(ValueError,"EXTRA_FRESH"):
            protocol.derive_cohort(scans[:-1],self.plan,"pilot")
        scans[1]["world_hash"]=scans[0]["world_hash"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            protocol.derive_cohort(scans,self.plan,"pilot")

    def test_paired_actual_goal_not_forward_proxy_and_hard_stop(self):
        cohort=[{"seed":s,"world_hash":f"world-{s}"} for s in range(48)]
        trials=[]
        for w in cohort:
            for arm in protocol.PILOT_ARMS:
                trials.append({"seed":w["seed"],"world_hash":w["world_hash"],
                    "strategy":arm,"success":arm=="frozen_v5" and w["seed"]==0,
                    "unsafe":False,"abstained":False})
        readout=protocol.paired_physical_goal_readout(trials,cohort,"pilot")
        self.assertEqual(readout["candidateNovelSafeGoalWorldSeeds"],[])
        self.assertEqual(readout["candidateLostV5GoalWorldSeeds"],[0])
        self.assertTrue(readout["hardStopNoFurtherPhysics"])
        self.assertFalse(readout["modelPromotionAuthorized"])
        with self.assertRaisesRegex(ValueError,"INCOMPLETE"):
            protocol.paired_physical_goal_readout(trials[:-1],cohort,"pilot")


if __name__=="__main__":unittest.main()
