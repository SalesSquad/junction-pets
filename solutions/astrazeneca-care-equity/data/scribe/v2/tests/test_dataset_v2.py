"""Tests of the version-2 dataset and of scribe/v2/data_tools.py.

Run from the project directory:
    scribe/.venv/bin/python -m unittest discover -s data/scribe/v2/tests

The dataset tests read the files that `data_tools.py build` wrote; they fail if the dataset is absent.
"""

import collections
import datetime as dt
import hashlib
import itertools
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scribe/v2"))

import data_tools as T  # scribe/v2
import pyarrow.parquet as pq
import sample  # version 1
import verify  # version 1

HELD_IN = ("train", "val", "test_nemotron", "test_haiku")


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class ExpressionFormat(unittest.TestCase):
    def test_parse_printed_date_strings(self):
        note = "2025-03-20"
        cases = {
            "3.2.2025": {"kind": "ABSOLUTE", "date": "2025-02-03"},
            "3.2.": {"kind": "ABSOLUTE", "date": "2025-02-03"},
            "4. helmikuuta 2025": {"kind": "ABSOLUTE", "date": "2025-02-04"},
            "20.7.1961": {"kind": "ABSOLUTE", "date": "1961-07-20"},
            "helmikuussa 2025": {"kind": "MONTH", "year": 2025, "month": 2},
            "kesäkuussa 2024": {"kind": "MONTH", "year": 2024, "month": 6},
            "37 päivää sitten": {"kind": "DAYS_AGO", "n": 37},
            "2 viikkoa sitten": {"kind": "WEEKS_AGO", "n": 2},
        }
        for text, expected in cases.items():
            self.assertEqual(T.parse_expression(text, note), expected, text)
        for bad in ("eilen", "3.2", "2 kuukautta sitten", "noin 12 päivää sitten", "Helmikuussa 2025", "31.2.2025", ""):
            with self.assertRaises(ValueError, msg=bad):
                T.parse_expression(bad, note)

    def test_resolve_does_the_date_arithmetic(self):
        self.assertEqual(T.resolve_date({"kind": "ABSOLUTE", "date": "2025-02-03"}, "2025-03-20"), ("2025-02-03", "DAY"))
        self.assertEqual(T.resolve_date({"kind": "MONTH", "year": 2025, "month": 2}, "2025-03-20"), ("2025-02-01", "MONTH"))
        self.assertEqual(T.resolve_date({"kind": "DAYS_AGO", "n": 37}, "2025-03-20"), ("2025-02-11", "DAY"))
        self.assertEqual(T.resolve_date({"kind": "WEEKS_AGO", "n": 2}, "2025-03-20"), ("2025-03-06", "DAY"))
        # across a year boundary and a leap day
        self.assertEqual(T.resolve_date({"kind": "DAYS_AGO", "n": 20}, "2024-01-10"), ("2023-12-21", "DAY"))
        self.assertEqual(T.resolve_date({"kind": "WEEKS_AGO", "n": 1}, "2024-03-07"), ("2024-02-29", "DAY"))
        self.assertEqual(T.resolve_date({"kind": "DAYS_AGO", "n": 0}, "2024-03-07"), ("2024-03-07", "DAY"))
        obj = {
            "entry_route": "OCCUPATIONAL",
            "events": [
                {"type": "DIAGNOSIS", "date": {"kind": "MONTH", "year": 2025, "month": 10}},
                {"type": "REFERRAL_SENT", "date": {"kind": "WEEKS_AGO", "n": 4}},
            ],
        }
        self.assertEqual(
            compact(T.resolve_expression(obj, "2025-10-15")),
            '{"entry_route":"OCCUPATIONAL","events":[{"type":"REFERRAL_SENT","date":"2025-09-17","precision":"DAY"},'
            '{"type":"DIAGNOSIS","date":"2025-10-01","precision":"MONTH"}]}',
        )
        self.assertEqual(T.resolve_expression({"entry_route": "PRIVATE", "events": []}, "2025-10-15"), {"entry_route": "PRIVATE", "events": []})

    def test_resolve_rejects_malformed_output(self):
        ok = {"type": "DIAGNOSIS", "date": {"kind": "DAYS_AGO", "n": 3}}
        bad_dates = [
            {"kind": "DAYS_AGO", "n": -1},
            {"kind": "DAYS_AGO", "n": "3"},
            {"kind": "DAYS_AGO", "n": True},
            {"kind": "DAYS_AGO", "n": 3.0},
            {"kind": "DAYS_AGO", "n": 10**9},
            {"kind": "DAYS_AGO"},
            {"kind": "DAYS_AGO", "n": 3, "date": "2025-01-01"},
            {"kind": "WEEKS_AGO", "n": None},
            {"kind": "MONTH", "year": 2025, "month": 13},
            {"kind": "MONTH", "year": 2025},
            {"kind": "MONTH", "year": "2025", "month": 2},
            {"kind": "ABSOLUTE", "date": "2025-02-30"},
            {"kind": "ABSOLUTE", "date": "3.2.2025"},
            {"kind": "ABSOLUTE", "date": "20250203"},
            {"kind": "ABSOLUTE", "date": 20250203},
            {"kind": "YEARS_AGO", "n": 1},
            {"date": "2025-02-03"},
            "2025-02-03",
            None,
        ]
        errors = (ValueError, KeyError, TypeError)  # all are caught by scribe/v2/formats.py
        for date in bad_dates:
            with self.assertRaises(errors, msg=repr(date)):
                T.resolve_date(date, "2025-03-20")
            with self.assertRaises(errors, msg=repr(date)):
                T.resolve_expression({"entry_route": "PRIVATE", "events": [{"type": "DIAGNOSIS", "date": date}]}, "2025-03-20")
        bad_objects = [
            {"entry_route": "PRIVATE"},
            {"entry_route": "PRIVATE", "events": {}},
            {"entry_route": "NOWHERE", "events": [ok]},
            {"entry_route": "PRIVATE", "events": [{**ok, "type": "BIOPSY"}]},
            {"entry_route": "PRIVATE", "events": [{**ok, "precision": "DAY"}]},
            {"entry_route": "PRIVATE", "events": [ok], "note": "x"},
            [],
        ]
        for obj in bad_objects:
            with self.assertRaises(errors, msg=repr(obj)):
                T.resolve_expression(obj, "2025-03-20")

    def test_parse_and_resolve_agree_with_the_version_1_date_parser(self):
        """For every date string of every specification: resolve(parse(s)) == sample.parse_date(s)."""
        checked = 0
        for spec in T.load_specs().values():
            note = dt.date.fromisoformat(spec["note_date"])
            for fact in spec["facts"]:
                expected_date, expected_precision = sample.parse_date(fact["expression"], note)
                got = T.resolve_date(T.parse_expression(fact["expression"], note), spec["note_date"])
                self.assertEqual(got, (expected_date.isoformat(), expected_precision), fact["expression"])
                self.assertEqual(got, (fact["date"], fact["precision"]), fact["expression"])
                checked += 1
        self.assertGreater(checked, 2000)

    def test_messages_ask_for_the_expression_format(self):
        row = {"note_date": "2025-03-20", "note_text": "Lähete lähti 2 viikkoa sitten."}
        system, user = T.expression_messages(row)
        self.assertEqual((system["role"], user["role"]), ("system", "user"))
        self.assertEqual(user["content"], "Note date: 2025-03-20\nLähete lähti 2 viikkoa sitten.")
        for word in (*T.EXPRESSION_KINDS, *sample.TYPES, *sample.ROUTES):
            self.assertIn(word, system["content"])


class Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {name: pq.read_table(T.DATASET / f"{name}.parquet").to_pylist() for name in T.FILES}
        cls.v1 = {name: pq.read_table(T.DATA / f"dataset-v1/{name}.parquet").to_pylist() for name in ("train", "val", "test", "rejected")}
        cls.stats = json.loads(T.STATS.read_text())

    def every_row(self, names=T.FILES):
        return itertools.chain.from_iterable(self.files[n] for n in names)

    # ---- no leakage ----------------------------------------------------------------------------
    def test_no_id_occurs_in_two_splits(self):
        ids = {name: [r["id"] for r in rows] for name, rows in self.files.items()}
        for name, values in ids.items():
            self.assertEqual(len(values), len(set(values)), f"an id is twice in {name}")
        for a, b in itertools.combinations(T.FILES, 2):
            self.assertEqual(set(ids[a]) & set(ids[b]), set(), f"{a} and {b} share an id")
        self.assertEqual(len(set().union(*map(set, ids.values()))), sum(len(v) for v in ids.values()))

    def test_no_ground_truth_with_events_occurs_in_two_splits(self):
        """For a note with events the id is the SHA-256 of the answer key, and no answer key is in two files."""
        where = collections.defaultdict(set)
        for name, rows in self.files.items():
            for r in rows:
                if r["events"]:
                    truth = {"entry_route": r["entry_route"], "events": r["events"]}
                    self.assertEqual(compact(truth), r["target_json"])
                    self.assertEqual(hashlib.sha256(json.dumps(truth, sort_keys=True).encode()).hexdigest(), r["id"])
                    where[r["target_json"]].add(name)
        self.assertGreater(len(where), 5000)
        self.assertEqual([k for k, v in where.items() if len(v) > 1], [])

    def test_no_note_text_occurs_in_two_splits(self):
        where = collections.defaultdict(set)
        for name, rows in self.files.items():
            for r in rows:
                where[r["note_text"]].add(name)
        self.assertEqual([k[:60] for k, v in where.items() if len(v) > 1], [])

    def test_haiku_ids_are_new(self):
        old = {r["id"] for rows in self.v1.values() for r in rows}
        pilot = T.DATA / "haiku-test.jsonl"
        if pilot.exists():
            old |= {json.loads(line)["id"] for line in pilot.read_text().splitlines() if line.strip()}
        haiku = {r["id"] for r in self.every_row() if r["writer"] == T.WRITER_HAIKU}
        self.assertEqual(haiku & old, set())
        self.assertEqual(haiku - set(T.load_specs()), set())

    # ---- the expression target -----------------------------------------------------------------
    def test_expression_target_resolves_to_the_absolute_target_for_every_row(self):
        checked = 0
        for row in self.every_row():
            resolved = T.resolve_expression(json.loads(row["expression_json"]), row["note_date"])
            self.assertEqual(compact(resolved), row["target_json"], row["id"])
            self.assertEqual(resolved, {"entry_route": row["entry_route"], "events": row["events"]}, row["id"])
            checked += 1
        self.assertEqual(checked, sum(len(v) for v in self.files.values()))
        self.assertEqual(checked, self.stats["expression_target"]["rows_checked_to_resolve_to_absolute_target"])

    def test_expression_target_is_what_the_note_prints(self):
        """Each event carries the parse of its own printed date string, in the order the strings appear."""
        for row in self.every_row():
            target = json.loads(row["expression_json"])
            self.assertEqual(row["expression_json"], compact(target))
            self.assertEqual(target["entry_route"], row["entry_route"])
            printed = sorted(compact({"type": f["type"], "date": T.parse_expression(f["expression"], row["note_date"])}) for f in row["facts"])
            self.assertEqual(sorted(compact(e) for e in target["events"]), printed, row["id"])
            self.assertEqual(row["expression_json"], T.expression_target({**row, "expression_json": None}), row["id"])
            self.assertEqual(row["date_forms"], [f["form"] for f in row["facts"]], row["id"])
        for row in self.every_row(HELD_IN):
            by_event = {compact({"type": f["type"], "date": T.parse_expression(f["expression"], row["note_date"])}): f["expression"] for f in row["facts"]}
            positions = [
                re.search(T.date_pattern(by_event[compact(e)]), row["note_text"]).start() for e in json.loads(row["expression_json"])["events"]
            ]
            self.assertEqual(positions, sorted(positions), row["id"])

    def test_every_expression_target_fits_the_schema(self):
        try:
            import constrained  # scribe/v2, written by another step
        except ImportError as e:
            self.skipTest(f"scribe/v2/constrained.py is not importable: {e}")
        automaton = constrained.Automaton()
        start = constrained.compile_schema(automaton, T.EXPRESSION_SCHEMA)
        for row in self.every_row():
            self.assertTrue(automaton.matches(start, row["expression_json"]), row["expression_json"])
        self.assertFalse(automaton.matches(start, '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","date":"2025-01-01"}]}'))
        self.assertFalse(automaton.matches(start, '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","date":{"kind":"DAYS_AGO","n":-3}}]}'))

    # ---- composition of the splits -------------------------------------------------------------
    def test_version_1_rows_are_unchanged(self):
        """test_nemotron is version-1 test; train and val start with version-1 train and val."""
        columns = [c for c in T.V1_COLUMNS if c != "split"]
        for new, old in (("test_nemotron", "test"), ("train", "train"), ("val", "val"), ("rejected", "rejected")):
            mine = [r for r in self.files[new] if r["writer"] == T.WRITER_NEMOTRON]
            self.assertEqual(len(mine), len(self.v1[old]))
            for a, b in zip(mine, self.v1[old]):
                self.assertEqual({c: a[c] for c in columns}, {c: b[c] for c in columns})
                self.assertEqual((a["kind"], a["split"]), ("standard", new))
        self.assertEqual(len(self.files["test_nemotron"]), len(self.v1["test"]))
        self.assertEqual(pq.read_schema(T.DATASET / "train.parquet").names[: len(T.V1_COLUMNS)], list(T.V1_COLUMNS))
        self.assertEqual(pq.read_schema(T.DATA / "dataset-v1/train.parquet").names, list(T.V1_COLUMNS))

    def test_haiku_hold_out(self):
        test = self.files["test_haiku"]
        self.assertEqual(len(test), T.TEST_HAIKU_N)
        self.assertEqual({r["writer"] for r in test}, {T.WRITER_HAIKU})
        val_haiku = [r for r in self.files["val"] if r["writer"] == T.WRITER_HAIKU]
        self.assertEqual(len(val_haiku), T.VAL_HAIKU_N)
        accepted = [r for r in self.every_row(HELD_IN) if r["writer"] == T.WRITER_HAIKU]
        by_kind = collections.Counter(r["kind"] for r in accepted)
        self.assertEqual(set(by_kind), set(T.KINDS))
        # stratified by kind: proportional allocation, so each kind is within one note of its share
        expected = T.allocate(dict(by_kind), T.TEST_HAIKU_N)
        got = collections.Counter(r["kind"] for r in test)
        self.assertEqual(dict(got), expected)
        for kind in T.KINDS:
            self.assertLess(abs(got[kind] - T.TEST_HAIKU_N * by_kind[kind] / len(accepted)), 1)
        # the assignment is the documented hash rule, not file order
        assignment, _ = T.assign_haiku(accepted)
        for name in ("train", "val", "test_haiku"):
            self.assertEqual({r["id"] for r in self.files[name] if r["writer"] == T.WRITER_HAIKU}, {i for i, s in assignment.items() if s == name})

    def test_columns_and_labels(self):
        for name, rows in self.files.items():
            for r in rows:
                self.assertEqual(r["split"], name)
                self.assertIn(r["writer"], (T.WRITER_NEMOTRON, T.WRITER_HAIKU))
                self.assertEqual(r["teacher_model"], r["writer"])
                self.assertIn(r["kind"], T.KINDS)
                self.assertTrue(r["synthetic"])
                self.assertEqual(r["accepted"], name != "rejected")
                self.assertEqual(r["reject_stage"] is None, name != "rejected")
                self.assertEqual(r["kind"] == "no_event", not r["events"])
                self.assertEqual(T.canonicalise(json.loads(r["target_json"])), {"entry_route": r["entry_route"], "events": r["events"]})
        self.assertEqual({r["kind"] for r in self.every_row() if r["writer"] == T.WRITER_NEMOTRON}, {"standard"})

    def test_accepted_rows_pass_both_gates(self):
        for r in self.every_row(HELD_IN):
            self.assertTrue(verify.code_check(r)["ok"], r["id"])
            p = dict(r["verifier_probabilities"])
            if r["kind"] == "no_event":
                self.assertTrue(T.no_event_accept(p), r["id"])
                self.assertLess(p[T.NO_EVENT_KEY], 0.5)
            else:
                self.assertTrue(verify.accept(p), r["id"])
                self.assertEqual(sum(k.startswith("event_") for k in p), len(r["events"]))
        for r in self.files["rejected"]:
            if r["writer"] != T.WRITER_HAIKU:
                continue
            p = dict(r["verifier_probabilities"])
            failed_code = not verify.code_check(r)["ok"]
            self.assertEqual(r["reject_stage"], "code_check" if failed_code else "verifier")
            self.assertTrue(failed_code or not (T.no_event_accept(p) if r["kind"] == "no_event" else verify.accept(p)), r["id"])

    def test_every_written_note_is_in_exactly_one_file(self):
        notes, cover = T.load_notes()
        haiku = collections.Counter(r["id"] for r in self.every_row() if r["writer"] == T.WRITER_HAIKU)
        self.assertEqual(set(haiku), set(notes))
        self.assertEqual(set(haiku.values()), {1})
        for r in self.every_row():
            if r["writer"] == T.WRITER_HAIKU:
                self.assertEqual(r["note_text"], notes[r["id"]]["note_text"])  # note text is not edited
        self.assertEqual(cover["notes"], self.stats["haiku"]["notes_loaded"])

    def test_statistics_file_matches_the_parquet_files(self):
        for name, rows in self.files.items():
            c = self.stats["counts"][name]
            self.assertEqual(c["rows"], len(rows))
            self.assertEqual(c["by_writer"], dict(collections.Counter(r["writer"] for r in rows)))
            self.assertEqual(c["by_kind"], dict(collections.Counter(r["kind"] for r in rows)))
            self.assertEqual(self.stats["outputs"][f"data/scribe/v2/dataset/{name}.parquet"]["sha256"], T.sha256_file(T.DATASET / f"{name}.parquet"))
        h = self.stats["haiku"]["all_kinds"]
        haiku = [r for r in self.every_row() if r["writer"] == T.WRITER_HAIKU]
        rejected = [r for r in haiku if not r["accepted"]]
        self.assertEqual(h["notes"], len(haiku))
        self.assertEqual(h["code_check_failure"]["k"], sum(r["reject_stage"] == "code_check" for r in rejected))
        self.assertEqual(h["jev_rejection_given_code_pass"]["k"], sum(r["reject_stage"] == "verifier" for r in rejected))
        self.assertEqual(h["jev_rejection_given_code_pass"]["n"], len(haiku) - h["code_check_failure"]["k"])
        t = self.stats["typesafe"]
        self.assertEqual(t["tokens"], t["input_tokens"] + t["output_tokens"])
        self.assertAlmostEqual(t["cost_usd"], t["tokens"] * 0.042 / 1e6, places=12)
        self.assertLess(t["cost_usd_counting_reservations"], t["limit_usd"])

    # ---- loaders -------------------------------------------------------------------------------
    def test_load_split(self):
        self.assertEqual(len(T.load_split("test_haiku")), T.TEST_HAIKU_N)
        self.assertEqual(len(T.load_split("test_nemotron")), len(self.v1["test"]))
        self.assertEqual(len(T.load_split("train_nemotron")), len(self.v1["train"]))
        self.assertEqual(len(T.load_split("val_haiku")), T.VAL_HAIKU_N)
        self.assertEqual(len(T.load_split("train_haiku")) + len(T.load_split("train_nemotron")), len(self.files["train"]))
        self.assertIsInstance(T.load_split("val_nemotron")[0]["verifier_probabilities"], dict)
        with self.assertRaises(ValueError):
            T.load_split("test")

    def test_the_training_code_finds_everything_it_asks_for(self):
        try:
            import data_iface  # scribe/v2, written by another step
            import formats
        except ImportError as e:
            self.skipTest(f"scribe/v2/data_iface.py or formats.py is not importable: {e}")
        self.assertEqual(formats.available("expression"), (True, ""))
        rows, source = data_iface.load_split("test_haiku")
        self.assertEqual((len(rows), source), (T.TEST_HAIKU_N, "data_tools.load_split('test_haiku')"))
        fmt = formats.get_format("expression")
        for row in rows:
            self.assertEqual(row["writer"], "haiku")
            self.assertEqual(fmt.target(row), row["expression_json"])
            prediction, mode, error = formats.interpret(fmt, fmt.target(row), row)
            self.assertEqual((compact(prediction), mode, error), (row["target_json"], "strict", ""))
        train, _ = data_iface.training_rows("nemotron+haiku")
        for name in ("val_nemotron", "val_haiku", "test_nemotron", "test_haiku"):
            data_iface.assert_disjoint(train, data_iface.load_split(name)[0], name)


if __name__ == "__main__":
    unittest.main()
