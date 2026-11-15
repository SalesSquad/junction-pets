import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from metrics import mcnemar, risk_coverage, summary, wilson
from prompts import canonicalise, messages, parse_output
from sample import FORMS, dt, parse_date, render, sample
from verify import accept, code_check


class Dates(unittest.TestCase):
    def test_forms(self):
        n = dt.date(2025, 10, 15)
        for form in FORMS:
            d = n - dt.timedelta(days=21)
            if form == "month":
                d = d.replace(day=1)
            with self.subTest(form=form):
                self.assertEqual(
                    parse_date(render(d, n, form), n),
                    (d, "MONTH" if form == "month" else "DAY"),
                )

    def test_sampling(self):
        for i in range(2000):
            r = sample(i)
            n = dt.date.fromisoformat(r["note_date"])
            dates = []
            for f in r["facts"]:
                d, p = parse_date(f["expression"], n)
                self.assertEqual((d.isoformat(), p), (f["date"], f["precision"]))
                self.assertTrue(0 <= (n - d).days <= 400)
                dates.append(d)
            self.assertEqual(dates, sorted(dates))

    def test_dates_code(self):
        r = {
            "facts": [{"expression": "3.9.2025"}],
            "distractors": [],
            "note_text": "3.9.2025 " + ("Vointi vakaa. " * 35),
        }
        self.assertTrue(code_check(r)["ok"])
        r["note_text"] = r["note_text"].replace("3.9.2025 ", "3.9.2025. ")
        self.assertTrue(code_check(r)["ok"])
        r["note_text"] = r["note_text"].replace("3.9.2025", "")
        self.assertFalse(code_check(r)["ok"])
        r["note_text"] = "3.9.2025 4.9.2025 " + ("Vointi vakaa. " * 35)
        self.assertFalse(code_check(r)["ok"])

    def test_extra_formats(self):
        for expr in [
            "2025-09-04",
            "4. syyskuuta 2025",
            "lokakuussa 2025",
            "3 viikkoa sitten",
            "eilen",
        ]:
            r = {
                "facts": [],
                "distractors": [],
                "note_text": expr + " " + ("Vointi vakaa. " * 35),
            }
            self.assertTrue(code_check(r)["extra"])


class Parsing(unittest.TestCase):
    def test_canonical(self):
        r = sample(10)
        x = parse_output("```json\n" + r["target_json"] + "\n```")
        self.assertEqual(canonicalise(x), json.loads(r["target_json"]))
        self.assertEqual(
            messages({**r, "note_text": "Merkintä"})[1]["content"],
            f"Note date: {r['note_date']}\nMerkintä",
        )
        with self.assertRaises(ValueError):
            parse_output('{"entry_route":"BAD","events":[]}')

    def test_month_invalid(self):
        with self.assertRaises(ValueError):
            canonicalise(
                {
                    "entry_route": "PRIVATE",
                    "events": [
                        {
                            "type": "DIAGNOSIS",
                            "date": "2025-03-02",
                            "precision": "MONTH",
                        }
                    ],
                }
            )

    def test_thresholds(self):
        self.assertTrue(accept({"event_0": 0.8, "unlisted": 0.49}))
        self.assertFalse(accept({"event_0": 0.79, "unlisted": 0.1}))
        self.assertFalse(accept({"event_0": 0.9, "distractor_0": 0.5}))


class Masking(unittest.TestCase):
    def test_only_json_tokens(self):
        from train_lora import encode

        class ToyTokenizer:
            def apply_chat_template(
                self, msgs, tokenize=False, add_generation_prompt=False
            ):
                text = "".join(m["role"] + ":" + m["content"] + "<end>" for m in msgs)
                return text + "assistant:" if add_generation_prompt else text

            def __call__(self, text, **kwargs):
                return {
                    "input_ids": list(range(len(text))),
                    "offset_mapping": [(i, i + 1) for i in range(len(text))],
                }

        row = sample(5)
        row["note_text"] = "Kuvitteellinen merkintä."
        tok = ToyTokenizer()
        out = encode(row, tok, 10000)
        labels = [v for v in out["labels"] if v != -100]
        self.assertEqual(len(labels), len(row["target_json"]))
        self.assertTrue(all(v == -100 for v in out["labels"][-5:]))


