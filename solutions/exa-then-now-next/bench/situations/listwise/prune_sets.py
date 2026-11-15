#!/usr/bin/env python3
"""Prune-then-listwise inputs: for every group with k > m, keep B0's top-m clauses (B0 raw scores, the same
order for valid and test, no labels used for pruning). Writes OUT/{valid,test}_m{m}.jsonl (default runs/prune;
the 2026-11-15 rounds used verda/job3/prune) with only those groups; `target` is remapped to the kept gold
clause, or to slot 0 when B0 pruned the gold out (those rows are counted as misses by the merge step, never by
train_list's own printout). Also reports B0 top-m recall on VALID only.
Usage (from the repository root): python3 bench/situations/listwise/prune_sets.py --m 3 4 5 [--out runs/prune]"""
import argparse, json, os
D = "bench/datasets/out/training"
SEP = " … "
own = lambda c: c.split(SEP)[-1]
ap = argparse.ArgumentParser(); ap.add_argument("--m", type=int, nargs="+", default=[3, 4, 5])
ap.add_argument("--out", default="runs/prune")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)


def b0(split):
    return {(j["question"], tuple(j["clauses"])): j["score"] for j in map(json.loads, open(f"runs/b0/{split}_scores.jsonl"))}


for split in ("valid", "test"):
    rows = [json.loads(l) for l in open(f"{D}/{split}.jsonl") if l.strip()]
    sc = b0(split)
    for m in a.m:
        out, kept_gold = [], 0
        for r in rows:
            k = len(r["clauses"])
            if k <= m:
                continue
            s = sc[(r["question"], tuple(r["clauses"]))]
            keep = sorted(sorted(range(k), key=lambda i: -s[i])[:m])  # original clause order inside the kept set
            g = own(r["clauses"][r["target"]])
            gold_slots = [j for j, i in enumerate(keep) if own(r["clauses"][i]) == g]
            kept_gold += bool(gold_slots)
            out.append({**r, "clauses": [r["clauses"][i] for i in keep], "target": gold_slots[0] if gold_slots else 0,
                        "orig_clauses": r["clauses"], "keep": keep})
        with open(f"{a.out}/{split}_m{m}.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in out)
        msg = {"split": split, "m": m, "groups": len(out)}
        if split == "valid":
            msg["b0_top_m_recall"] = round(kept_gold / max(1, len(out)), 4)
        print(json.dumps(msg))
