"""V7 portable evidence/strategy contracts; no synthetic MuJoCo PASS claim."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

spec=importlib.util.spec_from_file_location("rokoko_v7_feasibility_contract",Path(__file__).with_name("run.py"))
assert spec is not None and spec.loader is not None
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def observation(near=True):
    x=np.zeros(18,dtype=np.float32)
    x[6:8]=.09,.065 if near else .15
    x[9:12]=.99,1.,1.
    x[16:18]=.16,0.
    return x


class FeasibilityContracts(unittest.TestCase):
    def test_real_v6_frozen_weights_sha(self):
        self.assertEqual(run.digest(run.FROZEN_V6_WEIGHTS),
                         "ce00c75b40f508713011e522643910cc41cb2c900324e09275d5ae46ff077578")

    def test_v5_and_v6_are_distinct_frozen_strategies(self):
        self.assertEqual(len(run.STRATEGIES),8)
        self.assertEqual(run.STRATEGIES[:2],("frozen_v5","frozen_v6"))
        self.assertIsNot(type(run.policy_factory("frozen_v5")()),
                         type(run.policy_factory("frozen_v6")()))

    def test_six_new_macros_declared_at_source(self):
        self.assertEqual(len(set(run.STRATEGIES[2:])),6)
        self.assertIn("observed_branch",run.STRATEGIES)

    def test_unknown_strategy_denied(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN"):
            run.ExploratoryMacro("hidden_oracle")
        with self.assertRaisesRegex(ValueError,"NONREGISTERED"):
            run.policy_factory("human_mystery")

    def test_mask_deadman_abstain_for_all_six_macros(self):
        mask=np.asarray([False]*6+[True])
        for name in run.STRATEGIES[2:]:
            with self.subTest(name=name):
                self.assertEqual(run.ExploratoryMacro(name)(observation(),mask),6)

    def test_no_macro_bypasses_mask(self):
        for name in run.STRATEGIES[2:]:
            controller=run.ExploratoryMacro(name)
            for preferred in range(6):
                mask=np.asarray([False]*6+[True])
                mask[preferred]=True
                before=mask.copy()
                action=controller(observation(),mask)
                self.assertTrue(mask[action])
                np.testing.assert_array_equal(before,mask)

    def test_input_ABI_enforced(self):
        p=run.ExploratoryMacro("repeat_left")
        with self.assertRaisesRegex(ValueError,"18D"):
            p(np.zeros(17),np.ones(7,bool))
        with self.assertRaisesRegex(ValueError,"7MASK"):
            p(np.zeros(18),np.ones(8,bool))

    def test_repeat_left_initial_option(self):
        p=run.ExploratoryMacro("repeat_left")
        self.assertEqual(p(observation(),np.ones(7,bool)),3)

    def test_repeat_right_initial_option(self):
        p=run.ExploratoryMacro("repeat_right")
        self.assertEqual(p(observation(),np.ones(7,bool)),4)

    def test_align_then_side_is_not_threshold_tuning(self):
        p=run.ExploratoryMacro("align_left")
        self.assertEqual([p(observation(),np.ones(7,bool)) for _ in range(3)],
                         [0,0,3])

    def test_retreat_is_actuation_not_hold(self):
        p=run.ExploratoryMacro("retreat_left")
        self.assertEqual(p(observation(),np.ones(7,bool)),5)

    def test_branch_observes_map_sign(self):
        left=run.ExploratoryMacro("observed_branch")
        right=run.ExploratoryMacro("observed_branch")
        for _ in range(2):
            left(observation(True),np.ones(7,bool))
            minus=observation(True);minus[7]=-.065
            right(minus,np.ones(7,bool))
        self.assertEqual(left(observation(True),np.ones(7,bool)),3)
        minus=observation(True);minus[7]=-.065
        self.assertEqual(right(minus,np.ones(7,bool)),4)

    def test_train_seed_reservation_valid_frozen_domain(self):
        self.assertTrue(120000<=run.FIRST_SEED<run.FIRST_SEED+512<520000)
        self.assertEqual((run.FIRST_SEED,run.NEXT_TRAIN_SEED),(512000,513000))
        self.assertGreater(run.FIRST_SEED,run.v6.v5.v4.v3.v2.v1.SEED_BANDS["ood"][1])

    def test_out_of_env_seed_regression_fails_closed(self):
        args=run.parse_args(["--mode","train-feasibility", "--expected-head","a"*40,
                             "--output-dir","/tmp/unused"])
        with patch.object(run,"FIRST_SEED",5290000):
            with self.assertRaisesRegex(ValueError,"SEED_DOMAIN"):
                run.validate_args(args)

    def test_cli_cannot_open_holdout(self):
        with self.assertRaises(SystemExit):
            run.parse_args(["--mode","locked_test", "--expected-head","a"*40,
                            "--output-dir","/tmp/unused"])

    def test_selection_limit_above512_rejected(self):
        args=run.parse_args(["--mode","train-feasibility","--expected-head","a"*40,
                             "--max-seeds","513","--output-dir","/tmp/unused"])
        with self.assertRaisesRegex(ValueError,"SELECTION_LIMIT"):
            run.validate_args(args)

    def test_clean_exact_git_and_immutable_v6_ancestry(self):
        self.assertEqual(run.V6_SHA,"0fcf7fe87e6169aa383807ec8616cc6f98694aca")
        with self.assertRaises(PermissionError):
            run.source_identity(False,"a"*40)
        with patch.object(run.subprocess,"check_output",side_effect=["/tmp/src\n","a"*40+"\n",""]), \
             patch.object(run.subprocess,"run",return_value=SimpleNamespace(returncode=1)) as ancestry:
            with self.assertRaisesRegex(RuntimeError,"NOT_DESCENDED"):
                run.source_identity(True,"a"*40)
        self.assertIn(run.V6_SHA,ancestry.call_args.args[0])

    def test_sparse_indices_exact_contract(self):
        for n in (1,6,10,12,24,60):
            expected=sorted(set(range(min(12,n))) |
                            set(range(max(0,n-8),n)) |
                            set(range(0,n,5)))
            self.assertEqual(run.sparse_indices(n),expected)

    def test_all_8_strategies_pair_exact_same_160_worlds(self):
        near=[dict(seed=512000+i) for i in range(128)]
        clear=[dict(seed=512200+i) for i in range(32)]
        schedule=run.scheduled_trials(near,clear)
        self.assertEqual(len(schedule),1280)
        self.assertEqual({x["seed"] for x,_,_ in schedule},
                         {x["seed"] for x in near+clear})
        for seed in {x["seed"] for x in near+clear}:
            self.assertEqual({s for row,s,_ in schedule if row["seed"]==seed},
                             set(run.STRATEGIES))

    def test_first_public_observation_selects_near_and_clear(self):
        class FakeEnv:
            def reset(self,seed,ood):
                return observation(near=seed%3==0)
        fake=FakeEnv()
        with patch.object(run.v6.v5.v4.v3.v2.v1,"_world_signature",return_value="fixed"):
            near,clear,scan=run.select_train_worlds(fake,512)
        self.assertEqual((len(near),len(clear)),(128,32))
        self.assertEqual([r["seed"] for r in scan],
                         list(range(512000,512000+len(scan))))
        self.assertEqual(len({r["seed"] for r in near+clear}),160)
        self.assertEqual({r["world_hash"] for r in scan},{"fixed"})

    def test_advisory_zero_success_not_impossibility(self):
        row=dict(strategy="repeat_left",observed_corridor=True,
                 success=False,unsafe=False,abstained=True,contacts=0,
                 away_lateral_displacement=.009,
                 forward_reopened_after_side=0)
        q=run.assess([row],[dict(seed=1)],[dict(seed=2)])
        self.assertFalse(q["mechanism_positive"])
        self.assertFalse(q["promotion_authorized"])
        self.assertIn("NOT a mathematical impossibility proof",q["scientific_interpretation"])
        self.assertTrue(run.next_experiment(q)["no_auto_env_change"])

    def test_positive_mechanism_still_not_promotion(self):
        row=dict(seed=512000,strategy="repeat_left",observed_corridor=True,
                 success=True,unsafe=False,abstained=False,contacts=2,
                 away_lateral_displacement=.03,
                 forward_reopened_after_side=1)
        q=run.assess([row],[dict(seed=512000)],[dict(seed=512001)])
        self.assertTrue(q["mechanism_positive"])
        self.assertFalse(q["promotion_authorized"])
        self.assertTrue(q["at_least_one_safe_lateral_ge_025"])

    def test_dataset_sha_canonical_exact(self):
        self.assertEqual(run.digest({"a":1,"b":2}),run.digest({"b":2,"a":1}))
        self.assertNotEqual(run.digest([1,2]),run.digest([2,1]))

    def test_signed_away_is_positive_only_from_public_obstacle_side(self):
        first=observation();first[1]=0.;first[7]=.065
        last=first.copy();last[1]=-.03
        self.assertAlmostEqual(run.signed_obstacle_away_displacement(first,last),.03)
        last[1]=.03
        self.assertAlmostEqual(run.signed_obstacle_away_displacement(first,last),-.03)
        first[7]=-.065
        self.assertAlmostEqual(run.signed_obstacle_away_displacement(first,last),.03)
        self.assertAlmostEqual(run.signed_obstacle_away_displacement(first,first),0.)

    def test_contact_trace_cumulative_from_actual_infos(self):
        full=[dict(action=3,contacts_cumulative=1),
              dict(action=3,contacts_cumulative=2),
              dict(action=1,contacts_cumulative=2)]
        run.verify_contact_trace(full,2)
        with self.assertRaisesRegex(ValueError,"TERMINAL_TOTAL"):
            run.verify_contact_trace(full,3)
        with self.assertRaisesRegex(ValueError,"NOT_MONOTONE"):
            run.verify_contact_trace(full+[dict(action=0,contacts_cumulative=1)],1)

    def test_contact_trace_missing_raw_field_is_rejected(self):
        with self.assertRaises(KeyError):
            run.verify_contact_trace([dict(action=3)],1)


if __name__=="__main__":
    unittest.main()
