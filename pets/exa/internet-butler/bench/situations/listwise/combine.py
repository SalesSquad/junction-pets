#!/usr/bin/env python3
"""Valid-only combiner for clause judges (no test information is used for any choice).

Each judge gives, per group, one score per sibling clause. Scores are turned into per-group log-softmax
(pointwise raw logits are divided by the temperature fitted on valid). The combined score is a weighted
sum. Weights come from a small grid, chosen by 5-fold cross-validation on VALID grouped by provision
(simplest setting within one standard error of the best), then applied once to test.

G1 gate (pre-registered): a fixed 1:1 sum of pointwise and listwise beats pointwise alone on valid by at
least 1.0 point.

Usage:
  combine.py --valid VALID.jsonl --test TEST.jsonl --judge point=runs/b0 --judge list4b=runs/list4b [...] --out runs/combo
Each judge dir holds valid_scores.jsonl and test_scores.jsonl with {"question", "clauses", "score" | "lp"}.
"""
import argparse, itertools, json, math, os, statistics

ap = argparse.ArgumentParser()
ap.add_argument("--valid", required=True); ap.add_argument("--test", required=True)
ap.add_argument("--judge", action="append", required=True, help="name=dir; the first judge is the baseline")
ap.add_argument("--out", required=True)
ap.add_argument("--grid", default="0,0.5,1,1.5,2")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
SEP = " … "
own = lambda c: c.split(SEP)[-1]


def load_items(p):
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    for r in rows:
        g = own(r["clauses"][r["target"]])
        r["gold"] = {i for i, c in enumerate(r["clauses"]) if own(c) == g}
    return rows


def lse(xs):
    m = max(xs); return m + math.log(sum(math.exp(x - m) for x in xs))


def logsoftmax(xs, T=1.0):
    ys = [x / T for x in xs]; z = lse(ys); return [y - z for y in ys]


def load_scores(d, split):
    out = {}
    for l in open(f"{d}/{split}_scores.jsonl", encoding="utf-8"):
        j = json.loads(l)
        out[(j["question"], tuple(j["clauses"]))] = ("lp", j["lp"]) if "lp" in j else ("raw", j["score"])
    return out


valid, test = load_items(a.valid), load_items(a.test)
judges = [tuple(x.split("=", 1)) for x in a.judge]
names = [n for n, _ in judges]


def nll(rows, sc):
    return sum(-lse([s[i] for i in r["gold"]]) for r, s in zip(rows, sc)) / len(rows)


def matrix(rows, split):
    """Per judge, per row: log-softmax over the row's clauses (raw scores temperature-scaled on valid)."""
    per = {}
    for n, d in judges:
        sc = load_scores(d, split)
        vals = []
        for r in rows:
            kind, x = sc[(r["question"], tuple(r["clauses"]))]
            vals.append((kind, x))
        per[n] = vals
    return per


V, Tm = matrix(valid, "valid"), matrix(test, "test")
temps = {}
for n in names:
    if V[n][0][0] == "raw":
        temps[n] = min((0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6), key=lambda T: nll(valid, [logsoftmax(x, T) for _, x in V[n]]))
    else:
        temps[n] = 1.0
Vl = {n: [logsoftmax(x, temps[n]) for _, x in V[n]] for n in names}
Tl = {n: [logsoftmax(x, temps[n]) for _, x in Tm[n]] for n in names}


def combined(L, w, idx):
    return [[sum(w[j] * L[n][i][c] for j, n in enumerate(names)) for c in range(len(L[names[0]][i]))] for i in idx]


def acc(rows, sc):
    return sum(max(range(len(s)), key=lambda c: s[c]) in r["gold"] for r, s in zip(rows, sc)) / len(rows)


report = {"temperatures": temps, "valid_single": {n: round(acc(valid, Vl[n]), 4) for n in names}}
if len(names) >= 2:
    w11 = [1.0, 1.0] + [0.0] * (len(names) - 2)
    g1 = acc(valid, combined(Vl, w11, range(len(valid)))) - acc(valid, Vl[names[0]])
    report["G1_gain_points"] = round(100 * g1, 2)
    report["G1_pass"] = bool(g1 >= 0.01)

# provision-grouped 5-fold CV on valid
prov = sorted({r.get("provision") or r.get("gid") for r in valid})
fold_of = {p: i % 5 for i, p in enumerate(prov)}
folds = [[i for i, r in enumerate(valid) if fold_of[r.get("provision") or r.get("gid")] == f] for f in range(5)]
grid = [float(x) for x in a.grid.split(",")]
cands = [w for w in itertools.product(grid, repeat=len(names)) if any(w)]
res = []
for w in cands:
    accs = []
    for f in folds:
        rows = [valid[i] for i in f]
        accs.append(acc(rows, combined(Vl, w, f)))
    res.append((statistics.mean(accs), statistics.pstdev(accs) / math.sqrt(len(accs)), w))
best = max(res, key=lambda x: x[0])
simple = sorted([x for x in res if x[0] >= best[0] - best[1]], key=lambda x: (sum(v > 0 for v in x[2]), sum(x[2])))[0]
w = simple[2]
report["cv_best"] = {"weights": dict(zip(names, best[2])), "cv_acc": round(best[0], 4)}
report["chosen"] = {"weights": dict(zip(names, w)), "cv_acc": round(simple[0], 4), "rule": "simplest within 1 SE of best"}
report["valid_combined_full"] = round(acc(valid, combined(Vl, w, range(len(valid)))), 4)

# apply once to test; write judgments for the tournament (p = softmax of the combined score)
st = combined(Tl, w, range(len(test)))
with open(f"{a.out}/judgments.jsonl", "w", encoding="utf-8") as f:
    for r, s in zip(test, st):
        z = lse(s)
        for c, v in zip(r["clauses"], s):
            f.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": math.exp(v - z), "score": v, "ms": 0, "tokens": 0}, ensure_ascii=False) + "\n")
json.dump(report, open(f"{a.out}/combine_report.json", "w"), indent=1)
print(json.dumps(report, indent=1))