class Metrics(unittest.TestCase):
    def test_handmade(self):
        g = {
            "entry_route": "PRIVATE",
            "events": [{"type": "DIAGNOSIS", "date": "2025-01-01", "precision": "DAY"}],
        }
        r = {"target_json": json.dumps(g), "distractors": [{"date": "2026-01-01"}]}
        x = summary([r], [g])
        self.assertEqual(x["f1"], 1)
        self.assertEqual(x["note_exact_match"]["value"], 1)
        p = {
            "entry_route": "PRIVATE",
            "events": [{"type": "DIAGNOSIS", "date": "2026-01-01", "precision": "DAY"}],
        }
        x = summary([r], [p])
        self.assertEqual(x["f1"], 0)
        self.assertEqual(x["type_only_f1"], 1)
        self.assertEqual(x["date_errors_days"], [365])
        self.assertEqual(x["distractor_extraction"]["value"], 1)

    def test_duplicate_predictions(self):
        g = {
            "entry_route": "PRIVATE",
            "events": [{"type": "DIAGNOSIS", "date": "2025-01-01", "precision": "DAY"}],
        }
        p = {**g, "events": g["events"] * 2}
        m = summary([{"target_json": json.dumps(g)}], [p])
        self.assertEqual(m["precision"]["value"], 0.5)
        self.assertEqual(m["recall"]["value"], 1)

    def test_exported_acceptance(self):
        import pyarrow.parquet as pq

        root = pathlib.Path(__file__).resolve().parents[2] / "data/scribe/dataset-v1"
        for split in ["train", "val", "test"]:
            if not (root / f"{split}.parquet").exists():
                continue
            for row in pq.read_table(root / f"{split}.parquet").to_pylist():
                self.assertTrue(row["synthetic"])
                self.assertTrue(row["accepted"])
                probabilities = dict(row["verifier_probabilities"])
                self.assertTrue(accept(probabilities))
                self.assertGreaterEqual(probabilities["route"], 0.8)
                self.assertEqual(
                    canonicalise(json.loads(row["target_json"])),
                    json.loads(row["target_json"]),
                )
                self.assertTrue(60 <= len(row["note_text"].split()) <= 140)

    def test_mcnemar(self):
        self.assertEqual(mcnemar(0, 0), 1)
        self.assertAlmostEqual(mcnemar(0, 5), 0.0625)
        self.assertAlmostEqual(mcnemar(1, 4), 0.375)
        self.assertGreaterEqual(mcnemar(0, 2000), 0)

    def test_wilson_risk(self):
        self.assertAlmostEqual(wilson(0, 10)["ci95"][1], 0.2775328, places=6)
        self.assertEqual(wilson(0, 0)["value"], None)
        self.assertEqual(
            risk_coverage([3, 2, 1], [True, True, False])["largest_empirical_coverage"][
                "0.01"
            ],
            2 / 3,
        )

    def test_no_leakage(self):
        seen = {}
        for i in range(5000):
            r = sample(i)
            key = r["target_json"]
            if key in seen:
                self.assertEqual(seen[key], r["split"])
            seen[key] = r["split"]
        import pyarrow.parquet as pq

        root = pathlib.Path(__file__).resolve().parents[2] / "data/scribe/dataset-v1"
        actual = {}
        for split in ["train", "val", "test", "rejected"]:
            if (root / f"{split}.parquet").exists():
                for row in pq.read_table(root / f"{split}.parquet").to_pylist():
                    self.assertNotIn(row["target_json"], actual)
                    actual[row["target_json"]] = split


