"""Tests for the comparability gate (SYNTHETIC data). Run from the solution folder:
  flare/.venv/bin/python -m unittest discover -s flare/tests -v
"""
import datetime as dt
import json
import math
import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import gate as G  # noqa: E402

GATE = ROOT / "data/flare/gate-v1.json"
FORBIDDEN = ["auto-confirmed", "skips review", "clinically accurate", "works on real notes"]


class Rule(unittest.TestCase):
    def test_thresholds_are_strict_and_two_sided(self):
        self.assertTrue(G.gate(3, 0.10)["comparable"])
        self.assertTrue(G.gate(-3, 0.0)["comparable"])
        self.assertFalse(G.gate(3.5, 0.0)["comparable"])
        self.assertFalse(G.gate(-3.5, 0.0)["comparable"])
        self.assertFalse(G.gate(0, 0.1001)["comparable"])
        self.assertEqual(len(G.gate(-20, 0.2)["reasons"]), 2)

    def test_unknown_never_passes(self):
        self.assertFalse(G.gate(None, 0.0)["comparable"])
        self.assertFalse(G.gate(0, None)["comparable"])

    def test_placeholder_labels(self):
        self.assertEqual(G.THRESHOLD_LABEL, "placeholder (OECD/EU-reported target)")
        self.assertEqual(G.RULE_LABEL, "placeholder thresholds")
        self.assertEqual((G.RTT_THRESHOLD_DAYS, G.RTT_EDGE_DAYS, G.BIAS_LIMIT_DAYS, G.MISSED_LIMIT), (42, 42.5, 3.0, 0.10))

    def test_median_bias_is_shift_of_the_median(self):
        iv = [dict(true_days=d, pred_days=d + e) for d, e in [(10, 0), (20, 0), (30, 30), (40, -35), (50, 0)]]
        # median true 30, median measured sorted(10,20,60,5,50) -> 20: the county median moves by -10
        self.assertEqual(G.median_bias(iv), -10)
        self.assertIsNone(G.median_bias([]))


class Clock(unittest.TestCase):
    def test_rtt_records(self):
        d = dt.date(2025, 1, 1)
        ev = [dict(episode_id="a", event_type="REFERRAL_SENT", event_date=d),
              dict(episode_id="a", event_type="TREATMENT_START", event_date=d + dt.timedelta(days=42)),
              dict(episode_id="b", event_type="REFERRAL_SENT", event_date=d),
              dict(episode_id="c", event_type="REFERRAL_SENT", event_date=d),
              dict(episode_id="d", event_type="FIRST_CONTACT", event_date=d)]
        roster = [dict(episode_id=x, administratively_censored=["TREATMENT_START"] if x == "b" else []) for x in "abcd"]
        r = {x["episode_id"]: x for x in G.rtt_records(ev, roster)}
        self.assertEqual(sorted(r), ["a", "b", "c"])  # d never started the clock
        self.assertEqual((r["a"]["days"], r["a"]["open"]), (42, False))
        self.assertEqual((r["b"]["days"], r["b"]["open"]), (None, True))
        self.assertEqual((r["c"]["days"], r["c"]["open"]), (None, False))  # missing end date

    def test_negative_span_refused(self):
        d = dt.date(2025, 1, 10)
        ev = [dict(episode_id="a", event_type="REFERRAL_SENT", event_date=d),
              dict(episode_id="a", event_type="TREATMENT_START", event_date=d - dt.timedelta(days=1))]
        with self.assertRaises(ValueError):
            G.rtt_records(ev, [dict(episode_id="a")])

    def test_histogram_edge_counts_at_most_42_days(self):
        edge = math.log(G.RTT_EDGE_DAYS)
        self.assertLess(G.log_days(42), edge)
        self.assertGreaterEqual(G.log_days(43), edge)
        self.assertLess(G.log_days(0), edge)
        try:
            from run_fedstats import histogram_config
        except Exception:  # nvflare not importable outside flare/.venv
            self.skipTest("flare/.venv needed for run_fedstats")
        c = histogram_config(42)
        w = (c["range"][1] - c["range"][0]) / c["bins"]
        self.assertAlmostEqual(c["range"][0] + c["threshold_edge_index"] * w, edge, places=12)


