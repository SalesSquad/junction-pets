"""Small adversarial checks for the producer's receipt boundary (synthetic only)."""
import json
from pathlib import Path
import tempfile
import unittest

from attach_differential import attach, FROZEN_FILES, FIXTURE_FILES, CASE
from build_packets import BASE, CASES, digest


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


class ReceiptIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt_path = self.root / "receipt.json"
        self.packet_path = self.root / "packet.json"
        files = {name: f"synthetic input: {name}\n".encode() for name in FROZEN_FILES}
        manifest = {name: digest(data) for name, data in files.items()}
        harness_hash = canonical(manifest)
        self.receipt = {
            "schemaVersion": 1, "caseId": CASE, "createdAt": "2026-11-15T00:00:00Z",
            "repository": {"baseSha": BASE, "headSha": CASES["2283"]["sha"]},
            "harness": {"files": manifest, "sha256": harness_hash,
                        "inputSha256": canonical({k: manifest[k] for k in FIXTURE_FILES})},
            "revisions": [],
        }
        for role, passed, sha in (("base", False, BASE), ("head", True, CASES["2283"]["sha"])):
            for name, data in files.items():
                path = self.root / role / "harness" / name
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            status = "pass" if passed else "fail"
            counts = {"passed": int(passed), "failed": int(not passed), "skipped": 0}
            resolver = {"expectedHintName": "App.AppResolver.g.cs", "present": passed}
            observed = {"caseId": CASE, "status": status, "tests": counts, "generatedResolver": resolver,
                        "checks": {"libraryCompiled": True, "analyzerDidNotCrash": passed,
                                   "generatorDidNotCrash": passed, "noBlockingDiagnostics": passed,
                                   "generatedCodeCompiles": True, "consumerResolverGenerated": passed},
                        "diagnostics": []}
            observation_path = self.root / role / "observation.json"
            observation_path.write_text(json.dumps(observed))
            log_path = self.root / role / "build.log"; log_path.write_text("SYNTHETIC fixture build\n")
            self.receipt["revisions"].append({
                "role": role, "sourceSha": sha, "status": status, "exitCode": 0 if passed else 1,
                "harnessSha256": harness_hash, "executionOverlaySha256": manifest["global.json"],
                "build": {"exitCode": 0, "error": None}, "execution": {"error": None},
                "tests": counts, "generatedResolver": resolver,
                "observation": {"path": f"{role}/observation.json", "sha256": digest(observation_path.read_bytes())},
                "logs": [{"path": f"{role}/build.log", "sha256": digest(log_path.read_bytes())}],
            })
        self.packet = {"source": {"baseSha": BASE, "headSha": CASES["2283"]["sha"]}, "checks": [], "claims": []}

    def execute(self):
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.packet_path.write_text(json.dumps(self.packet))
        return attach(self.receipt_path, self.packet_path)

    def mutate_observation(self, change):
        run = self.receipt["revisions"][1]
        path = self.root / run["observation"]["path"]
        value = json.loads(path.read_text()); change(value); path.write_text(json.dumps(value))
        run["observation"]["sha256"] = digest(path.read_bytes())

    def test_complete_consistent_synthetic_fixture_is_structurally_accepted(self):
        result = self.execute()
        self.assertEqual((result["base"], result["head"]), ("fail", "pass"))

    def test_empty_manifest_cannot_claim_a_frozen_experiment(self):
        self.receipt["harness"]["files"] = {}
        self.receipt["harness"]["sha256"] = canonical({})
        for run in self.receipt["revisions"]: run["harnessSha256"] = canonical({})
        with self.assertRaisesRegex(ValueError, "all six"): self.execute()

    def test_partial_manifest_cannot_omit_a_probe(self):
        self.receipt["harness"]["files"].pop("Program.cs")
        with self.assertRaisesRegex(ValueError, "all six"): self.execute()

    def test_changed_input_digest_is_rejected(self):
        self.receipt["harness"]["inputSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input digest"): self.execute()

    def test_changed_execution_overlay_is_rejected(self):
        self.receipt["revisions"][1]["executionOverlaySha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "overlay"): self.execute()

    def test_contradictory_raw_status_is_rejected_even_with_updated_hash(self):
        self.mutate_observation(lambda value: value.update(status="inconclusive"))
        with self.assertRaisesRegex(ValueError, "contradict"): self.execute()

    def test_zero_actual_tests_cannot_be_promoted(self):
        self.mutate_observation(lambda value: value.update(tests={"passed": 0, "failed": 0, "skipped": 0}))
        with self.assertRaisesRegex(ValueError, "contradict"): self.execute()

    def test_missing_resolver_cannot_be_promoted(self):
        self.mutate_observation(lambda value: value["generatedResolver"].update(present=False))
        with self.assertRaisesRegex(ValueError, "Resolver"): self.execute()

    def test_execution_error_cannot_be_promoted(self):
        self.receipt["revisions"][1]["execution"]["error"] = "timeout"
        with self.assertRaisesRegex(ValueError, "execution error"): self.execute()

    def test_tampered_evidence_cannot_keep_its_old_digest(self):
        (self.root / "head/observation.json").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"): self.execute()


if __name__ == "__main__":
    unittest.main()
