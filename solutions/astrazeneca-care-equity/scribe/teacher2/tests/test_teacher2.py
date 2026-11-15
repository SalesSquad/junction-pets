"""Teaching round 2 unit tests. Standard library only, no network, no key.

Run from the project root:
    PYTHONDONTWRITEBYTECODE=1 scribe/.venv/bin/python -m unittest discover -s scribe/teacher2/tests -v
"""

import asyncio
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import protocol as P  # noqa: E402
import specs as SP  # noqa: E402

SPEC = {
    "id": "a" * 64,
    "curriculum": "hard_standard",
    "kind": "standard",
    "focus": "hard_standard",
    "style": "käyntimerkintä",
    "note_date": "2025-06-10",
    "facts_fi": ["syöpäpolun tuloreitti: työterveyshuolto", "lääkärin arvio: 3.2.2025", "lähetteen lähettäminen: 12 päivää sitten"],
    "date_strings": ["3.2.2025", "12 päivää sitten", "1.1.1960"],
    "wording": [],
    "facts": [
        {"type": "PHYSICIAN_ASSESSMENT", "date": "2025-02-03", "precision": "DAY", "expression": "3.2.2025", "form": "numeric", "meaning": "lääkärin arvio"},
        {"type": "REFERRAL_SENT", "date": "2025-05-29", "precision": "DAY", "expression": "12 päivää sitten", "form": "days", "meaning": "lähetteen lähettäminen"},
    ],
    "distractors": [{"kind": "birth", "expression": "1.1.1960", "date": "1960-01-01", "meaning": "syntymäaika"}],
    "ground_truth": {
        "entry_route": "OCCUPATIONAL",
        "events": [
            {"type": "PHYSICIAN_ASSESSMENT", "date": "2025-02-03", "precision": "DAY"},
            {"type": "REFERRAL_SENT", "date": "2025-05-29", "precision": "DAY"},
        ],
    },
    "date_forms": ["numeric", "days"],
}
FILLER = " ".join(["vointi"] * 70)
GOOD_NOTE = "Tuloreitti työterveyshuolto. Lääkäri arvioi 3.2.2025 ja lähetti lähetteen 12 päivää sitten. Syntynyt 1.1.1960. " + FILLER
BAD_NOTE = "Lääkäri arvioi 3.2.2025. " + FILLER  # two date strings missing
TRUTH = SPEC["ground_truth"]


def answer(events=None, route="OCCUPATIONAL"):
    return json.dumps({"entry_route": route, "events": TRUTH["events"] if events is None else events})


class FakeChat:
    """Stands in for the teacher: returns scripted notes and read-back answers, counts the calls."""

    def __init__(self, notes, readbacks):
        self.notes, self.readbacks, self.kinds = list(notes), list(readbacks), []

    async def __call__(self, kind, messages, max_tokens, temperature):
        self.kinds.append(kind)
        source = self.readbacks if kind == "readback" else self.notes
        return {"text": source.pop(0), "usage": {}, "seconds": 0.0}


class CollisionFilter(unittest.TestCase):
    def test_drops_used_and_repeated_ids(self):
        rows = [{"id": "x"}, {"id": "y"}, {"id": "y"}, {"id": "z"}]
        kept, dropped = SP.drop_collisions(rows, {"x"})
        self.assertEqual([r["id"] for r in kept], ["y", "z"])
        self.assertEqual([r["id"] for r in dropped], ["x", "y"])

    def test_nothing_used_keeps_everything_in_order(self):
        rows = [{"id": "b"}, {"id": "a"}]
        kept, dropped = SP.drop_collisions(rows, set())
        self.assertEqual(kept, rows)
        self.assertEqual(dropped, [])

    def test_hard_standard_rule(self):
        row = {"date_forms": ["days", "weeks", "month"], "distractors": [1, 2]}
        self.assertTrue(SP.is_hard(row))
        self.assertFalse(SP.is_hard(dict(row, date_forms=["days", "numeric", "month"])))
        self.assertFalse(SP.is_hard(dict(row, distractors=[1])))
        self.assertFalse(SP.is_hard(dict(row, date_forms=["days", "weeks", "numeric"])))


