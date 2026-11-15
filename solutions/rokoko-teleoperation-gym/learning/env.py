"""Synthetic option gym on the original MuJoCo XML. HOLD is a servo, not E-stop."""
from pathlib import Path
import random
import numpy as np
import mujoco as mj

SCENE = Path(__file__).resolve().parent.parent / 'sim' / 'scene.xml'
ACTIONS = ('ALIGN', 'PUSH_SLOW', 'PUSH_MEDIUM', 'APPROACH_LEFT',
           'APPROACH_RIGHT', 'RETREAT', 'ABSTAIN')
GOAL = np.array([.16, 0.])
OBS_SIZE = 18


class ContactEnv:
    def __init__(self, max_options=60):
        self.model = mj.MjModel.from_xml_path(str(SCENE))
        self.data = mj.MjData(self.model)
        self.max_options = max_options
        self.obj = self.model.body('object').id
        self.push = self.model.body('pusher').id
        self.og = self.model.geom('object_geom').id
        self.pg = self.model.geom('pusher_geom').id
        self.bg = self.model.geom('obstacle').id
        self.inertia = self.model.body_inertia[self.obj].copy()
        assert abs(self.model.opt.timestep - .002) < 1e-12

    def reset(self, seed, ood=False):
        if not 120000 <= seed < 520000:
            raise ValueError('Only fresh reserved world groups permitted')
        world = np.random.default_rng(np.random.SeedSequence([seed, 1]))
        self.sensor = np.random.default_rng(np.random.SeedSequence([seed, 2]))
        self.ack_rng = np.random.default_rng(np.random.SeedSequence([seed, 3]))
        mj.mj_resetData(self.model, self.data)
        self.model.body_mass[self.obj] = world.uniform(.04 if ood else .065, .15 if ood else .095)
        self.model.body_inertia[self.obj] = self.inertia * self.model.body_mass[self.obj] / .08
        self.model.geom_friction[self.og, 0] = world.uniform(.12 if ood else .32, .9 if ood else .48)
        self.model.geom_pos[self.bg, 1] = world.choice([-.065, -.03, 0., .03, .065]) if ood else world.choice([.15, .15, .065])
        self.mapped = self.model.geom_pos[self.bg, :2].copy() + self.sensor.normal(0, .007, 2)
        mj.mj_setConst(self.model, self.data)
        self.data.qpos[:2] = [world.uniform(-.018, .018), world.uniform(-.048, .048)]
        mj.mj_forward(self.model, self.data)
        self.target = self.data.xpos[self.push, :2].copy()
        self.ticks = self.steps = self.physics_steps = self.contacts = self.dwell = 0
        self.last = 0
        self.help = 2
        self.held = self.done = self.unsafe = self.abstained = False
        self.refusals = self.acks = self.holds = 0
        self.peak = 0.
        self.drop_start = int(world.integers(30, 170))
        self.drop_len = int(world.choice([0, 0, 12, 25]))
        self.release = int(world.choice([-1, -1, 160]))
        self.visible = self.data.xpos[self.obj, :2].copy() + self.sensor.normal(0, .0015, 2)
        self.seen = 0
        self._sense()
        return self.observation()

    def _sense(self):
        dropout = self.drop_start <= self.ticks < self.drop_start + self.drop_len
        self.live = self.release < 0 or self.ticks < self.release
        self.quality = .4 if dropout else .99
        if not dropout:
            self.visible = self.data.xpos[self.obj, :2].copy() + self.sensor.normal(0, .0015, 2)
            self.seen = self.ticks
        self.age = (self.ticks - self.seen) * .02
        p = self.data.xpos[self.push, :2]
        self.inside = bool(-.19 <= p[0] <= .29 and abs(p[1]) <= .19)
        healthy = self.live and self.quality > .8 and self.age <= .1 and self.inside
        if not healthy:
            self.held = True
        # Independent synthetic acknowledgement event, never derived from policy or health.
        ack = self.ack_rng.random() < .04
        if self.held and healthy and ack and self.help:
            self.held = False
            self.help -= 1
            self.acks += 1

    def observation(self):
        p = self.data.xpos[self.push, :2]
        return np.asarray([*self.visible, *p, *self.data.qvel[6:8], *self.mapped,
                           self.age, self.quality, self.live, self.inside, self.help / 2,
                           self.ticks / (10 * self.max_options), self.last / 6,
                           self.held, *GOAL], dtype=np.float32)

    def mask(self, obs=None):
        o = self.observation() if obs is None else obs
        allowed = np.ones(7, dtype=bool)
        if o[15] or not o[10] or not o[11] or o[8] > .1 or o[9] < .8:
            allowed[:6] = False
            return allowed
        # Conservative mapped corridor filter, independent of learned confidence.
        a, b, obstacle = o[:2], GOAL, o[6:8]
        v = b - a
        nearest = a + np.clip(np.dot(obstacle-a, v) / max(np.dot(v, v), 1e-12), 0, 1) * v
        if np.linalg.norm(nearest-obstacle) < .060:
            allowed[:5] = False
        if np.linalg.norm(o[2:4] - o[:2]) < .029:
            allowed[2] = False
        return allowed

    def _desired(self, action):
        obj, p = self.visible, self.data.xpos[self.push, :2]
        v = GOAL-obj
        v = v / max(np.linalg.norm(v), 1e-8)
        lateral = np.array([-v[1], v[0]])
        if action == 0:
            return obj - .041*v
        if action in (1, 2):
            return obj - (.029 if action == 1 else .0275)*v
        if action in (3, 4):
            return obj - .045*v + (.03 if action == 3 else -.03)*lateral
        return p - .035*v

    def step(self, action):
        if self.done:
            raise RuntimeError('episode finished')
        if not isinstance(action, (int, np.integer)) or not 0 <= action < 7:
            raise ValueError('invalid option')
        requested = action
        if not self.mask()[action]:
            action = 6 if self.held else 5
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
                    action = 5
                    self.refusals += 1
                desired = self._desired(action) if action != 6 else self.target
                delta = desired-self.target
                speed = .001 if action == 1 else .002
                candidate = self.target + delta * min(1., speed / max(np.linalg.norm(delta), 1e-12))
                # Pusher path filter catches lateral/retreat proposals too.
                if (-.19 <= candidate[0] <= .29 and abs(candidate[1]) <= .19
                        and np.linalg.norm(candidate-self.mapped) > .055):
                    self.target = candidate
                else:
                    self.refusals += 1
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
                    acks=self.acks, refusals=self.refusals, requested=int(requested))
        return self.observation(), reward, bool(self.done), info


def sample_nonterminal_exploration(mask):
    # A random exploratory option must not accidentally end almost every
    # episode through ABSTAIN when useful safe options remain available.
    # ABSTAIN is still mandatory when the independent shield leaves no option.
    available = np.flatnonzero(np.asarray(mask[:6], dtype=bool))
    return int(random.choice(available.tolist())) if available.size else 6


def heuristic(obs, mask):
    if mask[6] and not mask[:6].any():
        return 6
    if not mask[:5].any():
        return 6  # explicit risk/abstain baseline
    if np.linalg.norm(obs[:2]-GOAL) < .02:
        return 5
    v = GOAL-obs[:2]
    behind = obs[:2]-.041*v/max(np.linalg.norm(v), 1e-8)
    return 0 if np.linalg.norm(obs[2:4]-behind) > .011 else 1
