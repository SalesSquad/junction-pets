"""MuJoCo-only moving-obstacle contact task; extends, never patches, ContactEnv.

The implementation intentionally retains the original robot servo, contact
threshold, sensor/deadman logic, and success criterion.  The only added dynamics
are a continuously advanced mocap obstacle and observable obstacle-map updates.
"""
from __future__ import annotations

from pathlib import Path
import math
import sys

import mujoco as mj
import numpy as np

LEARNING_DIR = Path(__file__).resolve().parents[2]
if str(LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(LEARNING_DIR))

from env import ContactEnv, GOAL  # noqa: E402 -- existing source-bound MuJoCo task

SCENE = Path(__file__).with_name("moving_scene.xml")


class MovingContactEnv(ContactEnv):
    """Original option/contact model with MuJoCo-resolved moving obstacle.

    World, sensor, acknowledgement and motion seeds are independent streams.
    Observed geometry can lag or drop; the policy never receives the mover's
    hidden amplitude, frequency, phase, or uncorrupted position.
    """

    def __init__(self, max_options: int = 60):
        super().__init__(max_options=max_options)
        self.model = mj.MjModel.from_xml_path(str(SCENE))
        self.data = mj.MjData(self.model)
        self.obj = self.model.body("object").id
        self.push = self.model.body("pusher").id
        self.og = self.model.geom("object_geom").id
        self.pg = self.model.geom("pusher_geom").id
        self.bg = self.model.geom("obstacle").id
        self.inertia = self.model.body_inertia[self.obj].copy()
        mover_body = self.model.body("moving_obstacle").id
        self.mocap_id = int(self.model.body_mocapid[mover_body])
        if self.mocap_id < 0 or abs(float(self.model.opt.timestep) - 0.002) > 1e-12:
            raise RuntimeError("Moving obstacle lacks supported MuJoCo mocap/timestep")
        self._moving_ready = False
        self.amplitude = self.frequency = self.phase = 0.0

    def reset(self, seed: int, ood: bool = False):
        self._moving_ready = False
        motion = np.random.default_rng(np.random.SeedSequence([seed, 4]))
        self.amplitude = float(motion.uniform(0.018 if not ood else 0.024,
                                               0.035 if not ood else 0.045))
        self.frequency = float(motion.uniform(0.35, 0.75 if not ood else 1.0))
        self.phase = float(motion.uniform(-math.pi, math.pi))
        super().reset(seed=seed, ood=ood)
        self._advance_mover()
        mj.mj_forward(self.model, self.data)
        self.mapped = self.data.geom_xpos[self.bg, :2].copy() + self.sensor.normal(0, .005, 2)
        self._moving_ready = True
        self._sense()
        return self.observation()

    def _advance_mover(self):
        # mocap coordinates are world-frame; geom's randomized local y position
        # remains the same as ContactEnv's original world distribution.
        t = float(self.data.time)
        self.data.mocap_pos[self.mocap_id] = [
            0.09,
            self.amplitude * math.sin(2 * math.pi * self.frequency * t + self.phase),
            0.03,
        ]

    def _sense(self):
        super()._sense()
        if self._moving_ready and self.quality > .8:
            # Measured, noisy MuJoCo geometry, never hidden mover parameters.
            self.mapped = self.data.geom_xpos[self.bg, :2].copy() + self.sensor.normal(0, .005, 2)

    def mask(self, obs=None):
        o = self.observation() if obs is None else obs
        allowed = super().mask(o)
        if o[15] or not o[10] or not o[11] or o[8] > .1 or o[9] < .8:
            return allowed  # deadman, low quality and stale frames always win
        object_xy = np.asarray(o[:2], dtype=np.float64)
        obstacle_xy = np.asarray(o[6:8], dtype=np.float64)
        to_goal = GOAL - object_xy
        unit = to_goal / max(float(np.linalg.norm(to_goal)), 1e-9)
        nearest = object_xy + np.clip(
            np.dot(obstacle_xy-object_xy, to_goal) /
            max(np.dot(to_goal, to_goal), 1e-12), 0., 1.) * to_goal
        if float(np.linalg.norm(obstacle_xy - nearest)) < .060:
            # Never reopen forward pushes across a mapped obstacle; consider
            # alignment and both side approaches if their servo targets clear it.
            lateral = np.array([-unit[1], unit[0]])
            for option, offset in ((0, 0.), (3, .03), (4, -.03)):
                destination = object_xy - (.041 if option == 0 else .024) * unit + (
                    0. if option == 0 else (.019 if option == 3 else -.019)) * lateral
                allowed[option] = bool(np.linalg.norm(destination-obstacle_xy) > .055)
        return allowed

    def _desired(self, action):
        if action in (3, 4):
            # The inherited APPROACH side target (.045 behind, .03 lateral) is
            # outside the .032 sum of object/pusher radii and cannot induce a
            # multi-action detour. Here a shallow oblique contact is possible.
            # The same modified primitives are available to every controller.
            obj = self.visible
            toward = GOAL-obj
            unit = toward / max(np.linalg.norm(toward), 1e-8)
            lateral = np.array([-unit[1], unit[0]])
            return obj-.024*unit + (.019 if action == 3 else -.019)*lateral
        return super()._desired(action)

    def step(self, action):
        if self.done:
            raise RuntimeError("episode finished")
        if not isinstance(action, (int, np.integer)) or not 0 <= action < 7:
            raise ValueError("invalid option")
        requested = int(action)
        if not self.mask()[action]:
            action = 6 if self.held else 5
            self.refusals += 1
        self.last = action
        if action == 6 and not self.held:
            self.abstained = self.done = True
        old_error = np.linalg.norm(self.data.xpos[self.obj, :2] - GOAL)
        for _ in range(0 if self.done else 10):
            self._sense()
            if not self.held:
                if not self.mask()[action]:
                    action = 5
                    self.refusals += 1
                desired = self._desired(action) if action != 6 else self.target
                delta = desired - self.target
                speed = .001 if action == 1 else .002
                candidate = self.target + delta * min(1., speed / max(np.linalg.norm(delta), 1e-12))
                if (-.19 <= candidate[0] <= .29 and abs(candidate[1]) <= .19
                        and np.linalg.norm(candidate-self.mapped) > .055):
                    self.target = candidate
                else:
                    self.refusals += 1
            else:
                self.holds += 1
            self.data.ctrl[:] = [self.target[0]+.06, self.target[1]]
            for _ in range(10):
                # This is an actual MuJoCo integration step for each 2 ms.
                self._advance_mover()
                mj.mj_step(self.model, self.data)
                self.physics_steps += 1
                for k in range(self.data.ncon):
                    c = self.data.contact[k]
                    pair = {c.geom1, c.geom2}
                    if pair == {self.og, self.pg} or self.bg in pair and (
                            self.og in pair or self.pg in pair):
                        force = np.zeros(6)
                        mj.mj_contactForce(self.model, self.data, k, force)
                        impulse = np.linalg.norm(force[:3]) * .002
                        self.peak = max(self.peak, float(impulse))
                        self.contacts += int(pair == {self.og, self.pg} and impulse > 1e-8)
                        self.unsafe |= bool(impulse > .006 or self.bg in pair)
                for body in (self.obj, self.push):
                    x, y, z = self.data.xpos[body]
                    self.unsafe |= not (-.2 <= x <= .3 and abs(y) <= .2 and 0 <= z <= .06)
                self.dwell = self.dwell + 1 if np.linalg.norm(
                    self.data.xpos[self.obj, :2] - GOAL) < .02 else 0
                if self.unsafe:
                    break
            self.ticks += 1
            if self.unsafe or self.dwell >= 250 and self.contacts:
                break
        self.steps += 1
        success = bool(self.dwell >= 250 and self.contacts and not self.unsafe)
        self.done |= self.unsafe or success or self.steps >= self.max_options
        error = float(np.linalg.norm(self.data.xpos[self.obj, :2] - GOAL))
        reward = float(10*(old_error-error) - .01 + 10*success - 10*self.unsafe)
        info = dict(success=success, unsafe=bool(self.unsafe), cost=int(self.unsafe),
                    abstained=self.abstained, error=error, peak_impulse=self.peak,
                    contacts=self.contacts, physics_steps=self.physics_steps,
                    holds=self.holds, acks=self.acks, refusals=self.refusals,
                    requested=requested)
        return self.observation(), reward, bool(self.done), info
