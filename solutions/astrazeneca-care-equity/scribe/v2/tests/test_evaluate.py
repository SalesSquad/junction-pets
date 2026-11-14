import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

import fakes
import data_iface
import evaluate
import formats
import train


def fake_data_tools():
    """Stand-in for scribe/v2/data_tools.py: dates are given as days before the note date."""
    import datetime

    module = types.ModuleType("data_tools")

    def expression_messages(row):
        return [
            {"role": "system", "content": "Return events with days_ago."},
            {"role": "user", "content": f"Note date: {row['note_date']}\n{row['note_text']}"},
        ]

    def expression_target(row):
        note = datetime.date.fromisoformat(row["note_date"])
        truth = json.loads(row["target_json"])
        return {
            "entry_route": truth["entry_route"],
            "events": [
                {"type": e["type"], "days_ago": (note - datetime.date.fromisoformat(e["date"])).days} for e in truth["events"]
            ],
        }

    def resolve_expression(value, note_date):
        note = datetime.date.fromisoformat(note_date)
        return {
            "entry_route": value["entry_route"],
            "events": [
                {"type": e["type"], "date": (note - datetime.timedelta(days=e["days_ago"])).isoformat(), "precision": "DAY"}
                for e in value["events"]
            ],
        }

    module.expression_messages = expression_messages
    module.expression_target = expression_target
    module.resolve_expression = resolve_expression
    return module


class Parsing(unittest.TestCase):
    def test_tolerant_json(self):
        good = '{"entry_route":"SCREENING","events":[]}'
        self.assertEqual(formats.tolerant_json(good), (json.loads(good), "strict"))
        self.assertEqual(formats.tolerant_json(f"```json\n{good}\n```")[1], "strict")
        self.assertEqual(formats.tolerant_json(f"Here it is: {good} Thanks!"), (json.loads(good), "tolerant"))
        for bad in ("no json here", '{"entry_route":"SCREENING","events":[', ""):
            with self.assertRaises(ValueError):
                formats.tolerant_json(bad)

    def test_interpret_absolute(self):
        fmt = formats.get_format("absolute")
        row = fakes.note_row(1)
        prediction, mode, error = formats.interpret(fmt, row["target_json"], row)
        self.assertEqual((prediction, mode, error), (json.loads(row["target_json"]), "strict", ""))
        for text in ('{"entry_route":"NOPE","events":[]}', '{"entry_route":"SCREENING"}', "[1, 2]", '{"entry_route":"SCREENING","events":[{"type":"DIAGNOSIS","date":"2025-02-30","precision":"DAY"}]}'):
            self.assertEqual(formats.interpret(fmt, text, row)[:2], (None, "failed"), text)

    def test_records_and_confidence(self):
        fmt = formats.get_format("absolute")
        row = fakes.note_row(1)
        record = evaluate.make_record(row, fmt, row["target_json"], [-0.1, -0.3, -0.2], True)
        self.assertAlmostEqual(record["confidence"], -0.2)
        self.assertEqual(record["min_token_logprob"], -0.3)
        self.assertEqual((record["tokens"], record["stopped"], record["parse_mode"]), (3, True, "strict"))
        broken = evaluate.make_record(row, fmt, "not json", [-0.01, -0.01], False)
        self.assertIsNone(broken["prediction"])
        self.assertIsNone(broken["confidence"])  # an unparsable output has no confidence
        self.assertIsNone(evaluate.mean_logprob([]))


class Scoring(unittest.TestCase):
    def setUp(self):
        self.fmt = formats.get_format("absolute")
        self.rows = (
            [fakes.note_row(i, "nemotron", "standard") for i in range(4)]
            + [fakes.note_row(i, "haiku", "careful") for i in range(4, 6)]
            + [fakes.note_row(i, "haiku", "no_event", events=[]) for i in range(6, 8)]
        )

    def records(self, texts):
        return [evaluate.make_record(r, self.fmt, t, [-0.05, -0.05], True) for r, t in zip(self.rows, texts)]

    def test_metrics_and_breakdowns(self):
        texts = [r["target_json"] for r in self.rows]
        texts[1] = texts[1].replace("2025-03-04", "2025-03-05")  # wrong date
        texts[4] = "garbage"  # unparsable
        texts[6] = texts[0]  # an event invented for a no-event note
        m = evaluate.score(self.rows, self.records(texts))
        self.assertEqual(m["n"], 8)
        self.assertEqual(m["outcomes"], [True, False, True, True, False, True, False, True])
        self.assertAlmostEqual(m["note_exact_match"]["value"], 5 / 8)
        self.assertAlmostEqual(m["invalid_output"]["value"], 1 / 8)
        self.assertEqual(m["parse_modes"], {"strict": 7, "failed": 1})
        self.assertEqual(set(m["by_writer"]), {"nemotron", "haiku"})
        self.assertEqual(set(m["by_kind"]), {"standard", "careful", "no_event"})
        self.assertAlmostEqual(m["by_writer"]["nemotron"]["note_exact_match"]["value"], 3 / 4)
        self.assertAlmostEqual(m["by_kind"]["careful"]["note_exact_match"]["value"], 1 / 2)
        self.assertAlmostEqual(m["by_kind"]["no_event"]["note_exact_match"]["value"], 1 / 2)
        self.assertEqual(m["by_kind"]["careful"]["invalid_output"]["value"], 0.5)
        self.assertIsNone(m["confidences"][4])
        self.assertEqual(m["ids"], [r["id"] for r in self.rows])
        self.assertNotIn("curve", m["risk_coverage"])
        self.assertIn("curve", evaluate.score(self.rows, self.records(texts), curve=True)["risk_coverage"])

    def test_misaligned_records_are_refused(self):
        records = self.records([r["target_json"] for r in self.rows])
        with self.assertRaises(ValueError):
            evaluate.score(self.rows, records[::-1])
        with self.assertRaises(ValueError):
            evaluate.score(self.rows, records[:-1])

    def test_paired_test(self):
        ids = [f"n{i}" for i in range(10)]
        a = [True] * 8 + [False] * 2
        b = [True] * 2 + [False] * 8
        test = evaluate.paired_test(ids, a, ids, b)
        self.assertEqual((test["a_only_correct"], test["b_only_correct"], test["n"]), (6, 0, 10))
        self.assertAlmostEqual(test["exact_p"], 2 * 0.5**6)
        shuffled = evaluate.paired_test(ids, a, ids[::-1], b[::-1])
        self.assertEqual(shuffled["a_only_correct"], 6)


