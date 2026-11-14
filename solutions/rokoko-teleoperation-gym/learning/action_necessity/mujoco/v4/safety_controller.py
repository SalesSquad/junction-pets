"""Observation-only swept-lane safety hypothesis for the MuJoCo option gym.

No simulator state, hidden obstacle phase, seed, reward or outcome enters the
policy. All early detours use the existing seven-option action ABI and the
existing environment shield. This is an experimental controller, not a safety
certificate for physical hardware.
"""
from __future__ import annotations

from pathlib import Path
import math
import sys

import numpy as np

V3 = Path(__file__).resolve().parent.parent / "v3"
if str(V3) not in sys.path:
    sys.path.insert(0, str(V3))

from risk_controller import RiskAwareController  # noqa: E402


class SweptLaneController(RiskAwareController):
    """Use early lateral contact or explicitly refuse an uncertified passage.

    The public MuJoCo obstacle is a moving box near x=.09. Its y displacement
    is at most .035 in the development/calibration scene. A close centerline
    creates a swept-contact corridor. The v3 controller reacts only once
    forward actions are masked; by then its shallow side contact may be too
    late, and ALIGN/RETREAT can themselves create obstacle contact.

    V4 tries to set up a lane *before* entering the corridor and refuses
    risky last-resort motion. The min-clearance check is deliberately wider
    than v3's .008 m drift, accounting for up to ~.016 m unmodeled sinusoidal
    curvature over a .2 s option, plus noisy map updates. It is a bounded
    heuristic, not a formal guarantee with Gaussian (unbounded) noise.
    """

    COLLISION_CLEARANCE = .066
    # Conservative centerline threshold from box halfwidth .018, object
    # radius .020, up to .035 sin motion, and map noise. It is source geometry,
    # not a label learned from the opened calibration worlds.
    POSSIBLE_SWEEP_Y = .112
    CORRIDOR_ENTRY_X = .050
    CORRIDOR_EXIT_X = .132
    LANE_DISTANCE = .031

    def __init__(self):
        super().__init__()
        self.threat_latched = False
        self.threat_sign = 1.
        self.phase = "normal"
        self.risk_abstentions = 0

    def _clearance(self, o, action):
        """Observed object center separation over one actual option window."""
        obj = np.asarray(o[:2], dtype=float)
        obstacle = np.asarray(o[6:8], dtype=float)
        # The real pusher target can advance .002 m * ten controls in one
        # option. V3's .011 m forward estimate underbound that open-loop
        # traversal and could deem a contact path clear too late. The extra
        # few millimetres also cover modest object inertia/noisy servo lag.
        if action == 2:
            dx, dy = .024, 0.
        elif action == 1:
            dx, dy = .014, 0.
        elif action in (3, 4):
            dx, dy = .021, -.019 if action == 3 else .019
        else:
            return float("inf")
        gap_min = float("inf")
        for f in (.2, .4, .6, .8, 1.):
            predicted = obj + [dx * f, dy * f]
            mover_y = obstacle[1] + self.map_velocity_y * self.STEP_HORIZON * f
            for drift in (-.023, 0., .023):
                gap_min = min(gap_min, math.hypot(
                    float(predicted[0] - obstacle[0]),
                    float(predicted[1] - mover_y - drift)))
        return gap_min

    def _abstain(self):
        self.risk_abstentions += 1
        return 6

    def __call__(self, observation, mask):
        o = np.asarray(observation, dtype=float)
        m = np.asarray(mask, dtype=bool)
        if o.shape != (18,) or m.shape != (7,):
            raise ValueError("bad observation/mask ABI")
        if not m[:6].any():
            self.phase = "deadman_or_shielded"
            return 6  # The base deadman is absolute.

        # A close swept corridor must be remembered even when the moving box
        # later oscillates out of the current noisy field of view.
        self._observe(o)
        if abs(float(o[7])) < self.POSSIBLE_SWEEP_Y:
            self.threat_latched = True
            self.threat_sign = 1. if o[7] >= 0. else -1.
        if not self.threat_latched:
            self.phase = "normal"
            # Keep the successful v3 behavior away from swept obstacle space;
            # use the already-updated map state without a second update.
            return self._forward_or_detour(o, m)

        obj_x, obj_y = float(o[0]), float(o[1])
        safe_lane = obj_y * self.threat_sign <= -self.LANE_DISTANCE
        side_action = 3 if self.threat_sign > 0 else 4

        if obj_x < self.CORRIDOR_ENTRY_X:
            self.phase = "early_lane_setup"
            if not safe_lane:
                # Start the shallow oblique contact *before* forward passage;
                # v3 would postpone it until both forward actions are masked.
                return side_action if m[side_action] and self._safe(o, side_action) else self._abstain()
            self.phase = "early_lane_ready"
            return self._forward_or_abort(o, m)

        if obj_x <= self.CORRIDOR_EXIT_X:
            self.phase = "crossing_swept_corridor"
            if not safe_lane:
                return self._abstain()
            # Both side changes and even ALIGN/RETREAT can create delayed
            # pusher-obstacle contacts here. Permit only guarded forward motion.
            return self._forward_or_abort(o, m)

        # Once the *object* clears the swept contact corridor, pusher may still
        # be near it. Keep conservative forward/abstain until its observed x
        # clears too, then recover toward the goal under the inherited v3 logic.
        if float(o[2]) <= self.CORRIDOR_EXIT_X:
            self.phase = "pusher_clearance"
            return self._forward_or_abort(o, m)
        self.phase = "goal_recovery"
        return self._forward_or_detour(o, m)

    def _forward_or_abort(self, o, m):
        for option in (2, 1):
            if m[option] and self._safe(o, option):
                return option
        return self._abstain()

    def _forward_or_detour(self, o, m):
        for option in (2, 1):
            if m[option] and self._safe(o, option):
                return option
        # Do not send an uncertified ALIGN or RETREAT near the mover. In the
        # far clear region they are the existing shielded fallback options.
        if abs(float(o[0] - o[6])) > .095:
            return 0 if m[0] else 5 if m[5] else self._abstain()
        return self._abstain()


def make_controller():
    return SweptLaneController()
