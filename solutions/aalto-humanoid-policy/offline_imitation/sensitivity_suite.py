#!/usr/bin/env python3
"""Five fixed episode-holdout runs; report ALL seeds including regressions.

Offline public LeRobot Parquet only. This is joint-action prediction, not robot
behavior, safety, Isaac simulation or a physical task-success measurement.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

import offline_study as base

SEEDS = (20261114, 20261115, 20261116, 20261117, 20261118)
IMPROVEMENT_GATE = 0.05
REFERENCES = ("train_mean", "state_identity", "nearest_state_1nn")


def aggregate(reports: list[dict]) -> dict:
    if [r.get("split_seed") for r in reports] != list(SEEDS):
        raise ValueError("must report all five fixed held-out seeds in order")
    source = reports[0]["dataset"]
    if any(r["dataset"] != source or r["code_sha256"] != reports[0]["code_sha256"]
           for r in reports[1:]):
        raise ValueError("source/data/code provenance changed across held-out runs")
    seed_rows, exposure = [], {str(i): [] for i in range(base.N_EPISODES)}
    for r in reports:
        scores = {key: r["metrics"][key]["episode_macro_mae_rad"]
                  for key in (*REFERENCES, "ridge")}
        reference_name = min(REFERENCES, key=lambda k: (scores[k], k))
        reference = scores[reference_name]
        candidate = scores["ridge"]
        gain = (reference - candidate) / reference if reference > 0 else 0.0
        if abs(gain - r["ridge_relative_gain_over_best_deployable_baseline"]) > 1e-10:
            raise ValueError("stored relative gain disagrees with source metrics")
        seed_rows.append({"seed": r["split_seed"], "train_episode_ids": r["split"]["train"],
                          "validation_episode_ids": r["split"]["validation"],
                          "test_episode_ids": r["split"]["test"],
                          "test_frame_count": r["frame_counts"]["test"],
                          "ridge_alpha_selected_on_validation": r["selection"]["ridge_alpha"],
                          "ridge_validation_macro_mae_rad": r["selection"]["validation_macro_mae_by_alpha"][str(r["selection"]["ridge_alpha"])],
                          "reference_name": reference_name, "reference_test_macro_mae_rad": reference,
                          "ridge_test_macro_mae_rad": candidate,
                          "ridge_gain_fraction": gain})
        for ep in r["split"]["test"]:
            key = str(ep)
            exposure[key].append({"seed": r["split_seed"],
                                  "reference_mae_rad": r["metrics"][reference_name]["per_episode_mae_rad"][key],
                                  "ridge_mae_rad": r["metrics"]["ridge"]["per_episode_mae_rad"][key]})
    gains = [row["ridge_gain_fraction"] for row in seed_rows]
    per_episode = {
        key: {"test_exposures": len(rows), "rows": rows,
              "ridge_mae_median_rad": statistics.median(x["ridge_mae_rad"] for x in rows) if rows else None,
              "reference_mae_median_rad": statistics.median(x["reference_mae_rad"] for x in rows) if rows else None}
        for key, rows in exposure.items()
    }
    return {"result": "PUBLIC_DATA_HELDOUT_SENSITIVITY_NOT_ROBOT_SUCCESS",
            "source_dataset": source, "source_code_sha256": reports[0]["code_sha256"],
            "seeds_fixed_before_evaluation": list(SEEDS),
            "per_seed": seed_rows,
            "summary": {"median_gain_fraction": statistics.median(gains),
                        "worst_gain_fraction": min(gains),
                        "best_gain_fraction": max(gains),
                        "positive_gain_seeds": sum(g > 0 for g in gains),
                        "total_seeds": len(gains),
                        "episodes_ever_tested": sum(bool(x) for x in exposure.values()),
                        "test_exposures_not_independent": sum(map(len, exposure.values())),
                        "minimum_accepted_gain_fraction_each_seed": IMPROVEMENT_GATE,
                        "robust_improvement_pass": all(g >= IMPROVEMENT_GATE for g in gains)},
            "per_episode_heldout_exposures": per_episode,
            "limitations": ["Twenty sponsor episodes only; repeats overlap and are not independent samples.",
                            "Validation tunes alpha separately inside each split; never tune on test episodes.",
                            "All positive and negative seed results retained, no split cherry-picking.",
                            "No actuator, simulator, safety or task-success evidence."]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-root", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path,
                   help="new non-existing output dir; five run subdirs + summary.json")
    a = p.parse_args(argv)
    try:
        base.dataset_preflight(a.dataset_root)
        a.output.mkdir(parents=True, exist_ok=False)
        receipts = [base.run_study(a.dataset_root, a.output / f"seed-{seed}", seed)
                    for seed in SEEDS]
        summary = aggregate(receipts)
        summary["created_at"] = datetime.now(timezone.utc).isoformat()
        summary["sensitivity_suite_sha256"] = base.digest_file(Path(__file__).resolve())
        (a.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, RuntimeError) as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"result": summary["result"], "output": str(a.output),
                      "summary": summary["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
