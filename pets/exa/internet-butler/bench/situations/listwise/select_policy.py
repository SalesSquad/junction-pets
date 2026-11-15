#!/usr/bin/env python3
"""Valid-only policy selection: on-device student, cloud teachers, fusion, and confidence cascade.

Every choice (temperatures, fusion weight, cascade threshold, Finnish teacher, final policy) is made on VALID
with provision-grouped 5-fold cross-validation. Test is touched once, after the choice, to write tournament
judgments. Test accuracy is never computed here (compare.py / the tournament report it after the protocol
amendment that names the rule).

Language rule (owner, 2026-11-15): Nemotron (--teacher) is never used on Finnish rows. Finnish rows use one of
the --fi-teacher candidates (TypeSafe Jev, Claude Haiku ...), their sum, or no teacher; the choice is part of the
same CV selection.

Policies
  student            on-device side alone (temperature-scaled log-softmax)
  teacher            teacher alone (rows without a teacher fall back to the side)
  fuse(w)            w*side + teacher
  cascade(tau, w)    side if its top probability >= tau, else fuse(w)
The teacher call rate of each policy is reported (the cascade exists to cut cloud calls).

Usage:
  select_policy.py --valid V.jsonl --test T.jsonl --student runs/b0 --teacher runs/nemo [--extra lk=runs/lk]
                   [--fi-teacher haiku=runs/haiku_fi --fi-teacher jev=runs/jev_fi] --out runs/policy
Each judge dir holds valid_scores.jsonl and test_scores.jsonl rows {"question","clauses", "score"|"lp"}.
Finnish-teacher dirs may hold Finnish rows only.
"""
import argparse, json, math, os, re, statistics

ap = argparse.ArgumentParser()
ap.add_argument("--valid", required=True); ap.add_argument("--test", required=True)
ap.add_argument("--student", required=True); ap.add_argument("--teacher", required=True)
ap.add_argument("--extra", action="append", default=[], help="name=dir, on-device judges added to the student side")
ap.add_argument("--fi-teacher", action="append", default=[], help="name=dir, candidate teachers for Finnish rows")
ap.add_argument("--fi-lang", default="Finnish")
ap.add_argument("--out", required=True)
ap.add_argument("--wgrid", default="0.25,0.5,0.75,1,1.5,2,3")
ap.add_argument("--taugrid", default="0.5,0.6,0.7,0.8,0.85,0.9,0.95,0.98,1.01")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
SEP = " … "
own = lambda c: c.split(SEP)[-1]
TEMPS = (0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6)


def load_items(p):
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    for r in rows:
        g = own(r["clauses"][r["target"]])
        r["gold"] = {i for i, c in enumerate(r["clauses"]) if own(c) == g}
    return rows


def lse(xs):
    m = max(xs); return m + math.log(sum(math.exp(x - m) for x in xs))


def lsm(xs, T=1.0):
    ys = [x / T for x in xs]; z = lse(ys); return [y - z for y in ys]


def scores(d, split, rows, partial):
    sc = {}
    for l in open(f"{d}/{split}_scores.jsonl", encoding="utf-8"):
        j = json.loads(l)
        sc[(j["question"], tuple(j["clauses"]))] = j["lp"] if "lp" in j else j["score"]
    keys = [(r["question"], tuple(r["clauses"])) for r in rows]
    if not partial:
        return [sc[k] for k in keys]
    return [sc.get(k) for k in keys]


def nll(rows, L):
    return sum(-lse([s[i] for i in r["gold"]]) for r, s in zip(rows, L)) / len(rows)


def calibrated(d, valid, test, partial=False, fit_rows=None):
    """Valid-fitted temperature (raw scores and permutation-averaged log-probs alike); None where a row is absent.
    fit_rows (a predicate on a valid row) limits the rows the temperature is fitted on."""
    V, T = scores(d, "valid", valid, partial), scores(d, "test", test, partial)
    have = [(r, x) for r, x in zip(valid, V) if x is not None and (fit_rows is None or fit_rows(r))]
    temp = min(TEMPS, key=lambda t: nll([r for r, _ in have], [lsm(x, t) for _, x in have]))
    return temp, [lsm(x, temp) if x is not None else None for x in V], [lsm(x, temp) if x is not None else None for x in T]