class Expression(unittest.TestCase):
    def test_predictions_are_resolved_before_scoring(self):
        with mock.patch.dict(sys.modules, {"data_tools": fake_data_tools()}):
            self.assertEqual(formats.available("expression"), (True, ""))
            fmt = formats.get_format("expression")
            rows = [fakes.note_row(i) for i in range(3)]
            target = fmt.target(rows[0])
            self.assertEqual(json.loads(target)["events"][0], {"type": "REFERRAL_SENT", "days_ago": 89})
            wrong = target.replace("89", "88")
            records = [evaluate.make_record(r, fmt, t, [-0.1], True) for r, t in zip(rows, [target, wrong, "{}"])]
            self.assertEqual(records[0]["prediction"], json.loads(rows[0]["target_json"]))  # absolute form
            self.assertEqual(records[1]["prediction"]["events"][0]["date"], "2025-03-05")
            self.assertIsNone(records[2]["prediction"])
            m = evaluate.score(rows, records)
            self.assertEqual(m["outcomes"], [True, False, False])
            self.assertIsNone(fmt.schema())  # this stand-in exports no schema: constrained decoding falls back

    def test_round_trip_check_catches_a_mismatched_data_tools(self):
        rows = [fakes.note_row(i) for i in range(5)]
        good = fake_data_tools()
        with mock.patch.dict(sys.modules, {"data_tools": good}):
            self.assertEqual(formats.available("expression", rows), (True, ""))
        off_by_one = fake_data_tools()
        inner = off_by_one.resolve_expression
        off_by_one.resolve_expression = lambda value, note_date: inner(
            {"entry_route": value["entry_route"], "events": [dict(e, days_ago=e["days_ago"] + 1) for e in value["events"]]},
            note_date,
        )
        with mock.patch.dict(sys.modules, {"data_tools": off_by_one}):
            ok, why = formats.available("expression", rows)
            self.assertFalse(ok)
            self.assertIn("round trip failed on 5 of 5 rows", why)
        other_signature = fake_data_tools()
        other_signature.resolve_expression = lambda row: row
        with mock.patch.dict(sys.modules, {"data_tools": other_signature}):
            ok, why = formats.available("expression", rows)
            self.assertFalse(ok)
            self.assertIn("TypeError", why)

    def test_missing_data_tools_is_reported_not_guessed(self):
        with mock.patch.dict(sys.modules, {"data_tools": types.ModuleType("data_tools")}):
            ok, why = formats.available("expression")
            self.assertFalse(ok)
            self.assertIn("expression_messages", why)
            with self.assertRaises(data_iface.DataToolsMissing):
                formats.get_format("expression").target(fakes.note_row(1))


