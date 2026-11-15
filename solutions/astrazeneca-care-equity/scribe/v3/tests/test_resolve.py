"""Unit tests of scribe/v3/resolve.py and scribe/v3/lexicon.py on constructed strings. No network, no key.

The six date forms come from the note generator itself (scribe/sample.py render). Run:
  scribe/.venv/bin/python -m unittest discover -s scribe/v3/tests -p 'test_resolve*.py' -v
"""

import datetime as dt
import hashlib
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import lexicon  # noqa: E402
import resolve  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sample = _load("scribe_sample", ROOT / "scribe/sample.py")
NOTE = dt.date(2025, 6, 18)


def ev(t, d, p="DAY"):
    return dict(type=t, date=d, precision=p)


class SixForms(unittest.TestCase):
    """Every form scribe/sample.py render() writes."""

    def setUp(self):
        self.cases = {
            "numeric": dt.date(2025, 3, 5),
            "long": dt.date(2025, 3, 5),
            "no_year": dt.date(2025, 3, 5),
            "days": NOTE - dt.timedelta(days=38),
            "weeks": NOTE - dt.timedelta(days=21),
            "month": dt.date(2025, 3, 1),
        }

    def text(self, form):
        return f"Potilas kertoo, että {sample.render(self.cases[form], NOTE, form)} todettiin muutos."

    def test_rendered_strings(self):
        got = {f: sample.render(d, NOTE, f) for f, d in self.cases.items()}
        self.assertEqual(got, {"numeric": "5.3.2025", "long": "5. maaliskuuta 2025", "no_year": "5.3.",
                               "days": "38 päivää sitten", "weeks": "3 viikkoa sitten", "month": "maaliskuussa 2025"})

    def test_absolute_forms_are_written_dates(self):
        for form in ("numeric", "long", "no_year", "month"):
            with self.subTest(form=form):
                self.assertEqual(resolve.written_dates(self.text(form), NOTE), {self.cases[form].isoformat()})
                self.assertEqual(resolve.relative_dates(self.text(form), NOTE), [])

    def test_relative_forms_resolve_against_note_date(self):
        for form in ("days", "weeks"):
            for arm in resolve.ARMS:
                with self.subTest(form=form, arm=arm):
                    self.assertEqual(resolve.relative_dates(self.text(form), NOTE, arm), [self.cases[form].isoformat()])
                    self.assertEqual(resolve.written_dates(self.text(form), NOTE), set())

    def test_correct_prediction_is_never_changed(self):
        for form, d in self.cases.items():
            for arm in resolve.ARMS:
                with self.subTest(form=form, arm=arm):
                    p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("DIAGNOSIS", d.isoformat(), "MONTH" if form == "month" else "DAY")])
                    self.assertEqual(resolve.repair(p, self.text(form), NOTE, arm), p)
                    self.assertEqual(resolve.resolve(p, self.text(form), NOTE, arm)["changes"], [])

    def test_wrong_relative_date_is_recomputed(self):
        for form in ("days", "weeks"):
            with self.subTest(form=form):
                p = dict(entry_route="EMERGENCY", events=[ev("FIRST_CONTACT", "2025-04-30")])
                out = resolve.resolve(p, self.text(form), NOTE)
                self.assertEqual(out["prediction"]["events"], [ev("FIRST_CONTACT", self.cases[form].isoformat())])
                self.assertEqual(out["changes"][0]["phrase"], sample.render(self.cases[form], NOTE, form))
                self.assertEqual(out["changes"][0]["source"], "digits")

    def test_event_with_written_date_is_kept(self):
        text = f"{sample.render(dt.date(2025, 3, 5), NOTE, 'numeric')} lähete; {sample.render(NOTE - dt.timedelta(days=14), NOTE, 'days')} oireet."
        p = dict(entry_route="PRIVATE", events=[ev("REFERRAL_SENT", "2025-03-05"), ev("SYMPTOM_ONSET_REPORTED", "2025-06-01")])
        out = resolve.repair(p, text, NOTE)
        self.assertEqual(out["events"], [ev("REFERRAL_SENT", "2025-03-05"), ev("SYMPTOM_ONSET_REPORTED", "2025-06-04")])


