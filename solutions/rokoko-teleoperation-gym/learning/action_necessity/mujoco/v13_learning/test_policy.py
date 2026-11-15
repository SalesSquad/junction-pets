import unittest
from unittest.mock import patch

import policy
v12 = policy.v12


def observation(distance=.15):
    o = [0.] * 18
    o[7] = .05
    o[16] = distance
    return o


def model():
    return {"frozenV11GateParameters": {"kind": "blocked_or_abstain_side",
            "min_distance": .035, "obstacle_limit": .1, "min_streak": 1},
            "models": {str(a): {"supported": a in (1, 2, 3, 5)} for a in range(7)}}


def abstain_factory():
    return lambda obs, mask: 6


class V13PolicyTest(unittest.TestCase):
    def setUp(self):
        self.p = policy.ContinueAfterReopen(abstain_factory, model())
        self.scorer = patch.object(v12, "model_score", side_effect=lambda o,m,p,a,mod,s: a)
        self.scorer.start()
        self.addCleanup(self.scorer.stop)

    def test_continues_on_reopening_but_never_selects_illegal(self):
        self.assertEqual(self.p(observation(), [0,0,0,1,0,0,1]), 3)
        self.assertEqual(self.p(observation(), [0,1,0,0,0,0,1]), 1)
        self.assertEqual(self.p.mode_history[-1], "v13_continuation_unqualified")

    def test_rescue_cap_and_no_second_round(self):
        m = [0,0,0,1,0,0,1]
        for _ in range(v12.MAX_RESCUE_OPTIONS):
            self.assertEqual(self.p(observation(), m), 3)
        self.assertEqual(self.p(observation(), m), 6)
        self.assertEqual(self.p(observation(), m), 6)

    def test_no_override_when_only_abstain_legal_or_model_unsupported(self):
        self.assertEqual(self.p(observation(), [0,0,0,1,0,0,1]), 3)
        self.assertEqual(self.p(observation(), [0,0,0,0,1,0,1]), 6)
        self.assertFalse(self.p.rescue_active)

    def test_near_goal_returns_to_baseline(self):
        self.assertEqual(self.p(observation(), [0,0,0,1,0,0,1]), 3)
        self.assertEqual(self.p(observation(.03), [0,1,0,1,0,0,1]), 6)

    def test_bad_abi_fails_closed(self):
        with self.assertRaises(v12.V12ContractStop):
            self.p([float('nan')]*18, [0,0,0,1,0,0,1])

    def test_baseline_when_gate_does_not_fire(self):
        self.assertEqual(self.p(observation(.03), [0,1,0,1,0,0,1]), 6)
        self.assertEqual(self.p.mode_history, ["frozen_v5"])

if __name__ == '__main__':
    unittest.main()
