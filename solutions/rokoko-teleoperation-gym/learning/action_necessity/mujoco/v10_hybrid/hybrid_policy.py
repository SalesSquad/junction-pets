#!/usr/bin/env python3
"""Frozen, conservative V5-first/V8-early-rescue compositional motor policy.

This is a pre-registered *candidate*, not an independently measured physical
improvement. A source-verified V5 policy remains in charge until the public
mask shows forward obstruction with lateral action still available; the
original seven-option shield remains authoritative.
Only an 18D public observation, seven legal-mask bits and local action history
can influence a deployed decision. No simulator/world/seed/reward API is used.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
from typing import Callable

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
V8 = ROOT / "v8_learning"
V8_RUNNER_SHA256 = "73b31bf1a84ad9611552080e80fc26c009f45b0c78b73f01fb58d37b2ded9ee5"
V8_TRAINER_SHA256 = "6cacbdce011e3029289d32c24b0f0a3785a3872971c0d70f078ccbfa382b0d27"
V8_WEIGHTS_FILE_SHA256 = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
V8_RECEIPT_FILE_SHA256 = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"
V8_CANONICAL_MODEL_SHA256 = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
OBS = 18
ACTIONS = 7
ABSTAIN = 6
GOAL_APPROACH_RADIUS = .035
RESCUE_OPTIONS_PER_ROUND = 12
MAX_RESCUE_ROUNDS = 2
# 0.122 is an already preregistered public-observation corridor threshold,
# not a label or post-outcome classifier at inference.
NEAR_OBSERVED_OBSTACLE_THRESHOLD = .122
MODES = ("early-side-mask-rescue", "near-early-side-mask-rescue")


class HybridContractError(ValueError):
    """Source, public ABI or shield violation; fail the trial rather than fake success."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def original_public_inputs(observation, mask):
    try:
        obs = np.asarray(observation, dtype=np.float64)
        raw = np.asarray(mask)
    except (TypeError, ValueError) as exc:
        raise HybridContractError("HYBRID_PUBLIC_INPUTS_INVALID") from exc
    if (obs.shape != (OBS,) or not np.all(np.isfinite(obs)) or
            raw.shape != (ACTIONS,) or raw.dtype.kind not in ("b", "i", "u") or
            not np.all(np.isin(raw, (0, 1))) or not np.any(raw)):
        raise HybridContractError("HYBRID_PUBLIC_18D_SEVEN_MASK_REQUIRED")
    return obs, raw.astype(bool)


def checked_action(action, legal):
    # A silently repaired illegal original policy is not a valid qualification.
    if type(action) is not int or not 0 <= action < ACTIONS or not bool(legal[action]):
        raise HybridContractError("HYBRID_ORIGINAL_SEVEN_OPTION_SHIELD_VIOLATED")
    return action


def goal_distance(observation):
    # Goal coordinates are ALREADY in public observation slots 16–17.
    return math.hypot(float(observation[16] - observation[0]),
                      float(observation[17] - observation[1]))


