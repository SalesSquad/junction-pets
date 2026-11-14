"""Synthetic boundary tests only; no provider calls or real credentials."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

import run_nim

TEST_KEY = "nvapi-SYNTHETIC_ONLY_NOT_A_REAL_CREDENTIAL_12345"


class NimRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for name in run_nim.SOURCE_FILES:
            shutil.copyfile(run_nim.ROOT / name, self.repo / name)
        def git(*args):
            return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null",
                "-c", "commit.gpgsign=false", "-c", "user.name=R5 Test",
                "-c", "user.email=r5-test@example.invalid", *args], cwd=self.repo, text=True).strip()
        git("init", "-q"); git("add", "."); git("commit", "-qm", "synthetic source fixture")
        self.commit = git("rev-parse", "HEAD")
        image_root = self.root / "images"
        image_root.mkdir()
        images = []
        for index, colour in enumerate(("red", "green", "blue", "yellow")):
            path = image_root / (str(index) + ".png")
            Image.new("RGB", (16, 16), colour).save(path)
            images.append({"image_path": str(path), "image_sha256": run_nim.sha256(path.read_bytes())})
        cases = [{"case_id": "q" + str(i).zfill(4), "split": "dev", "image_root": str(image_root),
                  "query": {**images[0], "source_view_index": 1, "title": "FORBIDDEN_QUERY_TITLE"},
                  "candidates": [{**images[j], "source_view_index": 0, "alias": "c0" + str(j)}
                                 for j in range(1, 4)]} for i in range(1, 9)]
        self.cases = self.root / "cases.json"
        self.cases.write_text(json.dumps({"work_id": run_nim.WORK_ID, "cases": cases}))
        self.output = self.root / "output"
        self.addCleanup(patch.stopall)
        patch.object(run_nim, "ROOT", self.repo).start()

    def invoke(self, extra=(), key=TEST_KEY, callback=None):
        env = {} if key is None else {"NVIDIA_API_KEY": key}
        argv = ["--cases", str(self.cases), "--output", str(self.output),
                "--source-commit", self.commit, *extra]
        with patch.dict("os.environ", env, clear=True), patch.object(run_nim, "post", side_effect=callback) as mocked:
            with redirect_stdout(io.StringIO()) as stdout:
                code = run_nim.main(argv)
        result = json.loads((self.output / "summary.json").read_text())
        self.assertNotIn(TEST_KEY, stdout.getvalue())
        for path in self.output.rglob("*.json"):
            self.assertNotIn(TEST_KEY, path.read_text())
        return code, result, mocked

    def response(self, route, payload, key, timeout):
        self.assertEqual(key, TEST_KEY)
        self.assertEqual(timeout, 120)
        self.assertNotIn(TEST_KEY, json.dumps(payload))
        self.assertNotIn("FORBIDDEN_QUERY_TITLE", json.dumps(payload))
        if route == run_nim.NIM_OCR:
            self.assertEqual(len(payload["input"]), 1)
            obj = {"model": route.model, "data": [{"index": 0, "text_detections": []}]}
        else:
            self.assertEqual(route, run_nim.NIM_NANO)
            images = [p for p in payload["messages"][1]["content"] if p["type"] == "image_url"]
            self.assertEqual(len(images), 4)
            content = {"ranking": ["c03", "c01", "c02"], "proposed_candidate": None,
                       "identifiability": "insufficient", "observations": [],
                       "additional_observation": {"kind": "label_closeup", "reason": "Unreadable label."}}
            obj = {"model": route.model, "choices": [{"finish_reason": "stop",
                   "message": {"content": json.dumps(content)}}]}
        raw = run_nim.canonical(obj)
        receipt = {"provider": route.name, "returned_model": route.model, "http_status": 200,
                   "status": "response_received", "request_sha256": run_nim.sha256(run_nim.canonical(payload)),
                   "response_sha256": run_nim.sha256(raw), "attempts": 1, "retry_performed": False}
        return receipt, obj, raw

    def test_missing_and_wrong_provider_credentials_block_without_calls(self):
        for index, key in enumerate((None, "dc_SYNTHETIC_NOT_A_NVIDIA_KEY")):
            self.output = self.root / ("blocked" + str(index))
            code, result, mocked = self.invoke(key=key)
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "BLOCKED_AUTH")
            self.assertEqual(result["inference_calls_attempted"], 0)
            self.assertEqual(result["http200_calls"], 0)
            self.assertFalse(list(self.output.rglob("*.observation.json")))
            mocked.assert_not_called()

    def test_default_canary_has_two_calls_and_distinct_provenance(self):
        code, result, mocked = self.invoke(callback=self.response)
        self.assertEqual(code, 0)
        self.assertEqual((mocked.call_count, result["maximum_inference_calls"], result["valid_observations"]), (2, 2, 2))
        self.assertTrue(result["source_and_cases_unchanged"])
        observations = [json.loads(p.read_text()) for p in self.output.rglob("*.observation.json")]
        self.assertEqual({o["model"] for o in observations}, {run_nim.OCR_MODEL, run_nim.NANO_MODEL})
        self.assertEqual({o["provider"] for o in observations}, {run_nim.NIM_OCR.name, run_nim.NIM_NANO.name})
        self.assertTrue(all(not o["qualification"] and not o["action_authorized"] for o in observations))

    def test_maximum_calls_and_concurrency_are_bounded(self):
        lock, active, peak = threading.Lock(), 0, 0
        def bounded(*args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1; peak = max(peak, active)
            try:
                time.sleep(0.005)
                return self.response(*args, **kwargs)
            finally:
                with lock: active -= 1
        code, result, mocked = self.invoke(("--case-count", "8", "--workers", "4"), callback=bounded)
        self.assertEqual(code, 0)
        self.assertEqual((mocked.call_count, result["inference_calls_attempted"]), (16, 16))
        self.assertLessEqual(peak, 4)
        self.assertGreater(peak, 1)

    def test_provider_auth_failure_stops_remaining_jobs_without_retry(self):
        def denied(route, payload, key, timeout):
            return {"status": "authentication_failed", "http_status": 401,
                    "attempts": 1, "retry_performed": False}, None, b'{"error":"synthetic denial"}'
        code, result, mocked = self.invoke(("--case-count", "8", "--workers", "1"), callback=denied)
        self.assertEqual(code, 1)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(result["inference_calls_attempted"], 1)
        self.assertEqual(result["valid_observations"], 0)
        self.assertEqual(sum(r["status"] == "SKIPPED_STOP_OR_DEADLINE" for r in result["records"]), 15)

    def test_changed_pixels_block_before_any_call(self):
        (self.root / "images" / "0.png").write_bytes(b"tampered")
        code, result, mocked = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "BLOCKED_INPUT")
        self.assertEqual(result["inference_calls_attempted"], 0)
        mocked.assert_not_called()

    def test_truncated_nano_completion_stops_without_observation_or_retry(self):
        def truncated(*args, **kwargs):
            receipt, obj, _ = self.response(*args, **kwargs)
            obj["choices"][0].update(finish_reason="length", message={"content": None})
            raw = run_nim.canonical(obj)
            receipt["response_sha256"] = run_nim.sha256(raw)
            return receipt, obj, raw
        code, result, mocked = self.invoke(("--models", "nano", "--case-count", "8", "--workers", "1"), callback=truncated)
        self.assertEqual(code, 1)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(result["valid_observations"], 0)
        self.assertFalse(list(self.output.rglob("*.observation.json")))

    def test_source_manifest_change_during_call_invalidates_run(self):
        def changed(*args, **kwargs):
            response = self.response(*args, **kwargs)
            self.cases.write_text(self.cases.read_text() + "\n")
            return response
        code, result, _ = self.invoke(("--models", "ocr"), callback=changed)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "SOURCE_CHANGED")
        self.assertFalse(result["source_and_cases_unchanged"])


if __name__ == "__main__":
    unittest.main()
