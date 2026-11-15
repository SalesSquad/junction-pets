"""Tests for the stress set v1 builder and code gate. Constructed strings only; no network, no stress note is read.

Run: scribe/.venv/bin/python -m unittest discover -s scribe/stress/tests
"""

import datetime as dt
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check as C  # noqa: E402
import phrases as P  # noqa: E402
import specs as SP  # noqa: E402


class Phrases(unittest.TestCase):
    def test_heldout_render_and_arithmetic(self):
        for n, word in [(7, "seitsemän"), (8, "kahdeksan"), (9, "yhdeksän"), (10, "kymmenen"), (11, "yksitoista"), (12, "kaksitoista")]:
            self.assertEqual(P.render_heldout("heldout_days_word", n), f"{word} päivää sitten")
            self.assertEqual(P.heldout_days(f"{word} päivää sitten"), n)
            self.assertEqual(P.render_heldout("heldout_weeks_word", n), f"{word} viikkoa sitten")
            self.assertEqual(P.heldout_days(f"{word} viikkoa sitten"), 7 * n)
        self.assertEqual(P.render_heldout("heldout_toissa"), "toissapäivänä")
        self.assertEqual(P.heldout_days("toissapäivänä"), 2)
        for bad in ("kuusi päivää sitten", "8 päivää sitten", "eilen", "kahdeksan kuukautta sitten"):
            with self.assertRaises(ValueError):
                P.heldout_days(bad)
        with self.assertRaises(ValueError):
            P.render_heldout("heldout_days_word", 6)

    def test_heldout_phrases_are_outside_the_frozen_lexicon(self):
        R = C.resolver()[0]
        note = dt.date(2025, 3, 15)
        for family in P.HELDOUT_FAMILIES:
            for offset in P.heldout_offsets(family):
                n = None if family == "heldout_toissa" else (offset if family == "heldout_days_word" else offset // 7)
                text = f"Hoito alkoi {P.render_heldout(family, n)} poliklinikalla."
                self.assertEqual(R.relative_spans(text, note, "A"), [], text)
                self.assertEqual(R.relative_spans(text, note, "A'"), [], text)
                self.assertEqual(R.needs_person_spans(text, "A'"), [], text)

    def test_vague_windows(self):
        note = dt.date(2025, 3, 15)
        first, last, nominal, precision = P.vague_window("viime kuussa", note)
        self.assertEqual((first, last, nominal, precision), (dt.date(2025, 2, 1), dt.date(2025, 2, 28), dt.date(2025, 2, 1), "MONTH"))
        first, last, nominal, precision = P.vague_window("pari viikkoa sitten", note)
        self.assertEqual((note - last).days, 10)
        self.assertEqual((note - first).days, 21)
        self.assertEqual((note - nominal).days, 14)
        self.assertEqual(precision, "DAY")

    def test_undeclared_references(self):
        flagged = [
            "8 päivää sitten", "kaksi viikkoa sitten", "viikko sitten", "eilen", "Toissapäivänä", "viime viikolla",
            "maanantaina", "2 vk sitten", "3 kk", "marraskuussa", "2024", "12.3.", "pari kuukautta sitten", "kolmen viikon kuluttua",
        ]
        for text in flagged:
            self.assertTrue(P.undeclared(f"Potilas kävi {text} vastaanotolla."), text)
        for text in ("ja sitten kotiin", "kaksi kertaa", "aiemmin hoidettu", "myöhemmin sovitaan", "kuusi lääkettä"):
            self.assertEqual(P.undeclared(f"Potilas {text}."), [], text)


def _spec(facts, distractors=(), note="2025-03-15", bounds=(5, 60), route="PUBLIC_PRIMARY"):
    events = sorted([{k: f[k] for k in ("type", "date", "precision")} for f in facts if f.get("outcome", "date") == "date"],
                    key=lambda e: (e["date"], e["type"]))
    return dict(id="t", note_date=note, entry_route=route, facts=list(facts), distractors=list(distractors), word_bounds=list(bounds),
                ground_truth=dict(entry_route=route, events=events), vague_events=[])


class CodeGate(unittest.TestCase):
    def test_standard_and_heldout_resolve_to_key(self):
        facts = [
            dict(type="PHYSICIAN_ASSESSMENT", date="2025-01-10", precision="DAY", expression="10.1.2025", form="numeric", family="numeric"),
            dict(type="REFERRAL_SENT", date="2025-01-25", precision="DAY", expression="7 viikkoa sitten", form="weeks", family="weeks"),
            dict(type="DIAGNOSIS", date="2025-03-04", precision="DAY", expression="yksitoista päivää sitten", form="heldout_days_word", family="heldout_days_word"),
            dict(type="TREATMENT_START", date="2025-03-13", precision="DAY", expression="toissapäivänä", form="heldout_toissa", family="heldout_toissa"),
        ]
        note = ("Syöpäpolun tuloreitti on terveyskeskus. Lääkäri arvioi potilaan 10.1.2025. Lähete lähetettiin 7 viikkoa sitten. "
                "Diagnoosi vahvistettiin yksitoista päivää sitten ja hoito alkoi toissapäivänä. Vointi on hyvä.")
        r = C.code_check(_spec(facts), note)
        self.assertTrue(r["passed"], r["failures"])
        self.assertEqual([x["ok"] for x in r["resolution"]], [True] * 4)

    def test_wrong_key_date_is_caught(self):
        facts = [dict(type="DIAGNOSIS", date="2025-03-05", precision="DAY", expression="yksitoista päivää sitten", form="heldout_days_word", family="heldout_days_word")]
        r = C.code_check(_spec(facts), "Syöpäpolun tuloreitti on terveyskeskus. Diagnoosi vahvistettiin yksitoista päivää sitten. Vointi hyvä.")
        self.assertFalse(r["passed"])
        self.assertIn("not_resolved_to_key:yksitoista päivää sitten", r["failures"])

    def test_digits_capitals_and_extra_dates_fail(self):
        facts = [dict(type="DIAGNOSIS", date="2025-03-04", precision="DAY", expression="yksitoista päivää sitten", form="heldout_days_word", family="heldout_days_word")]
        for note, kind in [
            ("Diagnoosi vahvistettiin 11 päivää sitten terveyskeskuksen kautta tulleelle potilaalle.", "missing_date_string"),
            ("Yksitoista päivää sitten diagnoosi vahvistettiin terveyskeskuksen kautta tulleelle potilaalle.", "missing_date_string"),
            ("Diagnoosi vahvistettiin yksitoista päivää sitten ja lähete lähti eilen terveyskeskuksesta.", "undeclared_date"),
        ]:
            r = C.code_check(_spec(facts), note)
            self.assertFalse(r["passed"], note)
            self.assertTrue(any(f.startswith(kind) for f in r["failures"]), (note, r["failures"]))

    def test_word_bounds(self):
        facts = [dict(type="DIAGNOSIS", date="2025-03-13", precision="DAY", expression="toissapäivänä", form="heldout_toissa", family="heldout_toissa")]
        r = C.code_check(_spec(facts, bounds=(25, 49)), "Diagnoosi vahvistettiin toissapäivänä.")
        self.assertIn("words:3 outside 25-49", r["failures"])

    def test_vague_phrase_is_present_and_never_dated(self):
        first, last, nominal, precision = P.vague_window("pari viikkoa sitten", dt.date(2025, 3, 15))
        facts = [dict(type="SPECIALIST_VISIT", date=nominal.isoformat(), precision=precision, expression="pari viikkoa sitten", form="vague", family="vague",
                      outcome="person", window_start=first.isoformat(), window_end=last.isoformat())]
        r = C.code_check(_spec(facts), "Syöpäpolun tuloreitti on terveyskeskus. Potilas kävi onkologin vastaanotolla pari viikkoa sitten. Vointi hyvä.")
        self.assertTrue(r["passed"], r["failures"])
        self.assertIsNone(r["resolution"][0]["resolved_date"])
        self.assertTrue(r["resolution"][0]["frozen_aprime_to_person"])


class Builder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs, cls.summary = SP.build_all(dict(standard=30, terse=12, long=10, no_event=6, no_event_terse=4))

    def test_deterministic(self):
        again, _ = SP.build_all(dict(standard=30, terse=12, long=10, no_event=6, no_event_terse=4))
        self.assertEqual([s["id"] for s in again], [s["id"] for s in self.specs])

    def test_no_collision_with_earlier_datasets(self):
        used, files = SP.used_ids()
        self.assertTrue(any("v2/dataset" in f for f in files) and any("v3/dataset" in f for f in files))
        ids = [s["id"] for s in self.specs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(set(ids) & used)

    def test_keys_are_consistent(self):
        for s in self.specs:
            note = dt.date.fromisoformat(s["note_date"])
            self.assertIsNone(SP.problem(s["facts"], s["distractors"], note), s["id"])
            self.assertEqual(len(s["ground_truth"]["events"]) + len(s["vague_events"]), len(s["facts"]))
            for f in s["facts"]:
                if f["family"] in P.HELDOUT_FAMILIES:
                    self.assertEqual((note - dt.timedelta(days=P.heldout_days(f["expression"]))).isoformat(), f["date"])
                    self.assertLessEqual(note.toordinal() - dt.date.fromisoformat(f["date"]).toordinal(), 84)
            if s["phrase_plan"] == "heldout":
                self.assertTrue(s["has_heldout"])
            if s["phrase_plan"] == "vague":
                self.assertEqual(len(s["vague_events"]), 1)
            if s["kind"] == "no_event":
                self.assertEqual(s["ground_truth"]["events"], [])

    def test_shares(self):
        plans = [s["phrase_plan"] for s in self.specs if s["kind"] == "standard"]
        self.assertGreaterEqual(plans.count("heldout") / len(plans), 0.5)
        self.assertGreaterEqual(plans.count("vague"), 1)


if __name__ == "__main__":
    unittest.main()
