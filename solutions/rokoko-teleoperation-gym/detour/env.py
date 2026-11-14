"""Native MuJoCo wrapper. Copied M5 integration loop; unchanged damage/dwell gates.
HOLD retains servo force, never constitutes E-stop. No unrestricted parent step.
"""
import importlib.util
from pathlib import Path
import numpy as np
import mujoco as mj
_spec = importlib.util.spec_from_file_location('frozen_m5', Path(__file__).resolve().parents[1] / 'learning/env.py')
frozen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frozen)
ContactEnv, ACTIONS, GOAL = frozen.ContactEnv, frozen.ACTIONS, frozen.GOAL
from planner import mask, desired, healthy, clear, PUSHER_RADIUS, RouteCommitment


class DetourEnv(ContactEnv):
    def reset(self, seed, ood=False):
        obs = super().reset(seed, ood=ood)
        self.route_commitment = RouteCommitment(obs)
        self.failed_segment_rejections = 0
        return obs

    def _next_waypoint(self, obs):
        route = getattr(self, "route_commitment", None)
        return route.active(obs) if route is not None else None

    def mask(self, obs=None):
        o = self.observation() if obs is None else obs
        wp = self._next_waypoint(o)
        if wp is None:
            return np.array([False]*6 + [True], dtype=bool)
        return mask(o, wp)

    def _desired(self, action):
        o = self.observation()
        wp = self._next_waypoint(o)
        target = desired(o, action, wp) if wp is not None else None
        return self.target.copy() if target is None else target

    def step(self, action):
        if self.done:
            raise RuntimeError('episode finished')
        if not isinstance(action, (int, np.integer)) or not 0 <= action < 7:
            raise ValueError('invalid option')
        requested = action
        if not self.mask()[action]:
            action = 6
            self.refusals += 1
        self.last = action
        # HOLD rejects even high-confidence proposals but does not terminate sensor recovery.
        if action == 6 and not self.held:
            self.abstained = self.done = True
        old_error = np.linalg.norm(self.data.xpos[self.obj, :2]-GOAL)
        for _ in range(0 if self.done else 10):
            self._sense()
            if not self.held:
                if not self.mask()[action]:
                    action = 6
                    self.refusals += 1
                desired = self._desired(action) if action != 6 else self.target
                delta = desired-self.target
                speed = .001 if action == 1 else .002
                candidate = self.target + delta * min(1., speed / max(np.linalg.norm(delta), 1e-12))
                # Pusher path filter catches lateral/retreat proposals too.
                current = self.data.xpos[self.push, :2]
                if (healthy(self.observation()) and
                        clear(current, candidate, self.mapped, PUSHER_RADIUS) and
                        clear(self.target, candidate, self.mapped, PUSHER_RADIUS)):
                    self.target = candidate
                else:
                    self.refusals += 1
                    self.failed_segment_rejections += 1
            else:
                self.holds += 1
            self.data.ctrl[:] = [self.target[0]+.06, self.target[1]]
            for _ in range(10):
                mj.mj_step(self.model, self.data)
                self.physics_steps += 1
                for k in range(self.data.ncon):
                    c = self.data.contact[k]
                    pair = {c.geom1, c.geom2}
                    if pair == {self.og, self.pg} or self.bg in pair and (self.og in pair or self.pg in pair):
                        force = np.zeros(6)
                        mj.mj_contactForce(self.model, self.data, k, force)
                        impulse = np.linalg.norm(force[:3]) * .002
                        self.peak = max(self.peak, float(impulse))
                        self.contacts += int(pair == {self.og, self.pg} and impulse > 1e-8)
                        self.unsafe |= bool(impulse > .006 or self.bg in pair)
                for body in (self.obj, self.push):
                    x, y, z = self.data.xpos[body]
                    self.unsafe |= not (-.2 <= x <= .3 and abs(y) <= .2 and 0 <= z <= .06)
                self.dwell = self.dwell+1 if np.linalg.norm(self.data.xpos[self.obj, :2]-GOAL) < .02 else 0
                if self.unsafe:
                    break
            self.ticks += 1
            if self.unsafe or self.dwell >= 250 and self.contacts:
                break
        self.steps += 1
        success = bool(self.dwell >= 250 and self.contacts and not self.unsafe)
        self.done |= self.unsafe or success or self.steps >= self.max_options
        error = float(np.linalg.norm(self.data.xpos[self.obj, :2]-GOAL))
        reward = float(10*(old_error-error) - .01 + 10*success - 10*self.unsafe)
        info = dict(success=success, unsafe=bool(self.unsafe), cost=int(self.unsafe),
                    abstained=self.abstained, error=error, peak_impulse=self.peak,
                    contacts=self.contacts, physics_steps=self.physics_steps, holds=self.holds,
                    acks=self.acks, refusals=self.refusals, requested=int(requested),
                    route_stage=self.route_commitment.index,
                    route_advances=self.route_commitment.advances,
                    route_waypoints=len(self.route_commitment.points),
                    failed_segment_rejections=self.failed_segment_rejections)
        return self.observation(), reward, bool(self.done), info
