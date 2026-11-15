"""Lane B step 4 unit tests. Standard library only (plus the scribe venv), no network, no key.

Run from the project root:
    PYTHONDONTWRITEBYTECODE=1 scribe/.venv/bin/python -m unittest discover -s scribe/nemotron/tests -v
"""

import asyncio
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import common as C  # noqa: E402  (puts scribe/nemotron first on sys.path)
import cascade_agreement as CA  # noqa: E402
import reader as R  # noqa: E402
import reader_report as RR  # noqa: E402

NOTE = (
    "SYNTHETIC. Oireet alkoivat maaliskuussa 2025. Lääkärin arvio tehtiin 3.2.2025. "
    "Lähete lähetettiin 12 päivää sitten ja vastaanotettiin 2 viikkoa sitten. Kontrolli 5.3. Syntymäaika 1.1.1960."
)
ROW = {
    "id": "x" * 64,
    "note_date": "2025-06-10",
    "note_text": NOTE,
    "target_json": json.dumps(
        {
            "entry_route": "OCCUPATIONAL",
            "events": [
                {"type": "PHYSICIAN_ASSESSMENT", "date": "2025-02-03", "precision": "DAY"},
                {"type": "REFERRAL_SENT", "date": "2025-05-29", "precision": "DAY"},
            ],
        }
    ),
}
GOOD = '{"entry_route":"OCCUPATIONAL","events":[{"type":"PHYSICIAN_ASSESSMENT","date":{"kind":"ABSOLUTE","date":"2025-02-03"}},{"type":"REFERRAL_SENT","date":{"kind":"DAYS_AGO","n":12}}]}'
COMPUTED = '{"entry_route":"OCCUPATIONAL","events":[{"type":"PHYSICIAN_ASSESSMENT","date":{"kind":"ABSOLUTE","date":"2025-02-03"}},{"type":"REFERRAL_SENT","date":{"kind":"ABSOLUTE","date":"2025-05-29"}}]}'
MIXED = '{"entry_route":"OCCUPATIONAL","events":[{"type":"PHYSICIAN_ASSESSMENT","date":"2025-02-03"},{"type":"REFERRAL_SENT","date":{"kind":"DAYS_AGO","n":12}}]}'


def fake_chat(answers, seen):
    answers = list(answers)

    async def chat(messages, max_tokens, thinking, tag):
        seen.append(dict(messages=messages, max_tokens=max_tokens, thinking=thinking, tag=tag))
        return {"text": answers.pop(0), "reasoning": "", "usage": {}, "seconds": 0.1, "finish_reason": "stop"}

    return chat


class Prompts(unittest.TestCase):
    def test_v0_and_v1_differ_only_in_the_date_paragraph(self):
        a, b = R.system_prompt("absolute"), R.system_prompt("expression")
        self.assertEqual(a.replace(R._FORMAT["absolute"], ""), b.replace(R._FORMAT["expression"], ""))
        self.assertIn("do not calculate dates", b)
        self.assertIn("Resolve relative dates", a)

    def test_versions_change_one_thing_each(self):
        diff = lambda x, y: {k for k in R.CONFIG[x] if R.CONFIG[x][k] != R.CONFIG[y][k]}  # noqa: E731
        self.assertEqual(diff("v0", "v1"), {"fmt"})
        self.assertEqual(diff("v1", "v2"), {"validate"})
        self.assertEqual(diff("v2", "v2g"), {"ground"})
        self.assertEqual(diff("v2g", "v3"), {"thinking"})
        self.assertEqual(diff("v1", "v1rep"), set())


class Parsing(unittest.TestCase):
    def test_expression_is_resolved_by_code(self):
        pred, _ = R.parse("```json\n" + GOOD + "\n```", ROW["note_date"], "expression")
        self.assertEqual(pred, json.loads(ROW["target_json"]))

    def test_absolute(self):
        text = ROW["target_json"]
        pred, _ = R.parse("Here: " + text, ROW["note_date"], "absolute")
        self.assertEqual(pred, json.loads(text))

    def test_thinking_prefix_is_dropped(self):
        pred, _ = R.parse("<think>12 days before 10 June</think>" + GOOD, ROW["note_date"], "expression")
        self.assertEqual(pred, json.loads(ROW["target_json"]))

    def test_mixed_format_is_a_parse_failure(self):
        with self.assertRaises(ValueError):
            R.parse(MIXED, ROW["note_date"], "expression")
        with self.assertRaises(ValueError):
            R.parse("no json here", ROW["note_date"], "absolute")


