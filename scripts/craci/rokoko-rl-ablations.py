"""Fresh-world Rokoko control ablations; immutable weights and world-seed audit."""
import argparse
import csv
import hashlib
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--trained", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--learner-seed", type=int, required=True)
    parser.add_argument("--test", type=int, default=300)
    parser.add_argument("--ood", type=int, default=200)
    parser.add_argument("--max-seconds", type=int, default=850)
    args = parser.parse_args()
    if args.learner_seed not in (17, 43) or args.test != 300 or args.ood != 200:
        parser.error("Pre-registered learners 17/43 and fresh-world 300/200 grid only")
    if args.max_seconds < 1 or args.max_seconds > 850:
        parser.error("max-seconds must be 1..850")
    learning = args.source_root / "solutions/rokoko-teleoperation-gym/learning"
    sys.path.insert(0, str(learning))
    from train import Q, weights_hash
    from env import ContactEnv, heuristic
    torch.set_num_threads(1)
    torch.manual_seed(args.learner_seed)
    virgin = Q().cpu().eval()
    receipt = json.loads((args.trained / "receipt.json").read_text())
    assert receipt["device"] == "cpu" and not receipt["timed_out"]
    assert receipt["train_episodes"] == 1000 and receipt["gradient_steps"] > 0
    assert receipt["initial_parameter_sha256"] == weights_hash(virgin)
    assert receipt["final_parameter_sha256"] != receipt["initial_parameter_sha256"]
    weights = args.trained / "weights.pt"
    assert hashlib.sha256(weights.read_bytes()).hexdigest() == receipt["weights_sha256"]
    trained = Q().cpu().eval()
    trained.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    assert weights_hash(trained) == receipt["final_parameter_sha256"]
    for model in (virgin, trained):
        model.eval().requires_grad_(False)
        assert all(not p.requires_grad for p in model.parameters())
    env = ContactEnv(60)
    methods = ("trained_q", "untrained_q", "push_medium", "heuristic", "masked_random", "abstain")
    worlds = (("fresh_test", 321000, args.test), ("fresh_ood", 421000, args.ood))
    assert set(range(321000,321300)).isdisjoint(range(320000,320200))
    assert set(range(421000,421200)).isdisjoint(range(420000,420100))
    args.out.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + args.max_seconds
    results = []
    for split, base, count in worlds:
        for i in range(count):
            world_seed = base + i
            for method in methods:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Ablation timed out; incomplete evidence cannot qualify")
                obs = env.reset(world_seed, ood=split=="fresh_ood")
                done = False
                reward_sum = 0.0
                rng = random.Random(world_seed*1009 + 20261114)
                last = {}
                while not done:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Ablation timed out mid-episode")
                    mask = env.mask(obs)
                    if method in ("trained_q", "untrained_q"):
                        model = trained if method == "trained_q" else virgin
                        with torch.no_grad():
                            q = model(torch.as_tensor(obs))
                            action = int(q.masked_fill(~torch.as_tensor(mask), -torch.inf).argmax())
                    elif method == "push_medium":
                        action = 2 if mask[2] else (5 if mask[5] else 6)
                    elif method == "heuristic":
                        action = heuristic(obs, mask)
                    elif method == "masked_random":
                        allowed = np.flatnonzero(mask[:6])
                        action = int(rng.choice(allowed.tolist())) if allowed.size else 6
                    else:
                        action = 6
                    obs, reward, done, last = env.step(action)
                    reward_sum += reward
                results.append(dict(split=split, world_seed=world_seed, method=method,
                    success=bool(last["success"]), unsafe=bool(last["unsafe"]),
                    return_value=round(reward_sum, 8), options=env.steps,
                    final_error=round(last["error"], 7),
                    peak_impulse=round(last["peak_impulse"], 8),
                    physics_steps=env.physics_steps))
    grouped = defaultdict(dict)
    for r in results:
        grouped[(r["split"],r["world_seed"])][r["method"]] = r
    assert len(grouped) == args.test+args.ood
    assert all(set(g)==set(methods) for g in grouped.values())
    by_split = {}
    ci_rng = random.Random(20261114)
    for split, _, count in worlds:
        cells = [g for (group,seed),g in sorted(grouped.items()) if group==split]
        by_split[split] = {
            method: {
                "episodes":count,
                "success":sum(g[method]["success"] for g in cells),
                "unsafe":sum(g[method]["unsafe"] for g in cells),
                "unsafe_worlds":[seed for (group,seed),g in sorted(grouped.items()) if group==split and g[method]["unsafe"]],
                "mean_options":round(sum(g[method]["options"] for g in cells)/count,3)
            } for method in methods}
        for method in ("untrained_q","push_medium","heuristic","masked_random","abstain"):
            diffs=[int(g["trained_q"]["success"])-int(g[method]["success"]) for g in cells]
            boots=sorted(sum(diffs[ci_rng.randrange(count)] for _ in range(count))/count for _ in range(5000))
            by_split[split][method]["trained_minus_baseline_success_pp"]=round(100*sum(diffs)/count,3)
            by_split[split][method]["paired_bootstrap_95pct_pp"]=[
                round(100*boots[int(len(boots)*.025)],3),
                round(100*boots[int(len(boots)*.975)],3)]
    empirical_claim = ("DISCOVERY_ONLY_OOD_UNSAFE" if by_split["fresh_ood"]["trained_q"]["unsafe"]
                       else "DISCOVERY_ONLY_SYNTHETIC")
    report = {
        "schema":"craci.rokoko-rl-fresh-world-ablations.v1",
        "worlds_test":args.test,"worlds_ood":args.ood,
        "test_seed_range":[321000,321000+args.test-1],
        "ood_seed_range":[421000,421000+args.ood-1],
        "shared_worlds_paired":True, "trained_sha256":receipt["final_parameter_sha256"],
        "initial_sha256":receipt["initial_parameter_sha256"],
        "source_commit":receipt["source_commit"],
        "learner_seed":args.learner_seed,
        "methods":list(methods), "pre_registered":True,
        "quality_claim":empirical_claim,
        "source_only_simulation":True,"real_hardware_safety":False,
        "fresh_worlds_vs_previous_exploratory":True,
        "results":by_split
    }
    with (args.out/"episodes.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))


if __name__ == "__main__":
    main()
