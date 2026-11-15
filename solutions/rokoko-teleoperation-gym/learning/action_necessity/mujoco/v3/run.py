#!/usr/bin/env python3
"""MuJoCo risk-v3 fresh-dev/cal CPU evaluation; source-locked and fail closed."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "v2"
MUJOCO = HERE.parent
LEARNING = MUJOCO.parents[1]
V2_SHA = "b8f35db5e88eb0eb55157790618a52e73ca60220"

if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("rokoko_mujoco_frozen_v2_runner", V2 / "run.py")
if spec is None or spec.loader is None:
    raise ImportError("frozen v2 runner not available")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

from risk_controller import make_controller  # noqa: E402


def source_identity(require_git, expected_head, holdout):
    head = v2.source_identity(require_git, expected_head, holdout)
    if require_git or holdout:
        root = subprocess.check_output(
            ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], text=True).strip()
        if subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor",
                           V2_SHA, head], capture_output=True).returncode:
            raise RuntimeError("Source not descended from immutable negative v2 evidence")
    return head


def source_manifest():
    hashes = v2.extra_manifest()
    for f in (HERE / "run.py", HERE / "risk_controller.py", HERE / "test_contract.py"):
        hashes[str(f.relative_to(LEARNING.parent))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return hashes


def main(argv=None):
    args = v2.v1.parse_args(argv)
    if args.policy:
        raise ValueError("v3 controller is frozen; --policy injection disabled")
    if not 1 <= args.episodes <= 200 or not 1 <= args.max_options <= 60:
        raise ValueError("bounded 1..200 episodes and 1..60 options only")
    holdout = args.split in ("test", "ood")
    if holdout and not args.permit_holdout:
        raise PermissionError("test/OOD sealed without --permit-holdout")
    if args.split == "dev" and args.seed_offset < 10:
        raise ValueError("v3 dev qualification uses FRESH 129010+ (not v1/v2 eight worlds)")
    low, high = v2.v1.SEED_BANDS[args.split]
    if args.seed_offset < 0 or low+args.seed_offset+args.episodes-1 > high:
        raise ValueError("seed selection exceeds reserved group")
    head = source_identity(args.require_git, args.expected_head, holdout)
    try:
        import mujoco
        import numpy as np
        from physics import MovingContactEnv
    except ImportError as err:
        raise RuntimeError("Actual MuJoCo CPU physics is mandatory; install mujoco==3.3.7") from err
    if mujoco.__version__ != "3.3.7":
        raise RuntimeError(f"Expected MuJoCo 3.3.7, received {mujoco.__version__}")

    env = MovingContactEnv(max_options=args.max_options)
    controllers = {"constant": lambda: v2.v1.constant,
                   "adaptive_v2": v2.make_controller,
                   "risk_v3": make_controller}
    worlds = []
    for seed in range(low+args.seed_offset, low+args.seed_offset+args.episodes):
        rows = {}
        for name, factory in controllers.items():
            row = v2.episode(env, seed, args.split == "ood", name, factory)
            # Diagnostics only, after the policy finished: never returned to
            # any controller and not used to filter/weight qualification.
            row["diagnostic_deadman_release_tick"] = int(env.release)
            rows[name] = row
        if len({r["world_hash"] for r in rows.values()}) != 1:
            raise AssertionError(f"World mismatch across paired arms seed={seed}")
        worlds.append(rows)

    summaries = {name: v2.v1.summarize(worlds, name)
                 for name in controllers if name != "constant"}
    gate = v2.qualification(summaries["risk_v3"])
    result = dict(schema="rokoko-mujoco-real-physics-risk-v3",
                  actual_physics_engine=f"mujoco-{mujoco.__version__}",
                  numerical_backend="MuJoCo CPU mj_step, no trained model",
                  numpy_version=np.__version__, original_base_sha=v2.v1.BASE_SHA,
                  v1_sha=v2.V1_SHA, v2_sha=V2_SHA, executed_head=head,
                  source_sha256=source_manifest(), split=args.split,
                  first_seed=low+args.seed_offset, episodes=args.episodes,
                  max_options=args.max_options,
                  untouched_negative_runs=[43627944236, 43628857595],
                  world_pairing="same seed, independent motion/sensor RNG, same shield",
                  safety="model-only contacts and deadman; no hardware safety",
                  qualification=gate, summaries=summaries, paired_worlds=worlds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(dict(receipt=str(args.output), head=head,
                          risk_v3=summaries["risk_v3"], qualification=gate),
                     sort_keys=True))
    if not gate["scientifically_qualifies"]:
        print("V3 NO SCIENTIFIC WIN: negative/inconclusive receipt retained",
              file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
