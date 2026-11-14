"""Offline tests for the judges: fake transports only, nothing is sent anywhere.

  scribe/.venv/bin/python -m unittest discover -s scribe/judges/tests -v
"""

import asyncio
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analysis  # noqa: E402
import benchmark  # noqa: E402
import core  # noqa: E402
import corrupt  # noqa: E402
import run as runner  # noqa: E402

NOTE = "Potilas tuli päivystykseen. Lääkärin arvio tehtiin 3.2.2026 ja lähete lähetettiin 10.2.2026."
DATE = "2026-03-01"
CLAIM = {
    "entry_route": "EMERGENCY",
    "events": [
        {"type": "PHYSICIAN_ASSESSMENT", "date": "2026-02-03", "precision": "DAY"},
        {"type": "REFERRAL_SENT", "date": "2026-02-10", "precision": "DAY"},
        {"type": "DIAGNOSIS", "date": "2026-02-01", "precision": "MONTH"},
    ],
}
ENV = {"TYPESAFE_API_KEY": "test-typesafe", "OPENAI_API_KEY": "test-openai"}


class Fake:
    """Well-formed answers for both services; counts calls; can be told to misbehave."""

    def __init__(self, mode="ok", p_event=0.9, p_unlisted=0.1, route="EMERGENCY"):
        self.mode, self.calls, self.p_event, self.p_unlisted, self.route = mode, [], p_event, p_unlisted, route

    async def __call__(self, url, headers, body):
        self.calls.append(url)
        await asyncio.sleep(0)
        if self.mode == "http_500":
            return 500, {"error": {"code": "server_error"}}
        if self.mode == "model_refused":
            return 404, {"error": {"code": "model_not_found"}}
        if self.mode == "not_json":
            return 200, None
        dist = {r: (1.0 if r == self.route else 0.0) for r in core.ROUTES}
        if url == core.TYPESAFE_URL:
            answers = {}
            for name, q in body["questions"].items():
                if q["type"] == "choice":
                    answers[name] = {"type": "choice", "choice": self.route, "probabilities": dist, "confidence": 1.0}
                else:
                    answers[name] = {"type": "noul", "noul": self.p_unlisted if name == "unlisted" else self.p_event}
            if self.mode == "missing_answer":
                answers.pop("unlisted")
            if self.mode == "bad_probability":
                answers["unlisted"]["noul"] = 1.7
            if self.mode == "no_usage":
                return 200, {"answers": answers}
            return 200, {"model": body["model"], "answers": answers, "usage": {"input_tokens": 1000, "output_tokens": 100}}
        answers = []
        for q in body["questions"]:
            if q["type"] == "choice":
                answers.append(
                    {"type": "choice", "name": q["name"], "choice": self.route, "confidence": 1.0,
                     "probabilities": [{"value": k, "probability": v} for k, v in dist.items()]}
                )
            else:
                answers.append({"type": "predicate", "name": q["name"], "probability": self.p_unlisted if q["name"] == "unlisted" else self.p_event})
        if self.mode == "refusal":
            answers[0] = {"type": "refusal", "name": answers[0]["name"]}
        if self.mode == "missing_answer":
            answers.pop(0)
        if self.mode == "bad_probability":
            answers[0]["probability"] = "high"
        if self.mode == "no_usage":
            return 200, {"answers": answers}
        return 200, {"answers": answers, "usage": {"input_tokens": 1200}}


def judges(tmp, fake, **kw):
    return core.Judges(out_dir=tmp, post=fake, env=kw.pop("env", ENV), **kw)


TH = {"jev": {"event_min": 0.5, "unlisted_max": 0.5, "route_min": 0.5}, "decisions": {"event_min": 0.5, "unlisted_max": 0.5, "route_min": 0.5}}


