#!/usr/bin/env python3
"""Pre-registered, untuned fusion of the pointwise and listwise judges on the test split.

fused(clause) = log_softmax(pointwise_raw / T_point)(clause) + listwise_lp(clause)
T_point is the pointwise judge's temperature fitted on VALID in its own run (metrics.json). No weight
or threshold is chosen on test. Writes tournament judgments for: listwise alone, and fused.

Usage: fuse_fixed.py --test TEST.jsonl --point POINT_JUDGMENTS.jsonl --t-point 2.0 --list LIST_TEST_SCORES.jsonl --out DIR
"""
import argparse, json, math, os

ap = argparse.ArgumentParser()
ap.add_argument("--test", required=True); ap.add_argument("--point", required=True)
ap.add_argument("--t-point", type=float, required=True); ap.add_argument("--list", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)


def lsm(xs):
    m = max(xs); z = m + math.log(sum(math.exp(x - m) for x in xs)); return [x - z for x in xs]


point = {}
for l in open(a.point, encoding="utf-8"):
    j = json.loads(l); point[j["k"]] = j["score"]
lst = {}
for l in open(a.list, encoding="utf-8"):
    j = json.loads(l); lst[(j["question"], tuple(j["clauses"]))] = j["lp"]
test = [json.loads(l) for l in open(a.test, encoding="utf-8") if l.strip()]
outs = {name: open(f"{a.out}/{name}.judgments.jsonl", "w", encoding="utf-8") for name in ("listwise", "fused")}
missing = 0
for r in test:
    q, cs = r["question"], r["clauses"]
    lp_list = lst.get((q, tuple(cs)))
    raw = [point.get(f"student|{q}|{c}") for c in cs]
    if lp_list is None or any(v is None for v in raw):
        missing += 1
        continue
    lp_point = lsm([v / a.t_point for v in raw])
    for name, s in (("listwise", lsm(lp_list)), ("fused", lsm([x + y for x, y in zip(lp_point, lp_list)]))):
        for c, v in zip(cs, s):
            outs[name].write(json.dumps({"k": f"student|{q}|{c}", "p": math.exp(v), "score": v, "ms": 0, "tokens": 0}, ensure_ascii=False) + "\n")
for f in outs.values():
    f.close()
print(json.dumps({"items": len(test), "missing": missing}))
