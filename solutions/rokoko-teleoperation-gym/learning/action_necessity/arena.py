"""Deterministic *synthetic kinematic* action-necessity benchmark.

This is deliberately separate from the MuJoCo ContactEnv and its historic
receipts. It is not a physics, robot-safety, glove, or learning qualification.
The action shield receives true geometry; controllers only see delayed samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, sin
from random import Random
from typing import Callable


ACTIONS = ("FORWARD", "FORWARD_LEFT", "FORWARD_RIGHT", "LEFT", "RIGHT",
           "BRAKE", "REOBSERVE", "ABORT")
FWD, FWD_LEFT, FWD_RIGHT, LEFT, RIGHT, BRAKE, REOBSERVE, ABORT = range(8)
SEEDS = {"dev": 120000, "cal": 220000, "test": 320000, "ood": 420000}
MAX_STEPS = 90
DT = 0.14
ROBOT_RADIUS = 0.038
STATIC_RADIUS = 0.067
MOVING_RADIUS = 0.069
SAFETY_MARGIN = 0.012


@dataclass(frozen=True)
class World:
    seed: int
    split: str
    scenario: str
    friction: float
    drift: float
    goal_y: float
    static_x: float
    static_y: float
    static_enabled: bool
    moving_enabled: bool
    moving_phase: float
    moving_amplitude: float
    moving_speed: float
    sample_lag: int
    dropout_start: int
    dropout_length: int
    deadman_release: int


@dataclass(frozen=True)
class Sample:
    tick: int
    x: float
    y: float
    vx: float
    vy: float
    moving_y: float


@dataclass(frozen=True)
class Observation:
    x: float
    y: float
    vx: float
    vy: float
    moving_y: float
    goal_y: float
    static_x: float
    static_y: float
    static_enabled: bool
    moving_enabled: bool
    age: int
    quality: float
    deadman: bool
    tick: int


def make_world(split: str, seed: int) -> World:
    """World randomization is action/policy-independent and predeclared by split.

    'test' and 'ood' seed regions are reserved. Development should never query
    them while selecting an algorithm or changing its hyperparameters.
    """
    if split not in SEEDS or not SEEDS[split] <= seed < SEEDS[split] + 10000:
        raise ValueError("invalid split/seed; each split owns 10,000 distinct worlds")
    ood = split == "ood"
    r = Random(seed * 1610612741 + 107)
    scenario = r.choices(("clear", "side_blocked", "center_blocked", "crossing"),
                         weights=(20, 20, 35, 25) if not ood else (15, 20, 30, 35))[0]
    moving = scenario == "crossing" or scenario == "center_blocked" and r.random() < .45
    center = scenario == "center_blocked"
    side = scenario == "side_blocked"
    return World(seed=seed, split=split, scenario=scenario,
                 friction=r.uniform(.37 if ood else .70, 1.18 if ood else 1.04),
                 drift=r.uniform(-.020 if ood else -.006, .020 if ood else .006),
                 goal_y=r.uniform(-.14 if ood else -.09, .14 if ood else .09),
                 static_x=r.uniform(-.13, -.02),
                 static_y=r.uniform(-.05, .05) if center else r.choice((-1, 1)) * r.uniform(.26, .36),
                 static_enabled=center or side,
                 moving_enabled=moving,
                 moving_phase=r.uniform(-3.14, 3.14),
                 moving_amplitude=r.uniform(.17, .30 if ood else .22),
                 moving_speed=r.uniform(.23, .73 if ood else .45),
                 sample_lag=r.randint(2, 6 if ood else 4),
                 dropout_start=r.randint(14, 52),
                 dropout_length=r.choice((0, 0, 0, 3, 5, 8 if ood else 5)),
                 deadman_release=r.choice((33, -1, -1, -1, -1)) if ood else -1)


class Arena:
    """One non-actuating 2D kinematic rollout with independent sensor randomization."""

    def __init__(self, world: World):
        self.world = world
        self.tick = 0
        self.x, self.y = -.68, 0.0
        self.vx = self.vy = 0.0
        self.unsafe = self.aborted = self.success = False
        self.done = False
        self.refusals = self.holds = self.reobservations = self.dwell = 0
        self.min_clearance = float("inf")
        self.rng = Random(world.seed * 536870909 + 201)
        initial = Sample(0, self.x, self.y, 0., 0., self._moving_y(0))
        self.frames = [initial]
        self.seen = initial
        self.quality = 1.0

    def _moving_y(self, tick: int) -> float:
        w = self.world
        return w.moving_amplitude * sin(w.moving_phase + w.moving_speed * tick)

    def observe(self) -> Observation:
        w = self.world
        s = self.seen
        return Observation(x=s.x, y=s.y, vx=s.vx, vy=s.vy, moving_y=s.moving_y,
                           goal_y=w.goal_y, static_x=w.static_x, static_y=w.static_y,
                           static_enabled=w.static_enabled, moving_enabled=w.moving_enabled,
                           age=self.tick - s.tick, quality=self.quality,
                           deadman=w.deadman_release < 0 or self.tick < w.deadman_release,
                           tick=self.tick)

    def _clearance(self, x: float, y: float, at: float) -> float:
        w = self.world
        values = [min(x + .90, .90 - x, y + .44, .44 - y) - ROBOT_RADIUS]
        if w.static_enabled:
            values.append(hypot(x - w.static_x, y - w.static_y) - STATIC_RADIUS - ROBOT_RADIUS)
        if w.moving_enabled:
            values.append(hypot(x - .15, y - self._moving_y(at)) - MOVING_RADIUS - ROBOT_RADIUS)
        return min(values)

    def _fresh_sample(self, force: bool) -> None:
        w = self.world
        dropout = w.dropout_start <= self.tick < w.dropout_start + w.dropout_length
        if dropout:
            self.quality = .4
            return
        self.quality = 1.
        # Delayed readings are sampled from this world's own immutable history.
        # A REOBSERVE consumes an option to request a fresh frame when available.
        index = len(self.frames) - 1 if force else max(0, len(self.frames) - 1 - w.sample_lag)
        self.seen = self.frames[index]

    def step(self, action: int) -> Observation:
        if self.done:
            raise RuntimeError("episode already terminal")
        if type(action) is not int or action not in range(len(ACTIONS)):
            raise ValueError("invalid action")
        observed = self.observe()
        if action == ABORT:
            self.aborted = self.done = True
            return observed
        if action == REOBSERVE:
            self.reobservations += 1
        # Independent local shield refuses unsafe motions without routing through
        # controller confidence. Never call this a certified hardware interlock.
        healthy = observed.deadman and observed.quality >= .8 and observed.age <= 8
        if not healthy and action not in (BRAKE, REOBSERVE):
            self.refusals += 1
            self.holds += 1
            action = BRAKE
        acceleration = {
            FWD: (1.8, 0.), FWD_LEFT: (1.15, 1.8), FWD_RIGHT: (1.15, -1.8),
            LEFT: (0., 1.8), RIGHT: (0., -1.8), BRAKE: (0., 0.),
            REOBSERVE: (0., 0.),
        }[action]
        w = self.world
        # Unobserved friction and drift change halfway through the episode.
        traction = w.friction * (.74 if self.tick >= 34 else 1.)
        vx = max(-.36, min(.36, .68*self.vx + acceleration[0]*DT*traction))
        vy = max(-.36, min(.36, .68*self.vy + acceleration[1]*DT*traction + w.drift))
        if action in (BRAKE, REOBSERVE):
            vx *= .37
            vy *= .37
        nx, ny = self.x + vx*DT, self.y + vy*DT
        clearance = min(self._clearance(self.x+(nx-self.x)*f,
                                        self.y+(ny-self.y)*f, self.tick+f)
                        for f in (0., .25, .5, .75, 1.))
        if clearance < SAFETY_MARGIN:
            # Refuse before actuation. The moving obstacle can still approach a
            # stationary robot: a fresh safety check follows every option.
            self.refusals += 1
            self.holds += 1
            vx = vy = 0.
            nx, ny = self.x, self.y
        self.x, self.y, self.vx, self.vy = nx, ny, vx, vy
        self.tick += 1
        self.min_clearance = min(self.min_clearance, self._clearance(nx, ny, self.tick))
        self.unsafe = self.min_clearance < 0
        self.frames.append(Sample(self.tick, nx, ny, vx, vy, self._moving_y(self.tick)))
        self._fresh_sample(force=action == REOBSERVE)
        self.dwell = self.dwell+1 if .65 <= nx <= .82 and abs(ny - w.goal_y) <= .11 else 0
        self.success = self.dwell >= 2 and not self.unsafe
        self.done = self.success or self.unsafe or self.tick >= MAX_STEPS
        return self.observe()

    def receipt(self, policy: str) -> dict:
        return dict(seed=self.world.seed, split=self.world.split,
                    scenario=self.world.scenario, policy=policy,
                    success=self.success, unsafe=self.unsafe, aborted=self.aborted,
                    complete=self.done, options=self.tick, refusals=self.refusals,
                    holds=self.holds, reobservations=self.reobservations,
                    min_clearance=round(self.min_clearance, 5))


class RouteTeacher:
    """Observable-state, rule-based counterfactual teacher, NOT an RL policy."""

    def __init__(self):
        self.lane = None

    def __call__(self, o: Observation) -> int:
        if not o.deadman:
            return ABORT  # external deadman release cannot be overridden
        if o.quality < .8 or o.age > 7:
            return REOBSERVE
        if self.lane is None:
            avoid_center = o.static_enabled and abs(o.static_y) < .17
            if avoid_center or o.moving_enabled:
                # The opposite side of the latest moving-obstacle observation.
                self.lane = -.33 if o.moving_y >= 0 else .33
            else:
                self.lane = o.goal_y
        desired_y = self.lane if o.x < .33 else o.goal_y
        # Velocity compensation uses only observed velocity, never true friction.
        lateral_error = desired_y - o.y - .18*o.vy
        if o.x > .64:
            if abs(lateral_error) > .065:
                return LEFT if lateral_error > 0 else RIGHT
            return BRAKE if o.vx > .24 else FWD
        if abs(lateral_error) > .065:
            return FWD_LEFT if lateral_error > 0 else FWD_RIGHT
        return FWD


def constant_forward(_obs: Observation) -> int:
    """Pre-registered shielded always-FORWARD null; shield is identical."""
    return FWD


def run_episode(world: World, policy_name: str,
                policy_factory: Callable[[], Callable[[Observation], int]]) -> dict:
    arena = Arena(world)
    policy = policy_factory()
    while not arena.done:
        arena.step(policy(arena.observe()))
    return arena.receipt(policy_name)
