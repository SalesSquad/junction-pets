"""Regression checks for effective argv forwarding and child receipt binding."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from reliability_campaign import main
from test_reliability_experiment import model_artifact


class CampaignFreeze(unittest.TestCase):
    def exercise(self, *, tamper=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "fixture.json"
            model.write_text(json.dumps(model_artifact()))
            plan = root / "plan.json"
            plan.write_text(json.dumps({"partitions": {"development": ["fixture-development"],
                                                        "blind": ["fixture-blind"]}}))
            captured = []

            def source(path=None):
                return {"source_sha": "a" * 40, "files_sha256": {"policy.py": "b" * 64},
                        "model_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None}

            def child(command, **kwargs):
                captured.append((command, kwargs["env"]))
                value = lambda name: command[command.index(name) + 1]
                policy = value("--policy")
                manifest_path = Path(value("--freeze-manifest"))
                manifest = json.loads(manifest_path.read_text())
                config = dict(manifest["policies"][policy])
                config["freeze_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                if tamper:
                    config["late_threshold"] = 0.9
                receipt = {"world_id": "synthetic-" + policy, "state": "completed", "config": config,
                           "source": {"source_sha": manifest["source_sha"]}}
                (Path(value("--output")) / "run.json").write_text(json.dumps(receipt))
                return SimpleNamespace(returncode=0)

            argv = ["reliability_campaign.py", "--plan", str(plan), "--partition", "development",
                    "--policies", *( ["learned"] if tamper else ["baseline", "learned"] ),
                    "--output", str(root / "runs"), "--workers", "1"]
            with patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": str(model),
                                         "SPREAD_RELIABILITY_LATE_THRESHOLD": "0.02",
                                         "SPREAD_GUARD_POLICY": "risk_budget"}), \
                    patch("sys.argv", argv), patch("reliability_campaign.provenance", side_effect=source), \
                    patch("reliability_campaign.subprocess.run", side_effect=child):
                if tamper:
                    with self.assertRaisesRegex(ValueError, "child receipt"):
                        main()
                else:
                    main()
            return captured, str(model.resolve())

    def test_environment_model_and_threshold_become_explicit_child_arguments(self):
        captured, model = self.exercise()
        self.assertEqual(len(captured), 2)
        for command, environment in captured:
            policy = command[command.index("--policy") + 1]
            self.assertEqual(command[command.index("--late-threshold") + 1], "0.02")
            self.assertNotIn("SPREAD_RELIABILITY_MODEL", environment)
            self.assertNotIn("SPREAD_RELIABILITY_LATE_THRESHOLD", environment)
            if policy == "learned":
                self.assertEqual(command[command.index("--model") + 1], model)
            else:
                self.assertNotIn("--model", command)

    def test_changed_child_threshold_cannot_be_accepted_as_frozen_evidence(self):
        self.exercise(tamper=True)


if __name__ == "__main__":
    unittest.main()