class Assignment(unittest.TestCase):
    def test_deterministic_and_balanced(self):
        try:
            from gate_prep import assign
        except Exception:
            self.skipTest("gate_prep imports need the diagnose path")
        ids = [f"{i:064x}" for i in range(700)]
        a = assign(ids)
        random.Random(1).shuffle(ids)
        self.assertEqual(a, assign(ids))
        counts = [list(a.values()).count(c) for c in G.COUNTIES]
        self.assertEqual((min(counts), max(counts)), (30, 31))


@unittest.skipUnless(GATE.exists(), "data/flare/gate-v1.json not built yet")
class Output(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = GATE.read_text()
        cls.g = json.loads(cls.text)

    def test_labels(self):
        g = self.g
        self.assertTrue(g["synthetic"])
        self.assertEqual(g["label"], "SYNTHETIC")
        self.assertEqual(g["clock"]["threshold_label"], G.THRESHOLD_LABEL)
        self.assertEqual(g["rule"]["label"], G.RULE_LABEL)
        self.assertIn("six months", g["clock"]["threshold_text"])
        self.assertIn("FLARE-ready, not run in FLARE", g["rule"]["median_bias_computed_in"])
        for phrase in FORBIDDEN:
            self.assertNotIn(phrase, self.text.lower())

    def test_every_cell_recomputes_and_keeps_its_value(self):
        g = self.g
        self.assertEqual([r["county"] for r in g["counties"]], G.COUNTIES)
        for arm in G.ARMS:
            bad = [r["county"] for r in g["counties"] if not r["scribe"][arm]["comparable"]]
            self.assertEqual(bad, g["summary"][arm]["not_comparable_counties"])
            self.assertEqual(len(bad), g["summary"][arm]["not_comparable"])
        for r in g["counties"]:
            self.assertFalse(r["rtt"]["suppressed"])
            self.assertIsNotNone(r["rtt"]["share_within"])  # raw value kept even when not comparable
            self.assertAlmostEqual(r["rtt"]["share_within"], r["rtt"]["within"] / r["rtt"]["n"], places=12)
            for arm in G.ARMS:
                s = r["scribe"][arm]
                self.assertEqual(s["comparable"], G.gate(s["median_bias_days"], s["missed_share"])["comparable"])

    def test_national_row_from_county_rows(self):
        g = self.g
        self.assertEqual(g["national"]["n"], sum(r["rtt"]["n"] for r in g["counties"] if not r["rtt"]["suppressed"]))
        self.assertAlmostEqual(g["national"]["share_within"], g["national"]["share_within_central_pooled"], places=12)

    def test_flare_equivalence_and_crosschecks(self):
        g = self.g
        if g["flare"]["ran"]:
            eq = g["flare"]["equivalence"]
            self.assertTrue(eq["success"], eq["cells_failed"])
            self.assertEqual(eq["cells_ok"], eq["cells"])
            self.assertTrue(eq["suppressed_sets_identical"])
            self.assertTrue(g["flare"]["gate_decisions_identical_with_central_missed_share"])
        else:
            self.assertEqual(g["clock"]["computed_in"], "FLARE-ready, not run in FLARE")
        cc = g["crosscheck_stored_files"]
        for k in ("raw_missed_equal_stored_notes", "raw_interval_errors_equal_stored", "resolver_interval_errors_equal_stored",
                  "stored_interval_files_aligned"):
            self.assertTrue(cc[k], k)
        self.assertEqual(g["scribe_input"]["exact_notes"], {"raw": 305, "resolver": 651})

    def test_real_data_chip_names_areas_only(self):
        rd = self.g["realData"]
        self.assertEqual(rd["kind"], "PUBLISHED")
        self.assertEqual(rd["aim_pct"], 70)
        blob = json.dumps(rd)
        self.assertNotIn("HVA", blob)
        for a in rd["areas"]:
            v = a.get("pct", (a.get("pctRange") or [None, None])[1])
            self.assertEqual(a["canSee"], v >= rd["aim_pct"])
        self.assertEqual({a.get("pct") for a in rd["areas"]} - {None}, {42, 60, 72})


if __name__ == "__main__":
    unittest.main()
