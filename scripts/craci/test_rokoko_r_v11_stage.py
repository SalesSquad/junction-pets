"""Source goal250 and chronological stage guards: synthetic data only."""
import unittest
from rokoko_r_v11_extract import terminal_goal_and_stage


def fixture():
    return {
        "success": True,
        "unsafe": False,
        "abstained": False,
        "contacts": 10,
        "dwell_ticks_final": 250,
        "final_error": 0.01,
        "forward_reopened_after_side": 0,
        "stage_funnel": {
            "contact": True,
            "signed_lateral25_after_contact": False,
            "forward_reopen_after_lateral25": False,
            "full_contact_lateral_reopen_goal_dwell": False,
            "any_forward_reopen_after_side": False,
        },
    }


class StageAndTrueGoalTests(unittest.TestCase):
    def test_clear_goal_need_not_cross_lateral_stage(self):
        actual, flags = terminal_goal_and_stage(fixture())
        self.assertTrue(actual)
        self.assertFalse(flags["full_contact_lateral_reopen_goal_dwell"])

    def test_forged_success_without_dwell_rejected(self):
        t = fixture()
        t["dwell_ticks_final"] = 0
        with self.assertRaisesRegex(ValueError, "physical goal250"):
            terminal_goal_and_stage(t)

    def test_forged_success_without_contact_rejected(self):
        t = fixture()
        t["contacts"] = 0
        with self.assertRaisesRegex(ValueError, "physical goal250"):
            terminal_goal_and_stage(t)

    def test_forged_success_too_far_rejected(self):
        t = fixture()
        t["final_error"] = 0.02
        with self.assertRaisesRegex(ValueError, "physical goal250"):
            terminal_goal_and_stage(t)

    def test_fake_false_success_rejected(self):
        t = fixture()
        t["success"] = False
        with self.assertRaisesRegex(ValueError, "physical goal250"):
            terminal_goal_and_stage(t)

    def test_nonfinite_error_rejected(self):
        t = fixture()
        t["final_error"] = float("nan")
        with self.assertRaisesRegex(ValueError, "physical distance"):
            terminal_goal_and_stage(t)

    def test_boolean_counts_not_integers(self):
        t = fixture()
        t["dwell_ticks_final"] = True
        with self.assertRaisesRegex(ValueError, "terminal dwell"):
            terminal_goal_and_stage(t)

    def test_lateral_before_contact_rejected(self):
        t = fixture()
        t["success"] = False
        t["dwell_ticks_final"] = 0
        t["stage_funnel"]["contact"] = False
        t["stage_funnel"]["signed_lateral25_after_contact"] = True
        with self.assertRaisesRegex(ValueError, "lateral-before-contact"):
            terminal_goal_and_stage(t)

    def test_forward_without_lateral_rejected(self):
        t = fixture()
        t["stage_funnel"]["forward_reopen_after_lateral25"] = True
        with self.assertRaisesRegex(ValueError, "forward-before-lateral"):
            terminal_goal_and_stage(t)

    def test_full_chain_without_goal_rejected(self):
        t = fixture()
        t["success"] = False
        t["dwell_ticks_final"] = 0
        t["stage_funnel"]["signed_lateral25_after_contact"] = True
        t["stage_funnel"]["forward_reopen_after_lateral25"] = True
        t["stage_funnel"]["full_contact_lateral_reopen_goal_dwell"] = True
        with self.assertRaisesRegex(ValueError, "without physical goal"):
            terminal_goal_and_stage(t)

    def test_proxy_count_contradiction_rejected(self):
        t = fixture()
        t["forward_reopened_after_side"] = 1
        with self.assertRaisesRegex(ValueError, "proxy contradicts"):
            terminal_goal_and_stage(t)


if __name__ == "__main__":
    unittest.main()
