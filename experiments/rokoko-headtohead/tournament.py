#!/usr/bin/env python3
"""Pre-registered, source-bound *same-world* comparison of two frozen policies.

This is a comparison, not an online model selector. The locked worlds must only
be opened once on a separately qualified runner, after source and weights are
frozen. All physics here is the original synthetic 2D kinematics.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from random import Random
import statistics
import subprocess
import sys


V2_SOURCE = "f96788807c262b2233f034c045df4373cb3c428c"
TD_SOURCE = "f7b512d93ca46e6ddf7204f62f118eee800f285b"
V2_WEIGHTS = "1bab986c10be062cf87a4848916917cbab3a78b53e78cda8c2f8673f62d4cc55"
TD_WEIGHTS = "3868559e05f81e3148e34ebd99a7d874525e4ceba2ca942779628104d38fef28"
ARENA_SHA256 = "76b6cbe373323d944e21291fc10352f983ed8cf5d5bbc245ca37aadfda11089f"
RUN_SHA256 = "0ad2765fef407da181c83b0140de80a6f1d82fa0fa132cf1de73013c9cf9ffe0"
ARENA_PATH = "solutions/rokoko-teleoperation-gym/learning/action_necessity"

# Distinct from the exposed v1 (320000/420000), v2 (326000/426000),
# independent TD (325000/425000), and MuJoCo (329000/429000) lockboxes.
SPLITS = {
    "dev": ("dev", 128500, 100, False),
    "cal": ("cal", 228500, 100, False),
    "locked_test": ("test", 327000, 500, True),
    "locked_ood": ("ood", 427000, 300, True),
}


def sample_definition(name: str, episodes: int | None, confirm_locked: bool) -> tuple[str, int, int]:
    """Only development/calibration may use partial samples."""
    if name not in SPLITS:
        raise ValueError("UNKNOWN_FROZEN_SPLIT")
    generator_split, first, maximum, locked = SPLITS[name]
    count = maximum if episodes is None else episodes
    if type(count) is not int or not 1 <= count <= maximum:
        raise ValueError("INVALID_EPISODE_COUNT")
    if locked and (not confirm_locked or count != maximum):
        raise ValueError("LOCKBOX_REQUIRES_EXPLICIT_CONFIRMATION_AND_FULL_SAMPLE")
    return generator_split, first, count


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_checkout(root: Path, expected: str) -> Path:
    """Fail closed on source mismatch or unsafe working-copy overlays."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("SOURCE_ROOT_NOT_DIRECTORY")
    observed = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=20
    ).strip()
    if observed != expected:
        raise ValueError("FROZEN_SOURCE_HEAD_MISMATCH")
    changes = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=no"],
        text=True, timeout=20,
    ).strip()
    if changes:
        raise ValueError("TRACKED_SOURCE_OVERLAY_REFUSED")
    return root


def verify_shared_simulator(v2_root: Path, td_root: Path) -> tuple[Path, Path]:
    """Same shield and deterministic world generator in both source commits."""
    v2_src = v2_root / ARENA_PATH
    td_src = td_root / ARENA_PATH
    for filename, expected in (("arena.py", ARENA_SHA256), ("run.py", RUN_SHA256)):
        for role, parent in (("v2", v2_src), ("td", td_src)):
            try:
                actual = _sha(parent / filename)
            except OSError as error:
                # Source paths in a throwaway runner are not secrets, but retain
                # only the bounded role/basename/error-class in the public log.
                raise ValueError(
                    f"SHARED_SIMULATOR_UNREADABLE role={role} file={filename} "
                    f"error={type(error).__name__}"
                ) from error
            if actual != expected:
                raise ValueError(
                    f"SHARED_SIMULATOR_SHA_MISMATCH role={role} file={filename} "
                    f"expected={expected} observed={actual}"
                )
    if v2_src.resolve() == td_src.resolve():
        raise ValueError("SEPARATE_SOURCE_ROOTS_REQUIRED")
    return v2_src, td_src


