"""Real CLI subprocess checks using only synthetic files and isolated roots."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from jsonschema import Draft202012Validator
import numpy as np

from contract import strict_json_loads

SOURCE = Path(__file__).resolve().parent
R3_SHA256 = "933de9d32de9782e4b399ef7f5d0a87c94e8389dd65f7ed1eae96a541f0250b1"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="meta-acceleration-cli-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source" / "retrieval-acceleration"
        self.source.mkdir(parents=True)
        for name in ("cli.py", "contract.py", "candidate_index.py", "reconcile.py"):
            shutil.copy2(SOURCE / name, self.source / name)
        helper = SOURCE.parent / "retrieval-r3" / "visual_adapter.py"
        helper_bytes = helper.read_bytes()
        self.assertEqual(hashlib.sha256(helper_bytes).hexdigest(), R3_SHA256)
        helper_copy = self.source.parent / "retrieval-r3" / "visual_adapter.py"
        helper_copy.parent.mkdir()
        helper_copy.write_bytes(helper_bytes)
        self.cli = self.source / "cli.py"
        self.schema = strict_json_loads((SOURCE / "output.schema.json").read_bytes())
        Draft202012Validator.check_schema(self.schema)
        self.validator = Draft202012Validator(self.schema)

    def invoke(self, *args):
        environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                           PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-B", str(self.cli), *map(str, args)],
                              cwd=self.root, env=environment, capture_output=True,
                              text=True, timeout=20)

    def arrays(self, gallery_count=8, *, weights=False):
        gallery = np.zeros((gallery_count, 768), dtype=np.float32)
        gallery[np.arange(gallery_count), np.arange(gallery_count)] = 1
        arrays = {"gallery_features": gallery,
                  "gallery_ids": np.asarray([f"g{i:03}" for i in range(gallery_count)]),
                  "query_features": gallery[:2].copy(),
                  "query_ids": np.asarray(["q0", "q1"])}
        if weights:
            arrays["a"] = np.zeros((768, 64), dtype=np.float32)
            arrays["b"] = np.zeros((64, 768), dtype=np.float32)
            arrays["a"][0, 0] = .2
            arrays["b"][0, 1] = .1
        return arrays

    def bundle(self, name="features.npz", *, gallery_count=8, weights=False):
        path = self.root / name
        np.savez(path, **self.arrays(gallery_count, weights=weights))
        return path

    def assert_error(self, process, code, output):
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertEqual(process.stdout, "")
        self.assertNotIn("Traceback", process.stderr)
        error = strict_json_loads(process.stderr)
        self.assertEqual(error["kind"], "meta.retrieval-acceleration.error")
        self.assertEqual(error["code"], code)
        for key in ("qualification", "action_authorized", "physical_identity_verified"):
            self.assertIs(error[key], False)
        self.assertFalse(output.exists())

    def read_success(self, process, output, kind):
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        summary = strict_json_loads(process.stdout)
        self.assertEqual(summary["kind"], kind)
        result = strict_json_loads(output.read_bytes())
        self.validator.validate(result)
        for key in ("qualification", "action_authorized", "physical_identity_verified"):
            self.assertIs(result[key], False)
        return result

    def test_real_search_npz_identity_and_residual_are_schema_valid(self):
        for trained in (False, True):
            with self.subTest(trained=trained):
                source = self.bundle(f"features-{trained}.npz", weights=trained)
                output = self.root / f"ranked-{trained}.json"
                process = self.invoke("search", "--features", source, "--top-k", 3,
                                      "--batch-size", 1, "--output", output)
                result = self.read_success(process, output, "meta.retrieval-acceleration.candidates")
                self.assertEqual(result["feature_npz_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(result["index"]["adapter_rank"], 64 if trained else 0)
                self.assertEqual(result["query_chunks"], 2)
                self.assertIsNone(result["accepted_candidate"])
                self.assertIsNone(result["r3_selection"])
                self.assertEqual(result["queries"][0]["candidates"][0]["candidate_id"], "g000")
                self.assertEqual(result["queries"][1]["candidates"][0]["candidate_id"], "g001")
                second_score = result["queries"][0]["candidates"][1]["score"]
                if trained:
                    self.assertGreater(second_score, .01)
                else:
                    self.assertEqual(second_score, 0)

    def test_real_search_top128_and_gallery_limit(self):
        source = self.bundle(gallery_count=140)
        output = self.root / "top128.json"
        process = self.invoke("search", "--features", source, "--top-k", 128, "--output", output)
        result = self.read_success(process, output, "meta.retrieval-acceleration.candidates")
        self.assertEqual(len(result["queries"][0]["candidates"]), 128)
        self.assertEqual([item["gallery_index"] for item in result["queries"][0]["candidates"]], list(range(128)))
        invalid = self.root / "top129.json"
        self.assert_error(self.invoke("search", "--features", source, "--top-k", 129, "--output", invalid),
                          "invalid_limit", invalid)
        small = self.bundle("small.npz", gallery_count=7)
        invalid = self.root / "too-many-for-gallery.json"
        self.assert_error(self.invoke("search", "--features", small, "--top-k", 8, "--output", invalid),
                          "invalid_limit", invalid)

    def test_object_npz_is_rejected_without_pickle_loading(self):
        arrays = self.arrays()
        arrays["gallery_ids"] = np.asarray([{"never_unpickle": i} for i in range(8)], dtype=object)
        source = self.root / "object.npz"; np.savez(source, **arrays)
        output = self.root / "object-result.json"
        self.assert_error(self.invoke("search", "--features", source, "--top-k", 3, "--output", output),
                          "feature_dtype", output)

    def test_duplicate_npz_members_are_rejected(self):
        source = self.bundle()
        duplicate = self.root / "duplicate.npz"
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(duplicate, "w") as target:
            for item in original.infolist():
                target.writestr(item.filename, original.read(item.filename))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                target.writestr("gallery_ids.npy", original.read("gallery_ids.npy"))
        output = self.root / "duplicate-result.json"
        self.assert_error(self.invoke("search", "--features", duplicate, "--top-k", 3, "--output", output),
                          "feature_members", output)

    def test_oversize_shape_is_rejected_before_materialization(self):
        source = self.bundle()
        forged = self.root / "oversize-header.npz"
        header = io.BytesIO()
        np.lib.format.write_array_header_1_0(header, {"descr": "<f4", "fortran_order": False,
                                                    "shape": (50_001, 768)})
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(forged, "w") as target:
            for item in original.infolist():
                target.writestr(item.filename, header.getvalue() if item.filename == "gallery_features.npy"
                                else original.read(item.filename))
        self.assertLess(forged.stat().st_size, 100_000)
        output = self.root / "oversize-result.json"
        self.assert_error(self.invoke("search", "--features", forged, "--top-k", 3, "--output", output),
                          "feature_shape", output)

    def test_existing_output_is_never_overwritten(self):
        source = self.bundle()
        output = self.root / "existing.json"
        original = b'{"retained":"synthetic prior output"}\n'
        output.write_bytes(original)
        process = self.invoke("search", "--features", source, "--top-k", 3, "--output", output)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(strict_json_loads(process.stderr)["code"], "filesystem_error")
        self.assertEqual(output.read_bytes(), original)

    def test_identity_selection_uses_pinned_r3_neighbor(self):
        source = self.bundle()
        training = self.root / "identity-training"; training.mkdir()
        identity = {"kind": "identity", "epoch": 0, "checkpoint": None, "checkpoint_sha256": None}
        selection = {"schema_version": 1, "kind": "meta.visual_adapter.r3.selection",
                     "fresh_cal_test_evaluated": False, "primary": identity,
                     "confirmation_candidate": dict(identity)}
        raw = (json.dumps(selection, sort_keys=True) + "\n").encode()
        (training / "selection.json").write_bytes(raw)
        output = self.root / "identity-selection.json"
        process = self.invoke("search", "--features", source, "--r3-training-root", training,
                              "--top-k", 3, "--output", output)
        result = self.read_success(process, output, "meta.retrieval-acceleration.candidates")
        self.assertEqual(result["index"]["adapter_rank"], 0)
        self.assertEqual(result["r3_selection"]["selection_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["r3_selection"]["loader_sha256"], R3_SHA256)
        self.assertIsNone(result["r3_selection"]["checkpoint_sha256"])
        self.assertIs(result["r3_selection"]["qualification_evaluated"], False)

    def test_null_selection_is_a_structured_cli_error(self):
        source = self.bundle()
        training = self.root / "null-training"; training.mkdir()
        (training / "selection.json").write_text("null\n")
        output = self.root / "null-selection.json"
        self.assert_error(self.invoke("search", "--features", source, "--r3-training-root", training,
                                      "--top-k", 3, "--output", output), "r3_selection", output)

    def test_synthetic_safetensors_selection_and_checkpoint_binding(self):
        from safetensors.numpy import save_file
        source = self.bundle()
        training = self.root / "synthetic-adapter-training"; training.mkdir()
        arrays = self.arrays(weights=True)
        weights = {key: arrays[key] for key in ("a", "b")}
        checkpoint = training / "synthetic.safetensors"
        save_file(weights, str(checkpoint))
        digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        adapter = {"kind": "adapter", "epoch": 1, "checkpoint": checkpoint.name,
                   "checkpoint_sha256": digest}
        selection = {"schema_version": 1, "kind": "meta.visual_adapter.r3.selection",
                     "fresh_cal_test_evaluated": False, "primary": adapter,
                     "confirmation_candidate": dict(adapter)}
        raw = (json.dumps(selection, sort_keys=True) + "\n").encode()
        (training / "selection.json").write_bytes(raw)
        output = self.root / "synthetic-adapter-selection.json"
        process = self.invoke("search", "--features", source, "--r3-training-root", training,
                              "--top-k", 3, "--output", output)
        result = self.read_success(process, output, "meta.retrieval-acceleration.candidates")
        self.assertEqual(result["index"]["adapter_rank"], 64)
        self.assertEqual(result["r3_selection"]["selection_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["r3_selection"]["checkpoint_sha256"], digest)
        self.assertEqual(result["r3_selection"]["loader_sha256"], R3_SHA256)
        for key in ("a", "b"):
            expected = hashlib.sha256(weights[key].astype("<f4").tobytes(order="C")).hexdigest()
            self.assertEqual(result["index"]["bindings"][f"adapter_{key}_sha256"], expected)
        self.assertGreater(result["queries"][0]["candidates"][1]["score"], .01)
        self.assertIs(result["r3_selection"]["qualification_evaluated"], False)

        # Preserve both selection slots and alter only the declared checkpoint digest.
        for key in ("primary", "confirmation_candidate"):
            selection[key]["checkpoint_sha256"] = "0" * 64
        (training / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
        invalid = self.root / "mismatched-checkpoint-result.json"
        self.assert_error(self.invoke("search", "--features", source, "--r3-training-root", training,
                                      "--top-k", 3, "--output", invalid), "r3_selection", invalid)

    def test_real_reconciliation_cli_is_schema_valid(self):
        from test_reconcile import make_run
        args = make_run(self.root / "synthetic-r5", case_count=1)
        output = self.root / "reconciled.json"
        process = self.invoke("reconcile", "--run-dir", args["run_dir"], "--cases", args["cases_path"],
                              "--expected-source-commit", args["expected_source_commit"],
                              "--expected-model", args["expected_model"], "--output", output)
        result = self.read_success(process, output, "meta.retrieval-acceleration.r5-reconciliation")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["counts"]["valid_observations"], 4)
        self.assertIsNone(result["counts"]["actual_inference_calls"])
        self.assertEqual(len(result["additional_observation_requests"]), 1)
        request = result["additional_observation_requests"][0]
        self.assertEqual(request["requesting_lanes"], ["visual", "detail"])
        self.assertEqual(request["status"], "proposed")
        self.assertIs(request["captured"], False)
        self.assertFalse((self.root / "synthetic-r5/synthetic-images-not-captured").exists())


if __name__ == "__main__":
    unittest.main()