class Corruptions(unittest.TestCase):
    def diff(self, kind, ident="n1"):
        new, change = corrupt.corrupt(kind, CLAIM, DATE, ident)
        return new, change

    def test_claim_is_not_modified_and_every_kind_differs(self):
        before = copy.deepcopy(CLAIM)
        for kind in corrupt.KINDS:
            for ident in ("a", "b", "c", "d", "e"):
                new, change = corrupt.corrupt(kind, CLAIM, DATE, ident)
                self.assertEqual(CLAIM, before)
                self.assertNotEqual(new, CLAIM, kind)
                self.assertEqual(change["kind"], kind)
                self.assertEqual(corrupt.corrupt(kind, CLAIM, DATE, ident), (new, change))  # deterministic

    def test_date_shift_days_changes_one_day_date_by_1_to_3_days(self):
        for ident in map(str, range(40)):
            new, ch = corrupt.corrupt("date_shift_days", CLAIM, DATE, ident)
            self.assertEqual(new["entry_route"], CLAIM["entry_route"])
            changed = [i for i, (a, b) in enumerate(zip(CLAIM["events"], new["events"])) if a != b]
            self.assertEqual(changed, [ch["index"]])
            a, b = CLAIM["events"][ch["index"]], new["events"][ch["index"]]
            self.assertEqual((a["type"], a["precision"]), (b["type"], b["precision"]))
            self.assertEqual(a["precision"], "DAY")
            delta = (dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])).days
            self.assertIn(abs(delta), (1, 2, 3))
            self.assertLessEqual(b["date"], DATE)

    def test_date_shift_month_changes_one_date_by_one_calendar_month(self):
        for ident in map(str, range(40)):
            new, ch = corrupt.corrupt("date_shift_month", CLAIM, DATE, ident)
            changed = [i for i, (a, b) in enumerate(zip(CLAIM["events"], new["events"])) if a != b]
            self.assertEqual(changed, [ch["index"]])
            a, b = CLAIM["events"][ch["index"]], new["events"][ch["index"]]
            self.assertEqual((a["type"], a["precision"]), (b["type"], b["precision"]))
            da, db = dt.date.fromisoformat(a["date"]), dt.date.fromisoformat(b["date"])
            self.assertEqual(abs((db.year * 12 + db.month) - (da.year * 12 + da.month)), 1)
            if a["precision"] == "MONTH":
                self.assertEqual(db.day, 1)
        self.assertEqual(corrupt._shift_month(dt.date(2026, 3, 31), -1), dt.date(2026, 2, 28))
        self.assertEqual(corrupt._shift_month(dt.date(2025, 12, 15), 1), dt.date(2026, 1, 15))

    def test_type_swap_changes_one_type_to_its_neighbour(self):
        for ident in map(str, range(40)):
            new, ch = corrupt.corrupt("type_swap", CLAIM, DATE, ident)
            changed = [i for i, (a, b) in enumerate(zip(CLAIM["events"], new["events"])) if a != b]
            self.assertEqual(changed, [ch["index"]])
            a, b = CLAIM["events"][ch["index"]], new["events"][ch["index"]]
            self.assertEqual((a["date"], a["precision"]), (b["date"], b["precision"]))
            self.assertEqual(b["type"], corrupt.NEIGHBOUR[a["type"]])
            self.assertEqual(new["entry_route"], CLAIM["entry_route"])

    def test_event_removed_drops_exactly_one_event(self):
        for ident in map(str, range(20)):
            new, ch = corrupt.corrupt("event_removed", CLAIM, DATE, ident)
            self.assertEqual(len(new["events"]), len(CLAIM["events"]) - 1)
            self.assertEqual(new["events"], [e for i, e in enumerate(CLAIM["events"]) if i != ch["index"]])
            self.assertEqual(ch["removed"], CLAIM["events"][ch["index"]])
            self.assertEqual(new["entry_route"], CLAIM["entry_route"])

    def test_event_added_appends_exactly_one_new_type(self):
        for ident in map(str, range(20)):
            new, ch = corrupt.corrupt("event_added", CLAIM, DATE, ident)
            self.assertEqual(new["events"][:-1], CLAIM["events"])
            added = new["events"][-1]
            self.assertEqual(added, ch["added"])
            self.assertNotIn(added["type"], {e["type"] for e in CLAIM["events"]})
            self.assertNotIn(added["date"], {e["date"] for e in CLAIM["events"]})
            self.assertLess(added["date"], DATE)
            self.assertEqual(new["entry_route"], CLAIM["entry_route"])

    def test_route_swap_changes_only_the_route(self):
        for ident in map(str, range(20)):
            new, ch = corrupt.corrupt("route_swap", CLAIM, DATE, ident)
            self.assertEqual(new["events"], CLAIM["events"])
            self.assertNotEqual(new["entry_route"], CLAIM["entry_route"])
            self.assertIn(new["entry_route"], core.ROUTES)


