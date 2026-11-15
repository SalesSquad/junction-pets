import math
import unittest

import numpy as np

from evaluation import exact_upper, measure_policy, calibrate_policy, paired_family_bootstrap


class EvaluationTest(unittest.TestCase):
    def test_exact_binomial_bounds(self):
        self.assertAlmostEqual(exact_upper(0, 400), 1 - .05**(1/400), places=14)
        self.assertAlmostEqual(exact_upper(1, 10), 0.3941633024365047, places=13)
        self.assertEqual(exact_upper(10, 10), 1)
        self.assertGreater(exact_upper(1, 400), exact_upper(0, 400))

    def test_all_variants_and_combined_family_event(self):
        # 320 families with two tied variants: first is correct, second wrong.
        families = [str(i // 2) for i in range(640)]
        scores = np.zeros((640, 640), dtype=np.float32)
        for i in range(640):
            scores[i, (i // 2)*2:(i // 2)*2+2] = 1
        result = measure_policy(scores, families, .5)
        self.assertEqual(result['wrong_present_accepted'], 320)
        self.assertEqual(result['combined_families_with_any_error'], 320)
        self.assertEqual(result['combined_family_error_upper95'], 1)
        policy = calibrate_policy(scores, families)
        self.assertEqual(policy['calibration']['accepted'], 0)

    def test_present_and_absent_union_counts_family_once(self):
        families = [str(i) for i in range(400)]
        scores = np.eye(400, dtype=np.float32)
        scores[0,1] = 1.1
        result = measure_policy(scores, families, 1)
        self.assertEqual(result['present_families_with_any_error'], 1)
        self.assertEqual(result['absent_families_with_any_error'], 1)
        self.assertEqual(result['combined_families_with_any_error'], 1)

    def test_perfect_candidate_and_identity_bootstrap(self):
        scores = np.eye(400, dtype=np.float32)
        families = [str(i) for i in range(400)]
        policy = calibrate_policy(scores, families)
        measured = measure_policy(scores, families, policy['threshold'])
        self.assertEqual(measured['coverage'], 1)
        self.assertLess(measured['combined_family_error_upper95'], .01)
        paired = paired_family_bootstrap(scores, scores, families, resamples=50)
        self.assertEqual(paired['interval95'], [0, 0])
        self.assertFalse(paired['superiority_supported_by_interval'])

    def test_missing_family_sample_cannot_certify(self):
        scores = np.eye(200, dtype=np.float32)
        policy = calibrate_policy(scores, [str(i) for i in range(200)])
        self.assertIsNone(policy['threshold'])
        self.assertEqual(policy['calibration']['coverage'], 0)
        self.assertGreater(policy['calibration']['combined_family_error_upper95'], .01)


if __name__ == '__main__':
    unittest.main()
