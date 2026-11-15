#!/usr/bin/env python3
"""Network-free BAHN calibration: independent fresh seeds, exact cent ledger, no live Spread."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--shard", type=int, required=True)
parser.add_argument("--shards", type=int, default=8)
parser.add_argument("--seeds-per-shard", type=int, default=10000)
parser.add_argument("--base", type=int, default=700000)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
assert 0 <= args.shard < args.shards == 8
assert args.seeds_per_shard == 10000 and args.base == 700000
source = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
expected = os.environ["CRACI_SOURCE_SHA"]
assert len(expected) == 40 and all(c in "0123456789abcdef" for c in expected)
assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == expected
module_path = source / "solutions" / "bahn-freight-optimizer" / "optimizer.py"
spec = importlib.util.spec_from_file_location("bahn_verified_offline", module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert module.LABEL == "SYNTHETIC_OFFLINE"
assert module.TRAIN == (11, 29, 47) and module.HOLDOUT == (101, 211, 307)
args.out.mkdir(parents=True, exist_ok=False)
rng_start = args.base + args.shard * args.seeds_per_shard
rng_stop = rng_start + args.seeds_per_shard
assert not (set(range(rng_start, rng_stop)) & set(module.TRAIN + module.HOLDOUT))
columns = ["seed", "baseline_won", "baseline_ontime", "baseline_margin_cents",
           "baseline_ranked", "optimizer_won", "optimizer_ontime",
           "optimizer_margin_cents", "optimizer_ranked"]
totals = {f"{p}_{k}": 0 for p in ("baseline", "optimizer")
          for k in ("won", "ontime", "margin_cents", "ranked")}
quoted_by_level = {str(level): 0 for level in range(1, 9)}
abstained_by_level = {str(level): 0 for level in range(1, 9)}
on_time_counterexamples = []
start = time.monotonic()

def validated_simulation(seed, policy):
    result = module.simulate(seed, policy)
    assert result["seed"] == seed and result["policy"] == policy
    won, ontime, margin = (result["wonOrders"], result["onTimeOrders"], result["grossMarginCents"])
    assert type(won) is int and type(ontime) is int and type(margin) is int
    assert 0 <= ontime <= won <= 40 and len(result["ledger"]) == won
    assert (result["onTimeBps"] == ontime * 10000 // won if won else result["onTimeBps"] is None)
    assert result["ranked"] is (won > 0 and ontime * 10 >= won * 9)
    assert margin == sum(entry["revenueCents"] - entry["driverFeeCents"] for entry in result["ledger"])
    assert ontime == sum(entry["onTime"] is True for entry in result["ledger"])
    assert len(set(entry["requestId"] for entry in result["ledger"])) == won
    assert all(type(entry["revenueCents"]) is int and type(entry["driverFeeCents"]) is int
               and type(entry["onTime"]) is bool for entry in result["ledger"])
    totals[f"{policy}_won"] += won
    totals[f"{policy}_ontime"] += ontime
    totals[f"{policy}_margin_cents"] += margin
    totals[f"{policy}_ranked"] += int(result["ranked"])
    return result

with (args.out / "paired-seeds.csv").open("x", newline="", encoding="utf8") as stream:
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for seed in range(rng_start, rng_stop):
        baseline = validated_simulation(seed, "baseline")
        optimizer = validated_simulation(seed, "optimizer")
        writer.writerow({
            "seed": seed,
            "baseline_won": baseline["wonOrders"],
            "baseline_ontime": baseline["onTimeOrders"],
            "baseline_margin_cents": baseline["grossMarginCents"],
            "baseline_ranked": int(baseline["ranked"]),
            "optimizer_won": optimizer["wonOrders"],
            "optimizer_ontime": optimizer["onTimeOrders"],
            "optimizer_margin_cents": optimizer["grossMarginCents"],
            "optimizer_ranked": int(optimizer["ranked"]),
        })
        # Frozen 3+3 comparator seeds are excluded; 8 levels only validate the heuristic,
        # NOT true delivery performance outside level 8.
        if (seed - rng_start) % 125 == 0:
            for level in range(1, 9):
                snapshot = module.scenario(seed, level=level, count=40)
                result = module.recommend(snapshot)
                assert result["mode"] == "SYNTHETIC_OFFLINE"
                assert result["signed"] is False and len(result["rows"]) == 40
                for row in result["rows"]:
                    assert row["decision"] in ("QUOTE", "ABSTAIN")
                    if row["decision"] == "QUOTE":
                        option = row["recommendation"]
                        assert option["lowerSafetyBps"] >= 9000
                        assert option["reservedMarginCents"] > 0
                        assert type(option["priceCents"]) is int
                        assert type(option["feeCents"]) is int
                        quoted_by_level[str(level)] += 1
                    else:
                        abstained_by_level[str(level)] += 1
        if optimizer["wonOrders"] > 0 and not optimizer["ranked"] and len(on_time_counterexamples) < 100:
            on_time_counterexamples.append({
                "seed": seed, "optimizer_won": optimizer["wonOrders"],
                "optimizer_ontime": optimizer["onTimeOrders"],
                "ontime_bps": optimizer["onTimeBps"],
            })
assert totals["baseline_won"] >= totals["baseline_ontime"] >= 0
assert totals["optimizer_won"] >= totals["optimizer_ontime"] >= 0
assert all(quoted_by_level[str(k)] + abstained_by_level[str(k)] == 80 * 40 for k in range(1, 9))
def bps(policy):
    return totals[f"{policy}_ontime"] * 10000 // totals[f"{policy}_won"] if totals[f"{policy}_won"] else None
proof = {
    "schema": "craci.bahn-offline-cluster-calibration.v1",
    "qualification": "STRICT_INTERNAL_INVARIANTS_ONLY",
    "source_sha": expected,
    "source_file_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
    "seed_start": rng_start,
    "seed_end_exclusive": rng_stop,
    "seed_count": args.seeds_per_shard,
    "shard": args.shard, "shards": args.shards,
    "policy": "PAIRED_SAME_OUTCOME_RANDOMNESS_LEVEL_8",
    "level_sweep": "ALL_8_HEURISTIC_ONLY_NOT_OUTCOME_QUALIFICATION",
    "per_level_quotes": quoted_by_level,
    "per_level_abstentions": abstained_by_level,
    "totals": totals,
    "aggregate_baseline_ontime_bps": bps("baseline"),
    "aggregate_optimizer_ontime_bps": bps("optimizer"),
    "optimizer_90pct_aggregate_observed": bool((bps("optimizer") or 0) >= 9000),
    "counterexamples_first100": on_time_counterexamples,
    "duration_seconds": round(time.monotonic() - start, 3),
    "actual_delivery_evidence": False,
    "sponsor_connected": False,
    "spread_key_accessed": False,
    "commercial_actions": False,
}
(args.out / "coverage-proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in proof.items() if k not in ("counterexamples_first100","per_level_quotes","per_level_abstentions")}, sort_keys=True))
