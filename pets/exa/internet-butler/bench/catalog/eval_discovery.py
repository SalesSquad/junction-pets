#!/usr/bin/env python3
"""Discovery measured on the Exa study's items: does the on-device catalog find the provision?

Items: exactly the ones bench/exa_study/discovery.mjs searched (first non-attack situation per provision in
bench/exa_study/all-situations.jsonl, key = gid|question.slice(0, 80)), joined to Exa's row in discovery.jsonl.

Arms (all judged the way discovery.mjs judges Exa: section = same CFR title and section, part = same title and
part, a section hit also counts as a part hit; top 5):
  catalog   the person's message as written (no translation, no rewriting), embedded with the query prompt and
            compared with every catalog vector of a provision that exists in the item's edition year
  bm25      Okapi BM25 (k1 1.2, b 0.75) over the same catalog text, same year restriction
  exa       Exa's top 5 on the official domains, read from discovery.jsonl (not called here)
  union     catalog top 5 or Exa top 5 (ten candidates)

The 14 UK/EU items have no CFR provision; the catalog and BM25 score them as misses.

READ THIS BEFORE QUOTING THE NUMBERS: every benchmark situation was written by a language model from clauses
of its gold provision, and those clauses come from the same dataset the catalog is built from. The catalog
searches about 6,000 known provisions, one of which is always the answer; Exa searches the open web. The
comparison says what a closed catalog buys on its own coverage, not that it is a better search engine.

Usage:
  .venv-catalog/bin/python bench/catalog/eval_discovery.py                       # both recipes, MLX queries
  .venv-catalog/bin/python bench/catalog/eval_discovery.py --query-runtime onnx --recipes clauses1200
"""
import argparse
import collections
import json
import math
import os
import re
import time

import numpy as np

from embedder import DIM, OUT, QUERY_PREFIX, ROOT, footprint_gb, load_embedder, out_path

ap = argparse.ArgumentParser()
ap.add_argument("--recipes", nargs="+", default=["clauses1200", "heading60"], help="first one is the default catalog")
ap.add_argument("--query-runtime", choices=["mlx", "onnx"], default="mlx", help="onnx = the model a browser would run")
ap.add_argument("--k", type=int, default=5)
ap.add_argument("--max-tokens", type=int, default=512)
args = ap.parse_args()
DEFAULT_RECIPE = "clauses1200"
K = args.k
YEARS = list(range(1996, 2027))


def js_slice(s, n=80):
    """JavaScript String.prototype.slice(0, n) counts UTF-16 code units."""
    return s.encode("utf-16-le")[: 2 * n].decode("utf-16-le", errors="ignore")


# ---- items, exactly as discovery.mjs --unique picked them ---------------------------------------------------
exa = {}
with open(os.path.join(ROOT, "bench/exa_study/discovery.jsonl")) as f:
    for line in f:
        if line.strip():
            j = json.loads(line)
            exa[j["key"]] = j
items, seen = [], set()
with open(os.path.join(ROOT, "bench/exa_study/all-situations.jsonl")) as f:
    for line in f:
        if not line.strip():
            continue
        it = json.loads(line)
        if it.get("attack") or it["provision"] in seen:
            continue
        seen.add(it["provision"])
        k = f'{it["gid"]}|{js_slice(it["question"])}'
        items.append({"key": k, "gid": it["gid"], "lang": it["lang"], "jurisdiction": it["jurisdiction"], "question": it["question"], "ref": it["ref"], "date": it.get("date")})
assert {x["key"] for x in items} == set(exa) and len(items) == len(exa), "items do not match discovery.jsonl"
N = len(items)
for x in items:
    r = x["ref"]
    x["us"] = r["source"] == "ecfr"
    # A few items come from the eCFR versioner and carry no annual edition: the event date's year stands in.
    x["year"] = int(str(r.get("edition") or x["date"])[:4]) if x["us"] else None
    e = exa[x["key"]]
    x["exa"] = {"s1": e.get("rank") == 1, "s5": bool(e["section"]), "p5": bool(e["part"])}