class PostEvaluation(unittest.TestCase):
    """Checks added after review (scribe/post_eval.py). No model is loaded."""

    def test_exact_upper_bound(self):
        import post_eval as P

        # no error in n notes: the bound has the closed form 1 - 0.05^(1/n)
        for n in (8, 48, 77, 299):
            self.assertAlmostEqual(P.upper_bound(0, n), 1 - 0.05 ** (1 / n), places=9)
        self.assertLess(P.upper_bound(0, 299), 0.01)
        self.assertGreater(P.upper_bound(0, 298), 0.01)
        self.assertEqual(P.notes_needed_for(0.01), 299)
        self.assertEqual(P.notes_needed_for(0.05), 59)
        self.assertEqual(P.upper_bound(5, 5), 1.0)
        self.assertIsNone(P.upper_bound(0, 0))
        self.assertGreater(P.upper_bound(1, 77), P.upper_bound(0, 77))

    def test_threshold_is_fixed_on_one_set_and_applied_to_another(self):
        import post_eval as P

        scores = [-0.1, -0.2, -0.3, -0.4, -0.5, -0.6]
        outcomes = [True, True, True, False, True, False]
        self.assertEqual(P.threshold_from(scores, outcomes, 0.01), -0.3)      # the three best are all right
        self.assertEqual(P.threshold_from(scores, outcomes, 0.25), -0.5)      # 1 wrong in 5 = 20%
        self.assertIsNone(P.threshold_from([-0.1, -0.2], [False, False], 0.05))
        rows = [{"date_forms": ["days"]}, {"date_forms": ["long"]}, {"date_forms": ["numeric"]}]
        got = P.apply_threshold(rows, [-0.05, -0.25, -0.9], [False, True, True], -0.3)
        self.assertEqual((got["admitted"], got["errors_among_admitted"], got["admitted_with_relative_date"]), (2, 1, 1))
        self.assertEqual(got["error_rate_among_admitted"], 0.5)
        self.assertEqual(P.apply_threshold(rows, [0, 0, 0], [True] * 3, None)["admitted"], 0)

    def test_order_violations_use_the_documented_order(self):
        import post_eval as P
        from eventlog.schema import EVENT_TYPES

        order = {k: i for i, k in enumerate(EVENT_TYPES)}
        self.assertLess(order["DIAGNOSIS"], order["SPECIALIST_VISIT"])
        ok = [{"type": "DIAGNOSIS", "date": "2024-01-10"}, {"type": "SPECIALIST_VISIT", "date": "2024-01-10"}]
        self.assertEqual(P.order_violations(ok, order), [])                   # a tie is allowed
        fine = [{"type": "MDT_DECISION", "date": "2024-01-11"}, {"type": "SPECIALIST_VISIT", "date": "2024-09-01"}]
        self.assertEqual(P.order_violations(fine, order), [])                 # decision, then the visit
        bad = [{"type": "SPECIALIST_VISIT", "date": "2024-01-11"}, {"type": "MDT_DECISION", "date": "2024-09-01"}]
        self.assertEqual(P.order_violations(bad, order), ["MDT_DECISION dated after SPECIALIST_VISIT"])
        bad.append({"type": "DIAGNOSIS", "date": "2024-10-01"})
        self.assertEqual(sorted(P.order_violations(bad, order)), ["DIAGNOSIS dated after MDT_DECISION",
                         "DIAGNOSIS dated after SPECIALIST_VISIT", "MDT_DECISION dated after SPECIALIST_VISIT"])

    def test_stored_post_evaluation_is_consistent(self):
        path = pathlib.Path(__file__).resolve().parents[2] / "data/scribe/post-eval-v1.json"
        if not path.exists():
            self.skipTest("run scribe/post_eval.py first")
        import post_eval as P

        d = json.loads(path.read_text())
        self.assertTrue(d["synthetic"])
        for lim, v in d["selective"]["limits"].items():
            for part in ("validation", "test_all", "haiku"):
                c = v[part]
                if c.get("admitted"):
                    self.assertAlmostEqual(c["error_upper_bound_95_one_sided"], P.upper_bound(c["errors_among_admitted"], c["admitted"]), places=9)
                    self.assertGreaterEqual(c["error_upper_bound_95_one_sided"], c["error_rate_among_admitted"])
            self.assertLessEqual(v["validation"]["error_rate_among_admitted"], float(lim))   # the rule holds where it was fitted
        val = d["predictions"]["val"]
        self.assertEqual(len(val), d["selective"]["validation_notes"])
        self.assertEqual(sum(x["ok"] for x in val), round(d["selective"]["validation_exact_match"]["value"] * len(val)))
        o = d["pathway_order_check"]
        self.assertEqual(o["accepted_episodes_with_reversed_pair"], sum(o["episodes_with_reversed_pair"][k] for k in ("train", "val", "test")))