valid, test = load_items(a.valid), load_items(a.test)
judges = [("student", a.student)] + [tuple(x.split("=", 1)) for x in a.extra] + [("teacher", a.teacher)]
fi_judges = [tuple(x.split("=", 1)) for x in a.fi_teacher]
temps, VL, TL = {}, {}, {}
for n, d in judges:
    # Nemotron's temperature is fitted on non-Finnish valid rows only, so its Finnish scores cannot reach any
    # choice (fix of 2026-11-15 after the verification found the leak through the temperature fit)
    fit = (lambda r: r.get("lang") != a.fi_lang) if n == "teacher" else None
    temps[n], VL[n], TL[n] = calibrated(d, valid, test, fit_rows=fit)
for n, d in fi_judges:
    temps[n], VL[n], TL[n] = calibrated(d, valid, test, partial=True)
IS_FI = {"valid": [r.get("lang") == a.fi_lang for r in valid], "test": [r.get("lang") == a.fi_lang for r in test]}
for split, L in (("valid", VL), ("test", TL)):
    for n, _ in fi_judges:
        miss = sum(1 for i, f in enumerate(IS_FI[split]) if f and L[n][i] is None)
        assert miss == 0, f"{n} lacks {miss} Finnish {split} rows"

extras = [n for n, _ in judges if n not in ("student", "teacher")]
SIDES = [{"student": 1.0}]
for n in extras:
    SIDES += [{n: 1.0}] + [{"student": 1.0, n: v} for v in (0.5, 1.0, 2.0)]
FI_OPTS = [()] + [(n,) for n, _ in fi_judges] + ([tuple(n for n, _ in fi_judges)] if len(fi_judges) > 1 else [])


def side_scores(L, i, side):
    return lsm([sum(w * L[n][i][c] for n, w in side.items()) for c in range(len(L["student"][i]))])


def teacher_scores(L, i, fi_row, fi_opt):
    if not fi_row:
        return L["teacher"][i]  # Nemotron, never on Finnish rows
    if not fi_opt:
        return None
    return lsm([sum(L[n][i][c] for n in fi_opt) for c in range(len(L["student"][i]))])


def policy_scores(L, split, idx, pol):
    """Return (scores per item, teacher_called per item)."""
    kind, p = pol
    out, called = [], []
    for i in idx:
        s = side_scores(L, i, p.get("side", {"student": 1.0}))
        t = None if kind == "student" else teacher_scores(L, i, IS_FI[split][i], p.get("fi", ()))
        if t is None:
            out.append(s); called.append(False); continue
        if kind == "teacher":
            out.append(t); called.append(True); continue
        f = [p["w"] * x + y for x, y in zip(s, t)]
        if kind == "fuse" or math.exp(max(s)) < p["tau"]:
            out.append(f); called.append(True)
        else:
            out.append(s); called.append(False)
    return out, called


def hits(rows, sc):
    return [max(range(len(s)), key=lambda c: s[c]) in r["gold"] for r, s in zip(rows, sc)]


def acc(rows, sc):
    h = hits(rows, sc); return sum(h) / len(h)


def provision(r):
    """Provision key: the group id without its trailing date (-YYYY or -YYYY-MM-DD)."""
    return re.sub(r"-\d{4}(-\d{2}-\d{2})?$", "", r.get("provision") or r.get("gid") or r["question"])


prov = sorted({provision(r) for r in valid})
fold_of = {p: i % 5 for i, p in enumerate(prov)}
folds = [[i for i, r in enumerate(valid) if fold_of[provision(r)] == f] for f in range(5)]
W = [float(x) for x in a.wgrid.split(",")]
TAU = [float(x) for x in a.taugrid.split(",")]
cands = [("student", {"side": sd}) for sd in SIDES]
for fo in FI_OPTS:
    cands.append(("teacher", {"fi": fo}))
    for sd in SIDES:
        cands += [("fuse", {"w": w, "side": sd, "fi": fo}) for w in W]
        cands += [("cascade", {"w": w, "tau": t, "side": sd, "fi": fo}) for w in W for t in TAU]


