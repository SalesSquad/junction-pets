"""The resolver inside the product client (serve/client.py) and the cascade (scribe/v3/cascade.py). No network, no key.

Run: scribe/.venv/bin/python -m unittest discover -s scribe/v3/tests -p 'test_resolve*.py' -v
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


client = _load("sama_serve_client_under_test", ROOT / "serve/client.py")
PROMPTS = client.load_prompts()
SCHEMA = client.load_schema("absolute")
NOTE_DATE = "2025-06-18"


def answer(*events, route="PUBLIC_PRIMARY"):
    return json.dumps(dict(entry_route=route, events=[dict(type=t, date=d, precision="DAY") for t, d in events]))


def decode(content, text, arm="A'"):
    return client.decode_output(content, "absolute", NOTE_DATE, PROMPTS.canonicalise, SCHEMA, note_text=text, relative_dates=arm)


class ClientDecode(unittest.TestCase):
    def test_relative_date_is_recomputed_after_schema_validation(self):
        text = "Lähete lähetettiin 3 viikkoa sitten, diagnoosi 5.3.2025."
        out = decode(answer(("REFERRAL_SENT", "2025-05-20"), ("DIAGNOSIS", "2025-03-05")), text)
        self.assertEqual(out["errors"], [])
        self.assertEqual([e["date"] for e in out["canonical"]["events"]], ["2025-03-05", "2025-05-28"])
        self.assertEqual(out["date_resolution"]["arm"], "A'")
        self.assertEqual([(c["from_date"], c["to_date"], c["phrase"]) for c in out["date_resolution"]["changes"]],
                         [("2025-05-20", "2025-05-28", "3 viikkoa sitten")])
        self.assertEqual(out["flags"], [])

    def test_off_and_missing_note_text_keep_the_old_behaviour(self):
        content = answer(("REFERRAL_SENT", "2025-05-20"))
        for arm, text in (("off", "Lähete 3 viikkoa sitten."), ("A'", None)):
            with self.subTest(arm=arm):
                out = decode(content, text, arm)
                self.assertEqual(out["canonical"]["events"][0]["date"], "2025-05-20")
                self.assertIsNone(out["date_resolution"])
        old = client.decode_output(content, "absolute", NOTE_DATE, PROMPTS.canonicalise, SCHEMA)
        self.assertEqual(old["canonical"]["events"][0]["date"], "2025-05-20")

    def test_lexicon_phrase_in_arm_a_prime_only(self):
        text = "Lähete lähetettiin kolme viikkoa sitten."
        content = answer(("REFERRAL_SENT", "2025-05-20"))
        self.assertEqual(decode(content, text, "A")["canonical"]["events"][0]["date"], "2025-05-20")
        self.assertEqual(decode(content, text, "A'")["canonical"]["events"][0]["date"], "2025-05-28")

    def test_month_ago_goes_to_a_person(self):
        out = decode(answer(("SYMPTOM_ONSET_REPORTED", "2025-05-18")), "Oireet alkoivat kuukausi sitten.")
        self.assertEqual(out["canonical"]["events"][0]["date"], "2025-05-18")
        self.assertIn("relative_date_needs_person", out["flags"])
        self.assertEqual(out["date_resolution"]["needs_person"][0]["phrase"], "kuukausi sitten")
        decision, reasons, _ = client.route_decision(out, {"geo_mean_prob": 1.0}, "stop", 0.5, "geo_mean_prob", "e1")
        self.assertEqual(decision, "HUMAN_REVIEW")
        self.assertIn("relative_date_needs_person", reasons)

    def test_model_future_date_keeps_its_warning_after_re_dating(self):
        out = decode(answer(("SPECIALIST_VISIT", "2031-01-14")), "Erikoislääkäri 2 viikkoa sitten.")
        self.assertEqual(out["canonical"]["events"][0]["date"], "2025-06-04")
        self.assertIn("event_after_note_date", out["flags"])

    def test_event_scores_follow_re_dated_events(self):
        text = "Oireet 2 päivää sitten, lähete 1.6.2025."
        content = answer(("SYMPTOM_ONSET_REPORTED", "2025-05-01"), ("REFERRAL_SENT", "2025-06-01"))
        out = decode(content, text)
        self.assertEqual([e["type"] for e in out["canonical"]["events"]], ["REFERRAL_SENT", "SYMPTOM_ONSET_REPORTED"])
        scores = client._reorder_event_scores(out, "absolute", NOTE_DATE, [0.1, 0.9], None, text, "A'", None)
        self.assertEqual(scores, [0.9, 0.1])

    def test_client_default_arm_is_the_selected_one(self):
        rep = json.loads((ROOT / "data/scribe/v4/resolver/reproduce-v1.json").read_text())
        self.assertEqual(client.DEFAULT_RELATIVE_DATES, rep["arm_Aprime"]["product_default_arm"])
        c = client.ScribeClient("http://127.0.0.1:9")
        self.assertEqual(c.relative_dates, client.DEFAULT_RELATIVE_DATES)
        self.assertIn("scribe-v3-relative-resolver-v1", c.date_resolver_source)
        with self.assertRaises(client.ScribeError):
            client.ScribeClient("http://127.0.0.1:9", relative_dates="B")
        import argparse

        p = argparse.ArgumentParser()
        client.add_endpoint_arguments(p)
        self.assertEqual(p.parse_args([]).relative_dates, client.DEFAULT_RELATIVE_DATES)
        self.assertEqual(p.parse_args(["--relative-dates", "off"]).relative_dates, "off")


class Cascade(unittest.TestCase):
    def test_resolved_file_set_and_outcome(self):
        sys.path.insert(0, str(HERE))
        cascade = _load("sama_cascade_under_test", HERE / "cascade.py")
        self.assertEqual(cascade.RESOLVE, "off")
        self.assertEqual(cascade.PLAN.name, "plan-v1.json")
        meta = dict(id="x", note_text="Lähete 3 viikkoa sitten.", note_date=NOTE_DATE,
                    target_json=json.dumps(dict(entry_route="PRIVATE", events=[dict(type="REFERRAL_SENT", date="2025-05-28", precision="DAY")])))
        rec = dict(prediction=dict(entry_route="PRIVATE", events=[dict(type="REFERRAL_SENT", date="2025-05-20", precision="DAY")]))
        self.assertEqual(cascade.resolve_note(rec, meta, False, "off")[1], False)
        fixed, outcome = cascade.resolve_note(rec, meta, False, "A'")
        self.assertTrue(outcome)
        self.assertEqual(fixed["prediction_unresolved"], rec["prediction"])
        with self.assertRaises(SystemExit):
            cascade.resolve_note(rec, meta, True, "A'")  # stored outcome must equal exact match of the stored prediction
        cascade.use_resolver("A'")
        self.assertEqual(cascade.PLAN.name, "plan-v2-resolved-Aprime.json")
        self.assertEqual(cascade.RESULT.name, "cascade-v2-resolved-Aprime.json")


if __name__ == "__main__":
    unittest.main()
