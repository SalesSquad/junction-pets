"""Unit tests for step 8 scoring helpers. Made-up rows only; no model, no network.

    scribe/.venv/bin/python -m unittest discover -s scribe/v4/tests -v
"""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import eval8 as E  # noqa: E402


def row(i, events, route="PRIMARY_CARE", **kw):
    r = {"id": f"r{i}", "note_text": kw.pop("text", "teksti"), "note_date": "2025-04-01", "writer": kw.pop("writer", "nemotron-3.5-super-vl"),
         "target_json": json.dumps({"entry_route": route, "events": events}), "date_forms": kw.pop("forms", [])}
    r.update(kw)
    return r


def pred(events, route="PRIMARY_CARE", flag=False, phrases=(), conf=-0.1):
    return {"pred": {"entry_route": route, "events": events}, "parse_failed": False, "flag": flag, "flag_phrases": list(phrases),
            "confidence": conf, "engine": "t"}


EV = [{"type": "REFERRAL_SENT", "date": "2025-03-01", "precision": "DAY"}, {"type": "DIAGNOSIS", "date": "2025-03-21", "precision": "DAY"}]


class TestScoring(unittest.TestCase):
    def test_date_errors(self):
        rows = [row(1, EV)]
        p = {"r1": pred([{"type": "REFERRAL_SENT", "date": "2025-03-04", "precision": "DAY"}, {"type": "DIAGNOSIS", "date": "2025-03-21", "precision": "DAY"}])}
        d = E.date_errors(rows, p)
        self.assertEqual(d["gold_events"], 2)
        self.assertEqual(d["type_missing"], 0)
        self.assertEqual(d["event_date_error"]["mean_days"], 1.5)
        self.assertEqual(d["pathway_interval_error"]["n"], 1)
        self.assertEqual(d["pathway_interval_error"]["mean_days"], 3)

    def test_date_errors_parse_failure_counts_missing(self):
        rows = [row(1, EV)]
        p = {"r1": {"pred": None, "parse_failed": True, "flag": False, "flag_phrases": [], "confidence": None, "engine": "t"}}
        d = E.date_errors(rows, p)
        self.assertEqual(d["type_missing"], 2)
        self.assertEqual(d["event_date_error"], {"n": 0})

    def test_vague_outcomes(self):
        vague = [{"type": "TREATMENT_START", "phrase": "pari viikkoa sitten"}]
        rows = [row(i, EV, has_vague=True, vague_json=json.dumps(vague)) for i in range(4)]
        extra_day = EV + [{"type": "TREATMENT_START", "date": "2025-03-18", "precision": "DAY"}]
        extra_month = EV + [{"type": "TREATMENT_START", "date": "2025-03-01", "precision": "MONTH"}]
        per = {"r0": pred(extra_day, phrases=["pari viikkoa sitten"]), "r1": pred(extra_day), "r2": pred(extra_month), "r3": pred(EV)}
        v = E.vague_outcomes(rows, per, "A'")
        self.assertEqual(v["facts"], 4)
        for k in ("sent_to_person", "invented_precise_date", "month_without_flag", "dropped"):
            self.assertEqual(v[k]["k"], 1, k)
        self.assertEqual(v["precise_part_exact"]["k"], 4)
        # Nemotron flags a note, not a phrase
        per_n = {"r0": pred(extra_day, flag=True), "r1": pred(extra_day), "r2": pred(extra_month), "r3": pred(EV)}
        self.assertEqual(E.vague_outcomes(rows, per_n, "nemotron")["sent_to_person"]["k"], 1)

    def test_compare_direction(self):
        c = E.compare("A'", [True, False, False, True], "B", [True, True, True, False])
        self.assertEqual((c["a_only_correct"], c["b_only_correct"]), (1, 2))
        self.assertEqual(c["difference_b_minus_a_points"], 25.0)

    def test_agreement_scores(self):
        rows = [row(1, EV), row(2, EV)]
        g = {"r1": pred(EV, conf=-0.2), "r2": pred(EV[:1], conf=-0.05)}
        n = {"r1": pred(EV), "r2": pred(EV)}
        sc = E.cascade_scores("agreement", rows, g, n)
        self.assertEqual([s for s, _ in sc], [1.0, None])
        sc = E.cascade_scores("agreement+gemma_confidence", rows, g, n)
        self.assertEqual([s for s, _ in sc], [-0.2, None])
        sc = E.cascade_scores("gemma_confidence_alone", rows, g, n)
        self.assertEqual([s for s, _ in sc], [-0.2, -0.05])

    def test_leak_guard_refuses_test_ids(self):
        rows = [row(i, EV) for i in range(30)]
        preds = {"A'": {r["id"]: pred(EV) for r in rows}, "B": {r["id"]: pred(EV) for r in rows},
                 "C": {r["id"]: pred(EV) for r in rows}, "nemotron": {r["id"]: pred(EV) for r in rows}}
        with self.assertRaises(AssertionError):
            E.cascade(rows, preds, rows, preds)  # test ids equal validation ids: the guard must refuse

    def test_cascade_on_validation_only(self):
        val = [row(i, EV) for i in range(30)]
        test = [row(100 + i, EV) for i in range(10)]
        good = lambda rs: {r["id"]: pred(EV) for r in rs}  # noqa: E731
        vp = {"A'": good(val), "B": good(val), "C": good(val), "nemotron": good(val)}
        tp = {"A'": good(test), "B": good(test), "C": good(test), "nemotron": good(test)}
        tp["nemotron"]["r100"] = pred(EV[:1])  # one disagreement on test
        res = E.cascade(val, vp, test, tp)
        self.assertEqual(res["chosen"], {"gemma": "A'", "signal": "agreement"})
        ch = next(c for c in res["configurations"] if c["gemma"] == "A'" and c["signal"] == "agreement")
        self.assertEqual(ch["test"]["prefilled_for_one_click_confirmation"]["k"], 9)
        self.assertEqual(ch["test"]["error_among_prefilled"]["k"], 0)

    def test_stress_slices(self):
        r = {"has_heldout": True, "has_vague": False, "kind": "standard", "distractor_heldout": False}
        self.assertTrue(E.STRESS_SLICES["heldout"](r))
        self.assertFalse(E.STRESS_SLICES["standard"](r))
        r2 = {"has_heldout": False, "has_vague": False, "kind": "no_event", "distractor_heldout": True}
        self.assertTrue(E.STRESS_SLICES["no_event_with_heldout_distractor"](r2))


if __name__ == "__main__":
    unittest.main()