def frozen_td_digest(agent) -> str:
    """Exact producer canonicalization from reward-TD PR #160."""
    canonical = [[(repr(key), round(value, 12)) for key, value in
                  sorted(table.items(), key=lambda pair: repr(pair[0]))]
                 for table in agent.weights]
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()


def load_frozen_policies(v2_src: Path, td_src: Path):
    """Load separate policy modules against one byte-identical cached arena."""
    if "arena" in sys.modules or "v2_policy" in sys.modules or "run" in sys.modules:
        raise RuntimeError("UNCONTROLLED_PRELOADED_SIMULATOR_MODULE")
    sys.path.insert(0, str(v2_src))
    try:
        import arena  # type: ignore[import-not-found]
        import run as paired  # type: ignore[import-not-found]
        import v2_policy  # type: ignore[import-not-found]
        spec = importlib.util.spec_from_file_location(
            "frozen_reward_td", td_src / "rl" / "td_agent.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("TD_MODULE_LOAD_FAILED")
        td = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(td)
    finally:
        # TD inserts its own root when imported; restore command's import search.
        for path in (str(v2_src), str(td_src)):
            while path in sys.path:
                sys.path.remove(path)

    v2, v2_fit = v2_policy.fit_v2()
    td_agent, td_fit = td.train(6000)
    if v2.digest() != V2_WEIGHTS or frozen_td_digest(td_agent) != TD_WEIGHTS:
        raise ValueError("FROZEN_MODEL_WEIGHTS_MISMATCH")
    if td_fit.get("teacher_actions_seen") != 0 or td_fit.get("train_seed_range") != [122000, 127999]:
        raise ValueError("UNEXPECTED_TD_TRAINING_PROVENANCE")
    if v2_fit.get("fitted_weight_digest") != V2_WEIGHTS:
        raise ValueError("UNEXPECTED_V2_TRAINING_PROVENANCE")
    return arena, paired, v2_policy, td, v2, td_agent, v2_fit, td_fit


def paired_metric(rows_a: list[dict], rows_b: list[dict], field: str, reps: int = 4000) -> dict:
    """World-resampled descriptive CI for a numeric metric A minus B."""
    if len(rows_a) != len(rows_b) or not rows_a or reps < 100:
        raise ValueError("INVALID_PAIRED_METRIC_INPUT")
    if any(a["seed"] != b["seed"] for a, b in zip(rows_a, rows_b)):
        raise ValueError("UNPAIRED_WORLD_ORDER")
    if field not in ("success", "unsafe", "aborted", "holds", "refusals", "reobservations"):
        raise ValueError("UNREGISTERED_METRIC")
    differences = [float(a[field]) - float(b[field]) for a, b in zip(rows_a, rows_b)]
    random = Random(0x484541443248454144 + sum(map(ord, field)))
    n = len(differences)
    draws = sorted(sum(differences[random.randrange(n)] for _ in range(n))/n
                   for _ in range(reps))
    multiplier = 100 if field in ("success", "unsafe", "aborted") else 1
    return {
        "metric": field,
        "a_minus_b_mean": round(multiplier*statistics.mean(differences), 4),
        "paired_bootstrap_95": [round(multiplier*draws[int(reps*.025)], 4),
                                round(multiplier*draws[min(reps-1, int(reps*.975))], 4)],
        "units": "percentage_points" if multiplier == 100 else "mean_count_per_world",
        "method": f"paired world-level percentile bootstrap, {reps} resamples; descriptive",
    }


def compare_one_split(arena, paired, v2policy, td, v2, td_agent,
                      generator: str, first: int, count: int) -> dict:
    rows = {k: [] for k in ("v2", "td", "constant", "guarded_constant")}
    world_fingerprints = []
    for seed in range(first, first+count):
        world = arena.make_world(generator, seed)
        world_fingerprints.append({
            "seed": seed,
            "world_sha256": hashlib.sha256(
                json.dumps(asdict(world), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        })
        # Every policy runs a fresh Arena(world) with identical independent
        # pseudo-random sensor schedule and the exact same true-geometry shield.
        rows["v2"].append(arena.run_episode(world, "frozen_supervised_v2",
                                             lambda: v2policy.FittedForest(v2.trees)))
        rows["td"].append(arena.run_episode(world, "frozen_reward_td",
                                             lambda: lambda obs: td_agent.action(obs)))
        rows["constant"].append(arena.run_episode(world, "shielded_forward",
                                                   lambda: arena.constant_forward))
        rows["guarded_constant"].append(arena.run_episode(world, "matched_guard_forward",
                                                           lambda: td.guarded_constant_forward))
    for name, records in rows.items():
        if [row["seed"] for row in records] != list(range(first, first+count)):
            raise ValueError(f"WORLD_PAIRING_MISMATCH_{name}")
    source_meta = {"generator": generator, "seed_range": [first, first+count-1], "episodes": count}
    return {
        **source_meta,
        "safety_context": "identical deterministic per-world true-geometry shield; TD has separate scripted stale/deadman fallback",
        "summaries": {name: paired.summarize(values) for name, values in rows.items()},
        "v2_minus_td": {
            "success": paired_metric(rows["v2"], rows["td"], "success"),
            "unsafe": paired_metric(rows["v2"], rows["td"], "unsafe"),
            "aborted": paired_metric(rows["v2"], rows["td"], "aborted"),
            "holds": paired_metric(rows["v2"], rows["td"], "holds"),
            "refusals": paired_metric(rows["v2"], rows["td"], "refusals"),
        },
        "v2_minus_constant_success": paired.paired_bootstrap(rows["v2"], rows["constant"]),
        "td_minus_constant_success": paired.paired_bootstrap(rows["td"], rows["constant"]),
        "td_minus_matched_guard_success": paired.paired_bootstrap(rows["td"], rows["guarded_constant"]),
        "world_fingerprints": world_fingerprints,
        "per_world": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v2-root", type=Path, required=True)
    p.add_argument("--td-root", type=Path, required=True)
    p.add_argument("--split", choices=sorted(SPLITS), required=True)
    p.add_argument("--episodes", type=int, default=None)
    p.add_argument("--confirm-lockbox", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    generator, first, count = sample_definition(args.split, args.episodes, args.confirm_lockbox)
    if args.output.exists():
        raise RuntimeError("REFUSE_OVERWRITE_PREVIOUS_EVIDENCE")
    v2_root = verified_checkout(args.v2_root, V2_SOURCE)
    td_root = verified_checkout(args.td_root, TD_SOURCE)
    v2_src, td_src = verify_shared_simulator(v2_root, td_root)
    arena, paired, v2policy, td, v2, td_agent, v2_fit, td_fit = load_frozen_policies(v2_src, td_src)
    result = compare_one_split(arena, paired, v2policy, td, v2, td_agent, generator, first, count)
    payload = {
        "schema": "junction.rokoko.shared-world-tournament.v1",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "policy_sources": {"v2": V2_SOURCE, "td": TD_SOURCE},
        "weights_sha256": {"v2": V2_WEIGHTS, "td": TD_WEIGHTS},
        "shared_simulator_sha256": {"arena.py": ARENA_SHA256, "run.py": RUN_SHA256},
        "frozen_split": args.split,
        "training": {"v2": v2_fit, "td": td_fit},
        "result": result,
        "interpretation": "Descriptive head-to-head on identical new worlds; no model selection from locked outcomes",
        "limitations": [
            "Synthetic 2D motion only, not MuJoCo or any physical robot/SDK qualification",
            "The safety shield sees true geometry; not a certified interlock",
            "V2 is fitted supervised learning and TD is reward-driven; their scripted fallbacks differ",
            "Do not retune either model or evaluate a replacement against opened lockboxes",
            "Source-reported comparison, not provider-signed telemetry or Euro billing",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
    summary = {k: v for k, v in payload.items() if k != "result"}
    summary["result"] = {k: v for k, v in result.items() if k not in ("per_world", "world_fingerprints")}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
