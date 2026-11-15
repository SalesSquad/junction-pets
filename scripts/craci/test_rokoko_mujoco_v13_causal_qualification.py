"""Focused source/physics/forensic adversarial tests; no paid hosted run."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


q = load(ROOT / "rokoko-mujoco-v13-causal-qualification.py", "v13_test_qualified")


class ForensicContract:
    """Source-checkout-independent stub, never used in actual hosted runner."""
    SOURCE_HEAD = q.V12_SOURCE_SHA
    HARNESS_HEAD = q.V12_HARNESS_SHA
    ARM_V5 = "frozen_v5"
    ARMS = (ARM_V5, "v12_phase_dwell_supported_actions",
            "v12_right_side_action4_exploration_train_only")
    RAW_SHAS = {"full_transitions.jsonl.gz":
                "7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91"}

    @staticmethod
    def public(obs, mask):
        if len(obs) != 18 or len(mask) != 7 or not all(bit in (0, 1) for bit in mask):
            raise ValueError("V13_ONLY_PUBLIC18_AND_ORIGINAL_SEVEN_MASK")


class OriginalPhysicsFixture:
    """Deterministic toy fixture to assert independent replay failure behavior.

    Never used by source entrypoint: actual hosted runner refuses a source
    without original V8/V7 MuJoCo 3.3.7 and SHA-bound V12 evidence.
    """
    def __init__(self, max_options=60):
        self.max_options = max_options
        self.reset(seed=518000, ood=False)

    def reset(self, seed, ood=False):
        self.seed = seed
        self.observation = [0.0] * 18
        self.observation[10] = 1.0
        self.observation[16] = .5
        self.steps = 0
        self.physics_steps = 0
        self.contacts = 0
        self.dwell = 0
        return list(self.observation)

    def mask(self, observation):
        return [1] * 7

    def step(self, action):
        self.steps += 1
        self.physics_steps += 1
        self.observation[0] += (action + 1) / 100
        info = {"cost": 0, "contacts": 0, "success": False,
                "unsafe": False, "error": .5 - self.observation[0]}
        return list(self.observation), 0.0, False, info


def fixture():
    forensic = ForensicContract
    env = OriginalPhysicsFixture()
    obs = env.reset(seed=518000, ood=False)
    nxt, _, _, _ = env.step(6)
    source_trace = [{"observation": obs, "mask": [1] * 7,
                     "action": 6, "reward": 0.0, "cost": 0, "done": False,
                     "contacts_cumulative": 0, "dwell_ticks_current": 0,
                     "dwell_ticks_cumulative": 0,
                     "success_info": False, "next_observation": nxt}]
    source = {"rows": {(518000, forensic.ARM_V5): {"world_hash": "toy-public-world"}},
              "traces": {(518000, forensic.ARM_V5): source_trace},
              "fullTransitionsSha256": forensic.RAW_SHAS["full_transitions.jsonl.gz"]}
    env.reset(seed=518000, ood=False)
    o = env.observation.copy()
    mask = env.mask(o)
    next_o, reward, done, info = env.step(1)
    trace = [{"observation": o, "mask": mask, "action": 1,
              "reward": reward, "cost": info["cost"], "done": done,
              "contacts_cumulative": env.contacts,
              "dwell_ticks_current": env.dwell,
              "dwell_ticks_cumulative": env.dwell,
              "success_info": info["success"], "next_observation": next_o}]
    branch = {"schema": "test.synthetic.branch",
              "seed": 518000, "branchId": "v13-seen-train-518000-00",
              "sourceWorldHash": "toy-public-world",
              "forkOptionIndexZeroBased": 0,
              "exactOriginalPrefixReplayed": True,
              "decisionPublic18D": o, "decisionOriginalMask7": mask,
              "actions": [1], "trace": trace, "traceSha256": q.digest(trace),
              "lastPublicObservation18D": next_o,
              "lastOriginalMask7": env.mask(next_o),
              "actualOptionSteps": 1, "actualPhysicsSteps": 1,
              "actualContacts": 0, "actualDwellTicks": 0,
              "actualGoalSuccess250Tick": False, "actualUnsafe": False,
              "sourceOnlyUnattestedExecution": True,
              "newRealMuJoCoExecuted": False,
              "trainingOnly": True, "modelPromotionAuthorized": False}
    return forensic, None, source, branch


class CausalQualificationContract(unittest.TestCase):
    def test_product_unique_import_and_exact_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = Path(tmp)
            (product_dir / "forensic.py").write_text(
                f'SOURCE_HEAD={q.V12_SOURCE_SHA!r}\n'
                f'HARNESS_HEAD={q.V12_HARNESS_SHA!r}\n')
            (product_dir / "causal.py").write_text(
                'import forensic\nMAX_DEPTH=3\nBEAM_WIDTH=2\n'
                'MAX_WORLD_BRANCHES=20\nMAX_TOTAL_BRANCHES=720\n'
                'MAX_RUNTIME_SECONDS=1200\n')
            forensic, causal = q.import_v13_product(product_dir)
            self.assertIs(causal.forensic, forensic)
            self.assertEqual(causal.MAX_TOTAL_BRANCHES, 720)

    def test_original_mask_public_and_true_physics_replay(self):
        f, _, source, b = fixture()
        q.validate_raw_branch(b, f, source)
        count, goal = q.independent_branch_replay(
            b, f, source, OriginalPhysicsFixture,
            lambda _: "toy-public-world", time.monotonic() + 10)
        self.assertEqual(count, 1)
        self.assertFalse(goal)

    def test_forged_raw_transition_sha_hard_stop(self):
        f, _, source, b = fixture()
        bad = copy.deepcopy(b)
        bad["trace"][0]["reward"] = 3
        with self.assertRaisesRegex(ValueError, "SHA_INVALID"):
            q.validate_raw_branch(bad, f, source)

    def test_illegal_action_seven_shield_hard_stop(self):
        f, _, source, b = fixture()
        bad = copy.deepcopy(b)
        bad["trace"][0]["mask"][1] = 0
        bad["traceSha256"] = q.digest(bad["trace"])
        with self.assertRaisesRegex(ValueError, "ILLEGAL_SEVEN_MASK"):
            q.validate_raw_branch(bad, f, source)

    def test_mask_legal_physics_rewards_still_independent(self):
        f, _, source, b = fixture()
        bad = copy.deepcopy(b)
        bad["trace"][0]["reward"] = 99
        bad["traceSha256"] = q.digest(bad["trace"])
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_ALL_REAL_OPTION_PHYSICS_DIVERGED"):
            q.independent_branch_replay(
                bad, f, source, OriginalPhysicsFixture,
                lambda _: "toy-public-world", time.monotonic() + 10)

    def test_unsupported_250tick_success_claim_hard_stop(self):
        f, _, source, b = fixture()
        bad = copy.deepcopy(b)
        bad["actualGoalSuccess250Tick"] = True
        with self.assertRaisesRegex(ValueError, "REPLAY_TERMINAL_250TICK"):
            q.independent_branch_replay(
                bad, f, source, OriginalPhysicsFixture,
                lambda _: "toy-public-world", time.monotonic() + 10)

    def test_forged_or_unseen_original_world_cannot_be_replayed(self):
        f, _, source, b = fixture()
        bad = copy.deepcopy(b)
        bad["seed"] = 600000
        with self.assertRaisesRegex(ValueError, "ORIGINAL_TRAIN_WORLD"):
            q.validate_raw_branch(bad, f, source)

    def test_false_original_world_hash_prohibits_branch(self):
        f, _, source, b = fixture()
        bad = copy.deepcopy(b)
        bad["sourceWorldHash"] = "forged-world"
        with self.assertRaisesRegex(ValueError, "ORIGINAL_TRAIN_WORLD"):
            q.validate_raw_branch(bad, f, source)

    def test_product_collision_prevents_wrong_forensic_import(self):
        import sys
        stale = object()
        previous = sys.modules.get("forensic")
        sys.modules["forensic"] = stale
        try:
            with tempfile.TemporaryDirectory() as tmp:
                product_dir = Path(tmp)
                (product_dir / "forensic.py").write_text(
                    f'SOURCE_HEAD={q.V12_SOURCE_SHA!r}\n'
                    f'HARNESS_HEAD={q.V12_HARNESS_SHA!r}\n')
                (product_dir / "causal.py").write_text(
                    'import forensic\nMAX_DEPTH=3\nBEAM_WIDTH=2\n'
                    'MAX_WORLD_BRANCHES=20\nMAX_TOTAL_BRANCHES=720\n'
                    'MAX_RUNTIME_SECONDS=1200\n')
                f, c = q.import_v13_product(product_dir)
                self.assertIs(c.forensic, f)
                self.assertIs(sys.modules["forensic"], stale)
        finally:
            if previous is None:
                del sys.modules["forensic"]
            else:
                sys.modules["forensic"] = previous

    def test_empty_source_index_absent_fails_closed(self):
        f, _, _, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "AUDITED_TRAJECTORY_INDEX_SHA"):
                q.verified_trajectory_index(Path(tmp) / "missing.json", f)

    def test_partial_branch_journal_persists_even_on_source_error(self):
        f, _, source, branch = fixture()
        class CrashesAfterOne:
            SCHEMA = "junction.rokoko.v13.finite-original-mujoco-causal-replay.v1"
            @staticmethod
            def run_budgeted_diagnostic(source, env_factory, signature, *,
                                        max_depth, beam_width, max_world_branches,
                                        deadline, on_branch, on_step):
                step = branch["trace"][0]
                on_step({"schema": CrashesAfterOne.SCHEMA + ".option-journal.v1",
                         "seed": branch["seed"], "branchId": branch["branchId"],
                         "sourceWorldHash": branch["sourceWorldHash"],
                         "forkOptionIndexZeroBased": 0,
                         "optionIndexZeroBased": 0, "phase": "COUNTERFACTUAL",
                         "transition": step, "transitionSha256": q.digest(step),
                         "sourceOnlyUnattestedExecution": True,
                         "physicsQualificationPending": True})
                on_branch(branch)
                raise RuntimeError("source died later")
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "source"
            result, recorded, error, step_count = q.run_diagnostic(
                Path(tmp), Path(tmp), f, CrashesAfterOne, source,
                OriginalPhysicsFixture, lambda _: "toy-public-world",
                private, "a"*40, "b"*40, time.monotonic() + 10)
            self.assertEqual(result, {})
            self.assertEqual(len(recorded), 1)
            self.assertEqual(step_count, 1)
            self.assertEqual(error, "V13_SOURCE_OR_PHYSICS_EXCEPTION_RuntimeError")
            self.assertTrue((private / "full_transitions.jsonl.gz").is_file())
            complete = q.preserve_diagnostic(
                private, "a"*40, "b"*40, source, result, recorded, error,
                option_events=step_count)
            self.assertFalse(complete)
            self.assertEqual((private / "early_stop.json").is_file(), True)

    def test_false_science_complete_world_matrix_rejected(self):
        f, _, source, b = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp)
            with self.assertRaisesRegex(ValueError, "ALL36_SEEN_FAILURES"):
                q.independent_qualification(
                    private, source, f, OriginalPhysicsFixture,
                    lambda _: "toy-public-world", [b],
                    {"allWorldsComplete": True, "worldResults": []},
                    time.monotonic() + 10)


if __name__ == "__main__":
    unittest.main()
