"""Focused unit and immutable-checkpoint controls for V11; no charged physics."""

from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

import learn_gate
import policy
import prospective_train


HERE = Path(__file__).resolve().parent
GATE = HERE / "frozen-v10-train-approved" / "gate.json"


def observation(distance=.5, obstacle=.05):
    obs = [0.0] * 18
    obs[7] = obstacle
    obs[16] = distance
    return obs


def blocked_mask():
    return [1, 0, 0, 1, 1, 0, 1]


def v5_factory():
    def selected(obs, mask):
        return 1 if mask[1] else 6 if mask[6] else next(i for i,v in enumerate(mask) if v)
    return selected


def v10_factory():
    def selected(obs, mask):
        return 3 if mask[3] else next(i for i,v in enumerate(mask) if v)
    return selected


class TestFrozenV11SourceOnly(unittest.TestCase):
    def test_checkpoint_has_exact_committed_bytes(self):
        actual = hashlib.sha256(GATE.read_bytes()).hexdigest()
        self.assertEqual(actual, policy.GATE_SHA256)
        self.assertEqual(policy.load_frozen_gate(GATE),
                         {"kind":"blocked_or_abstain_side","min_distance":.035,
                          "min_streak":1,"obstacle_limit":.1})

    def test_gate_rejects_wrong_checkpoint(self):
        with self.assertRaisesRegex(policy.ProspectiveV11ContractError, "V11_FROZEN_GATE_SHA_CHANGED"):
            policy.load_frozen_gate(HERE / "frozen-v10-train-approved" / "analysis.json")

    def test_frozen_v5_remains_decider_with_legal_forward(self):
        p = policy.policy_factory(v5_factory, v10_factory, GATE)()
        legal = [1,1,0,1,1,0,1]
        self.assertEqual([p(observation(),legal) for _ in range(4)], [1]*4)
        self.assertEqual(p.rescue_rounds,0)

    def test_gate_preempts_stalled_v5_and_returns_on_forward_reopen(self):
        p = policy.policy_factory(v5_factory, v10_factory, GATE)()
        self.assertEqual(p(observation(),blocked_mask()),3)
        self.assertEqual(p.rescue_rounds,1)
        self.assertEqual(p(observation(),blocked_mask()),3)
        self.assertEqual(p(observation(),[1,1,0,1,1,0,1]),1)
        self.assertFalse(p.rescue_active)
        self.assertEqual(p(observation(),blocked_mask()),6) # exhausted rescue budget
        self.assertEqual(p.mode_history.count("rescue"),2)

    def test_only_one_rescue_and_max8_source_learned_options(self):
        p = policy.policy_factory(v5_factory,v10_factory,GATE)()
        actions = [p(observation(),blocked_mask()) for _ in range(20)]
        self.assertEqual(actions[:8],[3]*8)
        self.assertEqual(actions[8:],[6]*12)
        self.assertEqual(p.rescue_rounds,1)

    def test_public_goal_approach_and_obstacle_exclude_rescue(self):
        for obs in [observation(.02), observation(.5,.101)]:
            p = policy.policy_factory(v5_factory,v10_factory,GATE)()
            self.assertEqual(p(obs,blocked_mask()),6)
            self.assertEqual(p.rescue_rounds,0)

    def test_bad_masks_obs_and_illegal_baseline_fail_closed(self):
        gate = policy.load_frozen_gate(GATE)
        p = policy.FrozenV11GoalPreservingRescue(v5_factory,v10_factory,gate)
        for obs,mask in [(observation(),[1,2,0,1,1,0,1]),
                         (observation(),[0]*7),([1]*17,blocked_mask()),
                         (observation(float("nan")),blocked_mask())]:
            with self.assertRaises(policy.ProspectiveV11ContractError):
                p(obs,mask)
        illegal = policy.FrozenV11GoalPreservingRescue(lambda: lambda o,m: 2,
                                                       v10_factory,gate)
        with self.assertRaisesRegex(policy.ProspectiveV11ContractError,"SHIELD_VIOLATION"):
            illegal(observation(),blocked_mask())

    def test_rescue_illegal_mask_is_not_repaired(self):
        gate = policy.load_frozen_gate(GATE)
        invalid_rescue = lambda: lambda o,m: 1
        p = policy.FrozenV11GoalPreservingRescue(v5_factory,invalid_rescue,gate)
        with self.assertRaisesRegex(policy.ProspectiveV11ContractError,"SHIELD_VIOLATION"):
            p(observation(),blocked_mask())

    def test_gate_score_never_fabricates_counterfactual(self):
        params = policy.load_frozen_gate(GATE)
        trace=[{"observation":observation(),"mask":blocked_mask(),"action":6}]
        self.assertEqual(learn_gate.episodes_with_gate(trace,params),0)
        self.assertEqual(learn_gate.episodes_with_gate(
            [{"observation":observation(.02),"mask":blocked_mask(),"action":6}],params),None)

    def test_future_public_world_protocol_is_frozen(self):
        plan = prospective_train.load_plan()
        self.assertEqual(plan["trainSeedRangeInclusive"],[517000,517511])
        self.assertEqual(plan["candidateModelGateSha256"],policy.GATE_SHA256)

    def test_original_v5_generic_policy_import_cannot_be_poisoned_by_v11(self):
        """Actual process import order: product V11 first, legacy V5 later."""
        script="""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, %r)
import prospective_train
assert 'policy' not in sys.modules, 'V11_STOLE_LEGACY_GENERIC_POLICY_NAME'
assert prospective_train.policy.__name__ == 'rokoko_v11_frozen_goal_rescue_policy'
with tempfile.TemporaryDirectory() as temporary:
    legacy=Path(temporary)/'policy.py'
    legacy.write_text('BOUNDS = (0,1)\\nDEFAULT = 0\\n')
    sys.path.insert(0, temporary)
    from policy import BOUNDS, DEFAULT
    assert BOUNDS == (0,1) and DEFAULT == 0
    assert Path(sys.modules['policy'].__file__).resolve() == legacy.resolve()
print('V11_PRODUCT_AND_V5_LEGACY_POLICY_NAMES_ISOLATED')
""" % str(HERE)
        result=subprocess.run([sys.executable,"-c",script],capture_output=True,
                              text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("V11_PRODUCT_AND_V5_LEGACY_POLICY_NAMES_ISOLATED",result.stdout)

    def test_exact512_initial_public_world_scan_128_near_32_clear(self):
        scan=[{"seed":517000+i,"world_hash":f"synthetic-{i}",
               "observation":observation(obstacle=.05 if i < 200 else .2),
               "mask":blocked_mask()} for i in range(512)]
        cohort=prospective_train.derive_cohort(scan)
        self.assertEqual(len(cohort),160)
        self.assertEqual([r["seed"] for r in cohort if r["observed_corridor"]],
                         list(range(517000,517128)))
        self.assertEqual([r["seed"] for r in cohort if not r["observed_corridor"]],
                         list(range(517200,517232)))
        with self.assertRaisesRegex(ValueError,"ALL_512"):
            prospective_train.derive_cohort(scan[:500])

    def test_physics_readout_requires_novel_goal_and_zero_loss(self):
        cohort=[{"seed":517000+i} for i in range(160)]
        def fake(seed,name):
            return {"seed":seed,"strategy":name,"world_hash":f"synthetic-{seed}",
                    "success":False,"unsafe":False,"abstained":False,
                    "observed_corridor":seed < 517128}
        trial=[fake(w["seed"],name) for w in cohort for name in prospective_train.ARMS]
        def row(seed,name):
            return next(r for r in trial if r["seed"]==seed and r["strategy"]==name)
        row(517000,"frozen_v5")["success"]=True
        row(517000,"v11_goal_preserving")["success"]=True
        self.assertEqual(prospective_train.readout(trial,cohort)["source_only_preliminary_training_gate"],
                         "NO_GO_LOST_GOAL_UNSAFE_OR_ZERO_NOVEL")
        row(517001,"v11_goal_preserving")["success"]=True
        self.assertEqual(prospective_train.readout(trial,cohort)["source_only_preliminary_training_gate"],
                         "CANDIDATE_FOR_INDEPENDENT_QUALIFICATION")
        row(517000,"v11_goal_preserving")["success"]=False
        self.assertEqual(prospective_train.readout(trial,cohort)["lost_frozen_v5_goal_seed_ids"],
                         [517000])


if __name__=="__main__": unittest.main()
