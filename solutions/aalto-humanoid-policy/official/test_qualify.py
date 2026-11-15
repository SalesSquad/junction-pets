"""Pure stdlib admission/parser tests. Never connect to the policy server."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import qualify as q


def good(n=100):
    return dict(calls=n, ticks=n, command_hz=42.5, min_hz=27.0,
                latency_ms_p50=23.04, latency_ms_max=43.71,
                errors=[], n_errors=0, **{"pass": True}, connect_s=0.01)


class ParserTests(unittest.TestCase):
    def test_official_literal_and_counts(self):
        self.assertEqual(q.parse_metrics(repr(good()), 100), good())
        self.assertEqual(q.parse_metrics(repr(good(2)), 2), good(2))
        self.assertEqual(q.parse_metrics(repr(good(200)), 200), good(200))

    def test_corrupted_metrics_fail_closed(self):
        cases = [("calls", 99), ("ticks", 101), ("calls", True),
                 ("command_hz", 26.999), ("command_hz", True),
                 ("command_hz", float("inf")), ("min_hz", 26.9),
                 ("n_errors", 1), ("n_errors", False), ("errors", ["failure"]),
                 ("errors", ()), ("pass", 1), ("pass", False),
                 ("connect_s", -1), ("latency_ms_p50", None),
                 ("latency_ms_p50", 50), ("latency_ms_max", 10 ** 400)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                m = good()
                m[key] = value
                with self.assertRaises(q.Rejected):
                    q.parse_metrics(repr(m), 100)

    def test_output_ambiguity_and_code_rejected(self):
        literal = repr(good())
        cases = [literal + "\n" + literal, "log\n" + literal,
                 "__import__('os').getcwd()", "[]", "{'pass': True}",
                 literal[:-1] + ", 'pass': True}", "x" * (q.MAX_OUTPUT + 1)]
        extra = good()
        extra["startup_s"] = 0
        cases.append(repr(extra))
        for output in cases:
            with self.subTest(output=output[:80]), self.assertRaises(q.Rejected):
                q.parse_metrics(output, 100)


class GuardTests(unittest.TestCase):
    def test_endpoint_and_count_guards(self):
        for url in ("ws://127.0.0.1:8000", "ws://localhost:8000"):
            self.assertEqual(q.policy_url(url), url)
        for url in ("wss://localhost:8000", "ws://example.com:8000",
                    "ws://127.0.0.2:8000", "ws://localhost:8000/",
                    "ws://localhost:8000?token=secret", "ws://user@localhost:8000",
                    "ws://localhost", "ws://localhost:0", "ws://localhost:65536",
                    "ws://localhost:8000#x", "ws://localhost.evil:8000"):
            with self.subTest(url=url), self.assertRaises(argparse.ArgumentTypeError):
                q.policy_url(url)
        for n in ("1", "201", "100.0", "no"):
            with self.assertRaises(argparse.ArgumentTypeError):
                q.count(n)

    def test_changed_upstream_sha_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(q, "git", side_effect=[str(root).encode(), b"0" * 40]):
                with self.assertRaisesRegex(q.Rejected, "HEAD"):
                    q.verify_sources(root)

    def test_source_bytes_and_shadow_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            pkg = root / "aaltonomous"
            pkg.mkdir()
            src = pkg / "__init__.py"
            src.write_bytes(b"# pinned\n")
            tree = (f"100644 blob {q.blob_id(src.read_bytes())}\taaltonomous/__init__.py\0").encode()
            with patch.object(q, "git", return_value=tree):
                self.assertIn("aaltonomous/__init__.py", q.verify_tree(root, q.UPSTREAM, "aaltonomous"))
                src.write_bytes(b"# changed\n")
                with self.assertRaisesRegex(q.Rejected, "bytes"):
                    q.verify_tree(root, q.UPSTREAM, "aaltonomous")
                src.write_bytes(b"# pinned\n")
                (pkg / "shadow.py").write_text("# untracked")
                with self.assertRaisesRegex(q.Rejected, "untracked"):
                    q.verify_tree(root, q.UPSTREAM, "aaltonomous")

    def test_mixed_import_provenance_rejected_before_replay(self):
        import types
        names = ("aaltonomous", "aaltonomous.deploy", "aaltonomous.interface",
                 "aaltonomous.deploy.protocol", "aaltonomous.deploy.policy_server",
                 "aaltonomous.deploy.runner", "aaltonomous.interface.backends")
        modules = {name: types.ModuleType(name) for name in names}
        for name, module in modules.items():
            module.__file__ = "/different-checkout/" + name.replace(".", "/") + ".py"
            module.__path__ = []
            if "." in name:
                parent, child = name.rsplit(".", 1)
                setattr(modules[parent], child, module)
        with patch.dict(sys.modules, modules), patch.dict(q.os.environ, {"PYTHONPATH": "/pinned"}), \
                patch("runpy.run_module") as run:
            old_path = sys.path[:]
            try:
                with self.assertRaisesRegex(RuntimeError, "mixed official"):
                    exec(q.BOOTSTRAP, {})
                run.assert_not_called()
            finally:
                sys.path[:] = old_path

    def test_mock_missing_or_unverified_asset_never_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(q.mock_status(root), "blocked_missing_asset")
            asset = root / q.URDF
            asset.parent.mkdir(parents=True)
            asset.write_text("not a verified licensed URDF")
            self.assertEqual(q.mock_status(root), "blocked_unverified_asset")

    def test_cli_blocked_receipt_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "receipt.json"
            args = ["--upstream", tmp, "--python", sys.executable,
                    "--policy", "ws://127.0.0.1:8000", "--mock", "--output", str(output)]
            with patch.object(q, "verify_sources", return_value={}), \
                    patch.object(q, "run_bounded") as run, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(q.main(args), 2)
                original = output.read_bytes()
                self.assertEqual(json.loads(original)["status"], "blocked_missing_asset")
                self.assertEqual(q.main(args), 2)
                self.assertEqual(output.read_bytes(), original)
                run.assert_not_called()

    def test_cli_rejects_outbound_before_source_or_execution(self):
        with patch.object(q, "verify_sources") as sources, patch.object(q, "run_bounded") as run, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                q.main(["--upstream", "/unused", "--python", sys.executable,
                        "--policy", "ws://outside.example:8000", "--output", "/unused"])
            sources.assert_not_called()
            run.assert_not_called()

    def test_cli_replay_receipt_requires_exit_and_stable_provenance(self):
        for rc, sources, expected_status in (
                (0, [{"pin": q.UPSTREAM}] * 2, "pass_protocol_only"),
                (1, [{"pin": q.UPSTREAM}] * 2, "rejected"),
                (0, [{"pin": q.UPSTREAM}, {"pin": "changed"}], "rejected")):
            with self.subTest(rc=rc, sources=sources), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "receipt.json"
                with patch.object(q, "verify_sources", side_effect=sources), \
                        patch.object(q, "run_bounded", return_value=(rc, repr(good()))) as run, \
                        contextlib.redirect_stdout(io.StringIO()):
                    result = q.main(["--upstream", tmp, "--python", sys.executable,
                                     "--policy", "ws://localhost:8000", "--output", str(output)])
                receipt = json.loads(output.read_text())
                self.assertEqual(receipt["status"], expected_status)
                self.assertEqual(result, 0 if expected_status == "pass_protocol_only" else 2)
                self.assertFalse(receipt["server_identity_verified"])
                self.assertFalse(receipt["robot_or_simulator_qualified"])
                command = run.call_args.args[0]
                self.assertEqual(command[-4:], ["--synthetic", "100", "--policy", "ws://localhost:8000"])


if __name__ == "__main__":
    unittest.main()
