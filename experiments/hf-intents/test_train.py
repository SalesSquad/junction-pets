import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name("train.py")
SPEC = importlib.util.spec_from_file_location("intent_train", SCRIPT)
train = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(train)


def parquet(path, texts, labels, dataset="banking77"):
    import pyarrow as pa
    import pyarrow.parquet as pq

    text, label, count = train.DATASETS[dataset]
    names = [f"class-{i}" for i in range(count)]
    meta = {"info": {"features": {label: {"names": names, "_type": "ClassLabel"}}}}
    table = pa.table({text: texts, label: labels}).replace_schema_metadata({b"huggingface": json.dumps(meta).encode()})
    pq.write_table(table, path)


class BudgetTests(unittest.TestCase):
    def test_expired_cutoff_refuses_before_data_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "never-created"
            result = subprocess.run([sys.executable, str(SCRIPT), "run", "--dataset", "banking77", "--lane", "word_svm",
                                     "--data-dir", "/nonexistent", "--out", str(out), "--seconds", "30",
                                     "--cutoff", "2020-01-01T00:00:00Z", "--source-sha", "a" * 40, "--run-id", "123"],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 3)
            self.assertIn("cutoff reached", result.stderr)
            self.assertFalse(out.exists())

    def test_caller_cannot_extend_hard_deadline(self):
        self.assertEqual(train.cutoff_timestamp("2099-01-01T00:00:00Z"), train.HARD_CUTOFF)
        with self.assertRaises(ValueError):
            train.require_time(train.HARD_CUTOFF, 5, now=train.HARD_CUTOFF)

    def test_checkpoint_corruption_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "best.skops").write_bytes(b"owned model bytes")
            train.atomic_json(root / "best.json", {"model_sha256": train.digest_file(root / "best.skops"), "dataset": "banking77"})
            self.assertEqual(train.validate_checkpoint(root, {"dataset": "banking77"})["dataset"], "banking77")
            (root / "best.skops").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                train.validate_checkpoint(root)

    def test_distinct_reproducible_trial_configs(self):
        self.assertEqual(train.configuration("banking77", "word_svm", 1), train.configuration("banking77", "word_svm", 1))
        self.assertNotEqual(train.configuration("banking77", "word_svm", 1), train.configuration("banking77", "word_svm", 2))

    def test_timed_out_candidate_is_terminated_and_previous_best_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {"texts": ["alpha", "beta"], "labels": [0, 1], "groups": ["alpha", "beta"],
                    "validation_texts": ["held alpha"], "validation_labels": [0],
                    "label_names": ["alpha", "beta"], "protocol": {}}
            identity = {"dataset": "banking77", "lane": "word_svm", "source_sha": "a" * 40,
                        "run_id": "123", "prepared_sha256": train.hashlib.sha256(train.canonical(data)).hexdigest()}
            (root / "best.skops").write_bytes(b"previous model")
            previous = dict(identity, trial=0, cv_macro_f1=0.5, model_sha256=train.digest_file(root / "best.skops"))
            train.atomic_json(root / "best.json", previous)
            now = [train.HARD_CUTOFF - 100]
            child = mock.Mock(pid=987654)
            def wait(timeout):
                if now[0] < train.HARD_CUTOFF - 90:
                    now[0] += 10
                    raise subprocess.TimeoutExpired("candidate", timeout)
                return 0
            child.wait.side_effect = wait
            args = train.argparse.Namespace(dataset="banking77", lane="word_svm", source_sha="a" * 40,
                         run_id="123", cutoff="2026-11-15T16:40:00Z", seconds=10, max_trials=10,
                         out=str(root), data_dir="not-opened")
            with mock.patch.object(train.time, "time", side_effect=lambda: now[0]), \
                 mock.patch.object(train, "split_data", return_value=data), \
                 mock.patch.object(train.subprocess, "Popen", return_value=child), \
                 mock.patch.object(train.os, "killpg") as kill:
                self.assertEqual(train.run(args), 0)
            kill.assert_called_once_with(987654, train.signal.SIGTERM)
            self.assertEqual(train.validate_checkpoint(root), previous)
            self.assertEqual(train.history_rows(root)[0]["status"], "timeout")

    def test_interrupted_checkpoint_trial_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {"texts": ["alpha", "beta"], "labels": [0, 1], "groups": ["alpha", "beta"],
                    "validation_texts": ["held alpha"], "validation_labels": [0],
                    "label_names": ["alpha", "beta"], "protocol": {}}
            identity = {"dataset": "banking77", "lane": "word_svm", "source_sha": "a" * 40,
                        "run_id": "123", "prepared_sha256": train.hashlib.sha256(train.canonical(data)).hexdigest()}
            (root / "best.skops").write_bytes(b"previous model")
            previous = dict(identity, trial=0, cv_macro_f1=0.5, model_sha256=train.digest_file(root / "best.skops"))
            train.atomic_json(root / "best.json", previous)
            interrupted = root / "checkpoints" / "trial-000003"
            interrupted.mkdir(parents=True)
            (interrupted / "best.skops").write_bytes(b"interrupted publication")
            args = train.argparse.Namespace(dataset="banking77", lane="word_svm", source_sha="a" * 40,
                         run_id="123", cutoff="2026-11-15T16:40:00Z", seconds=10, max_trials=4,
                         out=str(root), data_dir="not-opened")
            with mock.patch.object(train.time, "time", return_value=train.HARD_CUTOFF - 100), \
                 mock.patch.object(train, "split_data", return_value=data), \
                 mock.patch.object(train.subprocess, "Popen") as launch:
                self.assertEqual(train.run(args), 0)
            launch.assert_not_called()
            self.assertEqual(train.validate_checkpoint(root), previous)
            self.assertEqual((interrupted / "best.skops").read_bytes(), b"interrupted publication")


