"""serve/smoke_test.py against the fake server: report contents and exit status."""

import contextlib
import io
import json
import math
import os
import socket
import tempfile
import unittest

import support
import smoke_test
from fake_vllm import API_KEY, FakeVLLM

ROWS = support.heldout()


def answers(wrong=0, invalid=0, total_logprob=math.log(0.9)):
    """Gold answers, except the first `wrong` notes get a wrong route and the next
    `invalid` notes get text that is not JSON."""
    out = {}
    for i, row in enumerate(ROWS):
        content = row["target_json"]
        if i < wrong:
            target = json.loads(content)
            target["entry_route"] = "EMERGENCY" if target["entry_route"] != "EMERGENCY" else "PRIVATE"
            content = support.compact(target)
        elif i < wrong + invalid:
            content = "Potilas on"
        out[support.user_content(row)] = {"content": content, "total_logprob": total_logprob}
    return out


class SmokeTest(unittest.TestCase):
    def setUp(self):
        os.environ["SERVE_TEST_KEY"] = API_KEY
        self.addCleanup(os.environ.pop, "SERVE_TEST_KEY", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_smoke(self, base_url, *extra):
        out = os.path.join(self.tmp.name, "report.json")
        argv = ["--base-url", base_url, "--api-key-env", "SERVE_TEST_KEY", "--retries", "0", "--timeout", "5",
                "--confidence", "seq_prob", "--no-log", "--out", out, *extra]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = smoke_test.main(argv)
        report = None
        if os.path.exists(out):
            with open(out, encoding="utf-8") as handle:
                report = json.load(handle)
            os.unlink(out)
        return code, report, stderr.getvalue()

    def test_all_correct_passes(self):
        with FakeVLLM(answers()) as server:
            code, report, _ = self.run_smoke(server.base_url, "--threshold", "0.8")
            self.assertIn(("GET", "/v1/models"), server.paths)
        self.assertEqual(code, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["n"], 50)
        self.assertEqual(report["exact_match"]["value"], 1.0)
        self.assertEqual(report["exact_match"]["n"], 50)
        self.assertEqual(report["valid_output_rate"]["value"], 1.0)
        self.assertEqual(report["requests"], {"answered": 50, "valid_output": 50, "invalid_output": 0,
                                              "failed": 0, "retried": 0, "failure_kinds": []})
        self.assertEqual(report["decisions"], {"AUTO_ACCEPT": 50})
        self.assertEqual(report["auto_accept"]["wrong"], 0)
        latency = report["latency_seconds"]
        self.assertEqual(latency["n"], 49)  # first request reported apart
        for key in ("p50", "p90", "p95", "p99", "max", "mean", "first_request_s"):
            self.assertGreater(latency[key], 0.0, key)
        self.assertLessEqual(latency["p50"], latency["p90"])
        self.assertLessEqual(latency["p90"], latency["p95"])
        self.assertLessEqual(latency["p95"], latency["p99"])
        self.assertLessEqual(latency["p99"], latency["max"])
        self.assertTrue(report["synthetic"])
        self.assertEqual(report["served_models"], ["gemma-base", "pathway-scribe"])
        self.assertNotIn(API_KEY, json.dumps(report))

    def test_below_exact_match_floor_exits_1(self):
        with FakeVLLM(answers(wrong=45)) as server:
            code, report, err = self.run_smoke(server.base_url)
        self.assertEqual(code, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["exact_match"]["value"], 0.1)
        self.assertEqual(report["route_accuracy"]["value"], 0.1)
        self.assertEqual(report["floors"]["min_exact_match"], 0.2)
        self.assertIn("exact match 0.1 below floor 0.2", err)
        self.assertEqual(report["decisions"], {"HUMAN_REVIEW": 50})

    def test_floor_is_configurable(self):
        with FakeVLLM(answers(wrong=30)) as server:
            code, report, _ = self.run_smoke(server.base_url)
            self.assertEqual((code, report["exact_match"]["value"]), (0, 0.4))
            code, report, err = self.run_smoke(server.base_url, "--min-exact-match", "0.5")
        self.assertEqual(code, 1)
        self.assertIn("exact match 0.4 below floor 0.5", err)

    def test_invalid_output_floor(self):
        with FakeVLLM(answers(invalid=10)) as server:
            code, report, err = self.run_smoke(server.base_url)
        self.assertEqual(code, 1)
        self.assertEqual(report["valid_output_rate"]["value"], 0.8)
        self.assertEqual(report["exact_match"]["value"], 0.8)
        self.assertEqual(report["requests"]["invalid_output"], 10)
        self.assertIn("valid-output rate 0.8 below floor 0.9", err)

    def test_latency_ceiling(self):
        with FakeVLLM(answers()) as server:
            code, report, err = self.run_smoke(server.base_url, "--max-p95-seconds", "0.000001")
        self.assertEqual(code, 1)
        self.assertIn("p95 latency", err)

    def test_limit(self):
        with FakeVLLM(answers()) as server:
            code, report, _ = self.run_smoke(server.base_url, "--limit", "7", "--concurrency", "1")
            self.assertEqual(len(server.requests), 7)
        self.assertEqual((code, report["n"]), (0, 7))

    def test_unreachable_endpoint_exits_2(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        code, report, err = self.run_smoke(f"http://127.0.0.1:{port}")
        self.assertEqual(code, 2)
        self.assertIsNone(report)
        self.assertIn("could not run", err)

    def test_adapter_not_served_exits_2(self):
        with FakeVLLM(answers(), models=("gemma-base",)) as server:
            code, report, err = self.run_smoke(server.base_url)
            self.assertEqual(server.requests, [])
        self.assertEqual(code, 2)
        self.assertIn("not served", err)

    def test_wrong_key_exits_2(self):
        os.environ["SERVE_TEST_KEY"] = "wrong"
        with FakeVLLM(answers()) as server:
            code, _, err = self.run_smoke(server.base_url)
        self.assertEqual(code, 2)
        self.assertNotIn("wrong", err.replace("wrong_", ""))

    def test_every_request_failing_exits_2(self):
        with FakeVLLM(answers(), fail_first=10**6) as server:
            code, report, err = self.run_smoke(server.base_url, "--limit", "5")
        self.assertEqual(code, 2)
        self.assertEqual(report["requests"]["failed"], 5)
        self.assertIn("every request failed", err)

    def test_prompt_format_mismatch_exits_2_before_any_request(self):
        with FakeVLLM(answers()) as server:
            code, _, err = self.run_smoke(server.base_url, "--format", "expression")
            self.assertEqual(server.paths, [])
        self.assertEqual(code, 2)
        self.assertIn("expression", err)

    def test_percentile_is_nearest_rank(self):
        values = [5, 1, 4, 2, 3]
        self.assertEqual(smoke_test.percentile(values, 50), 3)
        self.assertEqual(smoke_test.percentile(values, 90), 5)
        self.assertEqual(smoke_test.percentile(values, 20), 1)
        self.assertEqual(smoke_test.percentile(list(range(1, 101)), 95), 95)
        self.assertEqual(smoke_test.percentile(list(range(1, 101)), 99), 99)
        self.assertEqual(smoke_test.percentile([7], 99), 7)
        self.assertIsNone(smoke_test.percentile([], 50))


if __name__ == "__main__":
    unittest.main()
