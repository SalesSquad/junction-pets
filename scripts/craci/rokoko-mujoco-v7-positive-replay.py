#!/usr/bin/env python3
"""Independently replay positive v7 MuJoCo action traces on source-pinned physics.

This forensic verifier only replays *TRAIN* seeds already tried by the
feasibility experiment; no training labels/weights and no dev/cal/test/OOD.
The producer's success/contact flags are not sufficient proof on their own.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def near(a, b, tol=1e-5):
    return len(a) == len(b) and all(
        math.isfinite(float(x)) and math.isfinite(float(y)) and
        abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def positive_candidate(row):
    return (row["observed_corridor"] and
            (row["success"] or row["lateral_displacement"] >= .025))


def replay_positive(evidence_dir: Path, env_factory, policy_factory):
    with (evidence_dir / "training.json").open(encoding="utf8") as f:
        training = json.load(f)
    selected = {
        (row["seed"], row["strategy"]): row for row in training["trials"]
        if positive_candidate(row)
    }
    visited = set()
    verified_success = set()
    verified_displacement = set()
    env = env_factory()
    with gzip.open(evidence_dir / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as source:
        for line in source:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            if key not in selected:
                continue
            require(key not in visited, "DUPLICATE_POSITIVE_REPLAY_TRACE")
            row = selected[key]
            observation = env.reset(seed=doc["seed"], ood=False)
            controller = policy_factory(doc["strategy"])()
            initial_observation = list(map(float, observation))
            require(near(initial_observation[0:18],
                         doc["transitions"][0]["observation"]),
                    "PINNED_MUJOCO_REPLAY_INITIAL_OBSERVATION_MISMATCH")
            peak_dwell = 0
            last_info = None
            for idx, event in enumerate(doc["transitions"]):
                require(near(observation, event["observation"]),
                        "PINNED_MUJOCO_REPLAY_OBSERVATION_DRIFT")
                actual_mask = env.mask(observation)
                require([int(x) for x in actual_mask] == [int(x) for x in event["mask"]],
                        "PINNED_MUJOCO_REPLAY_SEVEN_ACTION_MASK_MISMATCH")
                action = event["action"]
                require(0 <= action < 7 and bool(actual_mask[action]),
                        "PINNED_MUJOCO_REPLAY_BYPASSED_SHIELD")
                # Replay must verify that the claimed source-frozen *policy*
                # actually generated this action, not just that some oracle
                # could force a feasible sequence through the physics.
                proposal = controller(observation.copy(), actual_mask.copy())
                require(type(proposal) is int and proposal == action,
                        "PINNED_POLICY_PROPOSAL_SEQUENCE_MISMATCH")
                observation, reward, done, info = env.step(action)
                peak_dwell = max(peak_dwell, int(env.dwell))
                require(near(observation, event["next_observation"]),
                        "PINNED_MUJOCO_REPLAY_NEXT_OBSERVATION_MISMATCH")
                require(abs(float(reward) - float(event["reward"])) <= 1e-5 and
                        bool(done) == event["done"] and
                        int(info["cost"]) == event["cost"],
                        "PINNED_MUJOCO_REPLAY_REWARD_COST_TERMINAL_MISMATCH")
                require(int(info["contacts"]) == event["contacts_cumulative"] and
                        bool(info["success"]) == event["success_info"] and
                        peak_dwell == event["dwell_ticks_cumulative"],
                        "PINNED_MUJOCO_REPLAY_CONTACT_DWELL_SUCCESS_MISMATCH")
                if "dwell_ticks_current" in event:
                    require(int(env.dwell) == event["dwell_ticks_current"],
                            "PINNED_MUJOCO_REPLAY_RESETTABLE_DWELL_MISMATCH")
                last_info = info
                require(not done or idx == len(doc["transitions"]) - 1,
                        "PINNED_MUJOCO_REPLAY_PROPOSED_ACTION_AFTER_TERMINATION")
            require(last_info is not None and bool(env.done) and
                    int(env.steps) == row["option_steps"] and
                    int(env.physics_steps) == row["physics_steps"] and
                    int(last_info["contacts"]) == row["contacts"] and
                    bool(last_info["success"]) == row["success"] and
                    bool(last_info["unsafe"]) == row["unsafe"] and
                    bool(last_info["abstained"]) == row["abstained"] and
                    abs(float(last_info["error"]) - row["final_error"]) < 1e-5,
                    "PINNED_MUJOCO_REPLAY_TERMINAL_PHYSICS_DIVERGENCE")
            away_sign = (-1. if initial_observation[7] >= initial_observation[1]
                         else 1.)
            actual_away = (float(observation[1]) -
                           initial_observation[1]) * away_sign
            require(abs(actual_away - row["lateral_displacement"]) < 1e-5,
                    "PINNED_MUJOCO_REPLAY_OBSTACLE_AWAY_PROGRESS_FORGERY")
            visited.add(key)
            if last_info["success"] and not last_info["unsafe"]:
                verified_success.add(doc["seed"])
            if actual_away >= .025 and not last_info["unsafe"]:
                verified_displacement.add(doc["seed"])
    require(visited == set(selected), "INCOMPLETE_POSITIVE_MECHANISM_PHYSICS_REPLAY")
    keys = sorted((seed, name) for seed, name in visited)
    key_sha = hashlib.sha256(json.dumps(keys, sort_keys=True,
                              separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "junction.rokoko.mujoco-v7-positive-replay.v1",
        "fully_replayed_positive_train_trials": len(visited),
        "verified_near_corridor_success_worlds": len(verified_success),
        "verified_obstacle_away_displacement_worlds": len(verified_displacement),
        "positive_trial_keys_sha256": key_sha,
        "claim_verified": True,
        "model_promotion_authorized": False,
        "no_dev_cal_test_ood": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--physics-dir", type=Path, required=True)
    parser.add_argument("--product-run", type=Path, required=True)
    a = parser.parse_args()
    sys.path.insert(0, str(a.physics_dir.resolve()))
    import mujoco
    require(mujoco.__version__ == "3.3.7", "PINNED_MUJOCO_VERSION_MISMATCH")
    from physics import MovingContactEnv
    product_path = a.product_run.resolve()
    require(product_path.is_file(), "FROZEN_PRODUCT_POLICY_SOURCE_MISSING")
    spec = importlib.util.spec_from_file_location("v7_frozen_replay_product", product_path)
    require(spec is not None and spec.loader is not None,
            "FROZEN_PRODUCT_POLICY_IMPORT_UNAVAILABLE")
    product = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(product)
    result = replay_positive(a.evidence_dir.resolve(),
                             lambda: MovingContactEnv(max_options=60),
                             product.policy_factory)
    outfile = a.evidence_dir / "independent-positive-replay.json"
    with outfile.open("x", encoding="utf8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
