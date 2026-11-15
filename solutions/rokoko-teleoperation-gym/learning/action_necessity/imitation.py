#!/usr/bin/env python3
"""A REAL fitted softmax policy trained only on synthetic teacher demonstrations.

This is supervised behavioral cloning, explicitly NOT reinforcement learning.
It cannot be used as evidence of original MuJoCo Double-DQN usefulness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from random import Random

from arena import (ACTIONS, Arena, Observation, RouteTeacher, SEEDS,
                   constant_forward, make_world, run_episode)
from run import paired_bootstrap, summarize


TRAIN_SEED_START = 121000  # disjoint from dev scoreboard 120000..120199
FEATURE_COUNT = 19


def features(o: Observation, initial_moving_y: float) -> list[float]:
    """Fixed observable features; neither true friction nor world seed enters."""
    goal_gap = o.goal_y-o.y
    is_center = float(o.static_enabled and abs(o.static_y) < .17)
    return [1., o.x, o.y, o.vx, o.vy, o.goal_y, goal_gap,
            float(o.static_enabled), is_center, o.static_y,
            float(o.moving_enabled), o.moving_y, initial_moving_y,
            min(o.age/8., 1.5), o.quality, float(o.deadman),
            float(o.x >= .33), float(o.x >= .64),
            goal_gap * float(o.x >= .33)]


class SoftmaxPolicy:
    def __init__(self, weights: list[list[float]]):
        if len(weights) != len(ACTIONS) or any(len(x) != FEATURE_COUNT for x in weights):
            raise ValueError("invalid fitted policy weights")
        self.weights = weights
        self.initial_moving_y = None

    def __call__(self, o: Observation) -> int:
        if self.initial_moving_y is None:
            self.initial_moving_y = o.moving_y
        x = features(o, self.initial_moving_y)
        scores = [sum(a*b for a, b in zip(row, x)) for row in self.weights]
        return max(range(len(scores)), key=lambda i: (scores[i], -i))


def collect_teacher_data(episodes: int) -> tuple[list[tuple[list[float], int]], dict]:
    if not 1 <= episodes <= 3000:
        raise ValueError("training episodes outside 1..3000")
    observations = []
    counts = [0]*len(ACTIONS)
    for i in range(episodes):
        w = make_world("dev", TRAIN_SEED_START+i)
        arena = Arena(w)
        teacher = RouteTeacher()
        first = arena.observe().moving_y
        while not arena.done:
            o = arena.observe()
            action = teacher(o)
            observations.append((features(o, first), action))
            counts[action] += 1
            arena.step(action)
    return observations, {name: c for name, c in zip(ACTIONS, counts)}


def fit(episodes: int = 700, epochs: int = 5, seed: int = 20261114):
    """Train multiclass linear softmax by SGD; no external model or API calls."""
    if not 1 <= epochs <= 20:
        raise ValueError("epochs outside 1..20")
    data, counts = collect_teacher_data(episodes)
    weights = [[0.]*FEATURE_COUNT for _ in ACTIONS]
    rng = Random(seed)
    order = list(range(len(data)))
    last_loss = float("nan")
    for epoch in range(epochs):
        rng.shuffle(order)
        lr = .085/(1.+.55*epoch)
        loss = 0.
        for i in order:
            x, label = data[i]
            z = [sum(a*b for a,b in zip(row,x)) for row in weights]
            high = max(z)
            exp = [math.exp(v-high) for v in z]
            denom = sum(exp)
            p = [v/denom for v in exp]
            loss -= math.log(max(p[label], 1e-12))
            for j, row in enumerate(weights):
                gradient = (p[j]-(j == label))*lr
                for k in range(FEATURE_COUNT):
                    row[k] -= gradient*x[k]
        last_loss = loss/len(data)
    return weights, {"train_worlds": episodes, "train_seed_range": [TRAIN_SEED_START,
                               TRAIN_SEED_START+episodes-1], "epochs": epochs,
                     "examples": len(data), "class_counts": counts,
                     "train_final_cross_entropy": round(last_loss, 5),
                     "initialization_seed": seed,
                     "method": "deterministic multiclass softmax SGD on RULE TEACHER labels, not RL"}


def evaluate_fit(weights: list[list[float]], split: str, episodes: int) -> dict:
    if split not in SEEDS or not 1 <= episodes <= 1000:
        raise ValueError("unknown split or episodes outside 1..1000")
    # Training seeds are 121000+, so declared dev scores 120000..199 and
    # all cal/test/OOD worlds are fresh even for supervised imitation.
    learned = []
    teacher = []
    constant = []
    for i in range(episodes):
        w = make_world(split, SEEDS[split]+i)
        learned.append(run_episode(w, "fitted_softmax_clone", lambda: SoftmaxPolicy(weights)))
        teacher.append(run_episode(w, "observable_rule_teacher", RouteTeacher))
        constant.append(run_episode(w, "shielded_constant_forward", lambda: constant_forward))
    vs_constant = paired_bootstrap(learned, constant)
    return {"split": split, "episodes": episodes,
            "learned": summarize(learned), "teacher": summarize(teacher),
            "constant": summarize(constant),
            "fitted_minus_constant": vs_constant,
            "fitted_minus_teacher": paired_bootstrap(learned, teacher),
            "model_better_than_null": (sum(x["success"] for x in learned) >
                                        sum(x["success"] for x in constant)),
            "learned_action_necessity_demo": (
                episodes >= 100
                and vs_constant["delta_pp"] >= 15
                and vs_constant["paired_bootstrap_95_pp"][0] > 0
                and sum(x["unsafe"] for x in learned) <= sum(x["unsafe"] for x in constant)),
            "rows": {"learned": learned, "teacher": teacher, "constant": constant}}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train-episodes", type=int, default=700)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--eval-split", choices=sorted(SEEDS), default="dev")
    p.add_argument("--eval-episodes", type=int, default=200)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise RuntimeError("output exists; refuse overwriting experimental receipt")
    if args.eval_split == "dev" and args.eval_episodes > 200:
        p.error("dev scoreboard uses reserved 120000..120199 only")
    weights, train = fit(args.train_episodes, args.epochs)
    outcome = evaluate_fit(weights, args.eval_split, args.eval_episodes)
    base = Path(__file__).resolve().parent
    contents = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                for f in sorted(base.glob("*.py"))}
    payload = {"schema": "junction.rokoko.action-necessity.behavior-clone.v1",
               "training": train, "validation": outcome,
               "weights": weights,
               "weights_sha256": hashlib.sha256(json.dumps(weights,separators=(",",":")).encode()).hexdigest(),
               "producer_sha256": contents,
               "environment": "SYNTHETIC_2D_KINEMATICS_NOT_MUJOCO",
               "limits": "Fitted supervised policy, no RL rewards/optimizer, no SDK, device, MuJoCo or safety certification."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True, indent=2)+"\n")
    print(json.dumps({k: v for k,v in payload.items() if k not in ("weights",)
                      and k != "validation"} | {"validation": {k:v for k,v in outcome.items() if k!="rows"}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
