import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("audit_scan", Path(__file__).with_name("scan.py"))
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)


def hashes(root):
    return {str(p.relative_to(root)): scan.sha256(p.read_bytes()) for p in root.rglob("*") if p.is_file()}


class ScannerGuards(unittest.TestCase):
    def test_expired_deadline_refuses_without_writing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "not-created"
            args = argparse.Namespace(source="/nonexistent", repository="SalesSquad/example", source_sha="a" * 40,
                                      output=str(out), deadline="2020-01-01T00:00:00Z", rules="/nonexistent")
            with self.assertRaisesRegex(ValueError, "deadline"):
                scan.scan(args)
            self.assertFalse(out.exists())

    def test_environment_contains_no_inherited_hooks_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/trusted/python/lib", "LD_PRELOAD": "/untrusted/hook", "GH_TOKEN": "fixture-secret",
                                              "SSL_CERT_FILE": "/trusted/provider.pem", "REQUESTS_CA_BUNDLE": "/trusted/requests.pem"}):
                env = scan.isolated_environment(Path(directory), [Path(sys.executable).parent])
            self.assertFalse({"GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY", "PYTHONPATH", "NODE_OPTIONS", "LD_PRELOAD"} & set(env))
            self.assertEqual(env["SEMGREP_SEND_METRICS"], "off")
            self.assertEqual(env["LD_LIBRARY_PATH"], "/trusted/python/lib")
            self.assertEqual(env["SSL_CERT_FILE"], "/trusted/provider.pem")
            self.assertEqual(env["REQUESTS_CA_BUNDLE"], "/trusted/requests.pem")

    def test_real_tools_find_bugs_without_loading_project_config_or_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            marker = root / "PROJECT_CONFIG_EXECUTED"
            secret = "sk-fixtureSensitiveValue0123456789"
            (source / "bug.py").write_text(f"def broken():\n    return missing_name\n\neval('{secret}')\n")
            (source / "bug.ts").write_text("export function broken(): boolean { return true; console.log('unreachable'); }\n")
            (source / "eslint.config.mjs").write_text(f"import fs from 'node:fs'; fs.writeFileSync({json.dumps(str(marker))}, 'executed'); throw new Error('project configuration loaded');\n")
            (source / "ruff.toml").write_text('[lint]\nignore = ["F821"]\n')
            (source / ".semgrepignore").write_text("*\n")
            before = hashes(source)
            rules = root / "rules.yml"
            rules.write_text('rules:\n  - id: fixed-python-eval\n    languages: [python]\n    severity: WARNING\n    message: "Review evaluation of $X"\n    pattern: eval($X)\n')
            out = root / "out"
            result = subprocess.run([sys.executable, str(Path(scan.__file__)), "--source", str(source),
                                     "--repository", "SalesSquad/fixture", "--source-sha", "a" * 40,
                                     "--output", str(out), "--deadline", "2026-11-15T17:00:00Z", "--rules", str(rules)],
                                    text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out / "result.json").read_text())
            self.assertEqual({name: item["status"] for name, item in report["analyzers"].items()},
                             {"semgrep": "success", "ruff": "success", "eslint": "success"})
            rules_found = {(item["tool"], item["rule_id"]) for item in report["findings"]}
            self.assertIn(("ruff", "F821"), rules_found)
            self.assertIn(("eslint", "no-unreachable"), rules_found)
            self.assertIn(("semgrep", "fixed-python-eval"), rules_found)
            self.assertEqual(hashes(source), before)
            self.assertFalse(marker.exists())
            self.assertNotIn(secret, (out / "result.json").read_text() + (out / "summary.md").read_text() + result.stdout + result.stderr)
            self.assertFalse(report["clean_claim"])


if __name__ == "__main__":
    unittest.main()