# ---- embed the messages as written -------------------------------------------------------------------------
emb = load_embedder(args.query_runtime)
emb.embed([QUERY_PREFIX + "warm up"], max_tokens=args.max_tokens)
t0 = time.time()
Q = emb.embed([QUERY_PREFIX + x["question"] for x in items], max_tokens=args.max_tokens, batch=8)
q_seconds = time.time() - t0
q_truncated = emb.last_truncated
print(f"{N} messages embedded with {emb.model_id} ({emb.runtime}) in {q_seconds:.1f} s; cut at {args.max_tokens} tokens: {q_truncated}; footprint {footprint_gb()}", flush=True)


def load_catalog(recipe):
    tag = "" if recipe == DEFAULT_RECIPE else recipe
    rows = [json.loads(l) for l in open(out_path("catalog.jsonl", tag))]
    E = np.load(out_path("embeddings.npy", tag)).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    exists = np.zeros((len(rows), len(YEARS)), dtype=bool)
    for i, r in enumerate(rows):
        for y in r["years"]:
            exists[i, y - YEARS[0]] = True
    by_sec, by_part = collections.defaultdict(list), collections.defaultdict(list)
    for i, r in enumerate(rows):
        by_sec[(r["title"], r["section"])].append(i)
        by_part[(r["title"], r["part"])].append(i)
    return rows, E, exists, by_sec, by_part


def judge(score_rows, cat, positive_only=False):
    """score_rows[i] = scores of item i over all catalog rows. Returns per-item rank of the gold section
    (None = not found) and whether a top-K row is in the gold part. Rows outside the item's year are excluded.
    Ties are broken against the gold row (pessimistic)."""
    rows, _, exists, by_sec, by_part = cat
    out = []
    for x, s in zip(items, score_rows):
        if not x["us"]:
            out.append({"rank": None, "p": False, "present": False, "top": []})
            continue
        ok = exists[:, x["year"] - YEARS[0]]
        s = np.where(ok, s, -np.inf)
        if positive_only:
            s = np.where(s > 0, s, -np.inf)
        g = x["ref"]
        gold = [i for i in by_sec.get((int(g["title"]), str(g["section"])), []) if ok[i]]
        gold_ok = [i for i in gold if np.isfinite(s[i])]
        rank = None
        if gold_ok:
            best = max(s[i] for i in gold_ok)
            rank = int((s >= best).sum()) - sum(1 for i in gold_ok if s[i] >= best) + 1
        top = [int(i) for i in np.argsort(-s, kind="stable")[:K] if np.isfinite(s[i])]
        part_rows = set(by_part.get((int(g["title"]), str(g["part"])), []))
        p = (rank is not None and rank <= K) or any(i in part_rows for i in top)
        out.append({"rank": rank, "p": bool(p), "present": bool(gold), "top": top})
    return out


# ---- BM25 over the catalog text ----------------------------------------------------------------------------
WORD = re.compile(r"\w+")


def bm25_scores(rows, k1=1.2, b=0.75):
    docs = [WORD.findall(r["text"].lower()) for r in rows]
    n = len(docs)
    avg = sum(map(len, docs)) / n
    post = collections.defaultdict(list)
    for i, d in enumerate(docs):
        for t, tf in collections.Counter(d).items():
            post[t].append((i, tf))
    dl = np.array([len(d) for d in docs], dtype=np.float32)
    table = {}
    for t, pl in post.items():
        ids = np.array([i for i, _ in pl], dtype=np.int32)
        tf = np.array([c for _, c in pl], dtype=np.float32)
        idf = math.log(1 + (n - len(pl) + 0.5) / (len(pl) + 0.5))
        table[t] = (ids, idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl[ids] / avg)))
    S = np.zeros((N, n), dtype=np.float32)
    for qi, x in enumerate(items):
        for t in set(WORD.findall(x["question"].lower())):
            if t in table:
                ids, w = table[t]
                S[qi, ids] += w
    return S


def pct(a, n):
    return f"{a}/{n} ({100 * a / max(1, n):.1f} %)"