class DataAndModelTests(unittest.TestCase):
    def test_grouped_validation_has_no_normalized_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            texts, labels = [], []
            for group in range(40):
                texts.extend([f"category {group % 2} item {group}", f" CATEGORY {group % 2}  ITEM {group} "])
                labels.extend([group % 2] * 2)
            parquet(Path(directory) / "train.parquet", texts, labels)
            data = train.split_data(directory, "banking77")
            self.assertFalse(set(data["groups"]) & {train.normalized_text(text) for text in data["validation_texts"]})
            self.assertEqual(len(data["texts"]) + len(data["validation_texts"]), len(texts))

    def test_official_validation_overlap_is_removed_from_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parquet(root / "train.parquet", ["A shared query", "alpha one", "beta two", "alpha three", "beta four"], [0, 0, 1, 0, 1], "massive-fi-FI")
            parquet(root / "validation.parquet", [" a SHARED   query ", "held beta"], [0, 1], "massive-fi-FI")
            data = train.split_data(root, "massive-fi-FI")
            self.assertEqual(data["protocol"]["overlapping_training_rows_removed"], 1)
            self.assertNotIn("a shared query", data["groups"])

    def test_tiny_training_checkpoint_safe_reload_and_evaluation(self):
        if dt.datetime.now(dt.timezone.utc).timestamp() >= train.HARD_CUTOFF:
            self.skipTest("authorized training window has ended")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            texts = [f"{'refund money' if i % 2 else 'activate card'} example number {i}" for i in range(100)]
            labels = [i % 2 for i in range(100)]
            parquet(root / "train.parquet", texts, labels)
            for lane in train.LANES:
                with self.subTest(lane=lane):
                    out = root / lane
                    command = [sys.executable, str(SCRIPT), "run", "--dataset", "banking77", "--lane", lane,
                               "--data-dir", str(root), "--out", str(out), "--seconds", "45", "--max-trials", "1",
                               "--cutoff", "2026-11-15T16:40:00Z", "--source-sha", "a" * 40, "--run-id", "123"]
                    result = subprocess.run(command, text=True, capture_output=True, timeout=55)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr + (out / "candidate.log").read_text())
                    best = train.validate_checkpoint(out)
                    self.assertEqual(best["trial"], 0)
                    self.assertEqual(best["source_sha"], "a" * 40)
                    rows_before = train.history_rows(out)
                    again = subprocess.run(command, text=True, capture_output=True, timeout=55)
                    self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                    self.assertEqual(train.history_rows(out), rows_before)
                    # Test data becomes available only for this final evaluation command.
                    parquet(root / "test.parquet", ["refund money please", "activate card please"], [1, 0])
                    evaluation = root / f"evaluation-{lane}.json"
                    scored = subprocess.run([sys.executable, str(SCRIPT), "evaluate", "--dataset", "banking77", "--model", str(out / "best.skops"),
                                             "--data-dir", str(root), "--out", str(evaluation)], text=True, capture_output=True, timeout=30)
                    self.assertEqual(scored.returncode, 0, scored.stdout + scored.stderr)
                    metrics = json.loads(evaluation.read_text())
                    if lane == "word_svm":
                        self.assertEqual(metrics["accuracy"], 1.0)
                    self.assertTrue(0 <= metrics["accuracy"] <= 1)
                    self.assertEqual(len(metrics["absent_classes"]), 75)


if __name__ == "__main__":
    unittest.main()
