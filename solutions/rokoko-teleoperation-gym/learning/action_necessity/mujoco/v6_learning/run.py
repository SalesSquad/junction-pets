#!/usr/bin/env python3
"""Actual reward/cost training of a stateful guarded MuJoCo corridor policy.

WorkID J26-CRACI-V6-CORRIDOR-20261114. No calibration/test/OOD access.
Frozen v5 negative physics receipt remains immutable. Train on 511000+ only,
freeze a novel contact-macro policy, then test once on fresh dev129250..329.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MUJOCO_DIR = HERE.parent
V5 = MUJOCO_DIR / "v5_learning"
V5_SHA = "4987f28540c5319deaa81dff5d700dcac9eab483"
for directory in (str(V5), str(MUJOCO_DIR)):
    if directory not in sys.path:
        sys.path.insert(0, directory)
spec = importlib.util.spec_from_file_location("rokoko_frozen_v5_learning", V5 / "run.py")
if spec is None or spec.loader is None:
    raise ImportError("FROZEN_V5_RUNNER_MISSING")
v5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v5)

from corridor_policy import (BOUNDS, DEFAULT, INTEGERS,
                             V5_FROZEN_WEIGHTS, V5_FROZEN_WEIGHTS_SHA256,
                             make_factory, validate_weights)  # noqa: E402

SCHEMA = "junction.rokoko.mujoco-v6.contact-corridor-learning.v1"
TRAIN_FIRST_SEED = 511_000
TRAIN_LAST_SEED = 511_999
DEV_FIRST_SEED = 129_250
DEV_LAST_SEED = 129_329
NEXT_TRAIN_SEED = 512_000
FROZEN_ENV_MIN_SEED = 120_000
FROZEN_ENV_MAX_SEED_EXCLUSIVE = 520_000
MAX_OPTIONS = 60
MAX_TRAIN_EPISODES = 64
MAX_DEV_EPISODES = 80
RNG_SEED = 20261114


def digest(obj):
    return v5.digest(obj)


def source_identity(require_git, expected_head):
    if not require_git or not expected_head or len(expected_head) != 40 or any(
            c not in "0123456789abcdef" for c in expected_head):
        raise PermissionError("EXACT_CLEAN_GIT_SHA_REQUIRED")
    root = subprocess.check_output(
        ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"],
        text=True, timeout=15).strip()
    observed = subprocess.check_output(
        ["git", "-C", root, "rev-parse", "HEAD"],
        text=True, timeout=15).strip()
    if observed != expected_head:
        raise RuntimeError("V6_EXECUTED_GIT_HEAD_MISMATCH")
    dirty = subprocess.check_output(
        ["git", "-C", root, "status", "--porcelain=v1", "--untracked-files=no"],
        text=True, timeout=15).strip()
    if dirty:
        raise RuntimeError("V6_TRACKED_SOURCE_OVERLAY_REFUSED")
    if subprocess.run(
        ["git", "-C", root, "merge-base", "--is-ancestor", V5_SHA, observed],
        capture_output=True, timeout=15).returncode:
        raise RuntimeError("V6_NOT_DESCENDED_FROM_IMMUTABLE_V5_NEGATIVE")
    return observed


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
    if not 1 <= args.train_episodes <= MAX_TRAIN_EPISODES:
        raise ValueError("TRAIN_EPISODES_OUT_OF_BOUNDS")
    if not 1 <= args.dev_episodes <= MAX_DEV_EPISODES:
        raise ValueError("DEV_EPISODES_OUT_OF_BOUNDS")
    if not 60 <= args.time_budget_seconds <= 1380:
        raise ValueError("TIME_BUDGET_OUT_OF_BOUNDS")
    if not (FROZEN_ENV_MIN_SEED <= TRAIN_FIRST_SEED <= TRAIN_LAST_SEED <
            FROZEN_ENV_MAX_SEED_EXCLUSIVE and
            FROZEN_ENV_MIN_SEED <= NEXT_TRAIN_SEED and
            NEXT_TRAIN_SEED + 999 < FROZEN_ENV_MAX_SEED_EXCLUSIVE):
        raise ValueError("FROZEN_CONTACT_ENV_TRAIN_SEED_DOMAIN_BREACH")
    if TRAIN_FIRST_SEED + args.train_episodes - 1 > TRAIN_LAST_SEED:
        raise ValueError("TRAIN_RESERVATION_EXCEEDED")
    if DEV_FIRST_SEED + args.dev_episodes - 1 > DEV_LAST_SEED:
        raise ValueError("FRESH_DEV_RESERVATION_EXCEEDED")
    if not (TRAIN_FIRST_SEED > v5.v4.v3.v2.v1.SEED_BANDS["ood"][1] and
            DEV_FIRST_SEED > 129249 and DEV_LAST_SEED <= 129999):
        raise ValueError("FROZEN_PHYSICS_SEED_OVERLAP")


def training_episode(env, seed, weights):
    """Real 18D/7mask reward and cost; all data are train-only evidence."""
    from env import ACTIONS
    import numpy as np
    controller = make_factory(weights)()
    observation = env.reset(seed=seed, ood=False)
    world_hash = v5.v4.v3.v2.v1._world_signature(env)
    transitions = []
    result = None
    for _ in range(MAX_OPTIONS):
        allowed = env.mask(observation)
        action = controller(observation.copy(), allowed.copy())
        if type(action) is not int or not 0 <= action < 7 or not allowed[action]:
            raise RuntimeError("V6_ACTION_BYPASSED_SEVEN_OPTION_SHIELD")
        before = np.asarray(observation, dtype=float).tolist()
        mask = np.asarray(allowed, dtype=bool).astype(int).tolist()
        observation, reward, done, result = env.step(action)
        transitions.append(dict(
            observation=before, mask=mask, action=int(action),
            action_name=ACTIONS[action], reward=float(reward),
            cost=int(result["cost"]), done=bool(done),
            next_observation=np.asarray(observation, dtype=float).tolist(),
            phase=controller.phase,
        ))
        if done:
            break
    if not transitions or result is None:
        raise AssertionError("NO_REAL_OPTION_TRANSITIONS")
    zero_abort = int(env.physics_steps) == 0
    if zero_abort and not (len(transitions) == 1 and transitions[0]["action"] == 6
                           and env.abstained and not env.unsafe
                           and not result["success"]):
        raise AssertionError("UNACCOUNTED_ZERO_PHYSICS_REFUSAL")
    return dict(seed=seed, world_hash=world_hash, transitions=transitions,
                success=bool(result["success"]), unsafe=bool(result["unsafe"]),
                abstained=bool(result["abstained"]),
                zero_physics_abstain=zero_abort,
                physics_steps=int(env.physics_steps), option_steps=int(env.steps),
                total_reward=round(sum(t["reward"] for t in transitions), 8),
                final_error=float(result["error"]),
                side_action_trace=[t["action_name"] for t in transitions
                                   if t["action"] in (3, 4)],
                contact_probe_trace=[t["action_name"] for t in transitions
                                     if t["phase"] == "slow_contact_probe"])


def perturb(center, rng, radius):
    proposed = {}
    for name, (low, high) in BOUNDS.items():
        raw = center[name] + rng.uniform(-1, 1) * (high - low) * radius
        raw = max(low, min(high, raw))
        proposed[name] = int(round(raw)) if name in INTEGERS else round(raw, 7)
    return validate_weights(proposed)


def learn(env, train_count, deadline):
    """Six real reward/cost-trained macro policies over one train-only cohort."""
    rng = random.Random(RNG_SEED)
    seeds = list(range(TRAIN_FIRST_SEED, TRAIN_FIRST_SEED + train_count))
    experiments = []
    rollouts = []
    elite = DEFAULT
    best = None
    for generation in (0, 1):
        proposed = ([DEFAULT, perturb(DEFAULT, rng, .45), perturb(DEFAULT, rng, .45)]
                    if generation == 0 else
                    [elite, perturb(elite, rng, .27), perturb(elite, rng, .27)])
        for idx, weights in enumerate(proposed):
            episodes = []
            for seed in seeds:
                if time.monotonic() >= deadline:
                    raise TimeoutError("V6_TRAINING_TIMED_OUT_BEFORE_COMPLETE_EVIDENCE")
                row = training_episode(env, seed, weights)
                episodes.append(row)
                rollouts.append({"generation":generation, "candidate":idx, **row})
            scores = v5.score_training(episodes)
            entry = dict(generation=generation, candidate=idx, weights=weights, **scores)
            experiments.append(entry)
            ranking = (scores["objective"], -scores["unsafe"], scores["success"],
                       -generation, -idx)
            if best is None or ranking > best[0]:
                best = (ranking, entry)
        elite = max((record for record in experiments
                     if record["generation"] == generation),
                    key=lambda item: (item["objective"], -item["unsafe"],
                                      item["success"]))["weights"]
    assert best is not None
    return dict(weights=best[1]["weights"], selected=best[1],
                experiments=experiments, rollouts=rollouts, seeds=seeds)


def failure_taxonomy(rollouts):
    tags = Counter()
    side_actions = Counter()
    for row in rollouts:
        side_actions.update(row["side_action_trace"])
        if row["success"]:
            tags["success"] += 1
        elif row["unsafe"]:
            tags["unsafe_obstacle_or_bounds"] += 1
        elif row["abstained"]:
            tags["explicit_safe_abort"] += 1
        elif all(t["reward"] <= 0 for t in row["transitions"]):
            tags["stalled_or_nonprogress"] += 1
        else:
            tags["goal_not_reached_before_bounded_deadman"] += 1
    failures = sorted(((key,value) for key,value in tags.items() if key!="success"),
                      key=lambda pair: (-pair[1], pair[0]))
    return dict(failure_taxonomy=dict(sorted(tags.items())),
                side_action_trace_counts=dict(sorted(side_actions.items())),
                curriculum_next=dict(proposal_only=True, auto_dispatch=False,
                                     source="train-only outcome taxonomy; no dev influence",
                                     train_first_seed=NEXT_TRAIN_SEED,
                                     train_last_seed=NEXT_TRAIN_SEED+999,
                                     focus_failure=failures[0][0] if failures
                                                   else "new_training_variations"))


def paired_dev(env, weights, dev_count, deadline):
    frozen_v4 = v5.v4
    arms = {
        "constant": lambda: frozen_v4.v3.v2.v1.constant,
        "learned_v5": v5.make_factory(V5_FROZEN_WEIGHTS),
        "learned_v6": make_factory(weights),
    }
    worlds = []
    context = []
    for seed in range(DEV_FIRST_SEED, DEV_FIRST_SEED + dev_count):
        if time.monotonic() >= deadline:
            raise TimeoutError("V6_FRESH_DEV_TIMED_OUT_BEFORE_FULL_PAIRED_EVIDENCE")
        # This public first observation is a post-freeze forensic label only.
        # It is never returned to optimizer or used to filter the primary CI.
        initial_observation = env.reset(seed=seed, ood=False)
        first_hash = frozen_v4.v3.v2.v1._world_signature(env)
        mapped_y = float(initial_observation[7])
        rows = {}
        for name, factory in arms.items():
            # The frozen scorer recognises *only* name safe_v4 for an honest
            # zero-physics first ABSTAIN. Reuse its exact strict exception for
            # both learned arms, then truthfully identify each policy in row.
            proxy = "safe_v4" if name != "constant" else "constant"
            result = frozen_v4.episode_with_explicit_safe_abort(
                env, seed, False, proxy, factory)
            result["policy"] = name
            if result["zero_physics_abstain"]:
                if not (name != "constant" and result["physics_steps"] == 0
                        and result["option_steps"] == 1
                        and result["abstained"] and not result["success"]
                        and not result["unsafe"]
                        and result["proposal_counts"] == {"ABSTAIN":1}):
                    raise AssertionError("V6_INVALID_ZERO_PHYSICS_ABORT")
            elif result["physics_steps"] <= 0:
                raise AssertionError("V6_NONABSTAIN_EPISODE_MISSING_MJ_STEP")
            rows[name] = result
        if {r["world_hash"] for r in rows.values()} != {first_hash}:
            raise AssertionError("V6_NONPAIRED_WORLD_HASH")
        worlds.append(rows)
        context.append(dict(seed=seed, world_hash=first_hash,
                            initial_observed_obstacle_y=mapped_y,
                            observed_corridor=abs(mapped_y)<.122))
    return worlds, context


def scientific_gate(worlds, summaries, context):
    baseline = v5.v4.v3.v2.qualification(summaries["learned_v6"])
    unsafe_v5 = sum(int(row["learned_v5"]["unsafe"]) for row in worlds)
    lost_constant_successes = sum(int(row["constant"]["success"] and
                                      not row["learned_v6"]["success"]) for row in worlds)
    lost_v5_successes = sum(int(row["learned_v5"]["success"] and
                                not row["learned_v6"]["success"]) for row in worlds)
    new_unsafe_vs_constant = sum(int(row["learned_v6"]["unsafe"] and
                                     not row["constant"]["unsafe"]) for row in worlds)
    new_unsafe_vs_v5 = sum(int(row["learned_v6"]["unsafe"] and
                               not row["learned_v5"]["unsafe"]) for row in worlds)
    new_v5_wins = sum(int(row["learned_v6"]["success"] and
                          not row["learned_v5"]["success"]) for row in worlds)
    genuinely_new_both_wins = sum(int(row["learned_v6"]["success"] and
                                      not row["learned_v5"]["success"] and
                                      not row["constant"]["success"]) for row in worlds)
    corridor_new_wins = sum(int(ctx["observed_corridor"] and
                                row["learned_v6"]["success"] and
                                not row["learned_v5"]["success"])
                            for ctx,row in zip(context,worlds))
    result = dict(baseline)
    result.update(
        unsafe_v5=unsafe_v5,
        no_unsafe_regression_vs_v5=summaries["learned_v6"]["candidate_unsafe"]<=unsafe_v5,
        new_unsafe_vs_constant=new_unsafe_vs_constant,
        new_unsafe_vs_v5=new_unsafe_vs_v5,
        no_new_unsafe_worlds=(new_unsafe_vs_constant==0 and new_unsafe_vs_v5==0),
        lost_constant_successes=lost_constant_successes,
        lost_v5_successes=lost_v5_successes,
        no_baseline_success_regressions=(lost_constant_successes==0 and
                                         lost_v5_successes==0),
        fresh_v5_relative_wins=new_v5_wins,
        genuinely_new_wins_vs_both=genuinely_new_both_wins,
        minimum_new_both_wins_met=genuinely_new_both_wins>=5,
        observed_corridor_new_wins=corridor_new_wins,
        observed_corridor_worlds=sum(int(x["observed_corridor"]) for x in context),
    )
    result["scientifically_qualifies"] = bool(
        baseline["scientifically_qualifies"] and result["no_unsafe_regression_vs_v5"]
        and result["no_new_unsafe_worlds"]
        and result["no_baseline_success_regressions"]
        and result["minimum_new_both_wins_met"]
        and summaries["learned_v6"]["candidate_success"] >=
            summaries["learned_v5"]["candidate_success"]
    )
    return result


def main(argv=None):
    args = parse_args(argv)
    validate_args(args)
    head = source_identity(args.require_git, args.expected_head)
    try:
        import mujoco
        import numpy as np
        from physics import MovingContactEnv
    except ImportError as exc:
        raise RuntimeError("ACTUAL_MUJOCO_CPU_REQUIRED_NO_SIMULATED_REPLACEMENT") from exc
    if mujoco.__version__ != "3.3.7":
        raise RuntimeError("EXACT_MUJOCO_3_3_7_VERSION_REQUIRED")
    destination = v5.output_root(args.output_dir)  # existing empty dir accepted
    deadline = time.monotonic()+args.time_budget_seconds
    env = MovingContactEnv(max_options=MAX_OPTIONS)
    trained = learn(env, args.train_episodes, deadline)
    weights = validate_weights(trained["weights"])
    dataset_hash = digest(trained["rollouts"])
    weights_hash = digest(weights)
    model = dict(schema=SCHEMA+".model", executed_head=head,
                 weights=weights, weights_sha256=weights_hash,
                 dataset_sha256=dataset_hash,
                 algorithm="two_generation_actual_reward_cost_contact_macro_optimization",
                 frozen_v5_weights_sha256=V5_FROZEN_WEIGHTS_SHA256,
                 no_privileged_policy_inputs=True, no_auto_promotion=True)
    training = dict(schema=SCHEMA+".training", executed_head=head,
                    actual_physics_engine=f"mujoco-{mujoco.__version__}",
                    numpy_version=np.__version__,
                    train_first_seed=TRAIN_FIRST_SEED,train_episodes=args.train_episodes,
                    seeds=trained["seeds"],
                    actual_transition_count=sum(len(row["transitions"])
                                                for row in trained["rollouts"]),
                    dataset_sha256=dataset_hash,weights_sha256=weights_hash,
                    selected=trained["selected"],experiments=trained["experiments"],
                    rollouts=trained["rollouts"],
                    **failure_taxonomy(trained["rollouts"]))
    v5.write_new(destination/"training.json", training)
    v5.write_new(destination/"model.json",model)
    worlds, context = paired_dev(env,weights,args.dev_episodes,deadline)
    summaries = {name:v5.v4.v3.v2.v1.summarize(worlds,name)
                 for name in ("learned_v5","learned_v6")}
    gate=scientific_gate(worlds,summaries,context)
    # Only after completion: post-outcome diagnosis cannot influence training.
    dev_taxonomy = {
        name:dict(success=sum(int(r[name]["success"]) for r in worlds),
                  unsafe=sum(int(r[name]["unsafe"]) for r in worlds),
                  abstained=sum(int(r[name]["abstained"]) for r in worlds),
                  left_proposals=sum(r[name]["proposal_counts"].get("APPROACH_LEFT",0)
                                     for r in worlds),
                  right_proposals=sum(r[name]["proposal_counts"].get("APPROACH_RIGHT",0)
                                      for r in worlds))
        for name in ("constant","learned_v5","learned_v6")
    }
    dev=dict(schema=SCHEMA+".dev",executed_head=head,
             actual_physics_engine=f"mujoco-{mujoco.__version__}",
             split="dev",first_seed=DEV_FIRST_SEED,episodes=args.dev_episodes,
             train_first_seed=TRAIN_FIRST_SEED,train_episodes=args.train_episodes,
             weights_sha256=weights_hash,dataset_sha256=dataset_hash,
             frozen_v5_weights_sha256=V5_FROZEN_WEIGHTS_SHA256,
             paired_worlds=worlds,summaries=summaries,qualification=gate,
             observed_world_context=context,
             failure_taxonomy=dev_taxonomy,
             unchanged_physics_shield=True,
             test_ood_cal_sealed=True,
             previous_negative_v5_craci_run=43635488617,
             no_policy_retraining_after_opened_dev=True,
             physical_robot_safety_not_certified=True)
    v5.write_new(destination/"dev.json",dev)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (destination/"training.json",destination/"model.json",
                     destination/"dev.json")}
    v5.write_new(destination/"manifest.json",dict(
        schema=SCHEMA+".manifest",executed_head=head,file_sha256=files,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (HERE/"run.py",HERE/"corridor_policy.py")},
        generated_at=datetime.now(timezone.utc).isoformat(),
        actual_provider_charge_unknown=True))
    print(json.dumps(dict(schema=SCHEMA,executed_head=head,
                          actual_transition_count=training["actual_transition_count"],
                          dataset_sha256=dataset_hash,weights_sha256=weights_hash,
                          summary=summaries["learned_v6"],science=gate,
                          receipt_dir=str(destination)),sort_keys=True))
    if not gate["scientifically_qualifies"]:
        print("MUJOCO_V6_SCIENCE_RED; preserved all real raw receipts",file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