class DifferenceClassifier(unittest.TestCase):
    def classes(self, got):
        return sorted(d["class"] for d in P.classify(P.canonicalise(TRUTH), P.parse_readback(got)))

    def test_identical_answer_has_no_difference(self):
        self.assertEqual(self.classes(answer()), [])

    def test_wrong_route(self):
        self.assertEqual(self.classes(answer(route="PRIVATE")), ["wrong_route"])

    def test_missing_event(self):
        self.assertEqual(self.classes(answer(TRUTH["events"][:1])), ["missing_event"])

    def test_extra_event(self):
        extra = TRUTH["events"] + [{"type": "DIAGNOSIS", "date": "2025-06-01", "precision": "DAY"}]
        self.assertEqual(self.classes(answer(extra)), ["extra_event"])

    def test_wrong_date_and_precision(self):
        moved = [TRUTH["events"][0], {"type": "REFERRAL_SENT", "date": "2025-05-30", "precision": "DAY"}]
        self.assertEqual(self.classes(answer(moved)), ["wrong_date"])
        month = [{"type": "PHYSICIAN_ASSESSMENT", "date": "2025-02-01", "precision": "MONTH"}, TRUTH["events"][1]]
        self.assertEqual(self.classes(answer(month)), ["wrong_date"])

    def test_wrong_type(self):
        swapped = [TRUTH["events"][0], {"type": "REFERRAL_RECEIVED", "date": "2025-05-29", "precision": "DAY"}]
        found = P.classify(P.canonicalise(TRUTH), P.parse_readback(answer(swapped)))
        self.assertEqual([d["class"] for d in found], ["wrong_type"])
        self.assertEqual(found[0]["expected"]["type"], "REFERRAL_SENT")
        self.assertEqual(found[0]["got"]["type"], "REFERRAL_RECEIVED")

    def test_combined(self):
        got = [{"type": "SPECIALIST_VISIT", "date": "2025-02-03", "precision": "DAY"}]
        self.assertEqual(self.classes(answer(got, route="SCREENING")), ["missing_event", "wrong_route", "wrong_type"])

    def test_expression_answer_is_resolved_by_code(self):
        got = json.dumps(
            {
                "entry_route": "OCCUPATIONAL",
                "events": [
                    {"type": "PHYSICIAN_ASSESSMENT", "date": {"kind": "ABSOLUTE", "date": "2025-02-03"}},
                    {"type": "REFERRAL_SENT", "date": {"kind": "DAYS_AGO", "n": 12}},
                ],
            }
        )
        self.assertEqual(P.parse_readback(got, "2025-06-10"), P.canonicalise(TRUTH))
        off = got.replace('"n": 12', '"n": 13')
        found = P.classify(P.canonicalise(TRUTH), P.parse_readback(off, "2025-06-10"))
        self.assertEqual([d["class"] for d in found], ["wrong_date"])
        with self.assertRaises(ValueError):
            P.parse_readback(got.replace("DAYS_AGO", "SOMEDAY"), "2025-06-10")

    def test_fenced_json_is_parsed_and_garbage_is_refused(self):
        self.assertEqual(P.parse_readback("```json\n" + answer() + "\n```"), P.canonicalise(TRUTH))
        with self.assertRaises(ValueError):
            P.parse_readback("ei tapahtumia")
        with self.assertRaises(ValueError):
            P.parse_readback('{"entry_route":"NOWHERE","events":[]}')


