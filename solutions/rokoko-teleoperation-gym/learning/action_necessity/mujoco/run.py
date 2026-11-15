#!/usr/bin/env python3
"""Source-bound paired MuJoCo CPU action-necessity experiment.

Run from a pinned checkout with `mujoco==3.3.7`; importing this module does not
pretend MuJoCo exists on hosts without its physics engine.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from numbers import Integral
from pathlib import Path
import random
import statistics
import subprocess
import sys

BASE_SHA = "312130c9f0b63b9623e4cc9401ace74539296733"
SEED_BANDS = {
    "dev": (129000, 129999),
    "cal": (229000, 229999),
    "test": (329000, 329199),
    "ood": (429000, 429199),
}
SOURCE = Path(__file__).resolve()


def source_manifest():
    root = SOURCE.parents[2]  # the original `learning/` source package
    files = (SOURCE, SOURCE.with_name("physics.py"), SOURCE.with_name("moving_scene.xml"),
             root / "env.py", root.parent / "sim" / "scene.xml")
    return {str(f.relative_to(root.parent)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in files}


def git_identity(require_git: bool, expected_head: str | None):
    try:
        toplevel = subprocess.check_output(
            ["git", "-C", str(SOURCE.parent), "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL).strip()
        head = subprocess.check_output(
            ["git", "-C", toplevel, "rev-parse", "HEAD"], text=True).strip()
        descendant = subprocess.run(
            ["git", "-C", toplevel, "merge-base", "--is-ancestor", BASE_SHA, head],
            check=False, capture_output=True).returncode == 0
        if not descendant:
            raise RuntimeError(f"Source HEAD {head} is not descendant of pinned PR #153 {BASE_SHA}")
        if expected_head and head != expected_head:
            raise RuntimeError(f"Source HEAD mismatch expected {expected_head}, got {head}")
        return head
    except (OSError, subprocess.CalledProcessError):
        if require_git or expected_head:
            raise RuntimeError("Source-locked run needs a checkout with git and pinned parent")
        return None


def teacher(observation, shield):
    """Observation-only fixed rule; not RL, not privy to mover ground truth."""
    import numpy as np

    if not shield[:6].any():
        return 6
    obj = observation[:2]
    pusher = observation[2:4]
    obstacle = observation[6:8]
    goal = np.array([.16, 0.])
    toward = goal - obj
    if np.linalg.norm(toward) < .02 and shield[5]:
        return 5
    projection = obj + np.clip(np.dot(obstacle-obj, toward) /
                               max(np.dot(toward, toward), 1e-12), 0, 1) * toward
    blocked = np.linalg.norm(projection-obstacle) < .060
    if blocked:
        side = 3 if obstacle[1] > obj[1] else 4
        if shield[side]:
            return side
        if shield[0]:
            return 0
        if shield[7-side]:  # other side: 3 <-> 4
            return 7-side
    unit = toward / max(np.linalg.norm(toward), 1e-12)
    behind = obj - .041*unit
    if np.linalg.norm(pusher-behind) > .011 and shield[0]:
        return 0
    if shield[1]:
        return 1
    if shield[3]:
        return 3
    if shield[4]:
        return 4
    return 5 if shield[5] else 6


def constant(observation, shield):
    # Fixed proposal, no consultation of the teacher. The same shield intercepts
    # unsafe proposals at the env boundary for every policy.
    return 2


def optional_policy(spec: str):
    if ":" not in spec:
        raise ValueError("--policy must be an importable module:function")
    module, function = spec.split(":", 1)
    if not module or not function:
        raise ValueError("missing policy module or callable")
    candidate = getattr(importlib.import_module(module), function)
    if not callable(candidate):
        raise TypeError("optional policy is not callable")
    return candidate


def _world_signature(env):
    # A latent world hash is evidence of matched scenario initial conditions.
    # This is logged after episodes; it is NOT supplied to any controller.
    body = [float(x) for x in env.data.qpos[:2]]
    values = dict(initial_position=body,
                  mass=float(env.model.body_mass[env.obj]),
                  friction=float(env.model.geom_friction[env.og, 0]),
                  obstacle_y=float(env.model.geom_pos[env.bg, 1]),
                  amplitude=env.amplitude, frequency=env.frequency, phase=env.phase,
                  drop_start=env.drop_start, drop_len=env.drop_len,
                  deadman_release=env.release)
    digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return digest


def episode(env, seed, ood, name, controller):
    observation = env.reset(seed=seed, ood=ood)
    world_hash = _world_signature(env)
    requested = []
    last = None
    for _ in range(env.max_options):
        mask = env.mask(observation)
        proposed = controller(observation.copy(), mask.copy())
        if not isinstance(proposed, Integral) or not 0 <= proposed < 7:
            raise ValueError(f"{name} returned invalid action {proposed!r}")
        requested.append(proposed)
        observation, _, done, last = env.step(proposed)
        if done:
            break
    if last is None:
        raise AssertionError("No physics option attempted")
    return dict(seed=seed, policy=name, world_hash=world_hash,
                success=bool(last["success"]), unsafe=bool(last["unsafe"]),
                abstained=bool(last["abstained"]),
                physics_steps=int(env.physics_steps), option_steps=int(env.steps),
                distinct_proposals=len(set(requested)), first_proposals=requested[:8],
                peak_impulse=float(last["peak_impulse"]),
                contacts=int(last["contacts"]), holds=int(last["holds"]),
                acks=int(last["acks"]), refusals=int(last["refusals"]),
                error=float(last["error"]))


def paired_bootstrap(differences: list[int], draws=2000):
    if not differences:
        raise ValueError("empty paired sample")
    rng = random.Random(20261114)
    n = len(differences)
    means = sorted(sum(differences[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(draws))
    return [round(100*means[int(.025*(draws-1))], 3),
            round(100*means[int(.975*(draws-1))], 3)]


def summarize(paired, name):
    baseline = [entry["constant"] for entry in paired]
    candidate = [entry[name] for entry in paired]
    delta = [int(a["success"]) - int(b["success"])
             for a, b in zip(candidate, baseline)]
    n = len(paired)
    return dict(episodes=n, constant_success=sum(x["success"] for x in baseline),
                candidate_success=sum(x["success"] for x in candidate),
                constant_unsafe=sum(x["unsafe"] for x in baseline),
                candidate_unsafe=sum(x["unsafe"] for x in candidate),
                constant_physics_steps=sum(x["physics_steps"] for x in baseline),
                candidate_physics_steps=sum(x["physics_steps"] for x in candidate),
                candidate_multi_action_episodes=sum(x["distinct_proposals"] >= 2
                                                    for x in candidate),
                delta_success_percentage_points=round(100*sum(delta)/n, 3),
                paired_bootstrap95_pp=paired_bootstrap(delta))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", choices=tuple(SEED_BANDS), default="dev")
    p.add_argument("--episodes", type=int, default=8)
    p.add_argument("--seed-offset", type=int, default=0)
    p.add_argument("--max-options", type=int, default=60)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--policy", help="optional trusted module:function(observation, mask)")
    p.add_argument("--permit-holdout", action="store_true",
                   help="required for one frozen-head test/ood evaluation")
    p.add_argument("--expected-head", help="pinned final Git HEAD; fails closed")
    p.add_argument("--require-git", action="store_true", help="require PR #153 ancestor")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not 1 <= args.episodes <= 200 or not 1 <= args.max_options <= 60:
        raise ValueError("bounded run: episodes 1..200, max-options 1..60")
    if args.split in ("test", "ood") and not args.permit_holdout:
        raise PermissionError("Holdout is locked until --permit-holdout at frozen head")
    low, high = SEED_BANDS[args.split]
    if args.seed_offset < 0 or low+args.seed_offset+args.episodes-1 > high:
        raise ValueError("Requested seeds exceed reserved disjoint band")
    head = git_identity(require_git=args.require_git, expected_head=args.expected_head)
    try:
        import mujoco
        import numpy as np
        from physics import MovingContactEnv
    except ImportError as err:
        raise RuntimeError("Actual MuJoCo CPU physics unavailable; install mujoco==3.3.7") from err
    if mujoco.__version__ != "3.3.7":
        raise RuntimeError(f"Pinned MuJoCo 3.3.7 required; observed {mujoco.__version__}")
    manifest = source_manifest()
    controllers = {"constant": constant, "teacher": teacher}
    if args.policy:
        controllers[args.policy] = optional_policy(args.policy)
    env = MovingContactEnv(max_options=args.max_options)
    paired = []
    ood = args.split == "ood"
    for seed in range(low+args.seed_offset, low+args.seed_offset+args.episodes):
        rows = {name: episode(env, seed, ood, name, fn)
                for name, fn in controllers.items()}
        hashes = {row["world_hash"] for row in rows.values()}
        if len(hashes) != 1:
            raise AssertionError(f"Same-seed world mismatch: {seed}")
        if any(row["physics_steps"] <= 0 for row in rows.values()):
            raise AssertionError(f"No actual MuJoCo steps recorded: {seed}")
        paired.append(rows)
    summaries = {name: summarize(paired, name) for name in controllers if name != "constant"}
    result = dict(schema="rokoko-mujoco-cpu-action-necessity-v1",
                  actual_physics_engine=f"mujoco-{mujoco.__version__}",
                  numerical_backend="MuJoCo mj_step CPU; not MJWarp/Isaac/robot",
                  numpy_version=np.__version__, base_sha=BASE_SHA, executed_head=head,
                  source_sha256=manifest, split=args.split, first_seed=low+args.seed_offset,
                  episodes=args.episodes, max_options=args.max_options,
                  success_definition="source ContactEnv: goal dwell >=250 physics ticks with contact",
                  safety_disclaimer="simulation hazard flag only; no physical safety certification",
                  summaries=summaries, paired_worlds=paired)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), head=head,
                          source_sha256=manifest, summaries=summaries), sort_keys=True))


if __name__ == "__main__":
    main()
