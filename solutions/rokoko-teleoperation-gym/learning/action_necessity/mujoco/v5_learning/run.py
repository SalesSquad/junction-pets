#!/usr/bin/env python3
"""Bounded actual MuJoCo reward/cost learning, then fresh same-world dev test.

The task is intentionally one manual, reproducible training experiment: two
small evolutionary updates learn four policy parameters on TRAIN-ONLY seeds.
The resulting frozen candidate is evaluated only afterward, without tuning
on any dev/cal/test/OOD outcome. A scientific red exits 2 *after* receipts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MUJOCO_DIR = HERE.parent
V4 = MUJOCO_DIR / "v4"
for directory in (str(V4), str(MUJOCO_DIR)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

spec = importlib.util.spec_from_file_location("rokoko_frozen_v4_science", V4 / "run.py")
if spec is None or spec.loader is None:
    raise ImportError("FROZEN_MUJOCO_V4_RUNNER_MISSING")
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
from policy import BOUNDS, DEFAULT, PARAMETERS, make_factory, validate_weights  # noqa: E402


SCHEMA = "junction.rokoko.mujoco-v5.reward-cost-learning.v1"
TRAIN_FIRST_SEED = 510_000          # Valid frozen ContactEnv range < 520000
TRAIN_LAST_SEED = 510_999           # Train-only namespace, never a holdout
DEV_FIRST_SEED = 129_170           # Fresh, not v4 exposed dev129030..169
DEV_LAST_SEED = 129_319            # Reserved for this single candidate cohort
NEXT_TRAIN_SEED = 511_000          # Only future train, not validation/test
V4_SOURCE_SHA = "5be248192d6eb09d54068d5509784644d763006f"
FROZEN_ENV_MIN_SEED = 120_000
FROZEN_ENV_MAX_SEED_EXCLUSIVE = 520_000
MAX_OPTIONS = 60
SHA = "0123456789abcdef"
MAX_TRAIN_EPISODES = 64
MAX_DEV_EPISODES = 150
RNG_SEED = 20261114


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def source_identity(require_git, expected_head):
    if not require_git or not expected_head or len(expected_head) != 40 or any(
            c not in SHA for c in expected_head):
        raise PermissionError("EXACT_CLEAN_GIT_HEAD_REQUIRED")
    root = subprocess.check_output(
        ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"],
        text=True, timeout=15).strip()
    head = subprocess.check_output(
        ["git", "-C", root, "rev-parse", "HEAD"],
        text=True, timeout=15).strip()
    if head != expected_head:
        raise ValueError("EXECUTED_HEAD_MISMATCH")
    dirty = subprocess.check_output(
        ["git", "-C", root, "status", "--porcelain=v1", "--untracked-files=no"],
        text=True, timeout=15).strip()
    if dirty:
        raise ValueError("TRACKED_SOURCE_OVERLAY_REFUSED")
    if subprocess.run(
        ["git", "-C", root, "merge-base", "--is-ancestor",
         V4_SOURCE_SHA, head], capture_output=True, timeout=15).returncode:
        raise ValueError("IMMUTABLE_V4_SOURCE_ANCESTOR_MISSING")
    return head


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=("train-dev",))
    p.add_argument("--require-git", action="store_true")
    p.add_argument("--expected-head", required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--train-episodes", type=int, default=48)
    p.add_argument("--dev-episodes", type=int, default=80)
    p.add_argument("--time-budget-seconds", type=int, default=1200)
    return p.parse_args(argv)


def validate_args(args):
    # Source-invariant check: ContactEnv.reset in frozen learning/env.py
    # rejects any seed outside [120000, 520000). Do not modify that env to
    # accommodate training; use a disjoint *valid* seed reservation instead.
    if not (FROZEN_ENV_MIN_SEED <= TRAIN_FIRST_SEED <= TRAIN_LAST_SEED
            < FROZEN_ENV_MAX_SEED_EXCLUSIVE
            and FROZEN_ENV_MIN_SEED <= NEXT_TRAIN_SEED
            and NEXT_TRAIN_SEED + 999 < FROZEN_ENV_MAX_SEED_EXCLUSIVE):
        raise ValueError("TRAIN_SEEDS_OUTSIDE_FROZEN_ENV_DOMAIN")
    if not 1 <= args.train_episodes <= MAX_TRAIN_EPISODES:
        raise ValueError("TRAIN_COUNT_OUT_OF_BOUNDS")
    if not 1 <= args.dev_episodes <= MAX_DEV_EPISODES:
        raise ValueError("DEV_COUNT_OUT_OF_BOUNDS")
    if TRAIN_FIRST_SEED + args.train_episodes - 1 > TRAIN_LAST_SEED:
        raise ValueError("TRAIN_EXCEEDS_RESERVED_RANGE")
    if DEV_FIRST_SEED + args.dev_episodes - 1 > DEV_LAST_SEED:
        raise ValueError("DEV_EXCEEDS_RESERVED_RANGE")
    if not 60 <= args.time_budget_seconds <= 1380:
        raise ValueError("TIME_BUDGET_OUT_OF_BOUNDS")
    if set(range(TRAIN_FIRST_SEED, TRAIN_FIRST_SEED + args.train_episodes)) & set(
            range(DEV_FIRST_SEED, DEV_FIRST_SEED + args.dev_episodes)):
        raise ValueError("TRAIN_VALIDATION_SEED_OVERLAP")


def output_root(path):
    if path.is_symlink():
        raise ValueError("OUTPUT_SYMLINK_REFUSED")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(path.iterdir()):
        raise FileExistsError("OUTPUT_DIRECTORY_MUST_BE_EMPTY")
    return path


def write_new(path, obj):
    with path.open("x", encoding="utf-8") as file:
        json.dump(obj, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")


def training_episode(env, seed, weights):
    """Only observations/masks/actions/reward/cost go into learning data."""
    from env import ACTIONS
    import numpy as np

    policy = make_factory(weights)()
    observation = env.reset(seed=seed, ood=False)
    world_hash = v4.v3.v2.v1._world_signature(env)
    transitions = []
    outcome = None
    for option in range(MAX_OPTIONS):
        allowed = env.mask(observation)
        proposal = policy(observation.copy(), allowed.copy())
        if type(proposal) is not int or not 0 <= proposal < 7:
            raise ValueError("TRAIN_POLICY_OUTSIDE_SEVEN_OPTION_ABI")
        # The independent environment shield (not the learned policy) remains
        # authoritative. A veto/refusal is evidence; never override its mask.
        was_allowed = bool(allowed[proposal])
        if not was_allowed:
            raise ValueError("TRAIN_POLICY_PROPOSED_MASKED_ACTION")
        previous = np.asarray(observation, dtype=float).tolist()
        observed_mask = np.asarray(allowed, dtype=bool).astype(int).tolist()
        next_observation, reward, done, outcome = env.step(proposal)
        transitions.append(dict(
            observation=previous, mask=observed_mask, action=int(proposal),
            action_name=ACTIONS[proposal], reward=float(reward),
            cost=int(outcome["cost"]), done=bool(done),
            next_observation=np.asarray(next_observation, dtype=float).tolist(),
        ))
        observation = next_observation
        if done:
            break
    if not transitions or outcome is None:
        raise AssertionError("TRAIN_WORLD_HAS_NO_ACTUAL_OPTION_TRANSITIONS")
    if int(env.physics_steps) == 0 and not (
        env.abstained and env.steps == 1 and transitions[0]["action"] == 6
        and not env.unsafe and not outcome["success"]
    ):
        raise AssertionError("UNACCOUNTED_ZERO_PHYSICS_TRAIN_WORLD")
    return dict(seed=seed, world_hash=world_hash, transitions=transitions,
                success=bool(outcome["success"]), unsafe=bool(outcome["unsafe"]),
                abstained=bool(outcome["abstained"]),
                zero_physics_abstain=int(env.physics_steps) == 0,
                physics_steps=int(env.physics_steps), option_steps=int(env.steps),
                total_reward=round(sum(t["reward"] for t in transitions), 8),
                final_error=float(outcome["error"]))


def score_training(rows):
    successes = sum(int(r["success"]) for r in rows)
    unsafe = sum(int(r["unsafe"]) for r in rows)
    abstained = sum(int(r["abstained"]) for r in rows)
    rewards = sum(r["total_reward"] for r in rows)
    # Actual observed simulator returns, not hand-labelled demonstrations.
    # Explicit safety constraint dominates any apparent reward gain.
    objective = round(100 * successes - 1000 * unsafe - 4 * abstained + rewards, 6)
    return dict(objective=objective, success=successes, unsafe=unsafe,
                abstained=abstained, total_reward=round(rewards, 6))


def perturb(center, rng, radius):
    candidate = {}
    for name in PARAMETERS:
        low, high = BOUNDS[name]
        value = center[name] + rng.uniform(-1., 1.) * (high - low) * radius
        candidate[name] = round(min(high, max(low, value)), 7)
    return validate_weights(candidate)


def learn(env, train_episodes, deadline):
    """Two genuine return-driven policy-search generations, no validation data."""
    rng = random.Random(RNG_SEED)
    seeds = list(range(TRAIN_FIRST_SEED, TRAIN_FIRST_SEED + train_episodes))
    experiments = []
    all_rollouts = []
    elite = DEFAULT
    best = None
    for generation in (0, 1):
        candidates = ([DEFAULT, perturb(DEFAULT, rng, .38), perturb(DEFAULT, rng, .38)]
                      if generation == 0 else
                      [elite, perturb(elite, rng, .19), perturb(elite, rng, .19)])
        for candidate_no, weights in enumerate(candidates):
            results = []
            for seed in seeds:
                if time.monotonic() >= deadline:
                    raise TimeoutError("TRAINING_TIME_CEILING_REACHED_BEFORE_COMPLETE_EXPERIMENT")
                episode = training_episode(env, seed, weights)
                results.append(episode)
                all_rollouts.append({"generation": generation, "candidate": candidate_no, **episode})
            score = score_training(results)
            entry = dict(generation=generation, candidate=candidate_no,
                         weights=weights, **score)
            experiments.append(entry)
            rank = (score["objective"], -score["unsafe"], score["success"],
                    -generation, -candidate_no)
            if best is None or rank > best[0]:
                best = (rank, entry)
        elite = max((x for x in experiments if x["generation"] == generation),
                    key=lambda x: (x["objective"], -x["unsafe"], x["success"]))["weights"]
    assert best is not None
    return dict(weights=best[1]["weights"], winner=best[1],
                experiments=experiments, rollouts=all_rollouts, seeds=seeds)


def taxonomy_and_curriculum(rollouts):
    """Training-only failure observations propose a future *train* cohort."""
    tags = Counter()
    for record in rollouts:
        if record["success"]:
            tags["success"] += 1
        elif record["unsafe"]:
            tags["unsafe_collision_or_bounds"] += 1
        elif record["abstained"]:
            tags["explicit_safe_abstain"] += 1
        elif all(t["reward"] <= 0 for t in record["transitions"]):
            tags["nonprogress_or_stall"] += 1
        else:
            tags["timeout_or_unresolved_goal"] += 1
    failures = [(key, value) for key, value in tags.items() if key != "success"]
    failures.sort(key=lambda item: (-item[1], item[0]))
    return dict(failure_taxonomy=dict(sorted(tags.items())),
                curriculum_next=dict(
                    proposal_only=True, automatic_rerun=False,
                    source="training episodes only; no validation outcome used",
                    next_train_first_seed=NEXT_TRAIN_SEED,
                    next_train_last_seed=NEXT_TRAIN_SEED + 999,
                    focus_failure=failures[0][0] if failures else "new_train_variation",
                    reason="highest-frequency failed training outcome; review before new job"))


def paired_dev(env, weights, dev_episodes, deadline):
    controllers = {
        "constant": lambda: v4.v3.v2.v1.constant,
        "safe_v4": v4.make_controller,
        "learned_v5": make_factory(weights),
    }
    rows = []
    for seed in range(DEV_FIRST_SEED, DEV_FIRST_SEED + dev_episodes):
        if time.monotonic() >= deadline:
            raise TimeoutError("DEV_TIME_CEILING_REACHED_BEFORE_COMPLETE_PAIRING")
        observed = {}
        for name, factory in controllers.items():
            # Frozen v4 specifically allows an exact first-option safe ABSTAIN
            # through its `safe_v4` label. Reuse unchanged validation for the
            # candidate, then truthfully relabel the model in this receipt.
            shim = "safe_v4" if name == "learned_v5" else name
            episode = v4.episode_with_explicit_safe_abort(
                env, seed, False, shim, factory)
            episode["policy"] = name
            if episode["zero_physics_abstain"]:
                if not (name != "constant" and episode["physics_steps"] == 0
                        and episode["option_steps"] == 1 and episode["abstained"]
                        and not episode["success"] and not episode["unsafe"]
                        and episode["proposal_counts"] == {"ABSTAIN": 1}):
                    raise AssertionError("INVALID_ZERO_STEP_REFUSAL")
            elif episode["physics_steps"] <= 0:
                raise AssertionError("NONABSTAINED_EPISODE_MISSING_MJ_STEPS")
            observed[name] = episode
        if len({r["world_hash"] for r in observed.values()}) != 1:
            raise AssertionError("POLICY_ARMS_NOT_ON_IDENTICAL_WORLD")
        rows.append(observed)
    return rows


def scientific_gate(paired, summaries):
    primary = v4.v3.v2.qualification(summaries["learned_v5"])
    unsafe_v4 = sum(int(entry["safe_v4"]["unsafe"]) for entry in paired)
    # Keep the original unchanged v2 significance/safety gate, and make the
    # comparison to safe-v4 stricter where the heuristic is already safe.
    actual = dict(primary)
    actual["unsafe_v4"] = unsafe_v4
    actual["no_unsafe_regression_vs_v4"] = summaries["learned_v5"]["candidate_unsafe"] <= unsafe_v4
    actual["scientifically_qualifies"] = bool(
        primary["scientifically_qualifies"] and actual["no_unsafe_regression_vs_v4"])
    return actual


def main(argv=None):
    args = parse_args(argv)
    validate_args(args)
    head = source_identity(args.require_git, args.expected_head)
    try:
        import mujoco
        import numpy as np
        from physics import MovingContactEnv
    except ImportError as exc:
        raise RuntimeError("ACTUAL_MUJOCO_3_3_7_CPU_REQUIRED") from exc
    if mujoco.__version__ != "3.3.7":
        raise RuntimeError(f"MUJOCO_VERSION_PIN_MISMATCH_{mujoco.__version__}")
    output = output_root(args.output_dir)
    deadline = time.monotonic() + args.time_budget_seconds
    env = MovingContactEnv(max_options=MAX_OPTIONS)
    learning = learn(env, args.train_episodes, deadline)
    weights = validate_weights(learning["weights"])
    dataset = learning["rollouts"]
    dataset_hash = digest(dataset)
    weights_hash = digest(weights)
    taxonomy = taxonomy_and_curriculum(dataset)
    model = dict(schema=SCHEMA + ".model", algorithm="bounded_two_generation_reward_cost_search",
                 executed_head=head, weights=weights, weights_sha256=weights_hash,
                 dataset_sha256=dataset_hash, trained_worlds_only=True,
                 no_privileged_inference=True, no_auto_promotion=True)
    training = dict(schema=SCHEMA + ".training", executed_head=head,
                    actual_physics_engine=f"mujoco-{mujoco.__version__}",
                    numpy_version=np.__version__,
                    train_first_seed=TRAIN_FIRST_SEED, train_episodes=args.train_episodes,
                    seeds=learning["seeds"], all_training_seeds_train_only=True,
                    actual_transition_count=sum(len(row["transitions"]) for row in dataset),
                    weights_sha256=weights_hash, dataset_sha256=dataset_hash,
                    selected=learning["winner"], experiments=learning["experiments"],
                    rollouts=dataset, **taxonomy)
    # Persist all real training observations BEFORE opening any dev world.
    # A later dev failure cannot erase the learned model or its data.
    write_new(output / "training.json", training)
    write_new(output / "model.json", model)
    paired = paired_dev(env, weights, args.dev_episodes, deadline)
    summaries = {name: v4.v3.v2.v1.summarize(paired, name)
                 for name in ("safe_v4", "learned_v5")}
    gate = scientific_gate(paired, summaries)
    dev = dict(schema=SCHEMA + ".dev", executed_head=head,
               actual_physics_engine=f"mujoco-{mujoco.__version__}", split="dev",
               first_seed=DEV_FIRST_SEED, episodes=args.dev_episodes,
               train_first_seed=TRAIN_FIRST_SEED,
               train_episodes=args.train_episodes,
               weights_sha256=weights_hash, dataset_sha256=dataset_hash,
               paired_worlds=paired, summaries=summaries,
               qualification=gate,
               evidence_scope="simulator-only; not physical robot certification",
               untouched_frozen_negative_runs=[43627944236,43628857595,43630195101,
                                               43630816368,43632630658],
               forbidden_tuning="no learning after observing dev/cal/test/OOD",
               cal_test_ood_sealed=True)
    write_new(output / "dev.json", dev)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (output / "training.json", output / "model.json", output / "dev.json")}
    write_new(output / "manifest.json", dict(schema=SCHEMA + ".manifest",
                                               executed_head=head,
                                               file_sha256=files,
                                               source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                                              for p in (HERE / "run.py", HERE / "policy.py")},
                                               no_provider_billing_assertion=True,
                                               generated_at=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(schema=SCHEMA, executed_head=head,
                          actual_transition_count=training["actual_transition_count"],
                          dataset_sha256=dataset_hash, weights_sha256=weights_hash,
                          summary=summaries["learned_v5"], science=gate,
                          receipts=str(output)), sort_keys=True))
    if not gate["scientifically_qualifies"]:
        print("MUJOCO_V5_SCIENCE_RED — all actual receipts retained; no promotion",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
