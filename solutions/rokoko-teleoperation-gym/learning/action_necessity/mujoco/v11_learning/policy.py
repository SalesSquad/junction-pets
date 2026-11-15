"""V11: frozen V5 as goal-first policy, one bounded V10 rescue opportunity.

The gate was fitted exclusively from original public 18D observations, seven
legal-mask bits and actions on the source-bound V10 TRAIN data.  Inference
cannot see seed, reward, simulator/world internals or success.  A rescue is a
prospective *hypothesis*; there has been no new V11 physics qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable

from learn_gate import candidate_input, public_distance


GATE_SHA256 = "b115fc329b50f2557e8c6074734990dbcf6d1c5046516fbbda6158c5c513eaa8"
MODEL_SCHEMA = "junction.rokoko.v11.goal-preserving-abstain-gate.v1"
V10_SOURCE_SHA = "9cc583d3f0f24484b79c1929ba875c7a3b667806"
MAX_RESCUE_OPTIONS = 8
MAX_RESCUE_ROUNDS = 1
FORWARD_OPTIONS = (1, 2)


class ProspectiveV11ContractError(ValueError):
    """Incorrect model evidence, public ABI or legal-mask action: STOP."""


def validate_public_inputs(observation, mask):
    try:
        normalized_obs = [value.item() if hasattr(value, "item") else value
                          for value in observation]
        normalized_mask = [bit.item() if hasattr(bit, "item") else bit
                           for bit in mask]
    except (TypeError, ValueError) as exc:
        raise ProspectiveV11ContractError("V11_PUBLIC_INPUT_NOT_ITERABLE") from exc
    if (len(normalized_obs) != 18 or len(normalized_mask) != 7 or
            any(type(value) not in (float, int) or not math.isfinite(value)
                for value in normalized_obs) or
            any(type(bit) not in (bool, int) or bit not in (0, 1)
                for bit in normalized_mask) or not any(normalized_mask)):
        raise ProspectiveV11ContractError("V11_PUBLIC_18D_SEVEN_ACTION_MASK_REQUIRED")
    return tuple(float(x) for x in normalized_obs), tuple(int(bit) for bit in normalized_mask)


def checked_action(action, mask):
    if type(action) is not int or action < 0 or action >= 7 or mask[action] != 1:
        raise ProspectiveV11ContractError("V11_ORIGINAL_SHIELD_VIOLATION")
    return action


def load_frozen_gate(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise ProspectiveV11ContractError("V11_FROZEN_GATE_FILE_UNSAFE")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != GATE_SHA256:
        raise ProspectiveV11ContractError("V11_FROZEN_GATE_SHA_CHANGED")
    model = json.loads(data)
    if (model.get("schema") != MODEL_SCHEMA or
            model.get("source", {}).get("sourceSha") != V10_SOURCE_SHA or
            model.get("training", {}).get("frozenV5Wins") != 37 or
            model.get("training", {}).get("v10NovelVsV5") != 0 or
            model.get("training", {}).get("v10LostV5Goals") != 11 or
            model.get("training", {}).get("firedOnV5SuccessFit") != 0 or
            model.get("training", {}).get("firedOnV5SuccessHeld") != 0 or
            model.get("futurePhysicsVerified") is not False or
            model.get("modelPromotionAuthorized") is not False or
            model.get("safety", {}).get("maxRescueRounds") != 1 or
            model.get("safety", {}).get("maxRescueOptionsPerRound") != 8 or
            model.get("training", {}).get("sourceObservedMotorBudgetFitHeld", {}).get("cap") != 8):
        raise ProspectiveV11ContractError("V11_UNQUALIFIED_FROZEN_GATE")
    return model["gate"]


class FrozenV11GoalPreservingRescue:
    """One-way, single-round arbitration: V5→bounded V10→fresh V5.

    V5's option decision is observed each baseline turn; in the rescue mode,
    control leaves V5 entirely.  Re-entry recreates fresh V5 state because
    pretending skipped V5 actions were executed would corrupt its history.
    Frozen training V5 wins showed zero gate triggers on their *original*
    trajectories. Prospective outcomes can differ and are NOT certified.
    """

    def __init__(self, baseline_factory: Callable, rescue_factory: Callable, gate: dict):
        if not callable(baseline_factory) or not callable(rescue_factory) or not isinstance(gate, dict):
            raise ProspectiveV11ContractError("V11_TWO_FROZEN_FACTORIES_AND_GATE_REQUIRED")
        self.baseline_factory = baseline_factory
        self.rescue_factory = rescue_factory
        self.gate = dict(gate)
        self.baseline = baseline_factory()
        if not callable(self.baseline):
            raise ProspectiveV11ContractError("V11_V5_FACTORY_NOT_CALLABLE")
        self.rescue = None
        self.rescue_active = False
        self.rescue_options = 0
        self.rescue_rounds = 0
        self.total_options = 0
        self.gate_streak = 0
        self.mode_history = []

    @staticmethod
    def _call(policy, observation, mask):
        # Original call sites supply NumPy observations/masks. A copied list
        # keeps these pure facades usable by both original and test policies.
        return checked_action(policy(list(observation), list(mask)), mask)

    def _finish_rescue(self):
        self.rescue_active = False
        self.rescue = None
        self.rescue_options = 0
        self.gate_streak = 0
        self.baseline = self.baseline_factory()
        if not callable(self.baseline):
            raise ProspectiveV11ContractError("V11_V5_RESET_FACTORY_NOT_CALLABLE")

    def __call__(self, observation, legal_mask):
        obs, mask = validate_public_inputs(observation, legal_mask)
        self.total_options += 1
        if self.rescue_active:
            # Return to baseline on observed forward reopen, any public goal
            # approach, or strict rescue budget exhaustion. No reward labels.
            if (any(mask[k] for k in FORWARD_OPTIONS) or
                    public_distance(obs) <= .035 or
                    self.rescue_options >= MAX_RESCUE_OPTIONS):
                self._finish_rescue()
            else:
                action = self._call(self.rescue, obs, mask)
                self.rescue_options += 1
                self.mode_history.append("rescue")
                return action

        v5_action = self._call(self.baseline, obs, mask)
        eligible = candidate_input(self.gate["kind"], obs, mask, v5_action,
                                   self.gate["min_distance"], self.gate["obstacle_limit"])
        self.gate_streak = self.gate_streak + 1 if eligible else 0
        if self.rescue_rounds < MAX_RESCUE_ROUNDS and self.gate_streak >= self.gate["min_streak"]:
            # No provider calls; the caller must inject the independently
            # source-verified, per-episode V10 factory. STOP if it is invalid.
            self.rescue = self.rescue_factory()
            if not callable(self.rescue):
                raise ProspectiveV11ContractError("V11_V10_FACTORY_NOT_CALLABLE")
            self.rescue_active = True
            self.rescue_rounds += 1
            self.rescue_options = 1
            self.gate_streak = 0
            action = self._call(self.rescue, obs, mask)
            self.mode_history.append("rescue")
            return action
        self.mode_history.append("frozen_v5")
        return v5_action


def policy_factory(frozen_v5_factory: Callable, frozen_v10_factory: Callable, gate_path):
    """Freeze exact candidate bytes, then yield one clean policy per episode.

    The external verified source paths (V5 original V8 runner, V10 trainer and
    model SHA) are checked by their original factories before calling this.
    """
    gate = load_frozen_gate(gate_path)
    return lambda: FrozenV11GoalPreservingRescue(frozen_v5_factory, frozen_v10_factory, gate)
