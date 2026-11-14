import math
import unittest

import fakes  # noqa: F401
import risk


class Binomial(unittest.TestCase):
    def test_cdf_matches_direct_sum(self):
        for n, p in ((1, 0.3), (12, 0.05), (59, 0.05), (300, 0.01)):
            for k in (0, 1, n // 3, n - 1):
                direct = sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))
                self.assertAlmostEqual(risk.binom_cdf(k, n, p), direct, places=10)
        self.assertEqual(risk.binom_cdf(-1, 10, 0.5), 0.0)
        self.assertEqual(risk.binom_cdf(10, 10, 0.5), 1.0)

    def test_minimum_number_of_accepted_notes(self):
        self.assertEqual(risk.min_accepted(0.05, 0.05), 59)
        self.assertEqual(risk.min_accepted(0.01, 0.05), 299)
        self.assertLessEqual(risk.binom_cdf(0, 59, 0.05), 0.05)
        self.assertGreater(risk.binom_cdf(0, 58, 0.05), 0.05)

    def test_upper_bound_inverts_the_tail(self):
        for k, n in ((0, 59), (3, 200), (10, 500)):
            upper = risk.clopper_pearson_upper(k, n, 0.05)
            self.assertAlmostEqual(risk.binom_cdf(k, n, upper), 0.05, places=6)
        self.assertLessEqual(risk.clopper_pearson_upper(0, 59, 0.05), 0.05)
        self.assertEqual(risk.clopper_pearson_upper(5, 5), 1.0)

    def test_grid_is_fixed_and_descending(self):
        grid = risk.default_grid()
        self.assertEqual(grid, sorted(grid, reverse=True))
        self.assertEqual(grid[-1], risk.ACCEPT_ALL)
        self.assertEqual(len(grid), 61)
        self.assertEqual(grid, risk.default_grid())  # no dependence on data or randomness


class Threshold(unittest.TestCase):
    def test_too_few_notes_certifies_nothing(self):
        fit = risk.ltt_threshold([-0.01] * 58, [False] * 58, alpha=0.05)
        self.assertIsNone(fit["threshold"])
        self.assertIn("too small", fit["reason"])
        self.assertEqual(fit["n_min_accepted"], 59)

    def test_clean_calibration_set_is_accepted_whole(self):
        fit = risk.ltt_threshold([-0.01] * 300, [False] * 300, alpha=0.05)
        self.assertEqual((fit["n_accepted"], fit["errors_accepted"], fit["coverage"]), (300, 0, 1.0))
        self.assertLessEqual(fit["risk_upper_bound"], 0.05)
        self.assertEqual(fit["reason"], "certified")

    def test_threshold_separates_confident_from_unconfident(self):
        scores = [-0.0001] * 200 + [-1.0] * 100
        errors = [False] * 200 + [True] * 100
        for method in ("fixed_sequence", "bonferroni"):
            fit = risk.ltt_threshold(scores, errors, alpha=0.05, method=method)
            self.assertEqual((fit["n_accepted"], fit["errors_accepted"]), (200, 0), method)
            stats = risk.selective_stats(scores, errors, fit["threshold"])
            self.assertEqual((stats["accepted"], stats["errors_accepted"], stats["risk"]), (200, 0, 0.0))

    def test_unparsable_outputs_are_never_accepted(self):
        scores = [-0.001] * 100 + [None] * 50
        errors = [False] * 100 + [True] * 50
        fit = risk.ltt_threshold(scores, errors, alpha=0.05)
        self.assertEqual(fit["n_accepted"], 100)
        self.assertEqual(fit["n_parsable"], 100)
        self.assertAlmostEqual(fit["coverage"], 100 / 150)
        self.assertEqual(risk.selective_stats(scores, errors, risk.ACCEPT_ALL)["accepted"], 100)

    def test_errors_among_the_most_confident_block_the_sequence(self):
        scores = [-1e-7] * 60 + [-0.01] * 240
        errors = [True] * 30 + [False] * 270
        self.assertIsNone(risk.ltt_threshold(scores, errors, alpha=0.05)["threshold"])

    def test_no_threshold_means_nothing_is_accepted(self):
        stats = risk.selective_stats([-0.1, -0.2], [False, True], None)
        self.assertEqual((stats["accepted"], stats["coverage"], stats["risk"]), (0, 0.0, None))

    def test_report_structure(self):
        scores = [-0.0001] * 320 + [-2.0] * 80
        errors = [False] * 320 + [True] * 80
        report = risk.calibrate_and_check(scores, errors, {"test": (scores[:100] + scores[-20:], errors[:100] + errors[-20:])})
        self.assertEqual(len(report["results"]), 4)  # two alphas x two methods
        self.assertEqual({r["alpha"] for r in report["results"]}, {0.01, 0.05})
        strict = next(r for r in report["results"] if r["alpha"] == 0.01 and r["method"] == "fixed_sequence")
        self.assertEqual(strict["calibration"]["n_accepted"], 320)  # 320 >= 299 notes without error
        self.assertEqual(strict["checks"]["test"]["accepted"], 100)
        self.assertTrue(strict["checks"]["test"]["risk_at_most_alpha"])
        self.assertAlmostEqual(report["calibration_error_rate"], 0.2)


class Guarantee(unittest.TestCase):
    """On synthetic exchangeable data the chosen threshold must have true risk <= alpha in at least
    95% of calibration draws. The bound allows three standard errors of Monte Carlo noise."""

    TRIALS = 600
    N = 400

    def test_violation_rate_stays_below_delta(self):
        bound = risk.monte_carlo_bound(risk.DELTA, self.TRIALS)
        for scenario in risk.SCENARIOS:
            for alpha in risk.ALPHAS:
                for row in risk.simulate(scenario, alpha, n=self.N, trials=self.TRIALS, seed=20261114):
                    with self.subTest(scenario=scenario, alpha=alpha, method=row["method"]):
                        self.assertLessEqual(row["violation_rate"], bound)

    def test_the_procedure_is_not_vacuous(self):
        rows = risk.simulate("informative", 0.05, n=self.N, trials=200, seed=1)
        found = {r["method"]: 1 - r["no_threshold"] / r["trials"] for r in rows}
        self.assertGreater(found["fixed_sequence"], 0.3)
        coverage = next(r["mean_coverage_when_found"] for r in rows if r["method"] == "fixed_sequence")
        self.assertGreater(coverage, 0.2)

    def test_uninformative_confidence_is_almost_never_certified(self):
        rows = risk.simulate("uninformative", 0.05, n=self.N, trials=300, seed=2)
        for row in rows:
            self.assertGreater(row["no_threshold"] / row["trials"], 0.9)

    def test_true_risk_integral(self):
        self.assertAlmostEqual(risk.true_risk(risk.SCENARIOS["uninformative"], risk.ACCEPT_ALL), 0.08, places=9)
        self.assertIsNone(risk.true_risk(risk.SCENARIOS["informative"], math.log1p(-(10**-5))))
        top = risk.true_risk(risk.SCENARIOS["informative"], math.log1p(-(10**-3)))
        everything = risk.true_risk(risk.SCENARIOS["informative"], risk.ACCEPT_ALL)
        self.assertLess(top, 0.05)
        self.assertGreater(everything, 0.05)


if __name__ == "__main__":
    unittest.main()
