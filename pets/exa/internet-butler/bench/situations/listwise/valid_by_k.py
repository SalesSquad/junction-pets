#!/usr/bin/env python3
"""Valid-only breakdown by group size k and language: B0, Nemotron, LK (if present) and simple fusions.
Reads only valid files. Usage: valid_by_k.py [runs/list4b_kd]"""
import json, math, sys
from collections import defaultdict
D = "bench/datasets/out/training"
SEP = " … "
own = lambda c: c.split(SEP)[-1]
valid = [json.loads(l) for l in open(f"{D}/valid.jsonl") if l.strip()]


def lse(xs):
    m = max(xs); return m + math.log(sum(math.exp(x - m) for x in xs))


def lsm(xs, T=1.0):
    ys = [x / T for x in xs]; z = lse(ys); return [y - z for y in ys]


def load(p, key):
    d = {}
    for l in open(p):
        j = json.loads(l); d[(j["question"], tuple(j["clauses"]))] = j[key]
    return [d[(r["question"], tuple(r["clauses"]))] for r in valid]


J = {"B0": [lsm(x, 2.0) for x in load("runs/b0/valid_scores.jsonl", "score")],
     "N": [lsm(x, 2.0) for x in load("runs/nemo/valid_scores.jsonl", "lp")]}
if len(sys.argv) > 1:
    J["LK"] = [lsm(x) for x in load(f"{sys.argv[1]}/valid_scores.jsonl", "lp")]
J["B0+N"] = [[a + b for a, b in zip(x, y)] for x, y in zip(J["B0"], J["N"])]
if "LK" in J:
    J["B0+LK"] = [[a + b for a, b in zip(x, y)] for x, y in zip(J["B0"], J["LK"])]
    J["B0+LK+N"] = [[a + b + c for a, b, c in zip(x, y, z)] for x, y, z in zip(J["B0"], J["LK"], J["N"])]
tab = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for i, r in enumerate(valid):
    gold = {c for c, t in enumerate(r["clauses"]) if own(t) == own(r["clauses"][r["target"]])}
    k = len(r["clauses"])
    for name, S in J.items():
        ok = max(range(k), key=lambda c: S[i][c]) in gold
        for key in ("all", f"k={k if k < 6 else '6+'}", f"lang={r.get('lang')}"):
            tab[key][name][0] += 1; tab[key][name][1] += ok
names = list(J)
print("slice".ljust(10), "n".rjust(4), *[n.rjust(8) for n in names])
for key in sorted(tab, key=lambda s: (s != "all", s)):
    n = tab[key][names[0]][0]
    print(key.ljust(10), str(n).rjust(4), *[f"{tab[key][x][1] / n:8.3f}" for x in names])
