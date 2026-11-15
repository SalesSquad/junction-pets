#!/usr/bin/env python3
"""MuJoCo adaptive-v2/constant/teacher paired CPU evaluation; sealed receipts.

The inherited v1 run (PR #162) is immutable. This script adds an observation-
only controller and a *separate* qualification gate without erasing negative
history or permitting silent locked-data inspection.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MUJOCO = HERE.parent
LEARNING = MUJOCO.parents[1]
SOURCE = HERE / "run.py"
V1_SHA = "cd7b2446c5f8d0e96761524f8a26a20ac4cbf44d"
if str(MUJOCO) not in sys.path:
    sys.path.insert(0, str(MUJOCO))

spec = importlib.util.spec_from_file_location("rokoko_mujoco_v1_runner", MUJOCO / "run.py")
if spec is None or spec.loader is None:
    raise ImportError("frozen MuJoCo v1 runner inaccessible")
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)

from controller import make_controller  # noqa: E402


def extra_manifest():
    base = v1.source_manifest()
    for f in (HERE / "run.py", HERE / "controller.py", HERE / "test_contract.py"):
        base[str(f.relative_to(LEARNING.parent))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return base


def source_identity(require_git, expected_head, holdout):
    if holdout and (not require_git or not expected_head):
        raise PermissionError(
            "Locked test/OOD requires --permit-holdout --require-git --expected-head exact SHA")
    head = v1.git_identity(require_git=require_git or holdout,
                           expected_head=expected_head)
    if require_git or holdout:
        root = subprocess.check_output(
            ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], text=True).strip()
        if subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor",
                           V1_SHA, head], capture_output=True).returncode:
            raise RuntimeError("Source HEAD not descendant of immutable negative MuJoCo v1")
    return head


def episode(env, seed, ood, name, make_policy):
    from env import ACTIONS

    observation = env.reset(seed=seed, ood=ood)
    initial_hash = v1._world_signature(env)
    controller = make_policy()
    actions = Counter()
    veto_proposals = no_contact_stalls = 0
    trace = []
    true_object = env.data.xpos[env.obj, :2]
    old_error = math.hypot(float(true_object[0])-.16, float(true_object[1]))
    previous_contacts = previous_refusals = 0
    last = None
    for option in range(env.max_options):
        allowed = env.mask(observation)
        proposal = controller(observation.copy(), allowed.copy())
        if not isinstance(proposal, (int,)) or not 0 <= proposal < 7:
            raise ValueError(f"{name} proposal outside 0..6: {proposal!r}")
        actions[ACTIONS[proposal]] += 1
        veto_proposals += int(not allowed[proposal])
        observation, _, done, last = env.step(proposal)
        added_contacts = int(last["contacts"])-previous_contacts
        progress = old_error-float(last["error"])
        no_contact_stalls += int(progress < .001 and added_contacts == 0 and old_error > .02)
        trace.append(dict(option=option+1, proposed=ACTIONS[proposal],
                          allowed=bool(allowed[proposal]),
                          progress_m=round(progress, 7),
                          contacts_added=added_contacts,
                          refusals_added=int(last["refusals"])-previous_refusals))
        old_error = float(last["error"])
        previous_contacts = int(last["contacts"])
        previous_refusals = int(last["refusals"])
        if done:
            break
    if not last or int(env.physics_steps) <= 0:
        raise AssertionError(f"{name} failed real MuJoCo physics-step gate on world {seed}")
    return dict(seed=seed, policy=name, world_hash=initial_hash,
                success=bool(last["success"]), unsafe=bool(last["unsafe"]),
                abstained=bool(last["abstained"]),
                physics_steps=int(env.physics_steps), option_steps=int(env.steps),
                distinct_proposals=len(actions), proposal_counts=dict(sorted(actions.items())),
                shield_veto_proposals=veto_proposals,
                no_contact_stall_options=no_contact_stalls,
                dwell_ticks_final=int(env.dwell),
                peak_impulse=float(last["peak_impulse"]),
                contacts=int(last["contacts"]), holds=int(last["holds"]),
                acks=int(last["acks"]), refusals=int(last["refusals"]),
                error=float(last["error"]), option_trace=trace)


def qualification(summary):
    # Re-evaluated on each dev/cal batch; holdout never opened for tuning.
    gains = summary["delta_success_percentage_points"]
    ci = summary["paired_bootstrap95_pp"]
    not_worse_unsafe = summary["candidate_unsafe"] <= summary["constant_unsafe"]
    return dict(positive_gain=gains > 0,
                no_unsafe_regression=not_worse_unsafe,
                paired_lower_bound_positive=ci[0] > 0,
                **{"scientifically_qualifies": gains > 0 and not_worse_unsafe and ci[0] > 0})


def main(argv=None):
    args = v1.parse_args(argv)
    if args.policy:
        raise ValueError("v2 controllers are fixed; --policy injection is disabled")
    if not 1 <= args.episodes <= 200 or not 1 <= args.max_options <= 60:
        raise ValueError("episodes 1..200 and max-options 1..60 only")
    holdout = args.split in ("test", "ood")
    if holdout and not args.permit_holdout:
        raise PermissionError("Heldout test/OOD is locked without --permit-holdout")
    low, high = v1.SEED_BANDS[args.split]
    if args.seed_offset < 0 or low+args.seed_offset+args.episodes-1 > high:
        raise ValueError("Requested seeds exceed dedicated physics seed band")
    head = source_identity(args.require_git, args.expected_head, holdout)
    import mujoco
    import numpy as np
    if mujoco.__version__ != "3.3.7":
        raise RuntimeError(f"Real MuJoCo 3.3.7 required, got {mujoco.__version__}")
    from physics import MovingContactEnv

    # All controllers use the exact same MjModel/MjData and shield. No model
    # training or privileged physics access is given to the proposed controller.
    env = MovingContactEnv(max_options=args.max_options)
    controllers = {"constant": lambda: v1.constant,
                   "original_teacher": lambda: v1.teacher,
                   "adaptive_v2": make_controller}
    paired = []
    for seed in range(low+args.seed_offset, low+args.seed_offset+args.episodes):
        rows = {name: episode(env, seed, holdout and args.split == "ood", name, factory)
                for name, factory in controllers.items()}
        if len({row["world_hash"] for row in rows.values()}) != 1:
            raise AssertionError(f"Paired world hash mismatch on {seed}")
        paired.append(rows)

    summaries = {name: v1.summarize(paired, name) for name in controllers if name != "constant"}
    gate = qualification(summaries["adaptive_v2"])
    receipt = dict(schema="rokoko-mujoco-cpu-adaptive-v2",
                   actual_physics_engine=f"mujoco-{mujoco.__version__}",
                   numerical_backend="MuJoCo CPU mj_step (not robot/Isaac/MJWarp)",
                   numpy_version=np.__version__, base_sha=v1.BASE_SHA, v1_sha=V1_SHA,
                   executed_head=head, source_sha256=extra_manifest(),
                   split=args.split, first_seed=low+args.seed_offset,
                   episodes=args.episodes, max_options=args.max_options,
                   scoring_provenance="world-paired real MuJoCo physical contact and dwell",
                   negative_v1_run="GitHub Actions #43627944236 (teacher0/8,constant5/8)",
                   safety_disclaimer="model hazard flag only; never physical safety",
                   qualification=gate, summaries=summaries, paired_worlds=paired)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(dict(output=str(args.output), head=head,
                          summary=summaries["adaptive_v2"], qualification=gate),
                     sort_keys=True))
    if not gate["scientifically_qualifies"]:
        print("V2 SCIENTIFIC NEGATIVE/INCONCLUSIVE: receipt retained, no win claimed",
              file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