def fake_rows(n=400):
    rows = []
    for w in benchmark.WRITERS.values():
        for i in range(n):
            rows.append(
                dict(id=f"{w}-{i}", accepted=True, writer=w, kind="standard", note_text=NOTE, note_date=DATE,
                     entry_route=CLAIM["entry_route"], events=copy.deepcopy(CLAIM["events"]))
            )
    rows.append(dict(rows[0], id="no-event", kind="no_event", events=[]))
    rows.append(dict(rows[0], id="rejected", accepted=False))
    return rows


class Design(unittest.TestCase):
    def setUp(self):
        self.notes = benchmark.select_notes(fake_rows())
        self.pairs = benchmark.make_pairs(self.notes)

    def test_halves_are_disjoint_and_balanced(self):
        cal = {p["note_id"] for p in self.pairs if p["half"] == "calibration"}
        rep = {p["note_id"] for p in self.pairs if p["half"] == "report"}
        self.assertFalse(cal & rep)
        self.assertEqual((len(cal), len(rep)), (150, 150))
        for w in benchmark.WRITERS:
            self.assertEqual(sum(n["writer_short"] == w for n in self.notes), 150)
            self.assertEqual(sum(n["writer_short"] == w and n["half"] == "calibration" for n in self.notes), 75)

    def test_one_clean_and_one_corrupted_pair_per_note_six_kinds_balanced(self):
        self.assertEqual(len(self.pairs), 600)
        self.assertEqual(len({p["id"] for p in self.pairs}), 600)
        for n in {p["note_id"] for p in self.pairs}:
            labels = sorted(p["label"] for p in self.pairs if p["note_id"] == n)
            self.assertEqual(labels, ["clean", "corrupted"])
        for k in corrupt.KINDS:
            self.assertEqual(sum(p["label"] == "corrupted" and p["kind"] == k for p in self.pairs), 50)
        self.assertNotIn("no-event", {p["note_id"] for p in self.pairs})
        self.assertNotIn("rejected", {p["note_id"] for p in self.pairs})

    def test_the_note_is_never_changed_and_clean_pairs_keep_the_key(self):
        for p in self.pairs:
            self.assertEqual((p["note_text"], p["note_date"]), (NOTE, DATE))
            same = p["entry_route"] == CLAIM["entry_route"] and p["events"] == CLAIM["events"]
            self.assertEqual(same, p["label"] == "clean")


class Requests(unittest.TestCase):
    def test_both_judges_get_the_same_questions(self):
        j = core.jev_body(NOTE, DATE, CLAIM["events"])
        d = core.decisions_body(NOTE, DATE, CLAIM["events"])
        self.assertEqual(list(j["questions"]), [q["name"] for q in d["questions"]])
        self.assertEqual(list(j["questions"]), ["event_0", "event_1", "event_2", "unlisted", "route"])
        for q in d["questions"]:
            self.assertEqual(q["instructions"], j["questions"][q["name"]]["instructions"])
        self.assertEqual(j["questions"]["route"]["type"], "choice")
        self.assertEqual(set(j["questions"]["route"]["criteria"]), set(core.ROUTES))
        self.assertEqual({c["value"] for c in d["questions"][-1]["choices"]}, set(core.ROUTES))
        self.assertIn("2026-02-03", j["questions"]["event_0"]["instructions"])
        self.assertIn("calendar month 2026-02", j["questions"]["event_2"]["instructions"])
        self.assertIn(DATE, j["questions"]["unlisted"]["instructions"])
        self.assertNotIn("EMERGENCY", json.dumps(j["state"]))  # the claimed route is not shown


