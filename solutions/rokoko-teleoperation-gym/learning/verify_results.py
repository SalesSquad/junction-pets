#!/usr/bin/env python3
"""Independent source/paired-result verification; no model execution or training."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
REPO = HERE.parents[2]
METHODS = frozenset(("dqn", "heuristic", "abstain"))
SPLITS = {
    "train": (120000, ("dqn",)),
    "cal": (220000, tuple(sorted(METHODS))),
    "test": (320000, tuple(sorted(METHODS))),
    "ood": (420000, tuple(sorted(METHODS))),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_source(receipt):
    commit = receipt.get("source_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("Source commit missing or malformed")
    manifest = receipt.get("producing_sha256")
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("No executable source SHA-256 attestation")
    for relative_path, expected_sha in manifest.items():
        if (not isinstance(relative_path, str) or
                relative_path.startswith("/") or
                ".." in Path(relative_path).parts):
            raise ValueError("Unsafe path in source attestation")
        blob = subprocess.check_output(
            ["git", "-C", str(REPO), "show",
             f"{commit}:solutions/rokoko-teleoperation-gym/{relative_path}"],
            timeout=25,
        )
        if hashlib.sha256(blob).hexdigest() != expected_sha:
            raise ValueError(f"Producer SHA mismatch: {relative_path}")
    return commit


def bool_value(value):
    if value in ("True", "true", True):
        return True
    if value in ("False", "false", False):
        return False
    raise ValueError(f"Unexpected boolean: {value!r}")


def summarize_rows(path):
    records = list(csv.DictReader(path.open(newline="", encoding="utf8")))
    if not records:
        raise ValueError("No episode rows")
    combos = {}
    stats = {}
    all_physics = 0
    for row in records:
        split = row.get("split")
        if split not in SPLITS:
            raise ValueError(f"Unknown split {split}")
        base, methods = SPLITS[split]
        method = row.get("method")
        seed = int(row["seed"])
        if method not in methods or not (base <= seed < base + 10000):
            raise ValueError(f"Invalid split/method/seed {split}/{method}/{seed}")
        key = (split, seed, method)
        if key in combos:
            raise ValueError("Duplicate split/seed/method")
        combos[key] = row
        if not bool_value(row["complete"]):
            raise ValueError(f"Incomplete episode {key}; preserve but do not qualify")
        physics = int(row["physics_steps"])
        if physics < 0:
            raise ValueError(f"Negative physics steps for {key}")
        all_physics += physics
        pair = (split, method)
        st = stats.setdefault(pair, {"episodes":0,"success":0,"unsafe":0,
                                   "abstained":0,"physics_steps":0})
        st["episodes"] += 1
        success = bool_value(row["success"])
        unsafe = bool_value(row["unsafe"])
        if success and unsafe:
            raise ValueError("Inconsistent success and unsafe")
        st["success"] += success
        st["unsafe"] += unsafe
        st["abstained"] += bool_value(row["abstained"])
        st["physics_steps"] += physics
    for split, (base, methods) in SPLITS.items():
        seeds = {seed for s, seed, method in combos if s == split}
        if len(seeds) != 0 and seeds != set(range(base, base + len(seeds))):
            raise ValueError(f"Split {split} has missing/noncontiguous seeded worlds")
        if split != "train":
            for seed in seeds:
                if {m for s, x, m in combos if s == split and x == seed} != set(methods):
                    raise ValueError(f"Split {split} not paired at seed {seed}")
    return records, stats, all_physics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result_dir = args.run_dir.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((result_dir/"receipt.json").read_text())
    cfg = json.loads((result_dir/"frozen-config.json").read_text())
    commit = verify_source(receipt)
    if receipt.get("device") != "cuda" or not receipt.get("cuda_device"):
        raise ValueError("GPU did not execute CUDA training")
    if receipt.get("gradient_steps", 0) < 1 or \
       receipt.get("initial_parameter_sha256") == receipt.get("final_parameter_sha256"):
        raise ValueError("No verified neural parameter learning")
    if sha256(result_dir/"weights.pt") != receipt.get("weights_sha256"):
        raise ValueError("Weights changed since source-bound execution")
    rows, stats, physics = summarize_rows(result_dir/"episodes.csv")
    if physics != receipt["physics_steps"]:
        raise ValueError("Receipt physics-step totals do not equal raw episode rows")
    raw_summary = receipt.get("summary", {})
    for (split, method), values in stats.items():
        entry = raw_summary[f"{split}/{method}"]
        if entry["episodes"] != values["episodes"] or \
           entry["success"] != values["success"] or \
           entry["unsafe"] != values["unsafe"]:
            raise ValueError(f"Receipt mismatched actual data: {split}/{method}")
        expected = int(cfg[f"{split}_episodes"])
        if expected != values["episodes"]:
            raise ValueError(f"Not all planned episodes qualified: {split}/{method}")
    if receipt.get("timed_out"):
        raise ValueError("Run did not complete under its declared ceiling")
    attestation = {
        "schema":"motionbridge.learning-independent-validation.v1",
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_commit":commit,
        "source_hashes_equal_pinned_git_blobs":True,
        "parameter_sha256_changed":True,
        "weights_sha256_equal_receipt":True,
        "all_declared_episodes_complete_and_paired":True,
        "gpu_model":receipt["cuda_device"],
        "gradient_steps":receipt["gradient_steps"],
        "training_transitions":receipt["train_transitions"],
        "physics_solver_steps_actual":physics,
        "total_episode_rows":len(rows),
        "episodes_csv_sha256":sha256(result_dir/"episodes.csv"),
        "episodes_jsonl_sha256":sha256(result_dir/"episodes.jsonl"),
        "receipt_sha256":sha256(result_dir/"receipt.json"),
        "summary":{f"{s}/{m}":v for (s,m),v in stats.items()},
        "quality_claim_original":receipt["quality_claim"],
        "physical_robot_qualified":False,
        "nvidia_isaac_qualified":False,
        "third_party_model_used":False,
    }
    output.write_text(json.dumps(attestation, indent=2, sort_keys=True)+"\n")
    print(json.dumps({k:attestation[k] for k in ("source_commit",
        "gradient_steps","training_transitions","physics_solver_steps_actual",
        "total_episode_rows","quality_claim_original")},sort_keys=True))


if __name__ == "__main__":
    main()
