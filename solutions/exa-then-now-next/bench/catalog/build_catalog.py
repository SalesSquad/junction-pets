#!/usr/bin/env python3
"""Build the on-device semantic catalog of amount-bearing CFR provisions.

One row per provision = (title, part, section). Provisions are renumbered and repealed over 30 years, so
every provision that carries an amount in ANY annual edition 1996-2026 is kept, with the heading and the
amount clauses of the newest edition it appears in and the list of years it exists in.

Text recipes (both fixed before the benchmark was run; eval_discovery.py reports both):
  clauses1200  (default, the build spec)
               "<title> CFR § <section> <heading>. " + amount clauses (context + clause, de-duplicated,
               money clauses first; the lead-in context is cut at 200 characters and the clause at 400)
               up to about 1,200 characters.
               Document prompt "title: none | text: ", at most 512 tokens.
  heading60    (the scout's probe recipe) heading in the prompt's title slot, then the first 60 words of the
               provision's first amount clause. Document prompt "title: <heading> | text: ", at most 256 tokens.

Output (bench/catalog/out/, the non-default recipe gets ".<recipe>" before the extension):
  catalog.jsonl    one JSON row per provision, in vector order
  embeddings.npy   float16 [rows, 768], L2-normalised
  manifest.json    model id, vector size, row count, build time, checksums

Usage:
  .venv-catalog/bin/python bench/catalog/build_catalog.py [--recipe clauses1200|heading60] [--limit N]
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
import platform
import time

import numpy as np

from embedder import DATA, DIM, DOC_PREFIX, DOC_PREFIX_TITLED, OUT, QUERY_PREFIX, MlxEmbedder, footprint_gb, out_path

DEFAULT_RECIPE = "clauses1200"
ap = argparse.ArgumentParser()
ap.add_argument("--recipe", choices=["clauses1200", "heading60"], default=DEFAULT_RECIPE)
ap.add_argument("--limit", type=int, default=0, help="embed only the first N rows (smoke test; writes *.smoke.* files)")
ap.add_argument("--batch", type=int, default=4, help="4 keeps MLX's peak near 1.1 GB at the same speed as 16")
ap.add_argument("--budget", type=int, default=1200, help="characters of clause text after the heading (clauses1200)")
ap.add_argument("--piece", type=int, default=400, help="characters kept of one clause (clauses1200)")
ap.add_argument("--lead", type=int, default=200, help="characters kept of a clause's lead-in context (clauses1200)")
args = ap.parse_args()
tag = ".".join(x for x in ("" if args.recipe == DEFAULT_RECIPE else args.recipe, "smoke" if args.limit else "") if x)
t_start = time.time()

import pyarrow as pa
import pyarrow.parquet as pq


def squash(s):
    return " ".join((s or "").split())


def clip(s, n):
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut + " …"


# ---- 1. keys: which provisions exist, in which years, and which edition is the newest for each -------------
t = pq.read_table(f"{DATA}/clauses.parquet", columns=["title", "year", "part", "section", "kind", "clause_idx", "edition"])
c_title, c_year, c_part, c_sec, c_kind, c_idx, c_ed = (t[c].to_pylist() for c in t.column_names)
n_clause_rows = t.num_rows
del t
amount_years = collections.defaultdict(set)
for a, y, p, s in zip(c_title, c_year, c_part, c_sec):
    amount_years[(a, p or "", s)].add(y)
last = {k: max(v) for k, v in amount_years.items()}
pick = [i for i, (a, y, p, s) in enumerate(zip(c_title, c_year, c_part, c_sec)) if last[(a, p or "", s)] == y]
newest_edition = {}
for a, y, e in zip(c_title, c_year, c_ed):
    if y >= newest_edition.get(a, (0, ""))[0]:
        newest_edition[a] = (y, e)

# Years in which the section exists at all (with or without an amount clause) come from sections.parquet.
t = pq.read_table(f"{DATA}/sections.parquet", columns=["title", "year", "part", "section"])
exist_years = collections.defaultdict(set)
for a, y, p, s in zip(*(t[c].to_pylist() for c in t.column_names)):
    exist_years[(a, p or "", s)].add(y)
del t

# ---- 2. text of the newest edition of each provision (only those rows are materialised) --------------------
t = pq.read_table(f"{DATA}/clauses.parquet", columns=["subject", "context", "clause"]).take(pa.array(pick))
texts = t.to_pylist()
del t
pa.default_memory_pool().release_unused()
by_key = collections.defaultdict(list)
for i, r in zip(pick, texts):
    by_key[(c_title[i], c_part[i] or "", c_sec[i])].append((c_idx[i], c_kind[i], squash(r["subject"]), squash(r["context"]), squash(r["clause"]), c_ed[i]))
del texts


def sort_key(k):
    a, p, s = k
    num = lambda x: [(0, int(z)) if z.isdigit() else (1, z) for z in x.replace("-", ".").split(".")]
    return (a, num(p), num(s))


rows, docs, prefixes = [], [], []
for key in sorted(by_key, key=sort_key):
    a, p, s = key
    items = by_key[key]  # file order = document order within the edition
    heading = next((x[2] for x in items if x[2]), "")
    # one unit per distinct (context, clause); it is a money unit if any of its amounts is money
    units = {}
    for idx, kind, _, ctx, cl, _ in items:
        u = units.setdefault((ctx, cl), {"idx": idx, "money": False, "ctx": ctx, "cl": cl})
        u["money"] = u["money"] or kind == "money"
    ordered = sorted(units.values(), key=lambda u: (not u["money"], u["idx"]))
    sec_show = s.replace("§", "").replace(" ", "").strip()
    h = heading.rstrip(". ")
    head = f"{a} CFR § {sec_show} {h}{'' if h.endswith(('?', '!')) else '.'} " if h else f"{a} CFR § {sec_show}. "
    if args.recipe == "clauses1200":
        body, last_ctx = "", None
        for u in ordered:
            lead = clip(u["ctx"], args.lead) + " " if u["ctx"] and u["ctx"] != last_ctx else ""
            piece = lead + clip(u["cl"], args.piece)
            if body and len(body) + 1 + len(piece) > args.budget:
                break
            body = (body + " " + piece).strip()
            last_ctx = u["ctx"]
        text, prefix = head + clip(body, args.budget), DOC_PREFIX
    else:
        first = items[0]
        text = " ".join((first[3] + " " + first[4]).split()[:60])
        prefix = DOC_PREFIX_TITLED.format(title=heading or "none")
    years = sorted(exist_years.get(key, set()) | amount_years[key])
    rows.append({
        "i": len(rows), "title": a, "part": p, "section": s, "subject": heading,
        "years": years, "amount_years": sorted(amount_years[key]), "text_year": last[key], "text_edition": items[0][5],
        "n_clauses": len(units), "n_money": sum(u["money"] for u in units.values()), "text": text,
    })
    docs.append(text)
    prefixes.append(prefix)
del by_key, c_title, c_year, c_part, c_sec, c_kind, c_idx, c_ed
if args.limit:
    rows, docs, prefixes = rows[: args.limit], docs[: args.limit], prefixes[: args.limit]
lens = sorted(len(d) for d in docs)
print(f"{len(rows)} provisions; text chars median {lens[len(lens) // 2]}, p90 {lens[int(len(lens) * 0.9)]}, max {lens[-1]}; footprint {footprint_gb()}", flush=True)

# ---- 3. embed ---------------------------------------------------------------------------------------------
max_tokens = 512 if args.recipe == "clauses1200" else 256
emb = MlxEmbedder(cache_mb=128)
emb.embed([prefixes[0] + docs[0]], max_tokens=max_tokens)  # warm up
t0 = time.time()
vecs = np.zeros((len(docs), DIM), dtype=np.float16)
truncated = 0
CHUNK = 512
for s in range(0, len(docs), CHUNK):
    v = emb.embed([p + d for p, d in zip(prefixes[s : s + CHUNK], docs[s : s + CHUNK])], max_tokens=max_tokens, batch=args.batch)
    truncated += emb.last_truncated
    vecs[s : s + CHUNK] = v.astype(np.float16)
    print(f"  embedded {min(s + CHUNK, len(docs))}/{len(docs)} in {time.time() - t0:.0f} s; footprint {footprint_gb()}", flush=True)
embed_s = time.time() - t0
norms = np.linalg.norm(vecs.astype(np.float32), axis=1)
assert np.isfinite(vecs).all() and abs(float(norms.min()) - 1) < 0.01 and abs(float(norms.max()) - 1) < 0.01, "vectors are not unit length"

# ---- 4. write ---------------------------------------------------------------------------------------------
os.makedirs(OUT, exist_ok=True)
f_cat, f_emb, f_man = out_path("catalog.jsonl", tag), out_path("embeddings.npy", tag), out_path("manifest.json", tag)
with open(f_cat, "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
np.save(f_emb, vecs)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


import mlx.core as mx

cur, peak = footprint_gb()
manifest = {
    "what": "semantic catalog of amount-bearing CFR provisions (titles 12, 14, 16, 20, 29, 49; annual editions 1996-2026)",
    "model": emb.model_id, "runtime": f"mlx {mx.__version__} (Metal)", "python": platform.python_version(),
    "dim": DIM, "dtype": "float16", "normalised": True, "rows": len(rows),
    "recipe": args.recipe, "doc_prefix": DOC_PREFIX if args.recipe == "clauses1200" else DOC_PREFIX_TITLED,
    "query_prefix": QUERY_PREFIX, "max_tokens": max_tokens, "docs_cut_at_max_tokens": truncated,
    "text_chars": {"median": lens[len(lens) // 2], "p90": lens[int(len(lens) * 0.9)], "max": lens[-1]},
    "provisions_by_title": dict(sorted(collections.Counter(r["title"] for r in rows).items())),
    "provisions_in_newest_edition_of_their_title": sum(r["text_year"] == newest_edition[r["title"]][0] for r in rows),
    "newest_edition_by_title": {str(a): e for a, (_, e) in sorted(newest_edition.items())},
    "source": {"clauses.parquet_rows": n_clause_rows, "dir": DATA},
    "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "build_seconds": round(time.time() - t_start, 1), "embed_seconds": round(embed_s, 1),
    "seconds_per_1000_docs": round(embed_s * 1000 / len(docs), 2),
    "peak_memory_gb": {"phys_footprint_peak": peak, **emb.peak()},
    "files": {os.path.basename(p): {"bytes": os.path.getsize(p), "sha256": sha(p)} for p in (f_cat, f_emb)},
}
with open(f_man, "w") as f:
    json.dump(manifest, f, indent=1)
print(json.dumps(manifest, indent=1))
