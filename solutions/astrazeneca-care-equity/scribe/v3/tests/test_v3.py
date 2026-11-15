"""Offline unit tests of scribe/v3 (no network, no key): audit scoring on a hand-made fixture, gate tables,
the dataset disjointness check. Run:
  scribe/.venv/bin/python -m unittest discover -s scribe/v3/tests -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow as pa  # noqa: E402

import build_dataset  # noqa: E402
import common  # noqa: E402
import gate  # noqa: E402
import score_audit  # noqa: E402

NOTE_A = "Työterveyslääkäri tutki potilaan 3.2.2025. Lähete lähti kirurgian pkl:lle 12 päivää sitten. Syntynyt 1.1.1960."
NOTE_B = "Syöpädiagnoosi varmistui 5.3.2025."
NOTE_C = "Verenpainekontrolli hoitajalla. Sädehoito aloitettiin 2.2.2025."
NOTE_D = "Lähete tehty 4.4.2025."


def ev(index, typ, date):
    return dict(index=index, type=typ, date=date, precision="DAY")


def fixture(root):
    """Eight notes: five accepted, three rejected. Returns the expected classes by audit id."""
    items = [
        ("n1", NOTE_A, [ev(0, "PHYSICIAN_ASSESSMENT", "2025-02-03"), ev(1, "REFERRAL_SENT", "2025-02-16")], "accepted", True),
        ("n2", NOTE_B, [ev(0, "DIAGNOSIS", "2025-03-06")], "accepted", True),
        ("n3", NOTE_C, [], "accepted", False),
        ("n4", NOTE_D, [ev(0, "REFERRAL_SENT", "2025-04-04")], "accepted", True),
        ("n5", NOTE_A, [ev(0, "PHYSICIAN_ASSESSMENT", "2025-02-03"), ev(1, "REFERRAL_RECEIVED", "2025-02-16")], "rejected", True),
        ("n6", NOTE_B, [ev(0, "MDT_DECISION", "2025-03-05")], "rejected", False),
        ("n7", NOTE_B, [ev(0, "DIAGNOSIS", "2025-03-05")], "rejected", True),
        ("n8", NOTE_D, [ev(0, "REFERRAL_SENT", "2025-04-04")], "accepted", True),
    ]
    slice_items = [dict(audit_id=a, note_date="2025-02-28", note_text=t, claimed=dict(entry_route="OCCUPATIONAL", events=e)) for a, t, e, _, _ in items]
    key = dict(items={a: dict(id="id-" + a, slice=1, status=s, readback_consistent=rb, curriculum="careful", kind="careful", n_events=len(e)) for a, _, e, s, rb in items})
    answers = [
        # n1 clean: two stated verdicts with exact quotes
        dict(audit_id="n1", events=[dict(index=0, verdict="stated", quote="Työterveyslääkäri tutki potilaan 3.2.2025"), dict(index=1, verdict="stated", quote="Lähete lähti kirurgian pkl:lle 12 päivää sitten")], unlisted_event=dict(present=False, quote=""), route_ok=True),
        # n2 wrong label: the claimed day is off by one
        dict(audit_id="n2", events=[dict(index=0, verdict="wrong_date", quote="varmistui 5.3.2025")], unlisted_event=dict(present=False, quote=""), route_ok=True),
        # n3 wrong label: an unlisted event in a note claimed to have none
        dict(audit_id="n3", events=[], unlisted_event=dict(present=True, quote="Sädehoito aloitettiin 2.2.2025"), route_ok=True),
        # n4 ambiguity only
        dict(audit_id="n4", events=[dict(index=0, verdict="ambiguous", quote="Lähete tehty 4.4.2025")], unlisted_event=dict(present=False, quote=""), route_ok=True),
        # n5 not scored: the quote of the second verdict is not in the note (case differs)
        dict(audit_id="n5", events=[dict(index=0, verdict="stated", quote="tutki potilaan 3.2.2025"), dict(index=1, verdict="wrong_type", quote="lähete lähti kirurgian pkl:lle")], unlisted_event=dict(present=False, quote=""), route_ok=True),
        # n6 wrong label (not_stated needs no quote) and the route is not ok
        dict(audit_id="n6", events=[dict(index=0, verdict="not_stated", quote="")], unlisted_event=dict(present=False, quote=""), route_ok=False),
        # n7 not scored: a stated verdict without a quote
        dict(audit_id="n7", events=[dict(index=0, verdict="stated", quote="")], unlisted_event=dict(present=False, quote=""), route_ok=True),
        # n8 has no answer; the next two must be ignored and counted
        dict(audit_id="zz", events=[], unlisted_event=dict(present=False, quote=""), route_ok=True),
        dict(audit_id="n1", events=[dict(index=0, verdict="not_stated", quote=""), dict(index=1, verdict="not_stated", quote="")], unlisted_event=dict(present=False, quote=""), route_ok=True),
    ]
    root = Path(root)
    (root / "out").mkdir(parents=True)
    (root / "slice-01.json").write_text(json.dumps(slice_items, ensure_ascii=False))
    (root / "key.json").write_text(json.dumps(key, ensure_ascii=False))
    (root / "out" / "slice-01.json").write_text(json.dumps(answers, ensure_ascii=False))


class ScoreAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        fixture(self.tmp.name)
        self.r = score_audit.score(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_input_counts(self):
        i = self.r["input"]
        self.assertEqual((i["items_in_key"], i["items_answered"], i["items_missing"]), (8, 7, 1))
        self.assertEqual((i["items_with_unknown_audit_id"], i["duplicate_items"], i["invalid_files"]), (1, 1, 0))

    def test_discarded_verdicts_are_counted(self):
        v = self.r["verdicts"]
        self.assertEqual(v["total"], 15)
        self.assertEqual((v["discarded"], v["discarded_quote_not_in_note"], v["discarded_quote_missing"]), (2, 1, 1))

    def test_accepted_and_rejected(self):
        a, rj = self.r["by_status"]["accepted"], self.r["by_status"]["rejected"]
        self.assertEqual((a["notes_in_sample"], a["notes_scored"], a["notes_not_scored"]), (5, 4, 1))
        self.assertEqual((a["wrong_label"]["numerator"], a["wrong_label"]["denominator"]), (2, 4))
        self.assertEqual((a["ambiguity_only"]["numerator"], a["ambiguity_only"]["denominator"]), (1, 4))
        self.assertEqual((a["clean"]["numerator"], a["clean"]["denominator"]), (1, 4))
        self.assertEqual(a["wrong_label"]["wilson95"], [0.15, 0.85])
        self.assertEqual(a["notes_with_at_least_one"], dict(wrong_date=1, wrong_type=0, not_stated=0, unlisted_event=1, ambiguous=1))
        self.assertEqual((rj["notes_in_sample"], rj["notes_scored"], rj["notes_not_scored"]), (3, 1, 2))
        self.assertEqual((rj["wrong_label"]["numerator"], rj["wrong_label"]["denominator"]), (1, 1))
        self.assertEqual((rj["route_not_ok"]["numerator"], rj["route_not_ok"]["denominator"]), (1, 1))
        self.assertEqual(rj["ambiguity_only"]["numerator"], 0)

    def test_split_by_readback(self):
        c, i = self.r["by_readback"]["consistent"], self.r["by_readback"]["inconsistent"]
        self.assertEqual((c["notes_in_sample"], c["notes_scored"]), (6, 3))
        self.assertEqual((c["wrong_label"]["numerator"], c["ambiguity_only"]["numerator"], c["clean"]["numerator"]), (1, 1, 1))
        self.assertEqual((i["notes_in_sample"], i["notes_scored"], i["wrong_label"]["numerator"]), (2, 2, 2))
        x = self.r["by_status_and_readback"]
        self.assertEqual(x["accepted/inconsistent"]["wrong_label"]["numerator"], 1)
        self.assertEqual(x["rejected/consistent"]["notes_scored"], 0)
        self.assertEqual(x["rejected/consistent"]["wrong_label"]["share"], None)

    def test_check_verdict(self):
        self.assertIsNone(score_audit.check_verdict("stated", "varmistui 5.3.2025", NOTE_B))
        self.assertIsNone(score_audit.check_verdict("not_stated", "", NOTE_B))
        self.assertEqual(score_audit.check_verdict("stated", "varmistui  5.3.2025", NOTE_B), "quote_not_in_note")
        self.assertEqual(score_audit.check_verdict("not_stated", "ei mainintaa", NOTE_B), "quote_not_in_note")
        self.assertEqual(score_audit.check_verdict("ambiguous", "", NOTE_B), "quote_missing")
        self.assertEqual(score_audit.check_verdict("correct", "varmistui", NOTE_B), "invalid_verdict")

    def test_missing_verdict_or_unlisted_answer_is_not_scored(self):
        s = score_audit.score_item(dict(events=[dict(index=0, verdict="stated", quote="tutki potilaan 3.2.2025")], unlisted_event=dict(present=False, quote="")), NOTE_A, 2)
        self.assertFalse(s["scored"])
        s = score_audit.score_item(dict(events=[dict(index=0, verdict="stated", quote="varmistui 5.3.2025")]), NOTE_B, 1)
        self.assertFalse(s["scored"])
        s = score_audit.score_item(dict(events=[dict(index=0, verdict="stated", quote="varmistui 5.3.2025")], unlisted_event=dict(present=True, quote="ei ole")), NOTE_B, 1)
        self.assertFalse(s["scored"])
        self.assertEqual(s["discarded"]["quote_not_in_note"], 1)


class Wilson(unittest.TestCase):
    def test_known_intervals(self):
        for num, den, lo, hi in ((2, 150, 0.0037, 0.0473), (126, 150, 0.7730, 0.8901), (0, 80, 0.0, 0.0458)):
            a, b = common.wilson(num, den)
            self.assertAlmostEqual(a, lo, places=4)
            self.assertAlmostEqual(b, hi, places=4)
        self.assertEqual(common.wilson(0, 0), (None, None))


class Gate(unittest.TestCase):
    def test_order_is_fixed_and_salted(self):
        self.assertEqual(common.order_key("abc", "s"), common.order_key("abc", "s"))
        self.assertNotEqual(common.order_key("abc", "s"), common.order_key("abc", "t"))

    def test_block_counts(self):
        def cand(i, cc, rb):
            return dict(id=i, code_check=dict(passed=cc), readback=dict(consistent=rb), curriculum="terse")

        def res(ok, err=None):
            return dict(error=err, usage=dict(input_tokens=10, output_tokens=1))

        cands = [cand("a", True, True), cand("b", True, False), cand("c", True, True), cand("d", False, None)]
        judged = {
            "a": {"pass": True, "readback_consistent": True, "judge_pass": dict(jev=True, decisions=False), "judges": dict(jev=res(True), decisions=res(False))},
            "b": {"pass": True, "readback_consistent": False, "judge_pass": dict(jev=True), "judges": dict(jev=res(True))},
            "c": {"pass": False, "readback_consistent": True, "judge_pass": dict(jev=False, decisions=False), "judges": dict(jev=res(False), decisions=res(False, "ValueError: refusal"))},
        }
        b = gate.block(cands, judged)
        self.assertEqual(b["candidates"], 4)
        self.assertEqual((b["code_check_pass"]["numerator"], b["code_check_pass"]["denominator"]), (3, 4))
        self.assertEqual((b["readback_consistent"]["numerator"], b["readback_consistent"]["denominator"]), (2, 3))
        self.assertEqual((b["jev"]["accepted"]["numerator"], b["jev"]["accepted"]["denominator"]), (2, 3))
        self.assertEqual((b["decisions"]["asked"], b["decisions"]["answered"], b["decisions"]["errors"]), (2, 1, 1))
        self.assertEqual((b["decisions"]["accepted"]["numerator"], b["decisions"]["accepted"]["denominator"]), (0, 1))
        self.assertEqual((b["rule"]["accepted_of_judged"]["numerator"], b["rule"]["accepted_of_candidates"]["denominator"]), (2, 4))
        self.assertEqual(
            b["readback_vs_rule"],
            dict(readback_consistent_rule_accept=1, readback_consistent_rule_reject=1, readback_inconsistent_rule_accept=1, readback_inconsistent_rule_reject=0, n=3),
        )
        self.assertEqual(b["jev_vs_decisions"]["n"], 1)
        self.assertEqual(b["jev_vs_decisions"]["jev_accept_decisions_reject"], 1)


class Disjoint(unittest.TestCase):
    @staticmethod
    def tables(train, val):
        t = lambda rows: pa.table(dict(id=[r[0] for r in rows], note_text=[r[1] for r in rows]))  # noqa: E731
        return dict(train=t(train), val=t(val), test_nemotron=t([("t1", "x")]), test_haiku=t([("t2", "y")]), rejected=t([("r1", "z")]))

    def test_clean_split_passes(self):
        res = build_dataset.check_disjoint(self.tables([("a", "one"), ("b", "two")], [("c", "three")]))
        self.assertEqual(res["heldout"]["val"], dict(ids_shared_with_train=0, note_texts_shared_with_train=0))
        self.assertEqual(res["ids_in_two_files"], 0)

    def test_shared_id_stops_the_build(self):
        with self.assertRaises(AssertionError):
            build_dataset.check_disjoint(self.tables([("a", "one")], [("a", "three")]))

    def test_shared_note_text_stops_the_build(self):
        with self.assertRaises(AssertionError):
            build_dataset.check_disjoint(self.tables([("a", "one")], [("c", "one")]))

    def test_duplicate_text_inside_train_stops_the_build(self):
        with self.assertRaises(AssertionError):
            build_dataset.check_disjoint(self.tables([("a", "one"), ("b", "one")], [("c", "three")]))


if __name__ == "__main__":
    unittest.main()