class Matching(unittest.TestCase):
    def test_one_to_one_by_smallest_total_difference(self):
        text = "Oireet alkoivat 70 päivää sitten, lääkäri 5 viikkoa sitten ja lähete 10 päivää sitten."
        p = dict(entry_route="PUBLIC_PRIMARY", events=[
            ev("REFERRAL_SENT", (NOTE - dt.timedelta(days=12)).isoformat()),
            ev("SYMPTOM_ONSET_REPORTED", (NOTE - dt.timedelta(days=80)).isoformat()),
            ev("PHYSICIAN_ASSESSMENT", (NOTE - dt.timedelta(days=30)).isoformat())])
        got = {e["type"]: e["date"] for e in resolve.repair(p, text, NOTE)["events"]}
        self.assertEqual(got, {"SYMPTOM_ONSET_REPORTED": (NOTE - dt.timedelta(days=70)).isoformat(),
                               "PHYSICIAN_ASSESSMENT": (NOTE - dt.timedelta(days=35)).isoformat(),
                               "REFERRAL_SENT": (NOTE - dt.timedelta(days=10)).isoformat()})

    def test_more_events_than_phrases(self):
        text = "Lähete 3 viikkoa sitten."
        p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("REFERRAL_SENT", "2025-05-30"), ev("DIAGNOSIS", "2025-01-02")])
        out = resolve.repair(p, text, NOTE)
        self.assertEqual(out["events"], [ev("DIAGNOSIS", "2025-01-02"), ev("REFERRAL_SENT", "2025-05-28")])

    def test_month_precision_becomes_day_when_matched(self):
        p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("DIAGNOSIS", "2025-05-01", "MONTH")])
        self.assertEqual(resolve.repair(p, "Diagnoosi 2 viikkoa sitten.", NOTE)["events"], [ev("DIAGNOSIS", "2025-06-04")])

    def test_none_input_and_no_mutation(self):
        self.assertIsNone(resolve.repair(None, "x", NOTE))
        self.assertIsNone(resolve.resolve(None, "x", NOTE)["prediction"])
        p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("DIAGNOSIS", "2025-05-01")])
        before = json.dumps(p)
        resolve.repair(p, "Diagnoosi 2 viikkoa sitten.", "2025-06-18")
        self.assertEqual(json.dumps(p), before)

    def test_non_iso_event_date_is_left_alone(self):
        p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("DIAGNOSIS", "eilen")])
        self.assertEqual(resolve.repair(p, "Diagnoosi 2 viikkoa sitten.", NOTE)["events"], [ev("DIAGNOSIS", "eilen")])

    def test_unknown_arm(self):
        with self.assertRaises(ValueError):
            resolve.relative_dates("2 päivää sitten", NOTE, "B")


