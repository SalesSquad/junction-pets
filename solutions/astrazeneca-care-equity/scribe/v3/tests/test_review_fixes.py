"""Offline tests for the review fixes: style-label detector, summary keys, audit strict-clean share."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: E402
import score_audit  # noqa: E402


class StyleLabel(unittest.TestCase):
    def test_detects_label_with_markup(self):
        self.assertTrue(common.starts_with_style_label("**Lähetekirje**\nPotilas ..."))
        self.assertTrue(common.starts_with_style_label("Käyntimerkintä: ..."))
        self.assertFalse(common.starts_with_style_label("Potilas tuli lähetekirjeen kanssa."))


class Summary(unittest.TestCase):
    def test_summary_flat_and_null_explained(self):
        s = json.loads((common.ROOT / "data/scribe/v3/summary-v1.json").read_text())
        self.assertIs(s["synthetic_only"], True)
        for k, v in s.items():
            if v is None:
                self.assertIn(k, s["_not_done"])
        for k in s:
            if not k.startswith("_") and k not in ("synthetic_only", "not_for_clinical_use", "generated_utc"):
                self.assertIn(k, s["_sources"] if v is not None else s["_not_done"]) if s[k] is not None else None


class Audit(unittest.TestCase):
    def test_route_not_ok_is_not_strict_clean(self):
        a = dict(events=[dict(index=0, verdict="stated", quote="abc")], unlisted_event=dict(present=False, quote=""), route_ok=False)
        r = score_audit.score_item(a, "abc", 1)
        self.assertEqual(r["label"], "clean")
        g = score_audit.group_report([({}, r)])
        self.assertEqual(g["clean_strict"]["numerator"], 0)
        self.assertEqual(g["clean"]["numerator"], 1)


if __name__ == "__main__":
    unittest.main()
