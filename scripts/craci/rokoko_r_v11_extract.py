#!/usr/bin/env python3
"""Verify immutable V11 TRAIN source and export same-world aggregates, never raw frames."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import zipfile

from rokoko_r_audit_extract import check, original, sha

ZIP_SHA = "bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae"
SOURCE_SHA = "ab6df4054ef6ed350b479469590a48046a0c0a68"
HARNESS_SHA = "b1938bee9dbca482f645b5dde3359de38e6c125e"
TRAIN_SHA = "c3b3b399344fa18eff7a303cf27e2a510ab9eb74111a6216df1ec11a906579df"
STREAM_SHA = "0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b"
ARMS = ("frozen_v5", "frozen_v6", "frozen_v8", "v10_loss_informed", "v11_goal_preserving")
FIELDS = ("seed", "stratum", "world_hash", "strategy", "safe_goal", "unsafe", "abstained",
          "forward_reopened_after_side", "full_transition_count", "full_transition_sha256")


def valid_public_step(step: dict) -> None:
    for key in ("observation", "next_observation"):
        obs = step.get(key)
        check(isinstance(obs, list) and len(obs) == 18 and
              all(type(x) in (int, float) and float("-inf") < x < float("inf")
                  for x in obs), "invalid public 18D observation")
    mask = step.get("mask")
    check(isinstance(mask, list) and len(mask) == 7 and
          all(type(x) is int and x in (0, 1) for x in mask), "invalid original 7-mask")
    action = step.get("action")
    check(type(action) is int and 0 <= action < 7 and mask[action] == 1,
          "invalid original executed legal action")


def export(path: Path, target: Path) -> dict:
    check(path.is_file(), "missing original archive")
    check(sha(path.read_bytes()) == ZIP_SHA, "original outer V11 archive SHA")
    with zipfile.ZipFile(path) as z:
        receipt = json.loads(z.read("receipt.json"))
        binding = receipt["binding"]
        check(binding["sourceSha"] == SOURCE_SHA and binding["harnessSha"] == HARNESS_SHA,
              "CRACI source/harness receipt binding")
        check(receipt.get("status") == "succeeded" and receipt["providerAttestationVerified"] is False,
              "source-only receipt attestation semantics")
        names = [n for n in z.namelist() if n.endswith("/retention-manifest.json")]
        check(len(names) == 1, "exact retention manifest missing")
        retention = json.loads(z.read(names[0]))
        check(retention["exact_source_sha"] == SOURCE_SHA, "original retention source SHA")
        sources = {s["name"]: s for s in retention["sources"]}
        check("training.json" in sources and "full_transitions.jsonl.gz" in sources,
              "missing original raw sources")
        check(sources["training.json"]["original_sha256"] == TRAIN_SHA, "training original pin")
        check(sources["full_transitions.jsonl.gz"]["original_sha256"] == STREAM_SHA,
              "full option-stream original pin")
        training = json.loads(original(z, sources["training.json"]))
        original(z, sources["full_transitions.jsonl.gz"])
    for k, expected in {
        "schema": "junction.rokoko.v11.goal-first-fresh-train.v1.training",
        "executed_head": SOURCE_SHA, "training_only": True,
        "model_promotion_authorized": False, "no_dev_test_ood": True,
        "actual_trials": 800, "actual_option_transitions": 34992,
    }.items():
        check(training.get(k) == expected, f"immutable training {k} mismatch")
    check(training["actual_physics_engine"] == "mujoco-3.3.7", "engine mismatch")
    check(tuple(training["strategies"]) == ARMS, "strategy source drift")
    scans = training["all_512_public_initial_scans"]
    check(len(scans) == 512, "must retain all 512 public TRAIN scans")
    scan_by_seed = {s["seed"]: s for s in scans}
    check(len(scan_by_seed) == 512 and set(scan_by_seed) == set(range(517000, 517512)),
          "future/train seed namespace drift")
    for s in scans:
        obs, mask = s["observation"], s["mask"]
        check(len(obs) == 18 and all(type(x) in (int, float) and
                                    float("-inf") < x < float("inf") for x in obs),
              "invalid public scan observation")
        check(len(mask) == 7 and all(type(x) is int and x in (0, 1) for x in mask),
              "invalid public scan mask")
    cohort = training["cohort"]
    world_by_seed = {w["seed"]: w for w in cohort}
    check(len(cohort) == 160 and len(world_by_seed) == 160, "160-world paired cohort")
    check(sum(bool(w["observed_corridor"]) for w in cohort) == 128,
          "128 near / 32 clear world source split")
    for seed, world in world_by_seed.items():
        check(scan_by_seed[seed]["world_hash"] == world["world_hash"],
              "original public scan world mismatch")
    check(len(training["trials"]) == 800, "actual trial count mismatch")
    seen, rows = set(), []
    for t in training["trials"]:
        seed, arm = t["seed"], t["strategy"]
        check(seed in world_by_seed and arm in ARMS and (seed, arm) not in seen,
              "missing or duplicate paired trial")
        seen.add((seed, arm))
        world = world_by_seed[seed]
        check(t["world_hash"] == world["world_hash"], "per-trial world SHA mismatch")
        check(type(t["unsafe"]) is bool and type(t["success"]) is bool, "goal flags missing")
        dwell = t["dwell_ticks_final"]
        check(type(dwell) in (int, float) and dwell >= 0, "goal dwell invalid")
        check(len(t["full_transition_sha256"]) == 64, "invalid original trace SHA")
        for step in t["transitions"]:
            valid_public_step(step)
        safe_goal = t["success"] and dwell >= 250 and not t["unsafe"]
        rows.append(dict(seed=seed, stratum="near" if world["observed_corridor"] else "clear",
                         world_hash=world["world_hash"], strategy=arm,
                         safe_goal=int(safe_goal), unsafe=int(t["unsafe"]),
                         abstained=int(t["abstained"]),
                         forward_reopened_after_side=int(t["forward_reopened_after_side"] > 0),
                         full_transition_count=t["full_transition_count"],
                         full_transition_sha256=t["full_transition_sha256"]))
    check(len(seen) == 800 and
          sum(r["full_transition_count"] for r in rows) == 34992, "original count drift")
    by_arm = {arm: {r["seed"]: r for r in rows if r["strategy"] == arm} for arm in ARMS}
    check(all(len(x) == 160 for x in by_arm.values()), "incomplete five-way pairing")
    goals = {arm: sum(x["safe_goal"] for x in v.values()) for arm, v in by_arm.items()}
    check(goals == dict(zip(ARMS, (18, 14, 0, 9, 18))), "source goal-count changed")
    check({a: sum(t["unsafe"] for t in v.values()) for a, v in by_arm.items()} ==
          dict(zip(ARMS, (0, 0, 1, 1, 0))), "original per-arm unsafe-count mismatch")
    baseline = by_arm["frozen_v5"]
    candidate = by_arm["v11_goal_preserving"]
    check(all(baseline[s]["safe_goal"] == candidate[s]["safe_goal"] for s in baseline),
          "unexpected V11 gained/lost goal from pinned evidence")
    check(sum(baseline[s]["full_transition_sha256"] !=
              candidate[s]["full_transition_sha256"] for s in baseline) == 62,
          "changed trace-count source drift")
    check(sum(r["forward_reopened_after_side"] for r in baseline.values()
              if r["stratum"] == "near") == 60, "V5 near reopening source drift")
    check(sum(r["forward_reopened_after_side"] for r in candidate.values()
              if r["stratum"] == "near") == 108, "V11 near reopening source drift")
    target.mkdir(parents=True, exist_ok=False)
    with (target / "v11-trials.csv").open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    provenance = {
        "run_id": 43653579339, "original_zip_sha256": ZIP_SHA,
        "source_head": SOURCE_SHA, "harness_head": HARNESS_SHA,
        "original_train_sha256": TRAIN_SHA, "full_raw_gzip_sha256": STREAM_SHA,
        "worlds": 160, "real_episodes": 800, "original_options": 34992,
        "original_scans": 512, "trials_replayed_as_physics": False,
        "source_receipt_provider_signed": False, "train_only": True,
        "dev_cal_test_ood_opened": False, "model_promotion_authorized": False,
    }
    with (target / "v11-provenance.json").open("x") as f:
        json.dump(provenance, f, indent=2, sort_keys=True)
        f.write("\n")
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v11-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = export(args.v11_zip, args.output_dir)
    print(f"V11_PINNED_OK: {result['real_episodes']} original TRAIN episodes, "
          f"{result['original_options']} option transitions; NO promotion/dispatch")