class QuestionSetV2(unittest.TestCase):
    def test_v2_adds_only_the_day_offset_and_v1_is_unchanged(self):
        v1 = core.jev_body(NOTE, DATE, CLAIM["events"])
        v2 = core.jev_body(NOTE, DATE, CLAIM["events"], "v2")
        self.assertEqual(v1, core.jev_body(NOTE, DATE, CLAIM["events"], "v1"))
        self.assertNotEqual(core.request_hash(v1), core.request_hash(v2))
        self.assertIn("(that is 26 days, i.e. 3 weeks and 5 days before the note date 2026-03-01)", v2["questions"]["event_0"]["instructions"])
        self.assertIn("(that is 19 days, i.e. 2 weeks and 5 days before the note date 2026-03-01)", v2["questions"]["event_1"]["instructions"])
        self.assertEqual(v1["questions"]["event_2"], v2["questions"]["event_2"])  # MONTH precision: no offset
        self.assertEqual(v1["questions"]["unlisted"], v2["questions"]["unlisted"])
        self.assertEqual(v1["questions"]["route"], v2["questions"]["route"])
        self.assertEqual(core.offset_hint("2026-03-01", {"date": "2026-03-01", "precision": "DAY"}), " (that is the note date itself)")
        self.assertEqual(core.offset_hint("2026-03-01", {"date": "2026-02-26", "precision": "DAY"}), " (that is 3 days before the note date 2026-03-01)")
        self.assertEqual(core.offset_hint("2026-03-01", {"date": "2026-02-15", "precision": "DAY"}), " (that is 14 days, i.e. 2 weeks before the note date 2026-03-01)")
        with self.assertRaises(ValueError):
            core.build_questions(DATE, CLAIM["events"], "v3")

    def test_run_file_follows_the_question_set_of_the_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in.jsonl").write_text(json.dumps(dict(id="x", note_text=NOTE, note_date=DATE, **CLAIM)) + "\n")
            p1, p2 = tmp / "p1.json", tmp / "p2.json"
            p1.write_text(json.dumps({"rule": "jev", "thresholds": TH}))
            p2.write_text(json.dumps({"rule": "jev", "jev_question_set": "v2", "thresholds": TH}))
            fake = Fake()
            J = judges(tmp / "j", fake)
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev",), policy_path=p1, J=J)
            self.assertEqual(json.loads((tmp / "out.jsonl").read_text())["judges"]["jev"]["question_set"], "v1")
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev",), policy_path=p2, J=judges(tmp / "j", fake))
            o = json.loads((tmp / "out.jsonl").read_text())
            self.assertEqual(o["judges"]["jev"]["question_set"], "v2")  # a v1 answer is not reused for a v2 policy
            self.assertEqual(len(fake.calls), 2)
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev",), policy_path=p2, J=judges(tmp / "j", fake))
            self.assertEqual(len(fake.calls), 2)


