"""Observation-only adaptive MuJoCo option controller, fixed before holdout.

This is an explicit attempt to repair a negative *development* result, not a
claim of learned or validated improvement.  No true state or MuJoCo instance is
available to this controller; it receives only the common sensor/shield API.
"""
from __future__ import annotations

import numpy as np


class AdaptiveController:
    """Use proven medium contact, spend detour actions only when blocked.

    Priority:
      1. Respect the same healthy/deadman shield as constant control.
      2. Medium push when allowed (including near goal for contact dwell).
      3. Slow push when medium is blocked by pusher/object proximity.
      4. Oblique side approach only while *both* forward pushes are prohibited.
      5. Align or retreat only as a last resort.

    The fixed 10-step side reconsideration avoids permanently pursuing the
    wrong side under an inaccurate moving-obstacle map.  No in-run tuning.
    """

    def __init__(self):
        self.side: int | None = None
        self.side_steps = 0
        self.block_checkpoint: np.ndarray | None = None
        self.decisions = 0

    def __call__(self, observation, shield):
        o = np.asarray(observation, dtype=np.float64)
        m = np.asarray(shield, dtype=bool)
        if o.shape != (18,) or m.shape != (7,):
            raise ValueError("bad observation/mask ABI")
        self.decisions += 1
        if not m[:6].any():
            return 6

        if m[2]:
            self.side = None
            self.side_steps = 0
            self.block_checkpoint = None
            return 2
        if m[1]:
            self.side = None
            self.side_steps = 0
            self.block_checkpoint = None
            return 1

        # Only masked forward paths may trigger lateral attempts.  From the
        # given observations, put the pusher on the obstacle-facing side to
        # steer the object away from it; never inspect hidden true geometry.
        available_sides = [a for a in (3, 4) if m[a]]
        if available_sides:
            if self.side not in available_sides:
                self.side = (3 if o[7] >= o[1] else 4)
                if self.side not in available_sides:
                    self.side = available_sides[0]
                self.side_steps = 0
                self.block_checkpoint = o[:2].copy()

            if self.side_steps >= 10 and len(available_sides) == 2:
                # Change side only when observable progress was below 4 mm
                # across ten options. Random observation noise can cause
                # occasional false switches; that uncertainty is measured.
                movement = float(np.linalg.norm(o[:2]-self.block_checkpoint))
                if movement < .004:
                    self.side = 7-self.side
                self.side_steps = 0
                self.block_checkpoint = o[:2].copy()
            self.side_steps += 1
            return int(self.side)

        if m[0]:
            return 0
        return 5 if m[5] else 6


def make_controller():
    """Return a fresh controller for each paired world (no cross-seed memory)."""
    return AdaptiveController()
