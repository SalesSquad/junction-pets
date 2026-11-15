"""Bounded public TRAIN acquisition only; no action4 model inference."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path

V12_POLICY_SHA256 = "bd748f604dafbc6e0d3d59e0a5b7e08dab5e9e8ed010a13053f1417a32fd6fc6"
SOURCE = Path(__file__).resolve().parent.parent / "v12_learning" / "policy.py"
if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != V12_POLICY_SHA256:
    raise ValueError("V13_ORIGINAL_V12_POLICY_SOURCE_CHANGED")
_spec = importlib.util.spec_from_file_location("rokoko_v13_original_v12_public_policy", SOURCE)
if _spec is None or _spec.loader is None:
    raise ImportError("V13_UNIQUE_ORIGINAL_POLICY_REQUIRED")
v12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v12)


class RightBurst:
    """One instance per episode. Never accepts hidden state or outcome labels."""
    def __init__(self, factory, gate, burst_length):
        v12.require(callable(factory), "V13_V5_FACTORY_REQUIRED")
        self.factory, self.gate, self.burst_length = factory, gate, burst_length
        self.v5 = factory()
        v12.require(callable(self.v5), "V13_V5_CALLABLE_REQUIRED")
        self.streak = self.remaining = 0
        self.used = self.reset_required = False
        self.mode_history = []

    def __call__(self, observation, mask):
        o, m = v12.public_abi(observation, mask)
        if self.reset_required:
            self.v5 = self.factory()
            v12.require(callable(self.v5), "V13_V5_RESET_FAILED")
            self.reset_required = False
        baseline = v12.checked_action(self.v5(list(o), list(m)), m)
        eligible = bool(m[4] and v12.gate_input(self.gate, o, m, baseline))
        if self.remaining and not eligible:
            # Abort this burst permanently and use a freshly reset V5 now.
            self.remaining = 0
            self.v5 = self.factory()
            v12.require(callable(self.v5), "V13_V5_RESET_FAILED")
            baseline = v12.checked_action(self.v5(list(o), list(m)), m)
        self.streak = self.streak + 1 if eligible else 0
        if not self.used and self.streak >= self.gate["min_streak"]:
            self.used = True
            self.remaining = self.burst_length
        if self.remaining:
            action = v12.checked_action(4, m)
            self.remaining -= 1
            self.reset_required = self.remaining == 0
            self.mode_history.append("UNTRAINED_RIGHT4_EXPLORATION_ONLY")
            return action
        self.mode_history.append("frozen_v5")
        return baseline


def right_burst_factory(frozen_v5_factory, model_path, burst_length: int):
    v12.require(type(burst_length) is int and burst_length in (2, 4),
                "V13_ONLY_PREREGISTERED_BURST2_OR_BURST4")
    gate = v12.load_frozen_model(model_path)["frozenV11GateParameters"]
    return lambda: RightBurst(frozen_v5_factory, gate, burst_length)