def cv(pol):
    accs, rates = [], []
    for f in folds:
        sc, called = policy_scores(VL, "valid", f, pol)
        accs.append(acc([valid[i] for i in f], sc)); rates.append(sum(called) / len(f))
    return statistics.mean(accs), statistics.pstdev(accs) / math.sqrt(len(accs)), statistics.mean(rates)


res = [(pol,) + cv(pol) for pol in cands]
best = max(res, key=lambda x: x[1])
KIND = {"student": 0, "teacher": 1, "fuse": 2, "cascade": 3}
within = [x for x in res if x[1] >= best[1] - best[2]]
chosen = min(within, key=lambda x: (round(x[3], 3), KIND[x[0][0]], len(x[0][1].get("fi", ()))))
cheap = [x for x in res if x[3] <= 0.5]
cheap_best = max(cheap, key=lambda x: x[1]) if cheap else None
dev_only = [x for x in res if x[0][0] == "student"]
dev_best = max(dev_only, key=lambda x: x[1])
on_device = min([x for x in dev_only if x[1] >= dev_best[1] - dev_best[2]], key=lambda x: (len(x[0][1]["side"]), sum(x[0][1]["side"].values())))


def fmt(x):
    d = {"policy": x[0][0]}
    for k, v in x[0][1].items():
        d[k] = list(v) if isinstance(v, tuple) else v
    return d | {"cv_acc": round(x[1], 4), "se": round(x[2], 4), "teacher_rate": round(x[3], 3)}


def by_lang(pol):
    sc, _ = policy_scores(VL, "valid", range(len(valid)), pol)
    h = hits(valid, sc); out = {}
    for r, ok in zip(valid, h):
        n, c = out.get(r.get("lang"), (0, 0)); out[r.get("lang")] = (n + 1, c + ok)
    return {k: round(c / n, 4) for k, (n, c) in sorted(out.items())}


fi_valid = [i for i, f in enumerate(IS_FI["valid"]) if f]
report = {
    "temperatures": temps,
    "valid_full": {n: round(acc(valid, VL[n]), 4) for n, _ in judges},
    "valid_finnish_only": {n: round(acc([valid[i] for i in fi_valid], [VL[n][i] for i in fi_valid]), 4) for n in list(VL)},
    "cv_best": fmt(best),
    "chosen": fmt(chosen) | {"rule": "within 1 SE of the best CV accuracy, fewest teacher calls, then simplest"},
    "cheap_best_le50pct_calls": fmt(cheap_best) if cheap_best else None,
    "on_device": fmt(on_device) | {"rule": "no teacher calls; within 1 SE of the best on-device CV accuracy, simplest side"},
    "valid_by_lang": {"chosen": by_lang(chosen[0]), "on_device": by_lang(on_device[0]), "cv_best": by_lang(best[0])},
    "all": sorted((fmt(x) for x in res), key=lambda d: -d["cv_acc"])[:15],
}

# apply once to test; accuracy is not computed here
refs = (("chosen", chosen), ("best", best), ("cheap", cheap_best), ("on_device", on_device),
        ("teacher", max((r for r in res if r[0][0] == "teacher"), key=lambda x: x[1])))
for tag, x in refs:
    if x is None:
        continue
    sc, called = policy_scores(TL, "test", range(len(test)), x[0])
    report.setdefault("test_teacher_rate", {})[tag] = round(sum(called) / len(test), 3)
    with open(f"{a.out}/{tag}.judgments.jsonl", "w", encoding="utf-8") as f:
        for r, s in zip(test, sc):
            z = lse(s)
            for c, v in zip(r["clauses"], s):
                f.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": math.exp(v - z), "score": v - z, "ms": 0, "tokens": 0}, ensure_ascii=False) + "\n")
json.dump(report, open(f"{a.out}/policy_report.json", "w"), indent=1)
print(json.dumps({k: v for k, v in report.items() if k != "all"}, indent=1))