class Validation(unittest.TestCase):
    def test_printed_dates(self):
        found = R.printed_dates(NOTE, ROW["note_date"])
        self.assertEqual(found["days"], {12})
        self.assertEqual(found["weeks"], {2})
        self.assertEqual(found["month"], {(2025, 3)})
        self.assertEqual(found["absolute"], {"2025-02-03", "2025-03-05", "1960-01-01"})

    def test_grounding_flags_a_computed_date(self):
        self.assertEqual(R.grounding_problems(json.loads(GOOD), NOTE, ROW["note_date"]), [])
        problems = R.grounding_problems(json.loads(COMPUTED), NOTE, ROW["note_date"])
        self.assertEqual(len(problems), 1)
        self.assertIn("events[1]", problems[0])

    def test_check_flags_future_and_duplicate(self):
        future = '{"entry_route":"OCCUPATIONAL","events":[{"type":"SPECIALIST_VISIT","date":{"kind":"ABSOLUTE","date":"2025-03-05"}},{"type":"SPECIALIST_VISIT","date":{"kind":"ABSOLUTE","date":"2025-03-05"}}]}'
        row = dict(ROW, note_date="2025-03-01")
        pred, _, problems = R.check(future, row, R.CONFIG["v2"])
        self.assertIsNotNone(pred)
        self.assertTrue(any("after the note date" in p for p in problems))
        self.assertTrue(any("listed twice" in p for p in problems))

    def test_unknown_route_is_not_valid(self):
        bad = GOOD.replace("OCCUPATIONAL", "HOSPITAL")
        pred, _, problems = R.check(bad, ROW, R.CONFIG["v2"])
        self.assertIsNone(pred)
        self.assertTrue(problems)


class Protocol(unittest.TestCase):
    def run_note(self, version, answers):
        seen = []
        out = asyncio.run(R.read_note(ROW, version, fake_chat(answers, seen)))
        return out, seen

    def test_v1_never_repairs(self):
        out, seen = self.run_note("v1", [MIXED])
        self.assertEqual(len(seen), 1)
        self.assertIsNone(out["prediction"])
        self.assertTrue(out["flagged"])

    def test_v2_repairs_a_parse_failure_once(self):
        out, seen = self.run_note("v2", [MIXED, GOOD])
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1]["tag"], "v2:repair")
        self.assertIn("Problems found", seen[1]["messages"][-1]["content"])
        self.assertEqual(out["selected_attempt"], 1)
        self.assertEqual(out["prediction"], json.loads(ROW["target_json"]))

    def test_v2_does_not_ground(self):
        out, seen = self.run_note("v2", [COMPUTED])
        self.assertEqual(len(seen), 1)
        self.assertFalse(out["flagged"])

    def test_v2g_repairs_a_computed_date_and_keeps_the_first_if_repair_also_fails(self):
        out, seen = self.run_note("v2g", [COMPUTED, GOOD])
        self.assertEqual((len(seen), out["selected_attempt"], out["flagged"]), (2, 1, False))
        out, seen = self.run_note("v2g", [COMPUTED, COMPUTED])
        self.assertEqual((len(seen), out["selected_attempt"], out["flagged"]), (2, 0, True))
        self.assertIsNotNone(out["prediction"])

    def test_v3_thinks_with_room_to_think(self):
        out, seen = self.run_note("v3", [GOOD])
        self.assertTrue(seen[0]["thinking"])
        self.assertEqual(seen[0]["max_tokens"], R.MAX_TOKENS_THINKING)
        self.assertEqual(out["prediction"], json.loads(ROW["target_json"]))


class LedgerAndReport(unittest.TestCase):
    def test_ledger_counts_and_caps(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = C.Ledger(pathlib.Path(d) / "l.json", cap=2)
            ledger.reserve()
            ledger.reserve()
            with self.assertRaises(C.CapReached):
                ledger.reserve()
            self.assertEqual(json.loads((pathlib.Path(d) / "l.json").read_text())["requests"], 2)

    def test_paired(self):
        a = [{"id": i, "exact": e} for i, e in enumerate([True, True, False, False])]
        b = [{"id": i, "exact": e} for i, e in enumerate([True, False, True, True])]
        p = RR.paired(a, b)
        self.assertEqual((p["before"], p["after"], p["gained"], p["lost"]), (2, 3, 2, 1))

    def test_cascade_agreement_rule(self):
        truth = json.loads(ROW["target_json"])
        wrong = dict(truth, entry_route="PRIVATE")
        rows = [dict(ROW, id=str(i), writer="claude-haiku-5-5") for i in range(3)]
        gemma = {"0": truth, "1": wrong, "2": wrong}
        nemo = {"0": truth, "1": truth, "2": wrong}
        s = CA.evaluate(rows, gemma, nemo)["all"]
        self.assertEqual(s["prefilled_for_one_click_confirmation"]["k"], 2)  # 0 and 2 agree
        self.assertEqual(s["error_among_prefilled"]["k"], 1)  # 2 agrees on a wrong answer
        self.assertEqual(s["flagged_where_nemotron_answer_is_exact"]["k"], 1)


if __name__ == "__main__":
    unittest.main()
