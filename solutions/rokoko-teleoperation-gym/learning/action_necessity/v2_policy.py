"""Pure-Python nonlinear behavioral cloning + DAgger, no teacher at inference.

All labels derive from observable-state RouteTeacher during TRAINING only.
The final fitted policy is an ensemble of ExtraTrees-like randomized CART
classifiers with class-weighted Gini splits and categorical action votes.
Neither a reward-trained RL model nor physical safety qualification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import sqrt
from random import Random

from arena import ACTIONS, Arena, Observation, RouteTeacher, make_world
from imitation import features as v1_features


FIT_VERSION = "v2-prelock-20261114"
CLASS_COUNT = len(ACTIONS)
FEATURE_COUNT = 26
TEACHER_TRAIN_BASE = 123000
DAGGER_TRAIN_BASE = 123450
TEACHER_WORLDS = 450
DAGGER_WORLDS = 150
TREE_COUNT = 11
TREE_DEPTH = 9
SAMPLE_PER_TREE = 5400
MIN_LEAF = 22
FIT_SEED = 20261114


def features(o: Observation, initial_obstacle: float) -> tuple[float, ...]:
    """No true friction, seed, collision distance or obstacle phase is exposed."""
    core = v1_features(o, initial_obstacle)
    gap = o.goal_y-o.y
    return tuple(core + [
        abs(gap), abs(o.y), o.x * gap,
        o.x * initial_obstacle,
        (o.y-initial_obstacle) * float(o.moving_enabled),
        float(o.static_enabled and -.3 < o.static_x-o.x < .3),
        float(o.quality < .8 or o.age > 7),
    ])


@dataclass
class TreeNode:
    feature: int | None = None
    cut: float = 0.
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None
    scores: list[float] | None = None

    def predict(self, x: tuple[float, ...]) -> list[float]:
        node = self
        while node.feature is not None:
            node = node.left if x[node.feature] <= node.cut else node.right
        return node.scores

    def as_list(self):
        if self.feature is None:
            return ["L", [round(v, 8) for v in self.scores]]
        return [self.feature, round(self.cut, 10), self.left.as_list(), self.right.as_list()]


def _gini(counts: list[float]) -> float:
    total = sum(counts)
    return 1.-sum((v/total)**2 for v in counts) if total else 0.


def fit_tree(examples: list[tuple[tuple[float, ...], int]],
             indices: list[int], rng: Random, class_weights: list[float],
             depth: int = 0) -> TreeNode:
    totals = [0.]*CLASS_COUNT
    for idx in indices:
        totals[examples[idx][1]] += class_weights[examples[idx][1]]
    total = sum(totals)
    probs = [(n+.02)/(total+.02*CLASS_COUNT) for n in totals]
    if (depth >= TREE_DEPTH or len(indices) < 2*MIN_LEAF
            or sum(c > 0 for c in totals) <= 1):
        return TreeNode(scores=probs)
    impurity = _gini(totals)
    best_gain = 1e-7
    best = None
    # Randomized CART searches the same fixed feature vocabulary in every
    # tree. Threshold candidates are seeded training samples, not test data.
    for feat in rng.sample(range(FEATURE_COUNT), 9):
        for _ in range(2):
            cut = examples[indices[rng.randrange(len(indices))]][0][feat]
            lc = [0.]*CLASS_COUNT
            left_n = 0
            for idx in indices:
                x, label = examples[idx]
                if x[feat] <= cut:
                    left_n += 1
                    lc[label] += class_weights[label]
            if left_n < MIN_LEAF or len(indices)-left_n < MIN_LEAF:
                continue
            rc = [a-b for a,b in zip(totals,lc)]
            left_weight = sum(lc)
            gain = impurity - left_weight/total*_gini(lc) - (total-left_weight)/total*_gini(rc)
            if gain > best_gain:
                best_gain = gain
                best = (feat, cut)
    if best is None:
        return TreeNode(scores=probs)
    feat, cut = best
    left = [idx for idx in indices if examples[idx][0][feat] <= cut]
    right = [idx for idx in indices if examples[idx][0][feat] > cut]
    return TreeNode(feature=feat, cut=cut,
                    left=fit_tree(examples, left, rng, class_weights, depth+1),
                    right=fit_tree(examples, right, rng, class_weights, depth+1))


class FittedForest:
    def __init__(self, trees: list[TreeNode]):
        self.trees = trees
        self.first_obstacle = None

    def __call__(self, obs: Observation) -> int:
        if self.first_obstacle is None:
            self.first_obstacle = obs.moving_y
        x = features(obs, self.first_obstacle)
        totals = [0.]*CLASS_COUNT
        for tree in self.trees:
            for idx, score in enumerate(tree.predict(x)):
                totals[idx] += score
        return max(range(CLASS_COUNT), key=lambda i: (totals[i],-i))

    def snapshot(self) -> dict:
        return {"kind":"randomized_tree_ensemble_v2", "trees": [t.as_list() for t in self.trees]}

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.snapshot(),sort_keys=True,separators=(",",":")).encode()).hexdigest()


def fit_forest(examples: list[tuple[tuple[float, ...], int]], seed: int) -> FittedForest:
    if not examples:
        raise ValueError("training data empty")
    rng = Random(seed)
    counts = [0]*CLASS_COUNT
    for _x,label in examples:
        counts[label] += 1
    # Rare action labels are not discarded by majority FORWARD examples.
    nonzero = [count for count in counts if count]
    reference = sum(nonzero)/len(nonzero)
    weights = [max(.6, min(3., sqrt(reference/max(1,n)))) for n in counts]
    trees = []
    for _ in range(TREE_COUNT):
        picks = [rng.randrange(len(examples)) for _ in range(min(SAMPLE_PER_TREE,len(examples)))]
        trees.append(fit_tree(examples,picks,rng,weights))
    return FittedForest(trees)


def gather_training_worlds(base_seed: int, episodes: int, policy_factory=None):
    """DAgger labels only the rollout's observed states, never shield truth."""
    data = []
    stats = {"worlds":0,"examples":0,"expert_actions":[0]*CLASS_COUNT,
             "rollout_policy":"teacher" if policy_factory is None else "fitted_student"}
    for offset in range(episodes):
        world = make_world("dev",base_seed+offset)
        arena = Arena(world)
        oracle = RouteTeacher()
        student = policy_factory() if policy_factory else None
        first = arena.observe().moving_y
        while not arena.done:
            observation = arena.observe()
            label = oracle(observation)
            data.append((features(observation,first),label))
            stats["expert_actions"][label] += 1
            arena.step(student(observation) if student else label)
        stats["worlds"] += 1
    stats["examples"] = len(data)
    return data,stats