class ConservativeHybrid:
    """Per-episode V5-first controller, two bounded reversible rescue modes.

    On the observed 513000 TRAIN control traces, the early lateral gate is
    absent from all 29 V5 goal-finishing trajectories. This is in-sample
    evidence only: perturbing a path can change a future mask and outcome.
    The V5 controller is reset after each V8 rescue because its unexecuted
    internal options must not be carried forward. No post-outcome state enters
    selection.
    """

    def __init__(self, baseline_factory: Callable, rescue_factory: Callable,
                 mode: str = "near-early-side-mask-rescue"):
        if mode not in MODES or not callable(baseline_factory) or not callable(rescue_factory):
            raise HybridContractError("HYBRID_FROZEN_MODE_AND_FACTORIES_REQUIRED")
        self.baseline_factory = baseline_factory
        self.rescue_factory = rescue_factory
        self.mode = mode
        self.baseline = baseline_factory()
        if not callable(self.baseline):
            raise HybridContractError("HYBRID_FROZEN_V5_FACTORY_INVALID")
        self.rescue = None
        self.rescue_active = False
        self.rescue_rounds = 0
        self.rescue_options = 0
        self.total_options = 0
        self.rescue_sides = 0

    def _checked_call(self, controller, observation, legal):
        return checked_action(controller(observation.copy(), legal.copy()), legal)

    def _start_rescue(self):
        self.rescue_rounds += 1
        self.rescue_options = 0
        self.rescue = self.rescue_factory()
        if not callable(self.rescue):
            raise HybridContractError("HYBRID_FROZEN_V8_FACTORY_INVALID")
        self.rescue_active = True

    def _finish_rescue(self):
        self.rescue_active = False
        self.rescue = None
        self.rescue_options = 0
        # Don't let V5's internal memory include an action we never executed.
        self.baseline = self.baseline_factory()
        if not callable(self.baseline):
            raise HybridContractError("HYBRID_V5_REENTRY_FACTORY_INVALID")

    def _rescue_action(self, observation, legal):
        action = self._checked_call(self.rescue, observation, legal)
        self.rescue_options += 1
        self.rescue_sides += int(action in (3, 4))
        return action

    def _eligible_preemptive_rescue(self, observation, legal):
        # At late V5 abstention masks are normally [0,0,0,0,0,0,1];
        # switching at that point cannot produce lateral escape. Instead the
        # earliest meaningful opportunity is forward blocked, side still legal.
        if ((legal[1] or legal[2]) or not (legal[3] or legal[4]) or
                goal_distance(observation) <= GOAL_APPROACH_RADIUS):
            return False
        return (self.mode == "early-side-mask-rescue" or
                abs(float(observation[7])) < NEAR_OBSERVED_OBSTACLE_THRESHOLD)

    def __call__(self, observation, mask):
        obs, legal = original_public_inputs(observation, mask)
        self.total_options += 1
        forward_open = bool(legal[1] or legal[2])
        if self.rescue_active:
            # Only a public *current mask* can signal the exit; no success,
            # contact count, hidden obstacle or reward is ever consulted.
            if ((self.rescue_options and forward_open) or
                    self.rescue_options >= RESCUE_OPTIONS_PER_ROUND):
                self._finish_rescue()
            else:
                return self._rescue_action(obs, legal)

        if (self.rescue_rounds < MAX_RESCUE_ROUNDS and
                self._eligible_preemptive_rescue(obs, legal)):
            self._start_rescue()
            return self._rescue_action(obs, legal)
        return self._checked_call(self.baseline, obs, legal)


def frozen_factories(weights_path: Path, receipt_path: Path):
    """Bind exact original V8 source/checkpoint; return per-episode factories.

    The V8 runner itself independently binds immutable V5/V7 physics and the
    4-stage weights. No optional injected policy factory is accepted here.
    """
    runner = V8 / "rollout_train.py"
    trainer = V8 / "run.py"
    weights_path = Path(weights_path).resolve(strict=True)
    receipt_path = Path(receipt_path).resolve(strict=True)
    expected = ((runner, V8_RUNNER_SHA256), (trainer, V8_TRAINER_SHA256),
                (weights_path, V8_WEIGHTS_FILE_SHA256),
                (receipt_path, V8_RECEIPT_FILE_SHA256))
    for path, sha in expected:
        if not path.is_file() or path.is_symlink() or sha256_file(path) != sha:
            raise HybridContractError("HYBRID_UNREVIEWED_V8_SOURCE_OR_CHECKPOINT")
    spec = importlib.util.spec_from_file_location("v10_hybrid_original_v8", runner)
    if spec is None or spec.loader is None:
        raise HybridContractError("HYBRID_V8_RUNNER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Explicitly reverify model and receipt against historically fitted HEAD.
    weights, _, canonical_sha = module.verify_frozen_model(
        weights_path, receipt_path, V8_CANONICAL_MODEL_SHA256)
    if canonical_sha != V8_CANONICAL_MODEL_SHA256:
        raise HybridContractError("HYBRID_FROZEN_V8_MODEL_MISMATCH")
    return (module.policy_factory("frozen_v5", weights),
            module.policy_factory("v8_hierarchical", weights))


def policy_factory(mode: str, weights_path: Path, receipt_path: Path):
    """Frozen source-bound callable factory matching original MuJoCo replay ABI."""
    if mode not in MODES:
        raise HybridContractError("HYBRID_UNKNOWN_PRE_FROZEN_MODE")
    v5, v8 = frozen_factories(weights_path, receipt_path)
    return lambda: ConservativeHybrid(v5, v8, mode)
