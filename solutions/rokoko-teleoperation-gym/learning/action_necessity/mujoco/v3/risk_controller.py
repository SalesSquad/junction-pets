"""Short-horizon observed-motion risk guard for a real MuJoCo option gym.

No privileged object state, hidden obstacle phase, MuJoCo calls or learned model
are used. All decisions arise solely from the existing observation and mask.
The controller cannot undo a permanent deadman release; that is deliberate.
"""
from __future__ import annotations

import math
import numpy as np


class RiskAwareController:
    # Geometry from the *public* XML: object radius .020, obstacle half-width
    # .018 and sensor noise approximately .005. The .055 center clearance is
    # a conservative local action veto, not a certified collision guarantee.
    COLLISION_CLEARANCE = .055
    STEP_HORIZON = .20  # ten controls * ten 2-ms MuJoCo integration steps

    def __init__(self):
        self.last_map = None
        self.map_velocity_y = 0.
        self.side = None
        self.side_steps = 0
        self.would_collide_rejections = 0
        self.decisions = 0

    def _observe(self, o):
        mapped = np.asarray(o[6:8], dtype=float)
        if self.last_map is not None and o[9] > .8 and o[8] <= .1:
            # Noisy map frame-to-frame: robustly smooth finite differences.
            raw = float(np.clip((mapped[1]-self.last_map[1]) / self.STEP_HORIZON,
                                -.20, .20))
            self.map_velocity_y = .65*self.map_velocity_y+.35*raw
        self.last_map = mapped.copy()

    def _clearance(self, o, action):
        """Predicted min center separation over one option, observed only."""
        obj = np.asarray(o[:2], dtype=float)
        obstacle = np.asarray(o[6:8], dtype=float)
        # Short contact motion is an overapproximation for one option; we also
        # check both signs of a bounded curvature/noise uncertainty band.
        if action == 2:
            dx, dy = .011, 0.
        elif action == 1:
            dx, dy = .007, 0.
        elif action in (3, 4):
            sign = 1 if action == 3 else -1
            dx, dy = .008, -.007*sign
        else:
            return float("inf")
        minimum = float("inf")
        for fraction in (.25, .5, .75, 1.):
            predicted_object = obj + [dx*fraction, dy*fraction]
            obstacle_future_y = obstacle[1] + self.map_velocity_y*self.STEP_HORIZON*fraction
            for drift in (-.008, 0., .008):
                gap = math.hypot(float(predicted_object[0]-obstacle[0]),
                                 float(predicted_object[1]-obstacle_future_y-drift))
                minimum = min(minimum, gap)
        return minimum

    def _safe(self, o, option):
        if self._clearance(o, option) > self.COLLISION_CLEARANCE:
            return True
        self.would_collide_rejections += 1
        return False

    def __call__(self, observation, mask):
        o = np.asarray(observation, dtype=float)
        m = np.asarray(mask, dtype=bool)
        if o.shape != (18,) or m.shape != (7,):
            raise ValueError("bad observation/mask ABI")
        self.decisions += 1
        self._observe(o)
        if not m[:6].any():
            return 6  # deadman/stale/held: never bypass base shield

        # Keep the successful medium-contact baseline whenever the shared
        # shield AND our conservative observed swept envelope allow it.
        if m[2] and self._safe(o, 2):
            # Preserve first safe detour direction even through a forward
            # interval: the v2 unsafe contact followed a late side reversal.
            self.side_steps = 0
            return 2
        if m[1] and self._safe(o, 1):
            self.side_steps = 0
            return 1

        # A side approach should only be used if forward control is genuinely
        # blocked. Never flip a previous direction merely because the dynamic
        # noisy map crosses the object later in the episode (v2's unsafe path).
        can_detour = not m[1] and not m[2]
        available = [a for a in (3, 4) if m[a] and self._safe(o, a)] if can_detour else []
        if available:
            if self.side not in available:
                # Once committed to a side, never reverse near the moving
                # obstacle; wait for clearance instead of contacting blindly.
                if self.side is not None:
                    return 0 if m[0] else 5 if m[5] else 6
                candidate = 3 if o[7] >= o[1] else 4
                self.side = candidate if candidate in available else available[0]
            self.side_steps += 1
            return self.side

        # Alignment keeps the pusher in a recoverable pose while a moving
        # obstacle clears; retreat is the last legal controlled waiting option.
        return 0 if m[0] else 5 if m[5] else 6


def make_controller():
    return RiskAwareController()