class Encoding(unittest.TestCase):
    def setUp(self):
        self.tok = fakes.FakeTokenizer()
        self.fmt = formats.get_format("absolute")
        self.row = fakes.note_row(1)
        self.eot = self.tok.convert_tokens_to_ids("<end_of_turn>")

    def test_loss_is_on_the_answer_and_its_stop_token_only(self):
        enc = train.encode(self.row, self.tok, self.fmt)
        supervised = [t for t in enc["labels"] if t != train.IGNORE]
        self.assertEqual(self.tok.decode(supervised), self.row["target_json"] + "<end_of_turn>")
        self.assertEqual(supervised[-1], self.eot)
        self.assertEqual(enc["labels"][-1], train.IGNORE)  # the newline after the stop token
        self.assertEqual(enc["input_ids"].count(self.tok.bos_token_id), 1)
        self.assertEqual(len(enc["input_ids"]), len(enc["labels"]))
        first = next(i for i, t in enumerate(enc["labels"]) if t != train.IGNORE)
        self.assertTrue(self.tok.decode(enc["input_ids"][:first]).endswith("<start_of_turn>model\n"))
        self.assertTrue(all(a == b for a, b in zip(enc["input_ids"], enc["labels"]) if b != train.IGNORE))

    def test_stop_token_can_be_left_unsupervised(self):
        enc = train.encode(self.row, self.tok, self.fmt, supervise_stop=False)
        supervised = [t for t in enc["labels"] if t != train.IGNORE]
        self.assertEqual(self.tok.decode(supervised), self.row["target_json"])

    def test_no_truncation_and_template_drift(self):
        with self.assertRaisesRegex(ValueError, "refusing to truncate"):
            train.encode(self.row, self.tok, self.fmt, max_length=50)
        with self.assertRaisesRegex(ValueError, "template drift"):
            train.encode(self.row, fakes.FakeTokenizer(mangle=True), self.fmt)

    def test_expression_targets_are_encoded_the_same_way(self):
        with mock.patch.dict(sys.modules, {"data_tools": fake_data_tools()}):
            fmt = formats.get_format("expression")
            enc = train.encode(self.row, self.tok, fmt)
            supervised = [t for t in enc["labels"] if t != train.IGNORE]
            self.assertEqual(self.tok.decode(supervised), fmt.target(self.row) + "<end_of_turn>")


class Data(unittest.TestCase):
    def test_normalise(self):
        row = data_iface.normalise(
            {
                "id": "x",
                "note_date": "2025-06-01",
                "note_text": "t",
                "ground_truth": {"entry_route": "PRIVATE", "events": []},
                "writer": "claude-haiku-5.5 (mcp__haiku__haiku_ask)",
                "kind": "no_event",
            }
        )
        self.assertEqual(row["target_json"], '{"entry_route":"PRIVATE","events":[]}')
        self.assertEqual((row["writer"], row["kind"], row["distractors"]), ("haiku", "no_event", []))
        v1 = data_iface.normalise(dict(fakes.note_row(3), writer=None, teacher_model="nemotron-3.5-super-vl", kind=None))
        self.assertEqual((v1["writer"], v1["kind"]), ("nemotron", "standard"))

    def test_train_and_heldout_must_not_share_ground_truth(self):
        rows = [fakes.note_row(i) for i in range(4)]
        data_iface.assert_disjoint(rows[:2], rows[2:])
        with self.assertRaisesRegex(ValueError, "both the training rows"):
            data_iface.assert_disjoint(rows[:3], rows[2:])

    def test_unknown_split(self):
        with self.assertRaises(ValueError):
            data_iface.load_split("test")

    def test_split_lookup_order(self):
        rows = [
            dict(fakes.note_row(i), writer="claude-haiku-5.5" if i % 2 else "nemotron-3.5-super-vl", kind="careful")
            for i in range(6)
        ]
        with tempfile.TemporaryDirectory() as d:
            folder = pathlib.Path(d)
            (folder / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
            with (
                mock.patch.object(data_iface, "FOLDERS", (folder,)),
                mock.patch.object(data_iface, "V1_FILES", {}),
                mock.patch.object(data_iface._paths, "ROOT", folder),
                mock.patch.dict(sys.modules, {"data_tools": types.ModuleType("data_tools")}),
            ):
                got, source = data_iface.load_split("train_haiku")  # one file for both writers, filtered
                self.assertEqual([r["id"] for r in got], ["note-0001", "note-0003", "note-0005"])
                self.assertEqual(source, "train.jsonl (writer haiku)")
                self.assertEqual({r["kind"] for r in got}, {"careful"})
                (folder / "train_haiku.jsonl").write_text(json.dumps(rows[1], ensure_ascii=False) + "\n")
                got, source = data_iface.load_split("train_haiku")  # a per-writer file is preferred
                self.assertEqual((len(got), source), (1, "train_haiku.jsonl"))
                with self.assertRaisesRegex(data_iface.SplitUnavailable, "val_haiku.parquet"):
                    data_iface.load_split("val_haiku")
        module = types.ModuleType("data_tools")
        module.load_split = lambda name: [fakes.note_row(9)]
        with mock.patch.dict(sys.modules, {"data_tools": module}):
            got, source = data_iface.load_split("test_haiku")  # a loader in data_tools wins over files
            self.assertEqual(([r["id"] for r in got], source), (["note-0009"], "data_tools.<lambda>('test_haiku')"))


class TestAccess(unittest.TestCase):
    def test_test_splits_need_a_frozen_selection(self):
        self.assertIsNone(evaluate.check_test_access(["val_nemotron"], None))
        with self.assertRaises(PermissionError):
            evaluate.check_test_access(["val_nemotron", "test_haiku"], None)
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "selection.json"
            path.write_text(json.dumps({"frozen": False}))
            with self.assertRaises(PermissionError):
                evaluate.check_test_access(["test_nemotron"], path)
            path.write_text(json.dumps({"frozen": True, "run": "x"}))
            self.assertEqual(evaluate.check_test_access(["test_nemotron"], path)["run"], "x")


if __name__ == "__main__":
    unittest.main()
