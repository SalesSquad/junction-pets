import json
import unittest

import fakes  # noqa: F401
import report
from test_selection import run


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, _ = run(100000)
        cls.out = json.loads(json.dumps(cls.out))  # exactly what would be read back from the JSON file
        cls.text = report.render(cls.out)

    def test_figures_come_from_the_json(self):
        selected = self.out["test"]["systems"]["selected"]["splits"]["test_nemotron"]
        self.assertIn(report.rate(selected["note_exact_match"]), self.text)
        self.assertIn(self.out["selection"]["description"], self.text)
        val = self.out["runs"]["A-4b-lora-r16"]["val"]["note_exact_match"]
        self.assertIn(report.rate(val), self.text)
        self.assertEqual(report.rate({"value": 0.832, "n": 500, "ci95": [0.796, 0.863]}), "83.2% (79.6-86.3)")
        test = next(t for t in self.out["test"]["mcnemar"] if (t["a"], t["b"], t["split"]) == ("selected", "v1_recipe", "pooled"))
        self.assertIn(f"| selected | v1_recipe | pooled | {test['a_only_correct']} | {test['b_only_correct']} | {test['exact_p']:.4f} |", self.text)

    def test_sections(self):
        for heading in (
            "## Selected configuration",
            "## Test results (first read in this session, after the selection was frozen)",
            "### Paired comparisons",
            "### Selected configuration by writer",
            "### Selected configuration by kind of note",
            "## Risk control for auto-accepting notes",
            "### Stage A: size ladder",
            "### Stage B: adapter method and initialisation",
            "### Stage C: output format",
            "### Stage C: training data",
            "## Dropped for time or unavailable",
        ):
            self.assertIn(heading, self.text)
        self.assertIn("SYNTHETIC", self.text)
        self.assertIn("not for clinical use", self.text)
        self.assertIn("Nothing was dropped.", self.text)
        self.assertIn("B-rslora-rank-x4", self.text)
        self.assertIn("| Nemotron-written | Haiku-written |", self.text)
        self.assertIn("| 86.0% of 250 | not run |", self.text)  # per-writer validation columns of a Stage A row
        self.assertIn("schema-constrained", self.text)
        self.assertIn("calibration set too small", self.text)  # alpha = 0.01 cannot be certified on 250 notes
        self.assertNotIn("WIRING TEST", self.text)

    def test_dropped_items_and_missing_parts_are_stated(self):
        out, _ = run(2)
        text = report.render(json.loads(json.dumps(out)))
        self.assertIn("A-4b-lora-r16", text)
        self.assertIn("does not fit", text)
        self.assertNotIn("Nothing was dropped.", text)
        self.assertNotIn("| v1_recipe |", text)

    def test_unfinished_run_shows_no_invented_numbers(self):
        text = report.render({"status": "in_progress", "runs": {}, "stages": {}})
        self.assertIn("Status: **in_progress**", text)
        self.assertGreaterEqual(text.count(report.NOT_RUN), 5)
        self.assertNotIn("%", text.split("## Notes and limits")[0])
        failed = report.render({"status": "failed", "error": "RuntimeError: Stage A produced no eligible run", "smoke": True})
        self.assertIn("Stage A produced no eligible run", failed)
        self.assertIn("WIRING TEST ONLY", failed)

    def test_formatting_of_missing_values(self):
        self.assertEqual(report.rate(None), report.NOT_RUN)
        self.assertEqual(report.rate({"value": None}), report.NOT_RUN)
        self.assertEqual(report.pct(None), report.NOT_RUN)
        self.assertEqual(report.num(None), report.NOT_RUN)
        self.assertEqual(report.pct(0.05), "5.0%")


class RealAblation(unittest.TestCase):
    """The finished A100 ablation (data/scribe/v2/ablation-v1.json): review findings 0 to 5, 7 and 21."""

    @classmethod
    def setUpClass(cls):
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[3] / "data/scribe/v2/ablation-v1.json"
        if not path.exists():
            raise unittest.SkipTest("the ablation result is not in this checkout")
        cls.out = json.loads(path.read_text())
        cls.text = report.render(cls.out, report.load_posthoc(path))

    def test_selection_is_described_by_what_ran(self):
        self.assertIn("only one ladder run finished (A-270m-lora-r16); no size was compared", self.text)
        self.assertIn("- Stage B: no arm ran", self.text)
        self.assertIn("A-270m-full-finetune vs A-270m-lora-r16: 0.377 vs 0.361, 10 vs 5 discordant notes, exact McNemar p = 0.302", self.text)
        self.assertIn("The time budget ruled out 2 size-ladder run(s)", self.text)
        self.assertNotIn("Selected: **A-270m-lora-r16**. A-270m-lora-r16 has the highest", self.text)

    def test_risk_table_flags_the_split_above_alpha(self):
        self.assertIn("| test_haiku | 6.5% | 2/13 = 15.4% | **no** | 41.0% | certified |", self.text)
        self.assertIn("The pooled test check mixes 200 Haiku-written of 700 notes", self.text)

    def test_unparsable_split_by_cause_and_test_overlap(self):
        self.assertIn("5.5% (3.1-9.6) (9 / 2)", self.text)
        self.assertIn("200 of its 500 notes were scored by the version-1 model", self.text)
        self.assertIn("Not a like-for-like check", self.text)

    def test_base_model_and_terms(self):
        self.assertIn("`unsloth/gemma-3-270m-it` at `23cf460f6bb16954176b3ddcc8d4f250501458a9`", self.text)
        self.assertIn("https://ai.google.dev/gemma/terms", self.text)


if __name__ == "__main__":
    unittest.main()