class ReviewFixes(unittest.TestCase):
    """Fixes after the independent review (runs/review-findings-wf1.json). No model is loaded, nothing is downloaded."""

    ROOT = pathlib.Path(__file__).resolve().parents[2]

    def test_risk_coverage_is_labelled_in_sample(self):
        rc = risk_coverage([3, 2, 1], [True, True, False])
        self.assertIn("In sample", rc["limit"])
        self.assertIn("Not an error guarantee", rc["limit"])

    def test_date_errors_do_not_depend_on_hash_order(self):
        g = {"entry_route": "PRIVATE", "events": [
            {"type": "DIAGNOSIS", "date": "2025-01-10", "precision": "DAY"},
            {"type": "FIRST_CONTACT", "date": "2025-01-01", "precision": "DAY"},
            {"type": "REFERRAL_SENT", "date": "2025-01-05", "precision": "DAY"}]}
        p = {"entry_route": "PRIVATE", "events": [
            {"type": "DIAGNOSIS", "date": "2025-01-13", "precision": "DAY"},
            {"type": "FIRST_CONTACT", "date": "2025-01-02", "precision": "DAY"},
            {"type": "REFERRAL_SENT", "date": "2025-01-07", "precision": "DAY"}]}
        # types visited in sorted order: DIAGNOSIS, FIRST_CONTACT, REFERRAL_SENT
        self.assertEqual(summary([{"target_json": json.dumps(g)}], [p])["date_errors_days"], [3, 1, 2])

    def test_dedup_rule(self):
        from build_dataset import dedup

        rows = [{"id": "a", "accepted": False, "n": 1}, {"id": "b", "accepted": True, "n": 2},
                {"id": "a", "accepted": True, "n": 3}, {"id": "b", "accepted": True, "n": 4}]
        self.assertEqual([r["n"] for r in dedup(rows)], [1, 2])                        # rule used for dataset-v1
        self.assertEqual([r["n"] for r in dedup(rows, prefer_accepted=True)], [3, 2])  # corrected rule, first-seen id order

    def test_cuda_path_check_helpers(self):
        import check_cuda_path as C

        src = "from transformers import TrainingArguments\nx = TrainingArguments(output_dir='o', warmup_ratio=0.1, seed=1)\n"
        self.assertEqual(C.training_argument_keywords(src), [{"line": 2, "keywords": ["output_dir", "warmup_ratio", "seed"]}])
        real = C.training_argument_keywords((self.ROOT / "scribe/train_lora.py").read_text())
        self.assertTrue(any("warmup_ratio" in c["keywords"] for c in real))
        self.assertEqual(C.unpinned_installs('pip install torch==2.15.0 transformers peft==0.21.3 accelerate pyarrow'), ["accelerate", "transformers"])
        self.assertEqual(C.unpinned_installs('# pip install torch\npip install pyarrow'), [])

    def test_stored_cuda_path_check(self):
        path = self.ROOT / "data/scribe/cuda-path-check-v1.json"
        if not path.exists():
            self.skipTest("run scribe/check_cuda_path.py first")
        d = json.loads(path.read_text())
        self.assertEqual(d["would_construct"], not d["keywords_rejected"])
        log = [json.loads(x) for x in (self.ROOT / "runs/train.jsonl").read_text().splitlines() if x.strip()]
        box = next(x for x in log if x["step"] == "gpu_setup")["metrics"]["transformers"]
        self.assertEqual(d["transformers_on_gpu_box"], box)

    def test_order_check_and_card_agree_with_the_validator(self):
        path = self.ROOT / "data/scribe/post-eval-v1.json"
        if not path.exists():
            self.skipTest("run scribe/post_eval.py first")
        o = json.loads(path.read_text())["pathway_order_check"]
        v = o["eventlog_validator"]["by_split"]
        for split, n in o["episodes_with_reversed_pair"].items():
            self.assertEqual(v[split]["episodes_flagged"], n)
            self.assertTrue(v[split]["same_episodes_as_pair_check"])
        card = (self.ROOT / "data/scribe/dataset-v1/CARD.md").read_text()
        self.assertIn(f"{o['accepted_episodes_with_reversed_pair']} of {o['accepted_episodes']} accepted episodes", card)
        overlap = json.loads(path.read_text())["split_overlap"]
        self.assertEqual(overlap["crossing_splits"], {"ids": 0, "targets": 0, "note_texts": 0})

    def test_validator_sees_a_reversed_ground_truth(self):
        import post_eval as P

        good = {"id": "g", "target_json": json.dumps({"entry_route": "PRIVATE", "events": [
            {"type": "DIAGNOSIS", "date": "2024-01-10", "precision": "DAY"}, {"type": "SPECIALIST_VISIT", "date": "2024-02-01", "precision": "DAY"}]})}
        bad = {"id": "b", "target_json": json.dumps({"entry_route": "PRIVATE", "events": [
            {"type": "SPECIALIST_VISIT", "date": "2024-01-10", "precision": "DAY"}, {"type": "MDT_DECISION", "date": "2024-02-01", "precision": "DAY"}]})}
        r = P.validator_order_check([good, bad])
        self.assertEqual((r["episodes_flagged"], r["flagged_ids"], r["strict_mode_valid"]), (1, ["b"], False))
        self.assertTrue(P.validator_order_check([good])["strict_mode_valid"])

    def test_provenance_matches_the_run_log(self):
        path = self.ROOT / "data/scribe/provenance-v1.json"
        if not path.exists():
            self.skipTest("run scribe/provenance.py first")
        prov = json.loads(path.read_text())
        calls = {}
        for line in (self.ROOT / "runs/scribe.jsonl").read_text().splitlines():
            if '"verifier_call"' in line:
                d = json.loads(line)
                calls[d["inputs"]["model"]] = calls.get(d["inputs"]["model"], 0) + 1
        self.assertEqual({k: v["calls"] for k, v in prov["verifier"]["calls_by_alias"].items()}, calls)
        self.assertEqual(prov["verifier"]["calls"], sum(calls.values()))
        for key in ("upstream_repository",):
            self.assertTrue(prov["base_model"][key])
        for key in ("gemma_terms_of_use", "gemma_prohibited_use_policy"):
            self.assertTrue(prov["terms"][key].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
