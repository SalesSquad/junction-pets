import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).with_name("integration_campaign.py")
spec = importlib.util.spec_from_file_location("rml1_integration", MODULE)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class ChibiAdapterTests(unittest.TestCase):
    def test_absent_checkout_is_explicit_and_nonexecuting(self):
        steps = []
        result = lab.verify_chibi(None, Path("/tmp"), steps, 100)
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(steps, [])

    def test_invalid_checkout_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            steps = []
            result = lab.verify_chibi(Path(temp), Path(temp), steps, 100)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(steps[0]["name"], "chibi_market_real_rust")

    def test_exact_source_and_bounded_count_forwarded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "chibi"
            script = root / "tools/ci/seeded_factory.py"
            script.parent.mkdir(parents=True)
            script.write_text("# test fixture\n")
            result_root = Path(temp) / "out"
            result_root.mkdir()
            steps = []
            sha = "a" * 40
            with patch.object(lab, "git_sha", return_value=sha), patch.object(
                lab, "run_step", return_value={"name": "chibi_market_real_rust", "status": "pass",
                                               "exit_code": 0}
            ) as runner:
                result = lab.verify_chibi(root, result_root, steps, 12345)
            self.assertEqual(result["status"], "pass")
            args, _ = runner.call_args
            command = args[1]
            self.assertIn(sha, command)
            self.assertEqual(command[command.index("--campaign-count") + 1], "12345")
            self.assertEqual(command[command.index("--lane") + 1], "market")
            self.assertEqual(steps[0]["status"], "pass")

    def test_report_displays_missing_chibi_without_forging_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = {
                "overall": "incomplete", "junction_source_sha": "a"*40,
                "factory_source_sha": None,
                "chibi_integration": {"status": "not_run"},
                "steps": [{"name": "factory_benign_broker", "status": "not_run"}],
                "simulation": None,
            }
            lab.write_report(Path(temp), receipt)
            report = (Path(temp) / "REPORT.md").read_text()
            self.assertIn("INCOMPLETE", report)
            self.assertIn("not_run", report)
            self.assertIn("runtime authorization **false**", report)


if __name__ == "__main__":
    unittest.main()
