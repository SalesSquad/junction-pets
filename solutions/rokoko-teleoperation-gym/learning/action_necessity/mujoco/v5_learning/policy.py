"""Frozen observation-only parameterized policy for real MuJoCo option control.

The vector is learned from simulator *training* rewards. No seed, privileged
MuJoCo state, hidden motion phase, or episode outcome enters policy inference.
The unchanged environment mask/deadman shield remains the final authority.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

V4 = Path(__file__).resolve().parent.parent / "v4"
if str(V4) not in sys.path:
    sys.path.insert(0, str(V4))
from safety_controller import SweptLaneController  # noqa: E402


PARAMETERS = (
    "COLLISION_CLEARANCE", "POSSIBLE_SWEEP_Y",
    "CORRIDOR_ENTRY_X", "LANE_DISTANCE",
)
BOUNDS = {
    "COLLISION_CLEARANCE": (.058, .080),
    "POSSIBLE_SWEEP_Y": (.085, .145),
    "CORRIDOR_ENTRY_X": (.030, .070),
    "LANE_DISTANCE": (.023, .045),
}
DEFAULT = {name: float(getattr(SweptLaneController, name)) for name in PARAMETERS}


def validate_weights(weights):
    if not isinstance(weights, dict) or set(weights) != set(PARAMETERS):
        raise ValueError("MODEL_PARAMETER_SCHEMA_MISMATCH")
    parsed = {}
    for name in PARAMETERS:
        value = weights[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"NONFINITE_MODEL_PARAMETER_{name}")
        low, high = BOUNDS[name]
        if not low <= value <= high:
            raise ValueError(f"OUT_OF_BOUNDS_MODEL_PARAMETER_{name}")
        parsed[name] = float(value)
    return parsed


class LearnedSweptController(SweptLaneController):
    def __init__(self, weights):
        super().__init__()
        for name, value in validate_weights(weights).items():
            setattr(self, name, value)


def make_factory(weights):
    frozen = validate_weights(weights)
    return lambda: LearnedSweptController(frozen)
