#!/usr/bin/env python3
"""Paired summary of run_pair RESULT lines: per policy vs a reference policy.

    python summarize_ai_campaign.py <ref-policy> runs/*.jsonl
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict


def main() -> None:
    ref = sys.argv[1]
    rows: dict[str, dict[str, dict]] = defaultdict(dict)  # policy -> seed -> row
    for path in sys.argv[2:]:
        for line in open(path):
            if line.strip():
                r = json.loads(line)
                rows[r["policy"]][r["seed"]] = r
    print(f"| policy | n | mean margin € | Δ vs {ref} (paired) | 95% CI Δ | better | worst on-time | <90% | <92% | p10 on-time | mean on-time | pass LB95 | score € |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    rng = random.Random(7)
    for pol in sorted(rows, key=lambda p: (p != ref, p)):
        seeds = rows[pol]
        n = len(seeds)
        mean = sum(r["marginCents"] for r in seeds.values()) / n / 100
        worst = min(r["onTimeShare"] for r in seeds.values())
        fail = sum(r["onTimeShare"] < 0.90 for r in seeds.values())
        warn = sum(r["onTimeShare"] < 0.92 for r in seeds.values())
        common = [s for s in seeds if s in rows.get(ref, {})]
        if pol != ref and common:
            # Ranked margin: an unranked world scores nothing in the competition.
            def eff(r: dict) -> float:
                return r["marginCents"] / 100 if r["onTimeShare"] >= 0.90 else 0.0
            d = [eff(seeds[s]) - eff(rows[ref][s]) for s in common]
            base = sum(eff(rows[ref][s]) for s in common)
            delta = sum(d) / base * 100 if base else 0.0
            boots = []
            for _ in range(4000):
                sample = [rng.choice(range(len(d))) for _ in d]
                b = sum(eff(rows[ref][common[i]]) for i in sample)
                boots.append(sum(d[i] for i in sample) / b * 100 if b else 0.0)
            boots.sort()
            ci = f"{boots[100]:+.1f}..{boots[3899]:+.1f}%"
            better = f"{sum(x > 0 for x in d)}/{len(d)}"
            dtxt = f"{delta:+.1f}% (n={len(d)})"
        else:
            ci, better, dtxt = "", "", "reference"
        ots = sorted(r["onTimeShare"] for r in seeds.values())
        p10 = ots[len(ots) // 10]
        mot = sum(ots) / len(ots)
        # Pre-registered score: mean margin x Wilson 95 % lower bound of the pass rate.
        z, ph = 1.96, (n - fail) / n
        lb = (ph + z * z / (2 * n) - z * ((ph * (1 - ph) + z * z / (4 * n)) / n) ** 0.5) / (1 + z * z / n)
        print(f"| {pol} | {n} | {mean:,.0f} | {dtxt} | {ci} | {better} | {worst:.1%} | {fail} | {warn} | {p10:.1%} | {mot:.1%} | {lb:.3f} | {mean * lb:,.0f} |")
    print("\nΔ uses ranked margin: a world under 90% on time counts as €0.")


if __name__ == "__main__":
    main()