def fit_v2() -> tuple[FittedForest,dict]:
    demonstrations, teacher_stats = gather_training_worlds(TEACHER_TRAIN_BASE,TEACHER_WORLDS)
    first = fit_forest(demonstrations,FIT_SEED)
    dagger,dagger_stats = gather_training_worlds(DAGGER_TRAIN_BASE,DAGGER_WORLDS,
                                                 policy_factory=lambda:FittedForest(first.trees))
    final = fit_forest(demonstrations+dagger,FIT_SEED+1)
    return final,{"version":FIT_VERSION, "teacher":teacher_stats,"dagger":dagger_stats,
                  "train_seed_ranges":[[TEACHER_TRAIN_BASE,TEACHER_TRAIN_BASE+TEACHER_WORLDS-1],
                                       [DAGGER_TRAIN_BASE,DAGGER_TRAIN_BASE+DAGGER_WORLDS-1]],
                  "trees":TREE_COUNT,"max_depth":TREE_DEPTH,"min_leaf":MIN_LEAF,
                  "samples_per_tree":SAMPLE_PER_TREE,"fitted_weight_digest":final.digest(),
                  "labels":"observable-state RouteTeacher only; no true hidden world-state and no test/OOD exposure",
                  "optimizer":"deterministic bootstrap ExtraTrees-like CART + one DAgger round, no reinforcement-learning reward gradients"}
