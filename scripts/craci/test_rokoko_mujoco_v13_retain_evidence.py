"""V13 bounded private retention: lossless, partial and tamper STOP tests."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from scripts.craci.test_rokoko_mujoco_v13_causal_qualification import fixture, q


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packer = load(Path(__file__).resolve().parent /
              "rokoko-mujoco-v13-retain-evidence.py", "v13_retain_contract")


def make_partial(private):
    f, _, source, branch = fixture()
    private.mkdir()
    raw = {"seed": branch["seed"], "branch_id": 0,
           "source_prefix": branch["forkOptionIndexZeroBased"],
           "actions": branch["actions"], "transitions": branch["trace"]}
    with gzip.open(private / "full_transitions.jsonl.gz", "wt",
                   encoding="utf8") as stream:
        stream.write(q.canonical(raw).decode() + "\n")
    event = {"schema":
             "junction.rokoko.v13.finite-original-mujoco-causal-replay.v1.option-journal.v1",
             "seed": branch["seed"], "branchId": branch["branchId"],
             "sourceWorldHash": branch["sourceWorldHash"],
             "forkOptionIndexZeroBased": branch["forkOptionIndexZeroBased"],
             "optionIndexZeroBased": 0, "phase": "COUNTERFACTUAL",
             "transition": branch["trace"][0],
             "transitionSha256": q.digest(branch["trace"][0]),
             "sourceOnlyUnattestedExecution": True,
             "physicsQualificationPending": True}
    with gzip.open(private / "option_journal.jsonl.gz", "wt",
                   encoding="utf8") as stream:
        stream.write(q.canonical(event).decode() + "\n")
    q.preserve_diagnostic(private, "a" * 40, "b" * 40, source,
                          {"allWorldsComplete": False,
                           "status": "INCOMPLETE",
                           "hardStopReason": "V13_FINITE_DEADLINE",
                           "rawBranches": [branch], "worldResults": []},
                          [branch], exception_code=None)


class RetentionContract(unittest.TestCase):
    def test_exact_partial_branch_preserved_under_original_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            collector = Path(tmp) / "collector"
            make_partial(private)
            packet = packer.publish(private, collector, complete=False)
            self.assertEqual(packet["exact_source_sha"], "a" * 40)
            self.assertEqual(set(packet["original_sha256"]),
                             set(packer.PARTIAL_SOURCES))
            self.assertLess(packet["collector_bytes"], 63 * 1024 * 1024)

    def test_partial_does_not_carry_complete_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            make_partial(private)
            with self.assertRaisesRegex(ValueError, "EXACT_ORIGINALS"):
                packer.publish(private, Path(tmp) / "collector", complete=True)

    def test_original_partial_raw_sha_tamper_hard_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            make_partial(private)
            with (private / "full_transitions.jsonl.gz").open("ab") as output:
                output.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "INCOMPLETE_EVIDENCE"):
                packer.publish(private, Path(tmp) / "collector", complete=False)

    def test_midbranch_only_executed_option_is_retained_without_forged_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            make_partial(private)
            # Simulate fatal stop immediately after one completed env.step,
            # BEFORE on_branch. No complete full branch must be fabricated.
            with gzip.open(private / "full_transitions.jsonl.gz", "wt",
                           encoding="utf8") as out:
                pass
            summary_file = private / "partial_training.json"
            summary = json.loads(summary_file.read_text())
            summary["recorded_branches"] = 0
            summary["recorded_real_options"] = 0
            summary["durably_journaled_all_executed_option_events"] = 1
            summary_file.write_bytes(q.canonical(summary) + b"\n")
            stop_file = private / "early_stop.json"
            stop = json.loads(stop_file.read_text())
            stop["recorded_branches"] = 0
            stop["recorded_real_options"] = 0
            stop["durably_journaled_all_executed_option_events"] = 1
            stop["raw_sha256"]["partial_training.json"] = packer.sha(summary_file)
            stop["raw_sha256"]["full_transitions.jsonl.gz"] = packer.sha(
                private / "full_transitions.jsonl.gz")
            stop_file.write_bytes(q.canonical(stop) + b"\n")
            result = packer.publish(private, Path(tmp) / "collector", complete=False)
            self.assertEqual(set(result["original_sha256"]),
                             set(packer.PARTIAL_SOURCES))

    def test_lossless_six_megabyte_split_and_sha_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            collector = Path(tmp) / "collector"
            make_partial(private)
            path = private / "partial_training.json"
            body = json.loads(path.read_text())
            body["synthetic_padding_to_prove_split_only"] = "x" * (6 * 1024 * 1024)
            path.write_bytes(q.canonical(body) + b"\n")
            stop_path = private / "early_stop.json"
            stop = json.loads(stop_path.read_text())
            stop["raw_sha256"]["partial_training.json"] = packer.sha(path)
            stop_path.write_bytes(q.canonical(stop) + b"\n")
            packet = packer.publish(private, collector, complete=False)
            retention = json.loads((collector / "retention-manifest.json").read_text())
            split = next(s for s in retention["sources"]
                         if s["name"] == "partial_training.json")
            self.assertGreaterEqual(len(split["parts"]), 2)
            self.assertEqual(packet["original_sha256"]["partial_training.json"],
                             packer.sha(path))
            # Even with extreme ZIP compression the raw six MiB chunk cap is
            # independently enforced, and reconstructed checksum matches.
            self.assertLess(packet["collector_bytes"], 63 * 1024 * 1024)

    def test_missing_collector_part_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            collector = Path(tmp) / "collector"
            make_partial(private)
            packer.publish(private, collector, complete=False)
            manifest = json.loads((collector / "retention-manifest.json").read_text())
            first = manifest["sources"][0]["parts"][0]["archive"]
            (collector / first).unlink()  # test-created synthetic archive only
            with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_MISSING_PART"):
                packer.verify_reassembled(collector, manifest)


if __name__ == "__main__":
    unittest.main()