class CacheAndBudget(unittest.TestCase):
    def test_cache_prevents_a_second_paid_call(self):
        for judge in ("jev", "decisions"):
            with tempfile.TemporaryDirectory() as tmp:
                fake = Fake()
                J = judges(tmp, fake)
                ask = getattr(J, judge)
                a = asyncio.run(ask(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
                b = asyncio.run(ask(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
                self.assertEqual(len(fake.calls), 1)
                self.assertFalse(a["cached"])
                self.assertTrue(b["cached"])
                self.assertEqual(a["probabilities"], b["probabilities"])
                # a new process (new Judges object) also reads the cache and the ledger
                J2 = judges(tmp, fake)
                c = asyncio.run(getattr(J2, judge)(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
                self.assertTrue(c["cached"])
                self.assertEqual(len(fake.calls), 1)
                self.assertEqual(J2.ledger[judge].d["requests"], 1)

    def test_identical_requests_in_flight_are_paid_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            J = judges(tmp, fake)

            async def go():
                return await asyncio.gather(*(J.decisions(NOTE, DATE, r, CLAIM["events"]) for r in ("EMERGENCY", "PRIVATE", "EMERGENCY")))

            res = asyncio.run(go())
            self.assertEqual(len(fake.calls), 1)  # the claimed route is not part of the request
            self.assertEqual(res[0]["probabilities"]["route"], 1.0)
            self.assertEqual(res[1]["probabilities"]["route"], 0.0)
            self.assertTrue(core.judge_pass(res[0], TH["decisions"]))
            self.assertFalse(core.judge_pass(res[1], TH["decisions"]))

    def test_a_changed_claim_is_a_new_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            J = judges(tmp, fake)
            asyncio.run(J.jev(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
            asyncio.run(J.jev(NOTE, DATE, "EMERGENCY", CLAIM["events"][:2]))
            self.assertEqual(len(fake.calls), 2)

    def test_budgets_stop_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            J = judges(tmp, fake, max_tokens_openai=4000, max_usd_typesafe=30_000 * core.TYPESAFE_USD_PER_TOKEN)
            first = asyncio.run(J.decisions(NOTE, DATE, "EMERGENCY", CLAIM["events"]))  # 1200 tokens used
            self.assertIsNone(first["error"])
            second = asyncio.run(J.decisions(NOTE, DATE, "EMERGENCY", CLAIM["events"][:2]))  # 1200 + 3000 > 4000
            self.assertTrue(second["error"].startswith("BUDGET_STOP"))
            self.assertEqual(len(fake.calls), 1)
            self.assertFalse(core.judge_pass(second, TH["decisions"]))
            self.assertEqual(J.ledger["decisions"].d["tokens"], 1200)
            j1 = asyncio.run(J.jev(NOTE, DATE, "EMERGENCY", CLAIM["events"]))  # 1100 tokens used, 20000 reserved
            self.assertIsNone(j1["error"])
            j2 = asyncio.run(J.jev(NOTE, DATE, "EMERGENCY", CLAIM["events"][:2]))  # 1100 + 20000 > 30000? no
            self.assertIsNone(j2["error"])
            j3 = asyncio.run(J.jev(NOTE, DATE, "EMERGENCY", CLAIM["events"][:1]))  # 2200 + 20000 <= 30000
            self.assertIsNone(j3["error"])
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            J = judges(tmp, fake, max_usd_typesafe=0.0)
            r = asyncio.run(J.jev(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
            self.assertTrue(r["error"].startswith("BUDGET_STOP"))
            self.assertEqual(fake.calls, [])

    def test_a_failed_request_keeps_its_reservation_and_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(mode="http_500")
            J = judges(tmp, fake)
            r = asyncio.run(J.decisions(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
            self.assertIn("HTTP 500", r["error"])
            self.assertEqual(len(fake.calls), 1)  # never retried automatically
            self.assertEqual(J.ledger["decisions"].d["reserved_tokens"], 3000)
            self.assertEqual(J.ledger["decisions"].d["failed_attempts"], 1)
            self.assertFalse(list(Path(tmp).glob("cache/decisions/*.json")))

    def test_missing_key_is_not_configured_and_nothing_is_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            J = judges(tmp, fake, env={})
            for judge in ("jev", "decisions"):
                r = asyncio.run(getattr(J, judge)(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
                self.assertEqual(r["error"], "NOT_CONFIGURED")
                self.assertFalse(core.judge_pass(r, TH[judge]))
            self.assertEqual(fake.calls, [])


class NeverAPass(unittest.TestCase):
    def test_refused_failed_or_malformed_answers_never_pass(self):
        loose = {"event_min": 0.0, "unlisted_max": 1.01, "route_min": 0.0}
        for mode in ("http_500", "model_refused", "not_json", "missing_answer", "bad_probability", "no_usage", "refusal"):
            for judge in ("jev", "decisions"):
                with tempfile.TemporaryDirectory() as tmp:
                    r = asyncio.run(getattr(judges(tmp, Fake(mode=mode)), judge)(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
                    if mode == "refusal" and judge == "jev":
                        continue  # Jev has no refusal answer type
                    self.assertTrue(r["error"], (mode, judge))
                    self.assertEqual(r["probabilities"], {})
                    self.assertFalse(core.judge_pass(r, loose), (mode, judge))
                    for rule in ("jev", "decisions", "both", "either"):
                        self.assertFalse(core.rule_pass(rule, {judge: r}, {"jev": loose, "decisions": loose}))

    def test_pass_needs_every_question_and_the_claimed_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = asyncio.run(judges(tmp, Fake()).jev(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
        self.assertTrue(core.judge_pass(good, TH["jev"]))
        for broken in (
            dict(good, probabilities={k: v for k, v in good["probabilities"].items() if k != "event_1"}),
            dict(good, probabilities=dict(good["probabilities"], unlisted=None)),
            dict(good, probabilities=dict(good["probabilities"], event_0=float("nan"))),
            dict(good, probabilities=dict(good["probabilities"], event_0=True)),
            dict(good, probabilities=dict(good["probabilities"], unlisted=0.9)),
            dict(good, probabilities=dict(good["probabilities"], event_2=0.1)),
            dict(good, route_choice="PRIVATE"),
            dict(good, n_events=None),
            dict(good, error="anything"),
            None,
            {},
        ):
            self.assertFalse(core.judge_pass(broken, TH["jev"]))
        self.assertFalse(core.judge_pass(good, None))
        self.assertTrue(core.rule_pass("either", {"jev": good}, TH))
        self.assertFalse(core.rule_pass("both", {"jev": good}, TH))  # the missing judge does not pass
        self.assertFalse(core.rule_pass("decisions", {"jev": good}, TH))

    def test_wrong_route_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = asyncio.run(judges(tmp, Fake(route="PRIVATE")).decisions(NOTE, DATE, "EMERGENCY", CLAIM["events"]))
        self.assertIsNone(r["error"])
        self.assertEqual(r["probabilities"]["route"], 0.0)
        self.assertFalse(core.judge_pass(r, {"event_min": 0.0, "unlisted_max": 1.01, "route_min": 0.0}))


class Tool(unittest.TestCase):
    def test_run_file_is_resumable_and_writes_the_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [dict(id=f"r{i}", note_text=NOTE + " " * i, note_date=DATE, **CLAIM) for i in range(4)]
            (tmp / "in.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            policy = tmp / "policy.json"
            policy.write_text(json.dumps({"rule": "both", "thresholds": TH}))
            fake = Fake()
            s1 = runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev", "decisions"), policy_path=policy, J=judges(tmp / "j", fake))
            self.assertEqual(len(fake.calls), 8)
            self.assertEqual(s1["passed"], 4)
            out = [json.loads(line) for line in (tmp / "out.jsonl").read_text().splitlines()]
            self.assertEqual([o["id"] for o in out], ["r0", "r1", "r2", "r3"])
            for o in out:
                self.assertEqual(set(o), {"id", "judges", "rule", "pass", "judge_pass"})
                self.assertEqual(o["rule"], "both")
                self.assertIs(o["pass"], True)
                self.assertEqual(set(o["judges"]), {"jev", "decisions"})
                self.assertEqual(set(o["judges"]["jev"]["probabilities"]), {"event_0", "event_1", "event_2", "unlisted", "route"})
            # second run: nothing is asked again, even with an empty cache directory
            fake2 = Fake()
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev", "decisions"), policy_path=policy, J=judges(tmp / "other", fake2))
            self.assertEqual(fake2.calls, [])
            # an interrupted output (cut line) and a new row: only the missing answers are asked
            lines = (tmp / "out.jsonl").read_text().splitlines()
            (tmp / "out.jsonl").write_text("\n".join(lines[:2]) + "\n" + lines[2][:40])
            fake3 = Fake()
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev", "decisions"), policy_path=policy, J=judges(tmp / "j", fake3))
            self.assertEqual(fake3.calls, [])  # the disk cache still has r2 and r3
            fake4 = Fake()
            runner.run_file(tmp / "in.jsonl", tmp / "out2.jsonl", ("jev",), policy_path=tmp / "none.json", J=judges(tmp / "j", fake4))
            self.assertEqual(fake4.calls, [])
            out2 = [json.loads(line) for line in (tmp / "out2.jsonl").read_text().splitlines()]
            self.assertTrue(all(o["pass"] is None and o["rule"] is None for o in out2))  # no policy file: no verdict

    def test_failed_rows_do_not_pass_and_are_asked_again_on_the_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in.jsonl").write_text(json.dumps(dict(id="x", note_text=NOTE, note_date=DATE, **CLAIM)) + "\n")
            policy = tmp / "policy.json"
            policy.write_text(json.dumps({"rule": "jev", "thresholds": TH}))
            bad = Fake(mode="http_500")
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev",), policy_path=policy, J=judges(tmp / "j", bad))
            o = json.loads((tmp / "out.jsonl").read_text())
            self.assertIs(o["pass"], False)
            self.assertTrue(o["judges"]["jev"]["error"])
            good = Fake()
            runner.run_file(tmp / "in.jsonl", tmp / "out.jsonl", ("jev",), policy_path=policy, J=judges(tmp / "j", good))
            self.assertEqual(len(good.calls), 1)
            self.assertIs(json.loads((tmp / "out.jsonl").read_text())["pass"], True)


class Statistics(unittest.TestCase):
    def test_wilson_kappa_and_noise_formula(self):
        lo, hi = analysis.wilson(2, 60)
        self.assertAlmostEqual(lo, 0.0092, places=4)  # the interval printed in data/scribe/label-audit-v1.json
        self.assertAlmostEqual(hi, 0.1136, places=4)
        self.assertIsNone(analysis.wilson(0, 0))
        self.assertAlmostEqual(analysis.cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]), 1.0)
        self.assertAlmostEqual(analysis.cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0]), 0.0)
        self.assertAlmostEqual(analysis.noise_after(0.1, 0.5, 0.0), 0.05 / 0.95)
        self.assertEqual(analysis.noise_after(0.1, 1.0, 0.2), 0.0)
        self.assertAlmostEqual(analysis.noise_after(0.2, 0.0, 0.0), 0.2)

    def test_calibration_uses_only_the_rows_it_is_given(self):
        def row(label, p):
            return dict(label=label, kind="type_swap", judges={"jev": dict(error=None, n_events=1, claimed_route="PRIVATE", route_choice="PRIVATE",
                                                                         probabilities={"event_0": p, "unlisted": 0.0, "route": 1.0})})

        rows = [row("clean", 0.75), row("clean", 0.85), row("corrupted", 0.65), row("corrupted", 0.1)]
        c = analysis.calibrate(rows, "jev")
        self.assertEqual(c["thresholds"]["event_min"], 0.7)
        self.assertEqual((c["calibration_caught"], c["calibration_false_reject"]), (1.0, 0.0))


if __name__ == "__main__":
    unittest.main()
