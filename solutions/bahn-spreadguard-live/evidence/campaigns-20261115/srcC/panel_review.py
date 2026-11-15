#!/usr/bin/env python3
"""Typed-decision panel over campaign statistics: code computes, Jev and OpenAI Decisions judge.

    python panel_review.py <ref-policy> runs/*.jsonl > runs/panel.json

Each policy's paired statistics against the reference go to both providers as one
state; each answers the same choice question. Code aggregates; no secrets printed.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict

import ai_decide

QUESTION = ai_decide.Question(
    "verdict",
    "A team plays ONE secret final world of a car-transport pricing game. Score = gross margin, but only if "
    "that world's on-time share is at least 90% (otherwise the team is unranked and scores nothing). "
    "`stats` compares a candidate policy with the reference policy on the same practice seeds (paired). "
    "`fail_rate` is the share of worlds under 90% on time; `ranked_margin_delta_pct` counts a failed world "
    "as zero margin. Decide what the team should do with the candidate for the final.",
    [("promote", "Use it as the final default: equal or lower failure risk than the reference and a "
                 "clearly positive ranked-margin gain whose interval mostly excludes zero."),
     ("keep_option", "Promising but not proven: a small or uncertain gain, or a modest extra risk; keep it "
                     "as a documented fallback or gather more seeds."),
     ("reject", "Higher failure risk, or no real ranked-margin gain over the reference.")])


def stats(ref: str, rows: dict[str, dict[str, dict]]) -> dict[str, dict]:
    out = {}
    for pol, seeds in rows.items():
        common = [s for s in seeds if s in rows[ref]]
        if not common:
            continue

        def eff(r: dict) -> float:
            return r["marginCents"] / 100 if r["onTimeShare"] >= 0.90 else 0.0
        cand = [seeds[s] for s in common]
        base = [rows[ref][s] for s in common]
        d = [eff(a) - eff(b) for a, b in zip(cand, base)]
        tot = sum(eff(b) for b in base) or 1.0
        se = statistics.pstdev(d) / max(1, len(d)) ** 0.5 if len(d) > 1 else 0.0
        out[pol] = {
            "policy": pol, "reference": ref, "paired_worlds": len(common),
            "mean_margin_eur": round(statistics.mean(r["marginCents"] for r in cand) / 100),
            "ranked_margin_delta_pct": round(sum(d) / tot * 100, 1),
            "ranked_margin_delta_pct_95ci": [round((sum(d) - 1.96 * se * len(d)) / tot * 100, 1),
                                             round((sum(d) + 1.96 * se * len(d)) / tot * 100, 1)],
            "worlds_better": sum(x > 0 for x in d),
            "fail_rate": round(sum(r["onTimeShare"] < 0.9 for r in cand) / len(cand), 3),
            "reference_fail_rate": round(sum(r["onTimeShare"] < 0.9 for r in base) / len(base), 3),
            "worst_on_time": round(min(r["onTimeShare"] for r in cand), 4),
            "p10_on_time": round(sorted(r["onTimeShare"] for r in cand)[len(cand) // 10], 4),
        }
    return out


def main() -> None:
    ref = sys.argv[1]
    rows: dict[str, dict[str, dict]] = defaultdict(dict)
    for path in sys.argv[2:]:
        for line in open(path):
            if line.strip():
                r = json.loads(line)
                rows[r["policy"]][r["seed"]] = r
    table = stats(ref, rows)
    verdicts = {}
    for pol, st in sorted(table.items()):
        if pol == ref:
            continue
        verdicts[pol] = {"stats": st}
        for prov in ("jev", "openai"):
            try:
                ans, _, ms = ai_decide.decide(prov, {"stats": st}, [QUESTION], timeout=15.0)
                a = ans["verdict"]
                verdicts[pol][prov] = {"choice": a.choice, "p": a.probabilities, "confidence": a.confidence}
            except Exception as exc:  # noqa: BLE001
                verdicts[pol][prov] = {"error": type(exc).__name__}
    print(json.dumps(verdicts, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
