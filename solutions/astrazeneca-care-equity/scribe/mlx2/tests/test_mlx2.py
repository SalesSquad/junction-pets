"""Unit tests for scribe/mlx2 on made-up SYNTHETIC strings (no MLX, no dataset rows needed).

  scribe/.venv/bin/python -m unittest discover -s scribe/mlx2/tests
"""

import json
import pathlib
import random
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import m2common as C  # noqa: E402
import data_tools as DT  # noqa: E402
import export as EX  # noqa: E402
import score as SC  # noqa: E402
from prompts import canonicalise  # noqa: E402


def make_row(text, note_date, facts, route="PUBLIC_PRIMARY", distractors=()):
    truth = {"entry_route": route, "events": [{"type": f["type"], "date": f["date"], "precision": f["precision"]} for f in facts]}
    row = {"id": "t1", "writer": "nemotron-3.5-super-vl", "note_text": text, "note_date": note_date, "facts": list(facts),
           "entry_route": route, "events": truth["events"], "distractors": list(distractors),
           "target_json": DT._compact(canonicalise(truth)), "date_forms": sorted({f["form"] for f in facts})}
    row["expression_json"] = DT._compact(DT.to_expression(row))
    return row


ROW = make_row(
    "Lähete on vastaanotettu 35 päivää sitten. Erikoislääkärikäynti oli 3.2.2025. 10 viikkoa sitten oireet alkoivat.",
    "2025-03-10",
    [{"type": "REFERRAL_RECEIVED", "date": "2025-02-03", "precision": "DAY", "expression": "35 päivää sitten", "form": "days", "meaning": ""},
     {"type": "SPECIALIST_VISIT", "date": "2025-02-03", "precision": "DAY", "expression": "3.2.2025", "form": "numeric", "meaning": ""},
     {"type": "SYMPTOM_ONSET_REPORTED", "date": "2024-12-30", "precision": "DAY", "expression": "10 viikkoa sitten", "form": "weeks", "meaning": ""}],
)


class TestRoundTrip(unittest.TestCase):
    def test_made_up_row_round_trips(self):
        self.assertEqual(EX.roundtrip_rows([ROW]), [("t1", True, "")])

    def test_wrong_label_fails(self):
        bad = dict(ROW, target_json=ROW["target_json"].replace("2025-02-03", "2025-02-04", 1))
        self.assertFalse(EX.roundtrip_rows([bad])[0][1])


class TestAugmentation(unittest.TestCase):
    def test_train_options_never_hold_out(self):
        held = EX.heldout_phrasings()["tokens"]
        for choices in EX.train_options().values():
            for phrase, expr in choices:
                self.assertFalse(any(re.search(rf"(?<!\w){h}(?!\w)", phrase) for h in held), phrase)
                self.assertIn(expr["kind"], ("DAYS_AGO", "WEEKS_AGO"))

    def test_options_cover_lexicon_number_words_1_to_6_and_offsets(self):
        offsets = set(EX.train_options())
        self.assertEqual(offsets, {1, 2, 3, 4, 5, 6, 7, 14, 21, 28, 35, 42})
        for off, choices in EX.train_options().items():
            for _, expr in choices:
                self.assertEqual(expr["n"] * (7 if expr["kind"] == "WEEKS_AGO" else 1), off)

    def test_augment_row_round_trips_and_keeps_order(self):
        for seed in range(50):
            new, rec = EX.augment_row(ROW, random.Random(seed))
            self.assertEqual(DT.resolve_expression(json.loads(new["expression_json"]), new["note_date"]),
                             json.loads(new["target_json"]))
            self.assertNotRegex(new["note_text"], r"\d+ (päivää|viikkoa) sitten")
            # newest original phrase gets the smallest new offset
            offs = {w["from"]: w["offset_days"] for w in rec["rewrites"]}
            self.assertLess(offs["35 päivää sitten"], offs["10 viikkoa sitten"])
            # untouched absolute date stays
            self.assertIn("3.2.2025", new["note_text"])
            self.assertTrue(new["augmented"])

    def test_sentence_start_is_capitalised(self):
        caps = set()
        for seed in range(40):
            new, rec = EX.augment_row(ROW, random.Random(seed))
            w = next(x for x in rec["rewrites"] if x["from"] == "10 viikkoa sitten")
            caps.add(w["to"][0].isupper())
            self.assertIn(". " + w["to"], new["note_text"])
        self.assertEqual(caps, {True})

    def test_unsafe_rows_are_not_candidates(self):
        dup = make_row("35 päivää sitten lähete. Toinen maininta: 35 päivää sitten.", "2025-03-10",
                       [{"type": "REFERRAL_RECEIVED", "date": "2025-02-03", "precision": "DAY", "expression": "35 päivää sitten",
                         "form": "days", "meaning": ""}])
        self.assertIsNone(EX.candidates(dup))
        none = make_row("Käynti 3.2.2025.", "2025-03-10",
                        [{"type": "SPECIALIST_VISIT", "date": "2025-02-03", "precision": "DAY", "expression": "3.2.2025", "form": "numeric", "meaning": ""}])
        self.assertIsNone(EX.candidates(none))

    def test_existing_phrasing_is_not_reused(self):
        row = make_row("Potilas soitti eilen. Lähete vastaanotettu 35 päivää sitten.", "2025-03-10",
                       [{"type": "REFERRAL_RECEIVED", "date": "2025-02-03", "precision": "DAY", "expression": "35 päivää sitten",
                         "form": "days", "meaning": ""}])
        for seed in range(60):
            new, rec = EX.augment_row(row, random.Random(seed))
            self.assertNotEqual(rec["rewrites"][0]["to"].lower(), "eilen")


class TestScoreParse(unittest.TestCase):
    def test_expression_output_resolves(self):
        variants, expr, model, mode, err = SC.parse("expression", ROW["expression_json"], ROW)
        self.assertEqual(variants["code"], json.loads(ROW["target_json"]))
        self.assertEqual(mode, "strict")

    def test_garbage_is_a_parse_failure(self):
        for fmt in ("expression", "absolute"):
            variants, _, _, mode, err = SC.parse(fmt, "not json at all", ROW)
            self.assertEqual(mode, "failed")
            self.assertTrue(all(v is None for v in variants.values()))

    def test_absolute_resolver_fixes_relative_dates(self):
        wrong = json.loads(ROW["target_json"])
        for e in wrong["events"]:
            if e["type"] == "REFERRAL_RECEIVED":
                e["date"] = "2025-01-20"  # model guessed the subtraction wrong
        variants, _, model, mode, _ = SC.parse("absolute", json.dumps(wrong), ROW)
        gold = json.loads(ROW["target_json"])
        self.assertNotEqual(variants["off"], gold)
        self.assertEqual(variants["A"], gold)
        self.assertEqual(variants["A'"], gold)

    def test_rate_and_compare(self):
        self.assertEqual(SC.rate(0, 0)["value"], None)
        c = SC.compare("a", [True, False, True], "b", [True, True, False])
        self.assertEqual((c["a_only_correct"], c["b_only_correct"]), (1, 1))


class TestSplitsGuard(unittest.TestCase):
    def test_test_and_stress_are_refused(self):
        for name in ("test_nemotron", "test_haiku", "stress"):
            with self.assertRaises(ValueError):
                C.load_split(name)


if __name__ == "__main__":
    unittest.main()
