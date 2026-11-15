#!/usr/bin/env python3
"""Merge prune-then-listwise scores back into full groups and pick the prune size m on VALID only.
For each adapter A and m in {3,4,5}: runs/{A}p_m{m}/{valid,test}_scores.jsonl = A's full listwise scores, except
that groups with k > m take the pruned-listwise log-probs on B0's kept top-m clauses; pruned-out clauses get
(min kept log-prob - 5). Prints valid accuracy for m = none/3/4/5 (overall and k >= 6); test accuracy is never
computed here. The chosen m (best valid accuracy, ties -> none, then smaller m) is written to
runs/{A}p_choice.json; runs/{A}p is a symlink to the chosen dir (or to A itself when m = none).
--prune-dir holds prune_sets.py's {valid,test}_m{m}.jsonl; --pruned-scores holds the GPU's prune_{A}_m{m}/ score
dirs (the 2026-11-15 rounds: --prune-dir verda/job3/prune --pruned-scores verda/job3/out3/runs).
Usage (from the repository root): python3 bench/situations/listwise/prune_merge.py list4b_kd2 [list4b_kd]
       [--prune-dir runs/prune] [--pruned-scores runs]"""
import argparse, json, os
D = "bench/datasets/out/training"
SEP = " … "
own = lambda c: c.split(SEP)[-1]
ap = argparse.ArgumentParser()
ap.add_argument("adapters", nargs="+", help="run names under runs/ (full listwise valid/test scores)")
ap.add_argument("--prune-dir", default="runs/prune")
ap.add_argument("--pruned-scores", default="runs")
a = ap.parse_args()


def rows(split):
    return [json.loads(l) for l in open(f"{D}/{split}.jsonl") if l.strip()]


def full_scores(path):
    return {(j["question"], tuple(j["clauses"])): j["lp"] for j in map(json.loads, open(path))}


def acc(rs, sc, kmin=0):
    n = ok = 0
    for r in rs:
        if len(r["clauses"]) < kmin:
            continue
        s = sc[(r["question"], tuple(r["clauses"]))]
        g = {i for i, c in enumerate(r["clauses"]) if own(c) == own(r["clauses"][r["target"]])}
        n += 1; ok += max(range(len(s)), key=lambda i: s[i]) in g
    return round(ok / max(1, n), 4)


for ad in a.adapters:
    base = {sp: full_scores(f"runs/{ad}/{sp}_scores.jsonl") for sp in ("valid", "test")}
    V = rows("valid")
    report = {"none": {"valid": acc(V, base["valid"]), "valid_k6plus": acc(V, base["valid"], 6)}}
    for m in (3, 4, 5):
        pdir = f"{a.pruned_scores}/prune_{ad}_m{m}"
        if not os.path.exists(f"{pdir}/valid_scores.jsonl"):
            continue
        merged = {}
        for sp in ("valid", "test"):
            meta = {(x["question"], tuple(x["clauses"])): x for x in map(json.loads, open(f"{a.prune_dir}/{sp}_m{m}.jsonl"))}
            sc = dict(base[sp])
            for j in map(json.loads, open(f"{pdir}/{sp}_scores.jsonl")):
                x = meta[(j["question"], tuple(j["clauses"]))]
                floor = min(j["lp"]) - 5.0
                lp = [floor] * len(x["orig_clauses"])
                for slot, i in enumerate(x["keep"]):
                    lp[i] = j["lp"][slot]
                sc[(x["question"], tuple(x["orig_clauses"]))] = lp
            merged[sp] = sc
            os.makedirs(f"runs/{ad}p_m{m}", exist_ok=True)
            with open(f"runs/{ad}p_m{m}/{sp}_scores.jsonl", "w", encoding="utf-8") as f:
                for r in rows(sp):
                    key = (r["question"], tuple(r["clauses"]))
                    f.write(json.dumps({"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "lp": sc[key]}, ensure_ascii=False) + "\n")
        report[f"m{m}"] = {"valid": acc(V, merged["valid"]), "valid_k6plus": acc(V, merged["valid"], 6)}
    order = ["none", "m3", "m4", "m5"]
    pick = max((k for k in order if k in report), key=lambda k: (report[k]["valid"], -order.index(k)))
    report["chosen"] = pick
    json.dump(report, open(f"runs/{ad}p_choice.json", "w"), indent=1)
    link = f"runs/{ad}p"
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.abspath(f"runs/{ad}" if pick == "none" else f"runs/{ad}p_{pick}"), link)
    print(ad, json.dumps(report))
