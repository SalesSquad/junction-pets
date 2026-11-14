"""Portable v6 contract tests; true MuJoCo runs only under pinned CRACI."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

import numpy as np
import corridor_policy as policy

spec=importlib.util.spec_from_file_location("mujoco_v6_training_runner_contract",Path(__file__).with_name("run.py"))
assert spec is not None and spec.loader is not None
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def observation(obstacle_y=.065,object_x=.0,object_y=.0,pusher_x=-.06,pusher_y=.0):
    arr=np.zeros(18,dtype=np.float32)
    arr[0:2]=object_x,object_y
    arr[2:4]=pusher_x,pusher_y
    arr[6:8]=.09,obstacle_y
    arr[9:12]=.99,1.,1.
    arr[16:18]=.16,0.
    return arr


class V6Contracts(unittest.TestCase):
    def test_v5_baseline_weights_hash_and_known_result(self):
        self.assertEqual(policy.canonical_sha(policy.V5_FROZEN_WEIGHTS),
                         "fc3504f64c7e283cb53fbb8801c99e3bd9065e1fb0bc19ae73a66b8f7e4b5875")

    def test_v6_parameters_are_novel_macro_controls(self):
        self.assertIn("side_budget",policy.DEFAULT)
        self.assertIn("contact_probe_period",policy.DEFAULT)
        self.assertIn("align_budget",policy.DEFAULT)
        self.assertNotIn("COLLISION_CLEARANCE",policy.DEFAULT)

    def test_bad_weights_rejected(self):
        with self.assertRaisesRegex(ValueError,"SCHEMA"):
            policy.validate_weights({**policy.DEFAULT,"hidden_obstacle_phase":.5})
        with self.assertRaisesRegex(ValueError,"INVALID_INTEGER"):
            policy.validate_weights({**policy.DEFAULT,"side_budget":math.nan})
        with self.assertRaisesRegex(ValueError,"INVALID_FLOAT"):
            policy.validate_weights({**policy.DEFAULT,"desired_lane_y":math.inf})

    def test_shield_deadman_forces_abstain(self):
        p=policy.CorridorContactController(policy.DEFAULT)
        a=p(observation(),np.asarray([False]*6+[True]))
        self.assertEqual(a,6)
        self.assertEqual(p.phase,"deadman_or_unhealthy_shield")

    def test_input_abi_and_mask_preserved(self):
        p=policy.CorridorContactController(policy.DEFAULT)
        mask=np.ones(7,bool)
        before=mask.copy()
        self.assertIn(p(observation(),mask),range(7))
        np.testing.assert_array_equal(mask,before)
        with self.assertRaisesRegex(ValueError,"ABI"):
            p(np.zeros(17),mask)

    def test_observed_center_starts_contact_setup_not_immediate_abstain(self):
        p=policy.CorridorContactController(policy.DEFAULT)
        mask=np.ones(7,bool)
        first=p(observation(obstacle_y=.065),mask)
        self.assertEqual(first,0)  # ALIGN first, unlike v4/v5 early side+abort
        self.assertEqual(p.phase,"align_for_lateral_contact")
        # Next visible position is already aligned; stage now tries side3.
        second=p(observation(obstacle_y=.065,pusher_x=-.04),mask)
        self.assertEqual(second,3)
        self.assertEqual(p.phase,"shallow_side_contact")

    def test_clear_path_uses_exact_v5_controller_for_entire_episode(self):
        p=policy.CorridorContactController(policy.DEFAULT)
        with patch.object(policy.LearnedSweptController,"__call__",return_value=2) as frozen:
            self.assertEqual(p(observation(obstacle_y=.15),np.ones(7,bool)),2)
            self.assertEqual(p.route_mode,"clear_v5")
            # Even if visible obstacle oscillates later, chosen clear route
            # must continue delegating to frozen v5, preserving clear wins.
            self.assertEqual(p(observation(obstacle_y=.10),np.ones(7,bool)),2)
        self.assertEqual(frozen.call_count,2)

    def test_retreat_is_not_a_noop(self):
        self.assertEqual(run.v5.v4.v3.v2.v1.SEED_BANDS["test"],(329000,329199))
        self.assertFalse(policy.CorridorContactController(policy.DEFAULT)._pusher_path_safe(
            observation(obstacle_y=.0,object_x=.09,pusher_x=.09),5))

    def test_train_only_seed_range_inside_real_frozen_env(self):
        self.assertEqual((run.TRAIN_FIRST_SEED,run.NEXT_TRAIN_SEED),(511000,512000))
        self.assertTrue(120000<=run.TRAIN_FIRST_SEED<520000)
        self.assertLess(run.NEXT_TRAIN_SEED+999,520000)
        self.assertGreater(run.TRAIN_FIRST_SEED,run.v5.v4.v3.v2.v1.SEED_BANDS["ood"][1])

    def test_invalid_train_domain_fails_closed(self):
        args=run.parse_args(["--mode","train-dev","--expected-head","a"*40,
                             "--output-dir","/tmp/none"])
        with patch.object(run,"TRAIN_FIRST_SEED",5290000):
            with self.assertRaisesRegex(ValueError,"TRAIN_SEED_DOMAIN"):
                run.validate_args(args)

    def test_dev_is_fresh_once_only(self):
        self.assertEqual((run.DEV_FIRST_SEED,run.DEV_LAST_SEED),(129250,129329))
        args=run.parse_args(["--mode","train-dev","--expected-head","a"*40,
                             "--dev-episodes","81","--output-dir","/tmp/none"])
        with self.assertRaisesRegex(ValueError,"DEV_EPISODES"):
            run.validate_args(args)

    def test_no_holdout_cli_or_autodiff_mode(self):
        with self.assertRaises(SystemExit):
            run.parse_args(["--mode","locked_test","--expected-head","a"*40,
                            "--output-dir","/tmp/none"])

    def test_clean_sha_and_immutable_v5_ancestry_required(self):
        self.assertEqual(run.V5_SHA,"4987f28540c5319deaa81dff5d700dcac9eab483")
        with self.assertRaises(PermissionError):
            run.source_identity(False,"a"*40)
        with patch.object(run.subprocess,"check_output",side_effect=["/tmp/source\n","a"*40+"\n",""]), \
             patch.object(run.subprocess,"run",return_value=SimpleNamespace(returncode=1)) as ancestor:
            with self.assertRaisesRegex(RuntimeError,"NOT_DESCENDED"):
                run.source_identity(True,"a"*40)
        self.assertIn(run.V5_SHA,ancestor.call_args.args[0])

    def test_optimizer_evaluates_six_real_candidate_stubs(self):
        def fake_episode(_,seed,weights):
            return dict(seed=seed,success=False,unsafe=False,abstained=False,
                        total_reward=weights["side_budget"]*.01,
                        transitions=[dict(reward=1)],
                        side_action_trace=["APPROACH_LEFT"])
        with patch.object(run,"training_episode",side_effect=fake_episode) as called:
            result=run.learn(object(),2,time.monotonic()+5)
        self.assertEqual(len(result["experiments"]),6)
        self.assertEqual(called.call_count,12)
        self.assertEqual(result["seeds"],[511000,511001])
        self.assertEqual(result["selected"]["objective"],
                         max(e["objective"] for e in result["experiments"]))

    def test_curriculum_uses_training_traces_only(self):
        rows=[dict(success=False,unsafe=False,abstained=True,
                   side_action_trace=["APPROACH_LEFT","APPROACH_LEFT"],
                   transitions=[dict(reward=-1)]),
              dict(success=False,unsafe=True,abstained=False,
                   side_action_trace=["APPROACH_RIGHT"],transitions=[dict(reward=-1)])]
        t=run.failure_taxonomy(rows)
        self.assertEqual(t["side_action_trace_counts"],
                         {"APPROACH_LEFT":2,"APPROACH_RIGHT":1})
        self.assertEqual(t["curriculum_next"]["train_first_seed"],512000)
        self.assertFalse(t["curriculum_next"]["auto_dispatch"])

    def test_gate_prohibits_any_v5_success_regression(self):
        worlds=[dict(learned_v5={"success":True,"unsafe":False},
                     learned_v6={"success":False,"unsafe":False})]
        s={"learned_v6":dict(delta_success_percentage_points=10,
                              paired_bootstrap95_pp=[1,20],
                              candidate_success=10,constant_success=9,
                              candidate_unsafe=0,constant_unsafe=0),
           "learned_v5":dict(candidate_success=9)}
        gate=run.scientific_gate(worlds,s,[dict(observed_corridor=True)])
        self.assertFalse(gate["scientifically_qualifies"])
        self.assertEqual(gate["lost_v5_successes"],1)

    def test_gate_preserves_unsafe_and_paired_ci(self):
        worlds=[dict(learned_v5={"success":False,"unsafe":False},
                     learned_v6={"success":True,"unsafe":True})]
        s={"learned_v6":dict(delta_success_percentage_points=10,
                              paired_bootstrap95_pp=[1,20],
                              candidate_success=10,constant_success=9,
                              candidate_unsafe=1,constant_unsafe=1),
           "learned_v5":dict(candidate_success=9)}
        gate=run.scientific_gate(worlds,s,[dict(observed_corridor=True)])
        self.assertFalse(gate["scientifically_qualifies"])
        self.assertFalse(gate["no_unsafe_regression_vs_v5"])
        self.assertEqual(gate["observed_corridor_new_wins"],1)

    def test_hash_uses_exact_sorted_compact_json(self):
        self.assertEqual(run.digest({"a":1,"b":2}),run.digest({"b":2,"a":1}))
        self.assertNotEqual(run.digest([1,2]),run.digest([2,1]))


if __name__=="__main__":
    unittest.main()
