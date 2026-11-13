import math
import unittest

from candidate_model import (
    FEATURES,
    TEST_COUNT,
    TEST_SEED,
    VALIDATION_COUNT,
    VALIDATION_SEED,
    candidate_proposal,
    metrics,
    synthetic_examples,
    train,
)


class SyntheticCandidateModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = train()

    def test_learned_and_reproducible(self):
        self.assertGreater(sum(abs(w) for w in self.model["weights"]), 0.25)
        self.assertEqual(self.model, train())

    def test_train_validation_test_generators_differ(self):
        tr = synthetic_examples(117, 8, domain="train")
        va = synthetic_examples(VALIDATION_SEED, VALIDATION_COUNT, domain="validation")
        te = synthetic_examples(TEST_SEED, TEST_COUNT, domain="shifted_test")
        self.assertNotEqual(tr[:8], va[:8])
        self.assertNotEqual(va[:8], te[:8])
        self.assertTrue(any(x.hard_negative for x in te))

    def test_validation_false_candidate_rate_is_bounded(self):
        m = self.model["validation"]
        self.assertLessEqual(m["falseCandidateRate"], 0.05)
        self.assertGreater(m["positiveRecall"], 0.08)
        self.assertGreater(m["trueCandidate"], 0)

    def test_shifted_holdout_is_reported_not_fitted(self):
        shifted = synthetic_examples(TEST_SEED, TEST_COUNT, domain="shifted_test")
        m = metrics(self.model, shifted)
        self.assertEqual(m["total"], TEST_COUNT)
        self.assertLessEqual(m["identityVerifications"], 0)
        self.assertLessEqual(m["authorizations"], 0)
        self.assertTrue(0 <= m["falseCandidateRate"] <= 1)

    def test_output_is_only_a_proposal_and_strictly_validated(self):
        clear = dict(zip(FEATURES, [0.99, 0.99, 0.98, 0.9, 0.4]))
        proposal = candidate_proposal(self.model, clear)
        self.assertIn(proposal["kind"], ("candidate", "abstain"))
        self.assertFalse(proposal["identityVerified"])
        self.assertFalse(proposal["actionAuthorized"])
        for invalid in ({}, {**clear, "text": math.nan}, {**clear, "quality": 2.0}, {**clear, "sourceReceipt": "fake"}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                candidate_proposal(self.model, invalid)

    def test_corrupt_model_fails_closed(self):
        obs = dict(zip(FEATURES, [0.8] * len(FEATURES)))
        for edit in ({"modelKind": "privileged-identity-proof"}, {"candidate_threshold": -1}, {"weights": [1.0]}, {"bias": math.inf}):
            malformed = {**self.model, **edit}
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                candidate_proposal(malformed, obs)


if __name__ == "__main__":
    unittest.main()
