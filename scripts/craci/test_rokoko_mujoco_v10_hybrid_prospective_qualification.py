"""Portable fail-closed contract tests; never pretend to run actual MuJoCo."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qual = load("rokoko-mujoco-v10-hybrid-prospective-qualification.py", "hybrid_craci_synthetic_contract")
packer = load("rokoko-mujoco-v10-hybrid-retain-evidence.py", "hybrid_bounded_packer_contract")


def generated():
    rows = []
    for offset in range(160):
        seed = qual.FIRST + offset
        near = offset < 128
        for strategy in qual.STRATEGIES:
            base = strategy in ("frozen_v5", "rescue_off_v5")
            success = (offset in (0, 2) and base) or (offset in (1, 2) and strategy ==
                      "near-early-side-mask-rescue")
            unsafe = offset == 3 and strategy == "near-early-side-mask-rescue"
            digest = hashlib.sha256(f"{seed}:v5".encode() if base else
                                     f"{seed}:{strategy}".encode()).hexdigest()
            rows.append({"seed": seed, "strategy": strategy,
                         "observed_corridor": near,
                         "world_hash": hashlib.sha256(str(seed).encode()).hexdigest(),
                         "full_transition_sha256": digest,
                         "success": success, "unsafe": unsafe,
                         "abstained": False, "dwell_ticks_final": 250 if success else 0,
                         "physics_steps": 12, "forward_reopened_after_side": 0,
                         "full_transition_count": 3})
    near = list(range(qual.FIRST, qual.FIRST + 128))
    clear = list(range(qual.FIRST + 128, qual.FIRST + 160))
    training = {"schema": qual.SCHEMA + ".training",
                "strategies": list(qual.STRATEGIES), "train_first_seed": qual.FIRST,
                "selection_seed_limit": 512, "selected_near_count": 128,
                "selected_clear_count": 32, "actual_trials": 640,
                "dev_cal_test_ood_opened": False, "no_dev_evaluation": True,
                "model_promotion_authorized": False, "trials": rows,
                "near_seeds": near, "clear_seeds": clear}
    stats = {}
    for name in qual.STRATEGIES:
        arm = [r for r in rows if r["strategy"] == name]
        stats[name] = {"real_trials": 160,
                       "safe_near_goals": sum(r["success"] and r["observed_corridor"] for r in arm),
                       "safe_clear_goals": 0,
                       "unsafe": sum(r["unsafe"] for r in arm),
                       "abstained": 0,
                       "timeouts": sum(not (r["success"] or r["unsafe"]) for r in arm),
                       "forward_reopened_after_side": 0,
                       "real_option_steps": 480}
    readout = {"schema": qual.SCHEMA + ".readout",
               "strict_original_v5_placebo_raw_trace_identical": True,
               "cohort": {"near": near, "clear": clear},
               "dev_cal_test_ood_opened": False, "promotion_authorized": False,
               "strategies": stats,
               "novel_hybrid_safe_goal_seeds_vs_v5": [qual.FIRST + 1],
               "lost_v5_safe_goal_seeds_under_hybrid": [qual.FIRST],
               "shared_v5_hybrid_safe_goal_seeds": [qual.FIRST + 2],
               "hybrid_new_unsafe_seeds_vs_v5": [qual.FIRST + 3]}
    return training, readout


class PairedTrainScience(unittest.TestCase):
    def setUp(self):
        self.training, self.readout = generated()

    def test_full_paired_four_arm_negative_science_not_promoted(self):
        science = qual.independent_paired_science(self.training, self.readout)
        self.assertEqual(science["verdict"], "NO_GO_ANY_CANDIDATE_UNSAFE")
        self.assertEqual((science["novel_goals"], science["lost_frozen_v5_goals"],
                          science["new_unsafe"]), (1, 1, 1))

    def test_omitted_failed_world_is_rejected(self):
        self.training["trials"] = self.training["trials"][:-4]
        with self.assertRaisesRegex(AssertionError, "INCOMPLETE"):
            qual.independent_paired_science(self.training, self.readout)

    def test_unpaired_placebo_is_rejected(self):
        row = next(x for x in self.training["trials"] if x["seed"] == qual.FIRST and
                   x["strategy"] == "rescue_off_v5")
        row["full_transition_sha256"] = "f" * 64
        with self.assertRaisesRegex(AssertionError, "PLACEBO"):
            qual.independent_paired_science(self.training, self.readout)

    def test_forged_goal_disappearance_is_rejected(self):
        self.readout["lost_v5_safe_goal_seeds_under_hybrid"] = []
        with self.assertRaisesRegex(AssertionError, "CHERRY_PICKED"):
            qual.independent_paired_science(self.training, self.readout)

    def test_forged_safety_is_rejected(self):
        self.readout["hybrid_new_unsafe_seeds_vs_v5"] = []
        with self.assertRaisesRegex(AssertionError, "CHERRY_PICKED"):
            qual.independent_paired_science(self.training, self.readout)

    def test_cherry_picked_seed_partition_is_rejected(self):
        self.training["near_seeds"] = self.training["near_seeds"][:-1]
        with self.assertRaisesRegex(AssertionError, "CHERRY_PICKED"):
            qual.independent_paired_science(self.training, self.readout)

    def test_producer_statistics_cannot_hide_timeout(self):
        self.readout["strategies"]["near-early-side-mask-rescue"]["timeouts"] -= 1
        with self.assertRaisesRegex(AssertionError, "STATISTICS"):
            qual.independent_paired_science(self.training, self.readout)

    def test_heldout_or_promotion_flag_fails_closed(self):
        self.training["dev_cal_test_ood_opened"] = True
        with self.assertRaisesRegex(AssertionError, "UNREVIEWED"):
            qual.independent_paired_science(self.training, self.readout)

    def test_unexpected_strategy_fails_closed(self):
        self.training["strategies"][0] = "new_oracle"
        with self.assertRaisesRegex(AssertionError, "UNREVIEWED"):
            qual.independent_paired_science(self.training, self.readout)


class ArchivePreflight(unittest.TestCase):
    def test_exact_three_original_files_and_independent_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {}
            for name in packer.FILES:
                raw = ("original-" + name).encode()
                (root / name).write_bytes(raw)
                files[name] = hashlib.sha256(raw).hexdigest()
            manifest = {"file_sha256": files, "executed_head": qual.PRODUCT_HEAD,
                        "harness_expected_head": "a" * 40}
            (root / "manifest.json").write_text(json.dumps(manifest))
            plan = {"schema": packer.SCHEMA, "archive_created_by_this_runner": False,
                    "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
                    "part_files_for_independent_external_packager": [
                        {"name": name, "sha256": files[name], "bytes": (root / name).stat().st_size}
                        for name in packer.FILES]}
            (root / "evidence-parts-plan.json").write_text(json.dumps(plan))
            check = {"schema": packer.QUALIFICATION_SCHEMA, "experiment_complete": True,
                     "source_head": qual.PRODUCT_HEAD, "harness_head": "a" * 40,
                     "real_original_mujoco_episodes": 640,
                     "all_original_full_traces_and_masks_verified": True,
                     "independent_true_physics_positive_replay": True,
                     "promotion_authorized": False, "dev_cal_test_ood_opened": False}
            (root / "independent-qualification.json").write_text(json.dumps(check))
            (root / "independent-positive-replay.json").write_text(
                json.dumps({"claim_verified": True}))

            class Hasher:
                @staticmethod
                def sha_file(path):
                    return hashlib.sha256(path.read_bytes()).hexdigest()

            self.assertEqual(packer.prereview_artifacts(root, Hasher()), manifest)
            (root / "paired-readout.json").write_text("MUTATED")
            with self.assertRaisesRegex(AssertionError, "UNBOUND_ORIGINAL_PARTS_PLAN"):
                packer.prereview_artifacts(root, Hasher())


if __name__ == "__main__":
    unittest.main()