class ArmAPrime(unittest.TestCase):
    def days(self, text, arm="A'"):
        return [(NOTE - dt.date.fromisoformat(d)).days for d in resolve.relative_dates(text, NOTE, arm)]

    def test_arm_a_is_digits_only(self):
        for text in ("kolme viikkoa sitten", "eilen", "viikko sitten", "päivä sitten"):
            with self.subTest(text=text):
                self.assertEqual(self.days(text, "A"), [])
                self.assertEqual(resolve.needs_person_spans("kuukausi sitten", "A"), [])

    def test_number_words_one_to_six(self):
        for word, n in lexicon.NUMBER_WORDS.items():
            with self.subTest(word=word):
                self.assertEqual(self.days(f"Oireet {word} päivää sitten."), [n])
                self.assertEqual(self.days(f"Lähete {word} viikkoa sitten."), [7 * n])
                self.assertEqual(self.days(f"{word.capitalize()} viikkoa sitten lähete."), [7 * n])

    def test_single_phrases(self):
        self.assertEqual(self.days("Soitti eilen terveyskeskukseen."), [1])
        self.assertEqual(self.days("Eilen soitti."), [1])
        self.assertEqual(self.days("Lähete viikko sitten."), [7])
        self.assertEqual(self.days("Oireet alkoivat päivä sitten."), [1])
        self.assertEqual(self.days("Yksi viikko sitten."), [7])

    def test_digits_and_words_in_text_order(self):
        spans = resolve.relative_spans("eilen soitti, 3 viikkoa sitten lähete, kaksi päivää sitten kuvaus", NOTE, "A'")
        self.assertEqual([(s["phrase"], s["days"], s["source"]) for s in spans],
                         [("eilen", 1, "lexicon"), ("3 viikkoa sitten", 21, "digits"), ("kaksi päivää sitten", 2, "lexicon")])

    def test_lexicon_resolves_where_arm_a_cannot(self):
        p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("REFERRAL_SENT", "2025-05-20")])
        text = "Lähete lähetettiin kolme viikkoa sitten."
        self.assertEqual(resolve.repair(p, text, NOTE, "A"), p)
        out = resolve.resolve(p, text, NOTE, "A'")
        self.assertEqual(out["prediction"]["events"], [ev("REFERRAL_SENT", "2025-05-28")])
        self.assertEqual(out["changes"][0]["source"], "lexicon")
        self.assertEqual(out["lexicon"], lexicon.VERSION)

    def test_held_out_phrases_are_not_resolved(self):
        held = ["seitsemän", "kahdeksan", "yhdeksän", "kymmenen", "yksitoista", "kaksitoista"]
        for word in held:
            with self.subTest(word=word):
                self.assertEqual(self.days(f"{word} päivää sitten"), [])
                self.assertEqual(self.days(f"{word} viikkoa sitten"), [])
        self.assertEqual(self.days("Oireet alkoivat toissapäivänä."), [])
        self.assertEqual(resolve.needs_person_spans("Oireet alkoivat toissapäivänä.", "A'"), [])
        tables = [lexicon.NUMBER_WORDS, lexicon.UNIT_DAYS, lexicon.SINGULAR_UNIT_DAYS, lexicon.ADVERB_DAYS,
                  lexicon.TO_PERSON_UNITS, lexicon.VAGUE_QUANTIFIERS, lexicon.TO_PERSON_PHRASES]
        words = {w for t in tables for w in t}
        self.assertFalse(words & set(held + ["toissapäivänä", "toissa"]))
        self.assertNotIn("toissa", (HERE / "lexicon.py").read_text(encoding="utf-8").lower())

    def test_vague_month_and_year_go_to_a_person(self):
        for text in ("Oireet alkoivat kuukausi sitten.", "Oireet 2 kuukautta sitten.", "Kuusi kuukautta sitten.",
                     "Lähete viime kuussa.", "Pari viikkoa sitten oireita.", "Muutama päivä sitten huimausta.",
                     "Puoli vuotta sitten.", "Viime viikolla soitti."):
            with self.subTest(text=text):
                self.assertEqual(self.days(text), [])
                person = resolve.needs_person_spans(text, "A'")
                self.assertEqual(len(person), 1)
                p = dict(entry_route="PUBLIC_PRIMARY", events=[ev("SYMPTOM_ONSET_REPORTED", "2025-05-01")])
                out = resolve.resolve(p, text, NOTE, "A'")
                self.assertEqual(out["prediction"], p)
                self.assertEqual([x["phrase"] for x in out["needs_person"]], [person[0]["phrase"]])

    def test_lexicon_size(self):
        lines = [x for x in (HERE / "lexicon.py").read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertLessEqual(len(lines), 25)


class PortIsTheDiagnoseRule(unittest.TestCase):
    """Arm A equals runs/diagnose/resolve_relative.py repair() on generated SYNTHETIC notes with perturbed answers."""

    def test_equal_on_generated_notes(self):
        sys.path.insert(0, str(ROOT / "runs/diagnose"))
        try:
            original = _load("diagnose_resolve_relative", ROOT / "runs/diagnose/resolve_relative.py").repair
        except ImportError as exc:  # pyarrow missing outside scribe/.venv
            self.skipTest(f"diagnose rule not importable: {exc}")
        rng = random.Random(7)
        changed = 0
        for i in range(400):
            s = sample.sample(i)
            parts = [f["expression"] for f in s["facts"]] + [d["expression"] for d in s["distractors"]]
            rng.shuffle(parts)
            text = " ja ".join(parts)
            pred = json.loads(s["target_json"])
            for e in pred["events"]:
                if rng.random() < 0.6:
                    e["date"] = (dt.date.fromisoformat(e["date"]) + dt.timedelta(days=rng.randint(-40, 40))).isoformat()
            row = dict(note_text=text, note_date=s["note_date"])
            mine = resolve.repair(pred, text, s["note_date"], "A")
            self.assertEqual(mine, original(row, pred))
            changed += mine != pred
        self.assertGreater(changed, 100)


class Frozen(unittest.TestCase):
    def test_frozen_files_unchanged(self):
        path = ROOT / "data/scribe/v4/resolver/freeze.json"
        if not path.exists():
            self.skipTest("not frozen yet")
        rec = json.loads(path.read_text())
        for f, h in rec["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / f).read_bytes()).hexdigest(), h, f)


if __name__ == "__main__":
    unittest.main()
