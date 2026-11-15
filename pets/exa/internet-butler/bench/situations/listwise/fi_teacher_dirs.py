#!/usr/bin/env python3
"""Judge dirs for the Finnish teachers (no API calls here).
runs/jev_fi:   Jev P(yes) -> score = logit(p), valid from TEACHERS/valid_fi.jev.jsonl, test from the cached
               bench/datasets/out/training/test.judgments.jsonl (jev keys; the cache is only read).
runs/haiku_fi: Haiku listwise log-probs from TEACHERS/{valid,test}.haiku_fi.jsonl.
TEACHERS is --teachers-dir (default runs/teachers, where teachers/*.py write; the 2026-11-15 run used nemotron).
Finnish rows only. Fails if any Finnish clause lacks a judgment.
Usage (from the repository root): python3 bench/situations/listwise/fi_teacher_dirs.py [--teachers-dir runs/teachers]"""
import argparse, json, math, os
D = "bench/datasets/out/training"
ap = argparse.ArgumentParser(); ap.add_argument("--teachers-dir", default="runs/teachers")
TD = ap.parse_args().teachers_dir


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4); return math.log(p / (1 - p))


def fi_rows(split):
    return [json.loads(l) for l in open(f"{D}/{split}.jsonl") if l.strip() and json.loads(l).get("lang") == "Finnish"]


for name, srcs in (("jev_fi", {"valid": f"{TD}/valid_fi.jev.jsonl", "test": f"{D}/test.judgments.jsonl"}),):
    os.makedirs(f"runs/{name}", exist_ok=True)
    for split, src in srcs.items():
        p = {}
        for l in open(src):
            j = json.loads(l)
            if j["k"].startswith("jev|"):
                p[j["k"]] = j["p"]
        out, miss = [], 0
        for r in fi_rows(split):
            ks = [f"jev|{r['question']}|{c}" for c in r["clauses"]]
            miss += sum(k not in p for k in ks)
            out.append({"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "score": [logit(p.get(k, 0.5)) for k in ks]})
        assert miss == 0, (name, split, miss)
        with open(f"runs/{name}/{split}_scores.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in out)
        print(name, split, len(out))
os.makedirs("runs/haiku_fi", exist_ok=True)
for split in ("valid", "test"):
    src = f"{TD}/{split}.haiku_fi.jsonl"
    rows = {(j["question"], tuple(j["clauses"])) for j in map(json.loads, open(src))}
    need = {(r["question"], tuple(r["clauses"])) for r in fi_rows(split)}
    assert need <= rows, ("haiku_fi", split, len(need - rows))
    dst = f"runs/haiku_fi/{split}_scores.jsonl"
    if os.path.lexists(dst):
        os.remove(dst)
    os.symlink(os.path.abspath(src), dst)
    print("haiku_fi", split, len(rows))
