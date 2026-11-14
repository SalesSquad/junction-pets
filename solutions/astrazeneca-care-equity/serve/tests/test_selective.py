"""serve/selective.py: exact binomial tail and the Learn-then-Test threshold."""

import contextlib
import fractions
import io
import json
import math
import os
import tempfile
import unittest

import support  # noqa: F401
import client
import selective


def exact_cdf(k, n, p):
    p = fractions.Fraction(p)
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1)))


class Binomial(unittest.TestCase):
    def test_cdf_equals_exact_rational_sum(self):
        for n, k, p in [(1, 0, "0.05"), (10, 0, "0.05"), (10, 3, "0.3"), (45, 0, "0.05"), (200, 4, "0.05"),
                        (500, 12, "0.05"), (1000, 37, "0.05"), (60, 2, "0.0333"), (7, 7, "0.5"), (7, 6, "0.5")]:
            self.assertAlmostEqual(selective.binom_cdf(k, n, float(fractions.Fraction(p))), exact_cdf(k, n, p), places=12)

    def test_edges(self):
        self.assertEqual(selective.binom_cdf(-1, 5, 0.3), 0.0)
        self.assertEqual(selective.binom_cdf(5, 5, 0.3), 1.0)
        self.assertEqual(selective.binom_cdf(0, 0, 0.3), 1.0)
        self.assertEqual(selective.binom_cdf(2, 5, 0.0), 1.0)
        self.assertEqual(selective.binom_cdf(2, 5, 1.0), 0.0)
        with self.assertRaises(ValueError):
            selective.binom_cdf(1, 5, 1.5)

    def test_zero_error_minimum(self):
        self.assertEqual(selective.min_accepted_for_zero_errors(0.05, 0.1), 45)
        self.assertLessEqual(0.95**45, 0.1)
        self.assertGreater(0.95**44, 0.1)

    def test_clopper_pearson_upper_is_the_test_boundary(self):
        for k, n, delta in [(0, 45, 0.1), (3, 200, 0.1), (10, 400, 0.05), (0, 10, 0.1)]:
            upper = selective.clopper_pearson_upper(k, n, delta)
            self.assertAlmostEqual(selective.binom_cdf(k, n, upper), delta, places=9)
            # p-value <= delta exactly when the upper bound is <= alpha
            for alpha in (upper * 0.99, upper * 1.01):
                self.assertEqual(selective.binom_cdf(k, n, alpha) <= delta, upper <= alpha)
        self.assertEqual(selective.clopper_pearson_upper(0, 0, 0.1), 1.0)
        self.assertAlmostEqual(selective.clopper_pearson_upper(0, 45, 0.1), 1 - 0.1 ** (1 / 45), places=9)


class LearnThenTest(unittest.TestCase):
    def test_45_clean_notes_certify_and_44_do_not(self):
        grid = [0.9, 0.8]
        ok = selective.ltt_threshold([0.95] * 45, [0] * 45, 0.05, 0.1, grid)
        self.assertEqual(ok["threshold"], 0.8)
        self.assertEqual((ok["n_accepted"], ok["errors_accepted"]), (45, 0))
        self.assertAlmostEqual(ok["p_value"], 0.95**45)
        self.assertEqual(ok["auto_accept_fraction"], 1.0)
        no = selective.ltt_threshold([0.95] * 44, [0] * 44, 0.05, 0.1, grid)
        self.assertIsNone(no["threshold"])
        self.assertIn("human review", no["note"])

    def test_stops_at_the_first_failure_and_never_resumes(self):
        # 100 clean notes at 0.9; 100 notes at 0.7 with 30 errors; 4000 clean notes at 0.5.
        scores = [0.9] * 100 + [0.7] * 100 + [0.5] * 4000
        errors = [0] * 100 + [1] * 30 + [0] * 70 + [0] * 4000
        result = selective.ltt_threshold(scores, errors, 0.05, 0.1, [0.85, 0.65, 0.45])
        self.assertEqual(result["threshold"], 0.85)
        self.assertEqual(result["thresholds_tested"], 2)
        self.assertGreater(selective.binom_cdf(30, 200, 0.05), 0.1)  # 0.65 fails
        # 0.45 would pass on its own (30 errors in 4200), but the sequence has stopped.
        self.assertLessEqual(selective.binom_cdf(30, 4200, 0.05), 0.1)

    def test_threshold_nobody_passes_stops_the_sequence(self):
        result = selective.ltt_threshold([0.6] * 200, [0] * 200, 0.05, 0.1, [0.9, 0.5])
        self.assertIsNone(result["threshold"])
        self.assertEqual(result["thresholds_tested"], 1)

    def test_bonferroni_is_valid_but_weaker(self):
        scores, errors = [0.95] * 45, [0] * 45
        self.assertIsNone(selective.ltt_threshold(scores, errors, 0.05, 0.1, [0.9, 0.8], "bonferroni")["threshold"])
        self.assertEqual(selective.ltt_threshold([0.95] * 60, [0] * 60, 0.05, 0.1, [0.9, 0.8], "bonferroni")["threshold"], 0.8)

    def test_argument_checks(self):
        with self.assertRaises(ValueError):
            selective.ltt_threshold([0.5], [0, 1], 0.05, 0.1)
        with self.assertRaises(ValueError):
            selective.ltt_threshold([0.5], [0], 0.05, 0.1, [0.5, 0.6])
        with self.assertRaises(ValueError):
            selective.ltt_threshold([0.5], [0], 0.0, 0.1)
        grid = selective.default_grid()
        self.assertEqual((grid[0], grid[-1], len(grid)), (0.995, 0.005, 199))
        self.assertEqual(selective.default_grid(0.9, 0.1, 0.5), [0.9, 0.8, 0.7, 0.6, 0.5])
        with self.assertRaises(ValueError):
            selective.default_grid(0.5, 0.1, 0.9)

    def test_command_line_writes_a_file_the_client_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "cal.jsonl")
            out = os.path.join(tmp, "threshold.json")
            with open(results, "w", encoding="utf-8") as handle:
                for i in range(120):
                    handle.write(json.dumps({"score": 0.97, "correct": True}) + "\n")
                for i in range(40):
                    handle.write(json.dumps({"score": 0.4, "correct": i % 2 == 0}) + "\n")
            argv = [results, "--confidence-kind", "seq_prob", "--format", "absolute", "--guided", "response_format",
                    "--model", "pathway-scribe", "--calibration-set", "unit test", "--out", out,
                    "--grid-start", "0.97"]
            # With the default grid (start 0.995) nobody passes the first threshold: nothing is certified.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(selective.main(argv[:-2]), 3)
            self.assertFalse(os.path.exists(out))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selective.main(argv), 0)
            key = {"confidence_kind": "seq_prob", "format": "absolute", "guided": "response_format", "model": "pathway-scribe"}
            value, data = client.load_threshold(out, key)
            # Every threshold from 0.97 down to 0.405 accepts the same 120 clean notes; 0.4 lets
            # the 40 mixed notes in and fails. The smallest certified threshold is reported.
            self.assertEqual(value, 0.405)
            self.assertEqual((data["n_accepted"], data["errors_accepted"], data["n_calibration"]), (120, 0, 160))
            self.assertEqual(data["auto_accept_fraction"], 0.75)
            self.assertLessEqual(data["clopper_pearson_upper"], 0.05)
            # Nothing certifiable: exit 3 and no file.
            with open(results, "w", encoding="utf-8") as handle:
                for i in range(30):
                    handle.write(json.dumps({"score": 0.97, "correct": True}) + "\n")
            os.unlink(out)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(selective.main(argv), 3)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
