"""Offline tests of scribe/v3/cascade.py on a fake dataset: threshold selection, the no-test-leak guard, the judge
score, the risk-coverage area, the logistic fit and the student-choice rule. No network, no key. Run:
  scribe/.venv/bin/python -m unittest discover -s scribe/v3/tests -v
"""

import random
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import cascade  # noqa: E402


def fake_notes(n, split="val", seed=0, prefix="v"):
    rng = random.Random(seed)
    notes = []
    for i in range(n):
        x = rng.random()
        notes.append(dict(id=f"{prefix}{i}", split=split, outcome=rng.random() < x, features=dict(student=x, jev=rng.random())))
    return notes


def brute(notes, scores, alpha_pct, min_acc):
    best = None
    for t in {s for s in scores if s is not None}:
        acc = [n["outcome"] for n, s in zip(notes, scores) if s is not None and s >= t]
        w = sum(not o for o in acc)
        if len(acc) >= min_acc and 100 * w <= alpha_pct * len(acc) and (best is None or len(acc) > best[1]):
            best = (t, len(acc), w)
    return best


class Threshold(unittest.TestCase):
    def test_matches_brute_force_on_random_fake_data(self):
        for seed in range(30):
            notes = fake_notes(120, seed=seed)
            rng = random.Random(100 + seed)
            # coarse scores create ties; some notes have no score (they go to a person)
            scores = [None if rng.random() < 0.05 else round(n["features"]["student"], 1) for n in notes]
            for a in (5, 10, 30):
                for m in (1, 20):
                    got = cascade.select_threshold(notes, scores, a, test_ids=set(), min_accepted=m)
                    want = brute(notes, scores, a, m)
                    if want is None:
                        self.assertIsNone(got["threshold"])
                    else:
                        self.assertEqual((got["threshold"], got["accepted"], got["wrong"]), want)

    def test_boundary_is_exact_and_largest_coverage_wins(self):
        # 19 correct, 1 wrong, 19 correct, 2 wrong: 2 wrong in 40 is exactly 5 % and allowed; 3 in 41 is not
        outcomes = [True] * 19 + [False] + [True] * 19 + [False, False]
        notes = [dict(id=f"v{i}", split="val", outcome=o) for i, o in enumerate(outcomes)]
        scores = list(range(len(notes), 0, -1))
        got = cascade.select_threshold(notes, scores, 5, set())
        self.assertEqual((got["accepted"], got["wrong"]), (40, 2))
        self.assertEqual(got["threshold"], scores[39])
        self.assertAlmostEqual(got["coverage"], 40 / 41)
        # the error can dip back under the target: the LARGEST feasible coverage is taken, not the first one
        dip = [dict(id=f"d{i}", split="val", outcome=o) for i, o in enumerate([True, False] + [True] * 50)]
        got = cascade.select_threshold(dip, list(range(52, 0, -1)), 5, set(), min_accepted=1)
        self.assertEqual((got["accepted"], got["wrong"]), (52, 1))  # 1/2 fails, 1/20 .. 1/52 pass again
        # exactly 1 wrong in 20 is allowed at 5 %
        got = cascade.select_threshold(notes[:20], scores[:20], 5, set())
        self.assertEqual((got["accepted"], got["wrong"]), (20, 1))

    def test_ties_enter_together(self):
        notes = [dict(id=f"v{i}", split="val", outcome=o) for i, o in enumerate([True] * 25 + [False, False, True])]
        scores = [2.0] * 25 + [1.0, 1.0, 1.0]
        got = cascade.select_threshold(notes, scores, 5, set())
        self.assertEqual((got["threshold"], got["accepted"]), (2.0, 25))  # 1.0 accepts all three tied notes: 2/28 > 5 %
        got = cascade.select_threshold(notes, scores, 10, set())
        self.assertEqual((got["threshold"], got["accepted"], got["wrong"]), (1.0, 28, 2))

    def test_too_few_notes_gives_no_threshold(self):
        notes = [dict(id=f"v{i}", split="val", outcome=True) for i in range(10)]
        got = cascade.select_threshold(notes, list(range(10)), 5, set())
        self.assertIsNone(got["threshold"])
        self.assertIn("at least 20", got["reason"])

    def test_none_score_never_accepted(self):
        notes = [dict(id=f"v{i}", split="val", outcome=False) for i in range(5)] + [
            dict(id=f"w{i}", split="val", outcome=True) for i in range(30)]
        scores = [None] * 5 + [1.0] * 30
        got = cascade.select_threshold(notes, scores, 5, set())
        self.assertEqual((got["accepted"], got["wrong"], got["n"]), (30, 0, 35))
        ev = cascade.evaluate(notes, scores, got["threshold"])
        self.assertEqual(ev["coverage"]["numerator"], 30)
        self.assertEqual(ev["coverage"]["denominator"], 35)


