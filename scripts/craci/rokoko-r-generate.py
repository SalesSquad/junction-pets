#!/usr/bin/env python3
"""Generate matched Rokoko MuJoCo rollout data for a CRACI/R policy-selector tournament.

Uses the pinned existing MuJoCo simulator, not invented labels. The fixed
source SHA is independently checked by the workflow before this starts.
Features are captured only BEFORE an episode, never from outcomes.
"""
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

PIN = "59479b42b177c1829a2e6678adfff1fb68aef09c"
SPLITS = (("train", 270000, 80), ("cal", 370000, 40),
          ("test", 390000, 60), ("ood", 490000, 40))
POLICIES = ("push_medium", "heuristic")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cohort", type=int, choices=range(4), required=True)
    p.add_argument("--max-seconds", type=int, default=1050)
    a = p.parse_args()
    if not 60 <= a.max_seconds <= 1100:
        p.error("max-seconds 60..1100")
    learning = a.source_root / "solutions/rokoko-teleoperation-gym/learning"
    scene = a.source_root / "solutions/rokoko-teleoperation-gym/sim/scene.xml"
    if not (learning / "env.py").is_file() or not scene.is_file():
        raise RuntimeError("Immutable Rokoko simulation source absent")
    sys.path.insert(0, str(learning))
    import numpy as np
    from env import ContactEnv, heuristic
    env = ContactEnv(max_options=60)
    start = time.monotonic()
    headers = ["split", "world_id", "cohort", "policy", "success", "unsafe",
               "options", "return_value"] + [f"x{i:02d}" for i in range(1, 19)]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with a.out.open("x", newline="", encoding="utf8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for split, base, count in SPLITS:
            counts[split] = 0
            for index in range(count):
                world = base + a.cohort * 3000 + index
                initial = None
                for policy in POLICIES:
                    if time.monotonic() - start > a.max_seconds:
                        raise TimeoutError(f"Incomplete cohort {a.cohort}: deadline")
                    obs = env.reset(world, ood=(split == "ood"))
                    if initial is None:
                        initial = np.array(obs, copy=True)
                    elif not np.array_equal(initial, obs):
                        raise RuntimeError("Matched worlds do not share initial features")
                    total = 0.0
                    done = False
                    info = {}
                    while not done:
                        if time.monotonic() - start > a.max_seconds:
                            raise TimeoutError("Deadline during episode; never qualify partial results")
                        mask = env.mask(obs)
                        if policy == "push_medium":
                            action = 2 if mask[2] else (5 if mask[5] else 6)
                        else:
                            action = int(heuristic(obs, mask))
                        obs, reward, done, info = env.step(action)
                        total += float(reward)
                    row = dict(split=split, world_id=world, cohort=a.cohort,
                               policy=policy, success=int(info["success"]),
                               unsafe=int(info["unsafe"]), options=env.steps,
                               return_value=round(total, 6))
                    row.update({f"x{i + 1:02d}": format(float(val), ".9g")
                                for i, val in enumerate(initial)})
                    writer.writerow(row)
                counts[split] += 1
    digest = hashlib.sha256(a.out.read_bytes()).hexdigest()
    report = {"schema": "craci.rokoko-r-policy-worlds.v1",
              "simulator_source_sha": PIN, "cohort": a.cohort,
              "counts_worlds": counts, "policies": list(POLICIES),
              "all_paired": True, "fresh_test_not_in_training": True,
              "hardware_safety": False, "data_kind": "synthetic_physics",
              "csv_sha256": digest, "elapsed_sec": round(time.monotonic() - start, 2)}
    (a.out.parent / "dataset-receipt.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
