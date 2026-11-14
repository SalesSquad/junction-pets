#!/usr/bin/env python3
"""Narrow, no-MuJoCo test contract for a forensic, read-only model gate."""
import json
from pathlib import Path
import tempfile
import unittest

import audit


class QualityRecoveryTests(unittest.TestCase):
    def test_left_only_with_forward_legal_is_a_diagnostic_failure(self):
        counts = {
            "stage2_forward_legal": 3745,
            "stage2_forward_selected": 0,
            "stage2_left_selected": 3745,
        }
        health = audit.action_health(counts)
        self.assertTrue(health["degenerate_stage2"])
        self.assertEqual(health["stage2_forward_selected"], 0)
        counts["stage2_forward_selected"] = 1
        self.assertFalse(audit.action_health(counts)["degenerate_stage2"])

    def test_sparse_examples_never_count_as_mass_action_regression(self):
        counts = {
            "stage2_forward_legal": 99,
            "stage2_forward_selected": 0,
            "stage2_left_selected": 99,
        }
        self.assertFalse(audit.action_health(counts)["degenerate_stage2"])

    def test_public_state_can_select_forward_only_when_mask_allows_it(self):
        memory = audit.PublicMemory()
        obs = [0.0] * 18
        obs[7] = .10
        obs[16] = .2
        obs[17] = .2
        mask = [1, 1, 1, 1, 1, 1, 1]
        stage, _, _ = memory.features(obs, mask)
        self.assertEqual(stage, 0)
        memory.remember(3)
        second = list(obs)
        second[1] = -.02
        stage, features, legal = memory.features(second, mask)
        self.assertEqual(stage, 2)
        weights = [[0.0] * 7 for _ in range(41)]
        weights[0][1] = 2.0
        self.assertEqual(audit.action_from_weights(features, legal, weights), 1)
        illegal = list(legal)
        illegal[1] = illegal[2] = False
        self.assertNotEqual(audit.action_from_weights(features, illegal, weights), 1)

    def test_mask_and_feature_contract_fail_closed(self):
        m = audit.PublicMemory()
        with self.assertRaisesRegex(ValueError, "INVALID_PUBLIC_18D_7MASK"):
            m.features([0.0] * 17, [1] * 7)
        with self.assertRaisesRegex(ValueError, "INVALID_PUBLIC_18D_7MASK"):
            m.features([0.0] * 18, [1, 1, 1, 1, 1, 1, 2])
        with self.assertRaisesRegex(ValueError, "EMPTY_SAFETY_MASK"):
            m.features([0.0] * 18, [0] * 7)

    def test_forged_evidence_and_model_weights_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "fake.zip"
            evidence.write_bytes(b"not the exact hosted evidence")
            with self.assertRaisesRegex(ValueError, "ORIGINAL_GITHUB_ARTIFACT_SHA_MISMATCH"):
                audit.read_original(evidence)
            model = Path(folder) / "fake-model.json"
            model.write_text(json.dumps({"weights": [[[0] * 7] * 41] * 4}))
            with self.assertRaisesRegex(ValueError, "FROZEN_MODEL_FILE_SHA_MISMATCH"):
                audit.load_weights(model, audit.V8_WEIGHTS_SHA)

    def test_no_inference_from_untrusted_nonfinite_features(self):
        m = audit.PublicMemory()
        obs = [0.] * 18
        obs[5] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_PUBLIC_18D_7MASK"):
            m.features(obs, [1] * 7)
        with self.assertRaisesRegex(ValueError, "INVALID_OBSERVATION_OR_LEGAL_MASK"):
            audit.action_from_weights([0.] * 40, [True] * 7,
                                      [[0.] * 7 for _ in range(41)])

    def test_reviewer_repro_nonfinite_must_never_select_masked_action(self):
        legal = [False] + [True] * 6
        weights = [[0.] * 7 for _ in range(41)]
        with self.assertRaisesRegex(ValueError, "INVALID_OBSERVATION_OR_LEGAL_MASK"):
            audit.action_from_weights([float("nan")] + [0.] * 40,
                                      legal, weights)
        weights[0][1] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_MODEL_WEIGHT_MATRIX"):
            audit.action_from_weights([0.] * 41, legal, weights)
        weights[0][1] = 0.
        weights[0][1] = float("inf")
        with self.assertRaisesRegex(ValueError, "INVALID_MODEL_WEIGHT_MATRIX"):
            audit.action_from_weights([0.] * 41, legal, weights)
        weights[0][1] = 0.
        weights[0][1] = 1.e308
        weights[1][1] = 1.e308
        with self.assertRaisesRegex(ValueError, "NONFINITE_LEGAL_ACTION_SCORE"):
            audit.action_from_weights([1.] * 41, legal, weights)


if __name__ == "__main__":
    unittest.main()