class RepairOnce(unittest.TestCase):
    def run_protocol(self, chat):
        return asyncio.run(P.run_protocol(SPEC, chat))

    def test_clean_first_note_is_not_repaired(self):
        chat = FakeChat([GOOD_NOTE], [answer()])
        attempts = self.run_protocol(chat)
        self.assertEqual(chat.kinds, ["write", "readback"])
        self.assertEqual(len(attempts), 1)
        self.assertFalse(P.candidate(SPEC, attempts)["repaired"])

    def test_code_check_failure_gets_one_repair_and_no_first_readback(self):
        chat = FakeChat([BAD_NOTE, GOOD_NOTE], [answer()])
        attempts = self.run_protocol(chat)
        self.assertEqual(chat.kinds, ["write", "repair", "readback"])
        row = P.candidate(SPEC, attempts)
        self.assertTrue(row["repaired"] and row["code_check"]["passed"] and row["readback"]["consistent"])
        self.assertIn("missing_date_string:12 päivää sitten", attempts[0]["code_check"]["failures"])

    def test_readback_disagreement_gets_one_repair(self):
        chat = FakeChat([GOOD_NOTE, GOOD_NOTE], [answer(route="PRIVATE"), answer(route="PRIVATE")])
        attempts = self.run_protocol(chat)
        self.assertEqual(chat.kinds, ["write", "readback", "repair", "readback"])
        self.assertEqual(chat.kinds.count("repair"), 1)
        row = P.candidate(SPEC, attempts)
        self.assertFalse(row["readback"]["consistent"])  # kept with its flag, not dropped
        self.assertEqual(row["readback"]["differences"][0]["class"], "wrong_route")
        self.assertEqual(len(row["attempts"]), 2)

    def test_note_that_never_passes_is_repaired_exactly_once(self):
        chat = FakeChat([BAD_NOTE] * 5, [answer()] * 5)
        attempts = self.run_protocol(chat)
        self.assertEqual(chat.kinds, ["write", "repair"])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(chat.notes), 3)  # three scripted notes were never asked for

    def test_better_first_attempt_is_kept_when_the_repair_is_worse(self):
        chat = FakeChat([GOOD_NOTE, BAD_NOTE], [answer(route="PRIVATE")])
        row = P.candidate(SPEC, self.run_protocol(chat))
        self.assertFalse(row["repaired"])
        self.assertTrue(row["repair_attempted"] and row["code_check"]["passed"])


class TellingOrder(unittest.TestCase):
    def test_order_of_date_strings_in_the_note(self):
        facts = SPEC["facts"]
        self.assertEqual(P.told_order(facts, "Arvio 3.2.2025. Lähete lähti 12 päivää sitten."), "chronological")
        self.assertEqual(P.told_order(facts, "Lähete lähti 12 päivää sitten. Arvio 3.2.2025."), "out_of_order")
        self.assertEqual(P.told_order(facts, "Arvio 3.2.2025."), "unknown")
        self.assertIsNone(P.told_order(facts[:1], "Arvio 3.2.2025."))

    def test_long_prompt_lists_date_strings_in_telling_order(self):
        spec = dict(SPEC, curriculum="long_multi_visit", facts_fi=["syöpäpolun tuloreitti: työterveyshuolto", "lähetteen lähettäminen: 12 päivää sitten", "lääkärin arvio: 3.2.2025", "syntymäaika: 1.1.1960"])
        prompt = P.write_messages(spec)[1]["content"]
        self.assertIn("'12 päivää sitten' -> '3.2.2025' -> '1.1.1960'", prompt)


class LedgerCap(unittest.TestCase):
    def test_cap_stops_requests_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "ledger.json"
            ledger = P.Ledger(path, cap=3)
            self.assertEqual([ledger.reserve() for _ in range(3)], [1, 2, 3])
            with self.assertRaises(P.CapReached):
                ledger.reserve()
            again = P.Ledger(path, cap=3)  # a new process does not reset the count
            self.assertEqual(again.requests, 3)
            with self.assertRaises(P.CapReached):
                again.reserve()
            self.assertEqual(json.loads(path.read_text())["teacher_requests"], 3)

    def test_teacher_sends_nothing_once_the_cap_is_reached(self):
        class Client:
            posts = 0

            async def post(self, *a, **k):
                Client.posts += 1
                raise AssertionError("no request may be sent")

        with tempfile.TemporaryDirectory() as d:
            ledger = P.Ledger(pathlib.Path(d) / "ledger.json", cap=0)
            teacher = P.Teacher.__new__(P.Teacher)
            teacher.ledger, teacher.deadline, teacher.client, teacher.url = ledger, None, Client(), "http://invalid.invalid"
            import collections

            teacher.errors, teacher.sent = collections.Counter(), collections.Counter()
            with self.assertRaises(P.CapReached):
                asyncio.run(teacher.chat("write", [], 10, 0.0))
            self.assertEqual(Client.posts, 0)
            self.assertEqual(ledger.requests, 0)


if __name__ == "__main__":
    unittest.main()
