#!/usr/bin/env python3
"""Paired summary of run_campaign.sh JSONL results against the `base` policy.

Usage: summarize_campaigns.py <file.jsonl> ...
Prints a Markdown table per seed group and paired totals per policy.
"""
import collections
import json
import sys


def main(paths: list[str]) -> None:
    rows = [json.loads(line) for path in paths for line in open(path) if line.strip()]
    by_seed: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for row in rows:
        by_seed[row["seed"]][row["policy"]] = row
    policies = sorted({row["policy"] for row in rows} - {"base"})
    print("| Policy | Paired seeds | Base margin € | Policy margin € | Δ € | Δ % | Seeds better | Min on-time | Not ranked |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for policy in policies:
        pairs = [(cells["base"], cells[policy]) for cells in by_seed.values()
                 if "base" in cells and policy in cells]
        if not pairs:
            continue
        base = sum(b["marginCents"] for b, _ in pairs) / 100
        cand = sum(p["marginCents"] for _, p in pairs) / 100
        better = sum(p["marginCents"] > b["marginCents"] for b, p in pairs)
        worst = min(p["onTimeShare"] for _, p in pairs)
        unranked = sum(not p["ranked"] for _, p in pairs)
        print(f"| {policy} | {len(pairs)} | {base:,.0f} | {cand:,.0f} | {cand - base:+,.0f} | "
              f"{(cand - base) / base:+.1%} | {better}/{len(pairs)} | {worst:.1%} | {unranked} |")
    print()
    print("| Seed | " + " | ".join(["base"] + policies) + " |")
    print("|---|" + "---:|" * (len(policies) + 1))
    for seed in sorted(by_seed):
        cells = by_seed[seed]
        out = []
        for policy in ["base"] + policies:
            row = cells.get(policy)
            out.append(f"{row['marginCents'] / 100:,.0f} / {row['wonOrders']} / {row['onTimeShare']:.1%}"
                       if row else "–")
        print(f"| {seed} | " + " | ".join(out) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
