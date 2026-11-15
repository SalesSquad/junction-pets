#!/usr/bin/env python3
"""Frozen-source REAL MuJoCo evaluation for swept-lane v4, no sealed-data tuning.

The v3 experimental source and both prior negative receipts are immutable.
This runner uses identical physics/seed/shield for all three policy arms.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
V3 = HERE.parent / "v3"
MUJOCO = HERE.parent
LEARNING = MUJOCO.parents[1]
V3_SHA = "466c4264468b35c954242d8c3409a47c5ba3b4b8"

if str(V3) not in sys.path:
    sys.path.insert(0, str(V3))
spec = importlib.util.spec_from_file_location("rokoko_mujoco_frozen_v3_runner", V3 / "run.py")
if spec is None or spec.loader is None:
    raise ImportError("frozen v3 MuJoCo runner missing")
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)

from safety_controller import make_controller  # noqa: E402


def source_identity(require_git, expected_head, holdout):
    head = v3.source_identity(require_git, expected_head, holdout)
    if require_git or holdout:
        root = subprocess.check_output(
            ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], text=True).strip()
        if subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor",
                           V3_SHA, head], capture_output=True).returncode:
            raise RuntimeError("V4 source is not descendant of immutable v3 scientific red")
    return head


def source_manifest():
    hashes = v3.source_manifest()
    for f in (HERE / "run.py", HERE / "safety_controller.py", HERE / "test_contract.py"):
        hashes[str(f.relative_to(LEARNING.parent))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return hashes


def post_step_unsafe_diagnostic(env, row):
    """After outcome only; impossible for controller to inspect this ground truth."""
    if not row["unsafe"]:
        return {"unsafe": False, "post_step_obstacle_pair": False, "post_step_bounds": False}
    import numpy as np
    contacts = []
    for k in range(env.data.ncon):
        c = env.data.contact[k]
        pair = {c.geom1, c.geom2}
        if env.bg in pair and (env.og in pair or env.pg in pair):
            contacts.append("object" if env.og in pair else "pusher")
    bounds = []
    for body, label in ((env.obj, "object"), (env.push, "pusher")):
        x, y, z = env.data.xpos[body]
        if not (-.2 <= x <= .3 and abs(y) <= .2 and 0 <= z <= .06):
            bounds.append(label)
    return {"unsafe": True, "post_step_obstacle_pair": bool(contacts),
            "post_step_obstacle_contacting": sorted(set(contacts)),
            "post_step_bounds": bool(bounds), "post_step_oob_bodies": sorted(bounds),
            "source": "post-outcome inspection, not controller input or qualification filter"}


def episode_with_explicit_safe_abort(env, seed, ood, name, make_policy):
    """Score a real first-action ABSTAIN as a nonphysical, failed episode.

    Frozen v2.episode deliberately requires >0 mj_step for a *physics* result.
    However the unchanged environment implements healthy ABSTAIN by ending
    immediately with zero steps, which is a valid explicit refusal. Never
    invent physical steps, an achieved goal, or physical safety evidence.
    This exception is accepted ONLY for the exact first-option safe refusal.
    Any other missing-physics or policy error still fails closed.
    """
    try:
        row = v3.v2.episode(env, seed, ood, name, make_policy)
        row["zero_physics_abstain"] = False
        return row
    except AssertionError as exc:
        expected = f"{name} failed real MuJoCo physics-step gate on world {seed}"
        allowed = (name == "safe_v4" and str(exc) == expected
                   and env.done is True and env.abstained is True
                   and env.unsafe is False and env.steps == 1
                   and env.physics_steps == 0 and env.last == 6)
        if not allowed:
            raise
        # The post-ABSTAIN state is physically unchanged (zero integration).
        # A matched latent world hash is still computed and cross-checked
        # against the independent constant/v3 arms below.
        xy = env.data.xpos[env.obj, :2]
        error = math.hypot(float(xy[0]) - .16, float(xy[1]))
        return dict(seed=seed, policy=name,
                    world_hash=v3.v2.v1._world_signature(env),
                    success=False, unsafe=False, abstained=True,
                    zero_physics_abstain=True,
                    physics_steps=0, option_steps=1,
                    distinct_proposals=1, proposal_counts={"ABSTAIN": 1},
                    shield_veto_proposals=0, no_contact_stall_options=0,
                    dwell_ticks_final=0, peak_impulse=0., contacts=0,
                    holds=0, acks=0, refusals=0, error=error,
                    option_trace=[dict(option=1, proposed="ABSTAIN",
                                       allowed=True, progress_m=0.,
                                       contacts_added=0, refusals_added=0)])


def main(argv=None):
    args = v3.v2.v1.parse_args(argv)
    if args.policy:
        raise ValueError("V4 swept-lane controller is frozen; --policy injection disabled")
    if not 1 <= args.episodes <= 200 or not 1 <= args.max_options <= 60:
        raise ValueError("bounded 1..200 episodes and 1..60 options only")
    holdout = args.split in ("test", "ood")
    if holdout and not args.permit_holdout:
        raise PermissionError("physics test/OOD remain sealed without --permit-holdout")
    if args.split == "dev" and args.seed_offset < 100:
        raise ValueError("V4 uses FRESH dev seed offset >=100; prior v4 30..99 batch exposed")
    if args.split == "cal" and args.seed_offset < 100:
        raise ValueError("V4 independent calibration offset >=100; v3 cal0..99 exposed")
    low, high = v3.v2.v1.SEED_BANDS[args.split]
    if args.seed_offset < 0 or low + args.seed_offset + args.episodes - 1 > high:
        raise ValueError("seed selection exceeds reserved group")
    head = source_identity(args.require_git, args.expected_head, holdout)

    try:
        import mujoco
        import numpy as np
        from physics import MovingContactEnv
    except ImportError as err:
        raise RuntimeError("Real MuJoCo 3.3.7 CPU physics is mandatory") from err
    if mujoco.__version__ != "3.3.7":
        raise RuntimeError(f"Expected MuJoCo 3.3.7; received {mujoco.__version__}")

    env = MovingContactEnv(max_options=args.max_options)
    controllers = {"constant": lambda: v3.v2.v1.constant,
                   "risk_v3": v3.make_controller,
                   "safe_v4": make_controller}
    worlds = []
    for seed in range(low + args.seed_offset, low + args.seed_offset + args.episodes):
        rows = {}
        for name, factory in controllers.items():
            row = episode_with_explicit_safe_abort(
                env, seed, args.split == "ood", name, factory)
            if row["zero_physics_abstain"]:
                if not (name == "safe_v4" and row["physics_steps"] == 0
                        and row["option_steps"] == 1 and row["abstained"]
                        and not row["success"] and not row["unsafe"]
                        and row["proposal_counts"] == {"ABSTAIN": 1}
                        and row["option_trace"] == [
                            dict(option=1, proposed="ABSTAIN", allowed=True,
                                 progress_m=0., contacts_added=0,
                                 refusals_added=0)]):
                    raise AssertionError("INVALID_ZERO_PHYSICS_SAFE_ABSTAIN_RECEIPT")
            elif row["physics_steps"] <= 0:
                raise AssertionError("NONABSTAINED_WORLD_LACKS_REAL_MJ_STEPS")
            # Diagnostics are appended only after the policy/physics episode
            # finishes. They are never seen by an action policy or gate logic.
            row["diagnostic_deadman_release_tick"] = int(env.release)
            row["post_step_forensic"] = post_step_unsafe_diagnostic(env, row)
            rows[name] = row
        if len({r["world_hash"] for r in rows.values()}) != 1:
            raise AssertionError(f"World mismatch across policy arms seed={seed}")
        worlds.append(rows)

    summaries = {name: v3.v2.v1.summarize(worlds, name)
                 for name in controllers if name != "constant"}
    gate = v3.v2.qualification(summaries["safe_v4"])
    abstentions = {
        name: {
            "explicit_abstained": sum(int(r[name]["abstained"]) for r in worlds),
            "zero_physics_abstained": sum(
                int(r[name]["zero_physics_abstain"]) for r in worlds),
        } for name in controllers
    }
    result = dict(schema="rokoko-mujoco-real-physics-swept-lane-v4",
                  actual_physics_engine=f"mujoco-{mujoco.__version__}",
                  numerical_backend="MuJoCo CPU mj_step, no trained model",
                  numpy_version=np.__version__, original_base_sha=v3.v2.v1.BASE_SHA,
                  v1_sha=v3.v2.V1_SHA, v2_sha=v3.V2_SHA, v3_sha=V3_SHA,
                  executed_head=head, source_sha256=source_manifest(),
                  split=args.split, first_seed=low + args.seed_offset,
                  episodes=args.episodes, max_options=args.max_options,
                  untouched_negative_runs=[43627944236, 43628857595,
                                           43630195101, 43630816368],
                  abstention_accounting=abstentions,
                  world_pairing="same seed, independent motion/sensor RNG, unchanged shield",
                  safety="model-only collision and deadman, no hardware certification",
                  qualification=gate, summaries=summaries, paired_worlds=worlds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps(dict(receipt=str(args.output), head=head,
                          safe_v4=summaries["safe_v4"], qualification=gate),
                     sort_keys=True))
    if not gate["scientifically_qualifies"]:
        print("V4 SCIENCE RED: safety/paired performance gate did not pass; preserve receipt",
              file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
