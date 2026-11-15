"""Bounded v2 contract tests: do not touch sealed test/OOD seed ranges."""

import unittest

from arena import Arena,make_world
from v2_policy import (DAGGER_TRAIN_BASE,TEACHER_TRAIN_BASE,TEACHER_WORLDS,
                       DAGGER_WORLDS,FIT_SEED,FEATURE_COUNT,FittedForest,features,
                       fit_forest,gather_training_worlds)
from v2_run import SCORE_SPLITS,evaluate


class NonlinearCloneTests(unittest.TestCase):
    def test_sealed_ranges_nonoverlap(self):
        self.assertEqual(SCORE_SPLITS["locked_test"],("test",326000,300))
        self.assertEqual(SCORE_SPLITS["locked_ood"],("ood",426000,200))
        self.assertGreaterEqual(TEACHER_TRAIN_BASE,123000)
        self.assertLess(TEACHER_TRAIN_BASE+TEACHER_WORLDS,DAGGER_TRAIN_BASE+1)
        self.assertLess(DAGGER_TRAIN_BASE+DAGGER_WORLDS,124000)

    def test_features_do_not_expose_hidden_dynamics(self):
        obs=Arena(make_world("dev",123001)).observe()
        self.assertEqual(len(features(obs,obs.moving_y)),FEATURE_COUNT)
        self.assertFalse(hasattr(obs,"friction"))
        self.assertFalse(hasattr(obs,"seed"))

    def test_fitted_tree_is_nonconstant_and_deterministic(self):
        examples,_=gather_training_worlds(123000,4)
        model=fit_forest(examples,FIT_SEED)
        self.assertEqual(model.digest(),fit_forest(examples,FIT_SEED).digest())
        self.assertTrue(model.trees)
        obs=Arena(make_world("dev",124010)).observe()
        self.assertEqual(FittedForest(model.trees)(obs),FittedForest(model.trees)(obs))

    def test_no_locked_partial_score_admission(self):
        examples,_=gather_training_worlds(123020,2)
        model=fit_forest(examples,FIT_SEED)
        with self.assertRaises(ValueError):
            evaluate(model,"locked_test",1)
        with self.assertRaises(ValueError):
            evaluate(model,"locked_ood",1)

    def test_only_dev_cal_smoke(self):
        examples,_=gather_training_worlds(123030,2)
        model=fit_forest(examples,FIT_SEED)
        result=evaluate(model,"cal",2)
        self.assertEqual(result["episodes"],2)
        self.assertEqual(result["world_seed_range"],[221000,221001])
        self.assertFalse(result["toy_acceptance"])


if __name__=="__main__":
    unittest.main()