class LeakGuard(unittest.TestCase):
    def setUp(self):
        self.val = fake_notes(60, "val", 1, "v")
        self.test = fake_notes(40, "test", 2, "t")
        self.test_ids = {n["id"] for n in self.test}

    def test_validation_only_passes(self):
        cascade.select_threshold(self.val, [n["features"]["student"] for n in self.val], 10, self.test_ids)
        cascade.fit_logistic(self.val, ("student", "jev"), self.test_ids)

    def test_test_split_is_refused(self):
        mixed = self.val + self.test[:1]
        with self.assertRaises(AssertionError):
            cascade.select_threshold(mixed, [n["features"]["student"] for n in mixed], 10, self.test_ids)
        with self.assertRaises(AssertionError):
            cascade.fit_logistic(mixed, ("student", "jev"), self.test_ids)

    def test_test_id_relabelled_as_val_is_refused(self):
        sneaky = dict(self.test[0], split="val")
        mixed = self.val + [sneaky]
        with self.assertRaises(AssertionError):
            cascade.select_threshold(mixed, [n["features"]["student"] for n in mixed], 10, self.test_ids)
        with self.assertRaises(AssertionError):
            cascade.fit_logistic(mixed, ("student",), self.test_ids)

    def test_guard_survives_python_O(self):
        code = (f"import sys; sys.path.insert(0, {str(HERE)!r}); import cascade\n"
                "try:\n cascade.assert_validation_only([dict(id='t1', split='test')], set(), 'x')\nexcept AssertionError:\n print('raised')")
        out = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.strip(), "raised", out.stderr)


class Pieces(unittest.TestCase):
    def test_judge_score(self):
        base = dict(error=None, n_events=2, claimed_route="PRIVATE", route_choice="PRIVATE",
                    probabilities=dict(event_0=0.9, event_1=0.5, unlisted=0.2, route=0.7))
        self.assertAlmostEqual(cascade.judge_score(base), 0.5 * 0.8)
        self.assertEqual(cascade.judge_score(dict(base, route_choice="EMERGENCY")), 0.0)
        self.assertAlmostEqual(cascade.judge_score(dict(base, n_events=0, probabilities=dict(unlisted=0.25, route=0.9))), 0.75)
        self.assertIsNone(cascade.judge_score(dict(base, error="HTTP 500", probabilities={})))
        self.assertIsNone(cascade.judge_score(dict(base, probabilities=dict(event_0=0.9, unlisted=0.2))))
        self.assertIsNone(cascade.judge_score(None))

    def test_aurc(self):
        # perfect order: correct, correct, wrong -> risks 0, 0, 1/3
        self.assertAlmostEqual(cascade.aurc([True, True, False], [3, 2, 1]), (0 + 0 + 1 / 3) / 3)
        # all tied: every prefix has the expected error 1/3
        self.assertAlmostEqual(cascade.aurc([True, True, False], [1, 1, 1]), 1 / 3)
        # a None score ranks last
        self.assertAlmostEqual(cascade.aurc([False, True], [None, 0.0]), (0 + 1 / 2) / 2)
        self.assertAlmostEqual(cascade.aurc_optimal([True, True, False]), (0 + 0 + 1 / 3) / 3)

    def test_logistic_orders_by_signal(self):
        notes = fake_notes(300, "val", 3)
        m = cascade.fit_logistic(notes, ("student",), set())
        self.assertGreater(m["weights"][1], 0)  # outcome probability rises with the feature in the fake data
        lo = cascade.logit(m, dict(student=0.1))
        hi = cascade.logit(m, dict(student=0.9))
        self.assertGreater(hi, lo)
        self.assertIsNone(cascade.logit(m, dict(student=None)))

    def test_choose_student(self):
        def c(run, k, n=310):
            lo, hi = cascade.wilson(k, n)
            return dict(run=run, k=k, n=n, exact_match=k / n, wilson95=[lo, hi])

        chosen, _ = cascade.choose_student([c("top", 134), c("prim", 124), c("other", 125)], "prim")
        self.assertEqual(chosen["run"], "prim")
        chosen, _ = cascade.choose_student([c("top", 200), c("prim", 124)], "prim")
        self.assertEqual(chosen["run"], "top")
        chosen, _ = cascade.choose_student([c("top", 134), c("prim", 134 - 1)], "missing")
        self.assertEqual(chosen["run"], "top")


if __name__ == "__main__":
    unittest.main()
