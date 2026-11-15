"""Observed-contact corridor planner, distinct from v5 threshold tuning.

Uses only the 18-element public observation, 7-element independent shield mask,
and own past proposals/observed displacement. No MuJoCo state, hidden obstacle
phase, release seed, reward or contact truth is accessible during inference.

The actual option ABI is ALIGN=0, PUSH_SLOW=1, PUSH_MEDIUM=2,
APPROACH_LEFT=3, APPROACH_RIGHT=4, RETREAT=5, ABSTAIN=6.
RETREAT is a servo command, not an E-stop or a literal no-op/HOLD.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

V5 = Path(__file__).resolve().parent.parent / "v5_learning"
if str(V5) not in sys.path:
    sys.path.insert(0, str(V5))
from policy import LearnedSweptController, validate_weights as validate_v5_weights  # noqa: E402


V5_FROZEN_WEIGHTS = {
    "COLLISION_CLEARANCE": .0597963,
    "CORRIDOR_ENTRY_X": .0586112,
    "LANE_DISTANCE": .0265924,
    "POSSIBLE_SWEEP_Y": .0903199,
}
V5_FROZEN_WEIGHTS_SHA256 = "fc3504f64c7e283cb53fbb8801c99e3bd9065e1fb0bc19ae73a66b8f7e4b5875"

BOUNDS = {
    "align_budget": (1, 4),
    "side_budget": (3, 16),
    "replan_budget": (1, 4),
    "contact_probe_period": (2, 6),
    "lateral_progress_epsilon": (.0005, .004),
    "desired_lane_y": (.022, .045),
    "corridor_exit_x": (.090, .145),
    "pusher_clearance": (.055, .080),
}
DEFAULT = {
    "align_budget": 2,
    "side_budget": 12,
    "replan_budget": 2,
    "contact_probe_period": 3,
    "lateral_progress_epsilon": .0012,
    "desired_lane_y": .028,
    "corridor_exit_x": .135,
    "pusher_clearance": .057,
}
INTEGERS = frozenset(("align_budget", "side_budget", "replan_budget",
                      "contact_probe_period"))


def canonical_sha(value):
    b = json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


if canonical_sha(V5_FROZEN_WEIGHTS) != V5_FROZEN_WEIGHTS_SHA256:
    raise RuntimeError("FROZEN_V5_BASELINE_WEIGHTS_DIGEST_MISMATCH")
validate_v5_weights(V5_FROZEN_WEIGHTS)


def validate_weights(weights):
    if not isinstance(weights, dict) or set(weights) != set(BOUNDS):
        raise ValueError("V6_PARAMETER_SCHEMA_MISMATCH")
    result = {}
    for name, (low, high) in BOUNDS.items():
        value = weights[name]
        if name in INTEGERS:
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"V6_INVALID_INTEGER_{name}")
        elif type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"V6_INVALID_FLOAT_{name}")
        result[name] = int(value) if name in INTEGERS else float(value)
    return result


class CorridorContactController(LearnedSweptController):
    """Guarded macro ALIGN -> SIDE -> SLOW_PUSH -> reobserve/replan -> cross.

    Crucially unlike v4/v5, this does not immediately ABSTAIN after shallow
    side approach fails to move the object; it allocates bounded contact setup
    attempts, measured by observed displacement. Every option is checked by
    the unchanged mask plus an observation-only pusher/obstacle sweep guard.
    """
    def __init__(self, weights):
        super().__init__(V5_FROZEN_WEIGHTS)
        self.w = validate_weights(weights)
        self.phase = "uninitialized"
        self.side = None
        self.align_count = 0
        self.side_count = 0
        self.replan_count = 0
        self.probe_count = 0
        self.no_lateral_progress = 0
        self.last_obj = None
        self.last_action = None
        self.last_side_sign = 1.
        self.total_actions = 0
        self.route_mode = None

    def _pusher_path_safe(self, o, action):
        """Conservative observed interpolation, never hidden contact geometry."""
        obj = np.asarray(o[:2], dtype=float)
        push = np.asarray(o[2:4], dtype=float)
        obstacle = np.asarray(o[6:8], dtype=float)
        direction = np.asarray(o[16:18], dtype=float)-obj
        direction /= max(float(np.linalg.norm(direction)), 1e-8)
        lateral = np.array([-direction[1], direction[0]], dtype=float)
        if action == 0:
            target = obj - .041*direction
        elif action == 3:
            target = obj - .024*direction + .019*lateral
        elif action == 4:
            target = obj - .024*direction - .019*lateral
        elif action == 5:
            target = push - .035*direction
        else:
            return True  # Forward actions also pass inherited `_safe` guard.
        # One option can move at most ~.020m under original servo. Inspect
        # the full push->target envelope conservatively, with mapped mover
        # motion and bounded drift; an uncertain route is refused.
        for fraction in (.2, .4, .6, .8, 1.):
            point = push + (target-push)*fraction
            mover_y = obstacle[1] + self.map_velocity_y*self.STEP_HORIZON*fraction
            for drift in (-.023, 0., .023):
                gap = math.hypot(float(point[0]-obstacle[0]),
                                 float(point[1]-mover_y-drift))
                if gap <= self.w["pusher_clearance"]:
                    return False
        return True

    def _proposal(self, o, m, action):
        if not bool(m[action]):
            return None
        if action in (1, 2, 3, 4) and not self._safe(o, action):
            return None
        if not self._pusher_path_safe(o, action):
            return None
        return action

    def _observe_progress(self, obj, sign):
        if self.last_obj is not None and self.last_action in (1, 3, 4):
            moved_away = (float(self.last_obj[1]) - float(obj[1]))*sign
            if moved_away >= self.w["lateral_progress_epsilon"]:
                self.no_lateral_progress = 0
            else:
                self.no_lateral_progress += 1
        self.last_obj = obj.copy()

    def _decide(self, o, m):
        obj = np.asarray(o[:2], dtype=float)
        obstacle = np.asarray(o[6:8], dtype=float)
        if self.side is None:
            self.last_side_sign = 1. if obstacle[1] >= obj[1] else -1.
            self.side = 3 if self.last_side_sign > 0 else 4
        self._observe_progress(obj, self.last_side_sign)
        lateral_ready = float(obj[1])*self.last_side_sign <= -self.w["desired_lane_y"]

        # Once both object and pusher have actually cleared the observed
        # corridor along x, switch back to the frozen v5 goal-recovery logic.
        # The crossing threshold is learned on training-only worlds.
        if (float(obj[0]) >= self.w["corridor_exit_x"] and
                float(o[2]) >= self.w["corridor_exit_x"]-.020):
            self.phase = "post_corridor_goal_recovery"
            return self._forward_or_detour(o, m)

        self.threat_latched = True
        if lateral_ready:
            self.phase = "guarded_corridor_transit"
            for action in (2, 1):
                candidate = self._proposal(o, m, action)
                if candidate is not None:
                    return candidate
            # If the moving obstacle masks progress, attempt bounded ALIGN or
            # RETREAT servo motions. They are not no-op waits or E-stops.
            if self.replan_count < self.w["replan_budget"]:
                for action in (0, 5):
                    candidate = self._proposal(o, m, action)
                    if candidate is not None:
                        self.replan_count += 1
                        return candidate
            return 6

        # Before side contact, put the pusher behind the object. The chosen
        # macro intentionally differs from v5 threshold-only behavior.
        push = np.asarray(o[2:4], dtype=float)
        needs_align = float(np.linalg.norm(push-obj)) > .049
        if needs_align and self.align_count < self.w["align_budget"]:
            candidate = self._proposal(o, m, 0)
            if candidate is not None:
                self.phase = "align_for_lateral_contact"
                self.align_count += 1
                return candidate

        # Repeated side approach can be needed before a real contact occurs.
        # Periodically probe with slow PUSH rather than retreat/ABSTAIN at the
        # exact step when the first shallow side approach did not move object.
        if self.side_count < self.w["side_budget"]:
            probe_due = (self.side_count >= 2 and
                         (self.side_count % self.w["contact_probe_period"] == 0
                          or self.no_lateral_progress >=
                          max(2, self.w["contact_probe_period"]-1)))
            if probe_due:
                probe = self._proposal(o, m, 1)
                if probe is not None:
                    self.phase = "slow_contact_probe"
                    self.probe_count += 1
                    self.side_count += 1
                    return probe
            side = self._proposal(o, m, self.side)
            if side is not None:
                self.phase = "shallow_side_contact"
                self.side_count += 1
                return side

        # Bounded re-plan: RETREAT is a *servo*, not a wait/no-op. When it is
        # unsafe/masked, ALIGN is a separate physical servo motion.
        if self.replan_count < self.w["replan_budget"]:
            for action in (5, 0):
                candidate = self._proposal(o, m, action)
                if candidate is not None:
                    self.phase = "bounded_retreat_reobserve"
                    self.replan_count += 1
                    self.side_count = 0
                    return candidate

        # No certified contact path remains. Zero-physics first-option ABSTAIN
        # and later ABSTAIN both count as failed episodes in real evaluation.
        self.phase = "explicit_safe_abort"
        return 6

    def __call__(self, observation, mask):
        o = np.asarray(observation, dtype=float)
        m = np.asarray(mask, dtype=bool)
        if o.shape != (18,) or m.shape != (7,):
            raise ValueError("V6_OBSERVATION_MASK_ABI_MISMATCH")
        if not m[:6].any():
            self.phase = "deadman_or_unhealthy_shield"
            self.last_action = 6
            return 6
        # Select route mode from the first **visible** obstacle map and keep
        # it for the episode. If clearly out of corridor, delegate every
        # subsequent action to the exact frozen v5 controller unchanged.
        # This prevents v6 state-machine adaptation from perturbing successes
        # of the v5 clear-world baseline when moving-map y later oscillates.
        if self.route_mode is None:
            self.route_mode = ("clear_v5" if abs(float(o[7])) >= .122
                               else "corridor_contact")
        if self.route_mode == "clear_v5":
            action = super().__call__(o, m)
            self.last_action = int(action)
            self.total_actions += 1
            return int(action)
        self._observe(o)
        action = self._decide(o, m)
        if action != 6 and not m[action]:
            raise AssertionError("V6_ACTION_BYPASSED_INDEPENDENT_SHIELD")
        self.last_action = int(action)
        self.total_actions += 1
        return int(action)


def make_factory(weights):
    frozen = validate_weights(weights)
    return lambda: CorridorContactController(frozen)