def wilson(a, n, z=1.96):
    if not n:
        return None
    p = a / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def mcnemar(b, c):
    """Exact two-sided McNemar p for b, c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


GROUPS = [("all", lambda x: True), ("English", lambda x: x["lang"] == "English"), ("German", lambda x: x["lang"] == "German"), ("Finnish", lambda x: x["lang"] == "Finnish"), ("US only", lambda x: x["us"])]


def arm_table(flags):
    """flags[i] = {"s1","s5","p5"} booleans (s1 may be None for the union)."""
    t = {}
    for name, f in GROUPS:
        idx = [i for i, x in enumerate(items) if f(x)]
        n = len(idx)
        row = {"n": n}
        for m, label in (("s1", "section@1"), ("s5", f"section@{K}"), ("p5", f"part@{K}")):
            if flags[idx[0]][m] is None:
                row[label] = None
                continue
            a = sum(bool(flags[i][m]) for i in idx)
            row[label] = pct(a, n)
            row[label + "_ci95"] = wilson(a, n)
        t[name] = row
    return t


def to_flags(j):
    return [{"s1": r["rank"] == 1, "s5": r["rank"] is not None and r["rank"] <= K, "p5": r["p"]} for r in j]


def paired(a, b, name_a, name_b):
    """Section@K on the same items: how often one arm finds the section and the other does not."""
    t = {}
    for name, f in GROUPS:
        idx = [i for i, x in enumerate(items) if f(x)]
        both = sum(a[i]["s5"] and b[i]["s5"] for i in idx)
        only_a = sum(a[i]["s5"] and not b[i]["s5"] for i in idx)
        only_b = sum(b[i]["s5"] and not a[i]["s5"] for i in idx)
        t[name] = {"n": len(idx), "both": both, f"{name_a}_only": only_a, f"{name_b}_only": only_b, "neither": len(idx) - both - only_a - only_b, "mcnemar_exact_p": float(f"{mcnemar(only_a, only_b):.3g}")}
    return t


exa_flags = [x["exa"] for x in items]
summary = {
    "items": N, "k": K,
    "items_by_language": dict(collections.Counter(x["lang"] for x in items)),
    "items_by_jurisdiction": dict(collections.Counter(x["jurisdiction"] for x in items)),
    "query_model": emb.model_id, "query_runtime": emb.runtime, "query_prefix": QUERY_PREFIX,
    "query_seconds": round(q_seconds, 1), "queries_cut_at_max_tokens": q_truncated,
    "judging": "section = same CFR title and section; part = same title and part (a section hit counts); catalog rows outside the item's edition year are excluded; the 14 UK/EU items are misses for catalog and BM25",
    "caveat": "The situations were written from clauses of the gold provisions, taken from the dataset the catalog is built from. The catalog is a closed set of about 6,000 provisions that always contains the answer; Exa searches the open web.",
    "arms": {"exa": arm_table(exa_flags)},
    "paired_section_at_k": {}, "diagnostics": {},
}
item_rows = [{"key": x["key"], "lang": x["lang"], "jurisdiction": x["jurisdiction"], "year": x["year"], "gold": f'{x["ref"].get("title")}-{x["ref"].get("section")}' if x["us"] else None, "exa": x["exa"]} for x in items]

for recipe in args.recipes:
    cat = load_catalog(recipe)
    rows, E = cat[0], cat[1]
    name = f"catalog[{recipe}]"
    t0 = time.time()
    S = Q @ E.T
    j = judge(S, cat)
    search_ms = 1000 * (time.time() - t0) / N
    f = to_flags(j)
    summary["arms"][name] = arm_table(f)
    union = [{"s1": None, "s5": a["s5"] or b["s5"], "p5": a["p5"] or b["p5"]} for a, b in zip(f, exa_flags)]
    summary["arms"][f"{name} or exa (10 candidates)"] = arm_table(union)
    summary["paired_section_at_k"][f"{name} vs exa"] = paired(f, exa_flags, "catalog", "exa")
    jb = judge(bm25_scores(rows), cat, positive_only=True)
    fb = to_flags(jb)
    summary["arms"][f"bm25[{recipe}]"] = arm_table(fb)
    summary["paired_section_at_k"][f"{name} vs bm25[{recipe}]"] = paired(f, fb, "catalog", "bm25")
    us = [i for i, x in enumerate(items) if x["us"]]
    d = {
        "rows": len(rows), "search_ms_per_item_numpy": round(search_ms, 2),
        "gold_provision_in_catalog_in_its_year": pct(sum(j[i]["present"] for i in us), len(us)),
        "candidates_per_item_after_year_filter": {"median": int(np.median([cat[2][:, items[i]["year"] - YEARS[0]].sum() for i in us])), "min": int(min(cat[2][:, items[i]["year"] - YEARS[0]].sum() for i in us))},
        "section_recall_at": {str(k): pct(sum(j[i]["rank"] is not None and j[i]["rank"] <= k for i in us), len(us)) for k in (1, 3, 5, 10, 20, 50)},
        "by_title_section_at_k": {},
        "by_text_age_section_at_k": {},
    }
    for a in sorted({int(items[i]["ref"]["title"]) for i in us}):
        idx = [i for i in us if int(items[i]["ref"]["title"]) == a]
        d["by_title_section_at_k"][str(a)] = {"catalog": pct(sum(f[i]["s5"] for i in idx), len(idx)), "exa": pct(sum(exa_flags[i]["s5"] for i in idx), len(idx))}
    # Does it matter that the catalog holds the newest text while the question is about an older edition?
    age = collections.defaultdict(list)
    for i in us:
        g = items[i]["ref"]
        gold = cat[3].get((int(g["title"]), str(g["section"])), [])
        if not gold:
            continue
        gap = max(rows[r]["text_year"] for r in gold) - items[i]["year"]
        age["same edition" if gap == 0 else "1-5 years older" if gap <= 5 else "6-15 years older" if gap <= 15 else "16+ years older"].append(i)
    for label in ("same edition", "1-5 years older", "6-15 years older", "16+ years older"):
        idx = age.get(label, [])
        d["by_text_age_section_at_k"][label] = {"catalog": pct(sum(f[i]["s5"] for i in idx), len(idx)), "exa": pct(sum(exa_flags[i]["s5"] for i in idx), len(idx))}
    # Matryoshka: the first 256 of the 768 dimensions, re-normalised (a third of the index size).
    Q2, E2 = Q[:, :256] / np.linalg.norm(Q[:, :256], axis=1, keepdims=True), E[:, :256] / np.linalg.norm(E[:, :256], axis=1, keepdims=True)
    summary["arms"][f"{name} 256-d"] = arm_table(to_flags(judge(Q2 @ E2.T, cat)))
    summary["diagnostics"][name] = d
    for r, a, b in zip(item_rows, j, jb):
        r[recipe] = {"rank": a["rank"], "part": a["p"], "top": [f'{rows[i]["title"]}-{rows[i]["section"]}' for i in a["top"]], "bm25_rank": b["rank"]}
    del S

suffix = "" if args.query_runtime == "mlx" else ".onnx-queries"
cur, peak = footprint_gb()
summary["peak_memory_gb"] = {"phys_footprint_peak": peak, **emb.peak()}
with open(os.path.join(OUT, f"eval.summary{suffix}.json"), "w") as fh:
    json.dump(summary, fh, indent=1, ensure_ascii=False)
with open(os.path.join(OUT, f"eval.items{suffix}.jsonl"), "w") as fh:
    for r in item_rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---- print -------------------------------------------------------------------------------------------------
print(f"\nDiscovery on the Exa study's {N} items (top {K}); query model {emb.model_id} ({emb.runtime})")
print(f'{"group":9} {"n":>5}  {"arm":44} {"section@1":>18} {"section@" + str(K):>18} {"part@" + str(K):>18}')
for g, _ in GROUPS:
    for arm, t in summary["arms"].items():
        r = t[g]
        print(f'{g:9} {r["n"]:>5}  {arm:44} {str(r["section@1"] or "-"):>18} {r["section@" + str(K)]:>18} {r["part@" + str(K)]:>18}')
    print()
print(f"Paired, section@{K} on the same items")
for pair, t in summary["paired_section_at_k"].items():
    for g, r in t.items():
        print(f"  {pair:42} {g:9} " + "  ".join(f"{k} {v}" for k, v in r.items()))
print()
for name, d in summary["diagnostics"].items():
    print(name, json.dumps(d, ensure_ascii=False))
print(f"\npeak memory {summary['peak_memory_gb']}; wrote out/eval.summary{suffix}.json and out/eval.items{suffix}.jsonl")
