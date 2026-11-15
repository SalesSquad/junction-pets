"""Tests for the offline scribe demo (serve/demo). Standard library only; no model is loaded unless SAMA_SCRIBE_SLOW=1.

Run: python3 -m unittest discover -s serve/demo/tests        (any of scribe/.venv, serve/.venv or system python3)
     SAMA_SCRIBE_SLOW=1 serve/.venv/bin/python -m unittest discover -s serve/demo/tests   (also loads the model)
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent
ROOT = DEMO.parents[1]
sys.path.insert(0, str(DEMO))

import engine  # noqa: E402

DATA = ROOT / "data" / "scribe" / "demo"
CUDA = ROOT / "data" / "scribe" / "v3" / "student" / "C-270m-all-v2data" / "val-records.json"
NOTE = ("Lähete lähetettiin kolme viikkoa sitten. Hoito aloitettiin eilen. Oireet alkoivat pari viikkoa sitten. "
        "Syntynyt 3.4.1950. Diagnoosi vahvistettiin 12. maaliskuuta 2025. Arvio tehtiin helmikuussa 2025. "
        "Kontrolli 40 päivää sitten.")
NOTE_DATE = "2025-04-10"


def raw(*events, route="PUBLIC_PRIMARY"):
    return json.dumps({"entry_route": route, "events": [dict(type=t, date=d, precision=p) for t, d, p in events]},
                      separators=(",", ":"))


class ResolverArm(unittest.TestCase):
    def test_frozen_files_give_arm_a_prime(self):
        info = engine.resolver_arm()
        self.assertEqual(info["arm"], "A'")
        self.assertTrue(info["frozen"])
        self.assertEqual(set(info["files"]), {"scribe/v3/resolve.py", "scribe/v3/lexicon.py"})

    def test_changed_file_falls_back_to_arm_a(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            for rel in ("scribe/v3/resolve.py", "scribe/v3/lexicon.py", "data/scribe/v4/resolver/freeze.json"):
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, tmp / rel)
            self.assertEqual(engine.resolver_arm(tmp / "data/scribe/v4/resolver/freeze.json", tmp)["arm"], "A'")
            with open(tmp / "scribe/v3/lexicon.py", "a", encoding="utf-8") as f:
                f.write("\n# edited after the freeze\n")
            info = engine.resolver_arm(tmp / "data/scribe/v4/resolver/freeze.json", tmp)
            self.assertEqual(info["arm"], "A")
            self.assertFalse(info["frozen"])
            self.assertEqual(engine.resolver_arm(tmp / "missing.json", tmp)["arm"], "A")


class Highlights(unittest.TestCase):
    def setUp(self):
        self.resolver = engine.client().load_date_resolver()

    def test_kinds_dates_and_order(self):
        spans = engine.highlights(NOTE, NOTE_DATE, self.resolver, "A'")
        got = [(s["kind"], s["phrase"], s["date"]) for s in spans]
        self.assertEqual(got, [
            ("relative", "kolme viikkoa sitten", "2025-03-20"),
            ("relative", "eilen", "2025-04-09"),
            ("needs_person", "pari viikkoa sitten", None),
            ("absolute", "3.4.1950", "1950-04-03"),
            ("absolute", "12. maaliskuuta 2025", "2025-03-12"),
            ("absolute", "helmikuussa 2025", "2025-02-01"),
            ("relative", "40 päivää sitten", "2025-03-01"),
        ])
        for s in spans:
            self.assertEqual(NOTE[s["start"]:s["end"]], s["phrase"])

    def test_arm_a_sees_digits_only(self):
        kinds = {(s["kind"], s["phrase"]) for s in engine.highlights(NOTE, NOTE_DATE, self.resolver, "A")}
        self.assertIn(("relative", "40 päivää sitten"), kinds)
        self.assertNotIn(("relative", "kolme viikkoa sitten"), kinds)
        self.assertNotIn(("relative", "eilen"), kinds)


class Postprocess(unittest.TestCase):
    def test_code_redates_relative_events_and_keeps_written_ones(self):
        out = engine.postprocess(raw(("REFERRAL_SENT", "2025-03-15", "DAY"), ("TREATMENT_START", "2025-04-02", "DAY"),
                                     ("DIAGNOSIS", "2025-03-12", "DAY")), NOTE, NOTE_DATE, "A'")
        events = {e["type"]: e for e in out["resolved"]["events"]}
        self.assertEqual(events["REFERRAL_SENT"]["date"], "2025-03-20")
        self.assertEqual(events["REFERRAL_SENT"]["model_date"], "2025-03-15")
        self.assertTrue(events["REFERRAL_SENT"]["date_computed_by_code"])
        self.assertEqual(events["REFERRAL_SENT"]["phrase"], "kolme viikkoa sitten")
        self.assertEqual(events["TREATMENT_START"]["date"], "2025-04-09")
        self.assertEqual(events["TREATMENT_START"]["phrase"], "eilen")
        self.assertFalse(events["DIAGNOSIS"]["date_computed_by_code"])
        self.assertEqual(events["DIAGNOSIS"]["phrase_kind"], "absolute")
        self.assertEqual(out["person_confirms"], "a person confirms every event")
        for e in out["resolved"]["events"]:
            self.assertEqual(e["status"], "proposed; a person confirms every event")
        # "pari viikkoa sitten" has no single day: a person sets it, so the note needs editing.
        self.assertEqual(out["review"], engine.NEEDS_EDITING)
        self.assertIn("relative_date_needs_person", out["flags"])

    def test_clean_note_is_prefilled(self):
        note = "Diagnoosi vahvistettiin 12. maaliskuuta 2025. Hoito aloitettiin 3 viikkoa sitten."
        out = engine.postprocess(raw(("DIAGNOSIS", "2025-03-12", "DAY"), ("TREATMENT_START", "2025-03-25", "DAY")), note, NOTE_DATE, "A'")
        self.assertEqual(out["review"], engine.PREFILLED)
        self.assertEqual([e["date"] for e in out["resolved"]["events"]], ["2025-03-12", "2025-03-20"])

    def test_two_reader_rule(self):
        note = "Diagnoosi vahvistettiin 12. maaliskuuta 2025. Hoito aloitettiin 3 viikkoa sitten."
        base = engine.postprocess(raw(("DIAGNOSIS", "2025-03-12", "DAY"), ("TREATMENT_START", "2025-03-25", "DAY")), note, NOTE_DATE, "A'")
        same = json.loads(json.dumps(base["resolved"]["prediction"]))
        other = json.loads(json.dumps(same))
        other["events"][0]["date"] = "2025-03-13"
        agree = engine.apply_second_reader(json.loads(json.dumps(base)), same, True, source="x")
        self.assertEqual(agree["review"], engine.PREFILLED)
        self.assertTrue(agree["second_reader"]["agrees"])
        differ = engine.apply_second_reader(json.loads(json.dumps(base)), other, True, source="x")
        self.assertEqual(differ["review"], engine.NEEDS_EDITING)
        self.assertEqual(differ["review_reason"], "readers disagree")
        missing = engine.apply_second_reader(json.loads(json.dumps(base)), None, False)
        self.assertEqual(missing["review"], engine.NEEDS_EDITING)
        self.assertEqual(missing["review_reason"], engine.NOT_RUN)
        flagged = engine.postprocess(raw(("DIAGNOSIS", "2025-03-12", "DAY")), NOTE, NOTE_DATE, "A'")
        flagged = engine.apply_second_reader(flagged, flagged["resolved"]["prediction"], True, source="x")
        self.assertEqual(flagged["review"], engine.NEEDS_EDITING)  # agreement never overrides a flag
        again = engine.apply_second_reader(agree, other, True, source="x")  # idempotent on the first reader's review
        self.assertEqual(again["single_reader_review"], engine.PREFILLED)
        self.assertEqual(again["review"], engine.NEEDS_EDITING)

    def test_unusable_answer_needs_editing(self):
        for bad in ("not json", '{"entry_route":"SCREENING"}', raw(("DIAGNOSIS", "2025-02-30", "DAY"))):
            out = engine.postprocess(bad, NOTE, NOTE_DATE, "A'")
            self.assertEqual(out["review"], engine.NEEDS_EDITING, bad)
            self.assertTrue(out["errors"], bad)
            self.assertEqual(out["resolved"]["events"], [])

    def test_no_banned_wording(self):
        text = json.dumps(engine.postprocess(raw(("DIAGNOSIS", "2025-03-12", "DAY")), NOTE, NOTE_DATE, "A'")).lower()
        for word in engine.BANNED:
            self.assertNotIn(word, text)

    def test_check_note(self):
        engine.check_note("x", "2025-01-31")
        for text, day in (("", "2025-01-01"), ("x" * (engine.MAX_NOTE_CHARS + 1), "2025-01-01"), ("x", "2025-02-30"),
                          ("x", "20250101"), (None, "2025-01-01"), ("x", None)):
            with self.assertRaises(ValueError):
                engine.check_note(text, day)


class StoredDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notes = json.loads((DATA / "demo-notes.json").read_text(encoding="utf-8"))
        cls.outputs = json.loads((DATA / "demo-outputs.json").read_text(encoding="utf-8"))
        cls.cuda = {r["id"]: r for r in json.loads(CUDA.read_text(encoding="utf-8"))}

    def test_twenty_synthetic_validation_notes(self):
        notes = self.notes["notes"]
        self.assertEqual(len(notes), 20)
        self.assertTrue(self.notes["synthetic"])
        self.assertEqual([n["demo_id"] for n in notes], [f"demo-{i:02d}" for i in range(1, 21)])
        for n in notes:
            self.assertTrue(n["synthetic"])
            self.assertEqual(n["source_split"], "val")
            self.assertIn(n["source_id"], self.cuda)  # a validation note: the stored validation records hold it
            self.assertNotIn(n["source_id"], self.notes["probe_ids"])
            if not n["rewritten_by_code"]:
                self.assertEqual(n["cuda"]["raw"], self.cuda[n["source_id"]]["raw"])
        self.assertEqual(len({n["source_id"] for n in notes}), 20)

    def test_code_written_phrases(self):
        rewritten = [n for n in self.notes["notes"] if n["rewritten_by_code"]]
        self.assertEqual(len(rewritten), 3)
        self.assertTrue(any("kolme viikkoa sitten" in n["note_text"] for n in rewritten))
        self.assertTrue(any(" eilen" in n["note_text"] for n in rewritten))
        self.assertGreaterEqual(sum(n["rewrite_kind"].startswith("number_word") for n in rewritten), 2)
        resolver = engine.client().load_date_resolver()
        for n in rewritten:
            gate = n["rewrite_gate"]
            self.assertTrue(gate["phrase_present_once"] and gate["arm_A_prime_resolves_to_key"] and not gate["arm_A_resolves"])
            spans = resolver.relative_spans(n["note_text"], n["note_date"], "A'")
            self.assertIn((n["rewrite"]["to_phrase"], n["rewrite"]["to_date"]), {(s["phrase"], s["date"]) for s in spans})
            self.assertIn(n["rewrite"]["to_date"], {e["date"] for e in n["answer_key"]["events"]})

    def test_outputs_are_reproducible_from_the_raw_answer(self):
        """The stored payload is exactly what the post-processing makes of the stored model answer."""
        results = self.outputs["results"]
        self.assertEqual(sorted(results), [n["demo_id"] for n in self.notes["notes"]])
        arm = self.outputs["provenance"]["resolver"]["arm"]
        self.assertEqual(arm, "A'")
        second = engine.load_second_reader()
        for n in self.notes["notes"]:
            r = results[n["demo_id"]]
            self.assertEqual(r["note"]["note_text"], n["note_text"])
            again = engine.postprocess(r["model"]["raw"], n["note_text"], n["note_date"], arm)
            # then the two-reader rule with Nemotron's stored answer (none for notes rewritten by code)
            available = not n["rewritten_by_code"] and n["source_id"] in second
            engine.apply_second_reader(again, second.get(n["source_id"]), available, source="data/scribe/nemotron/val-v3.jsonl")
            for key in ("highlights", "model", "resolved", "date_resolution", "flags", "errors", "single_reader_review",
                        "second_reader", "review", "review_reason", "person_confirms"):
                self.assertEqual(json.loads(json.dumps(again[key])), r[key], f"{n['demo_id']}: {key}")
            self.assertEqual(r["exact_match_with_answer_key"], r["resolved"]["prediction"] == n["answer_key"])
            self.assertIn(r["review"], (engine.PREFILLED, engine.NEEDS_EDITING))
            self.assertEqual(r["provenance"]["decoding"]["device"], "cpu")


@unittest.skipUnless(os.environ.get("SAMA_SCRIBE_SLOW") == "1", "loads the model; set SAMA_SCRIBE_SLOW=1 (serve/.venv)")
class LoadedModel(unittest.TestCase):
    def test_engine_reproduces_two_stored_demo_outputs(self):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        notes = json.loads((DATA / "demo-notes.json").read_text(encoding="utf-8"))["notes"]
        stored = json.loads((DATA / "demo-outputs.json").read_text(encoding="utf-8"))["results"]
        e = engine.Engine()
        for n in (notes[0], notes[1]):
            r = e.extract(n["note_text"], n["note_date"], n["demo_id"], True)
            self.assertEqual(r["model"]["raw"], stored[n["demo_id"]]["model"]["raw"])
            self.assertEqual(r["resolved"], stored[n["demo_id"]]["resolved"])


if __name__ == "__main__":
    unittest.main()
