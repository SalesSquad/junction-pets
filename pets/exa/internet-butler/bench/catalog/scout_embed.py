#!/usr/bin/env python3
"""Scout: does an embedding model work on this Mac, how fast, how much memory.

Runtimes: --runtime mlx (mlx-embeddings, Metal or CPU) or --runtime onnx (onnxruntime, CPU).
Checks:
  1. cross-lingual sanity: the Finnish and German sentence must be closer to the English one than to any
     unrelated sentence (several prefix conventions are tried and reported);
  2. throughput on 1,000 real short documents (about 60 words) from clauses.parquet;
  3. a small retrieval probe on those 1,000 documents (NOT the index, an indicative smoke test).

Usage:
  .venv-catalog/bin/python bench/catalog/scout_embed.py --runtime mlx \
      --model bench/catalog/out/models/mlx-community--embeddinggemma-300m-bf16 [--device cpu] [--batch 32]
  .venv-catalog/bin/python bench/catalog/scout_embed.py --runtime onnx \
      --model bench/catalog/out/models/onnx-community--embeddinggemma-300m-ONNX --onnx-file onnx/model_quantized.onnx
"""
import argparse
import collections
import ctypes
import json
import os
import resource
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.environ.get(
    "CFR_DATA",
    "/Users/mikaelervamaa/Library/Mobile Documents/com~apple~CloudDocs/Events/Junction-2026/Datasets/cfr-annual-focused",
)

ap = argparse.ArgumentParser()
ap.add_argument("--runtime", choices=["mlx", "onnx"], required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--onnx-file", default="onnx/model_quantized.onnx")
ap.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
ap.add_argument("--batch", type=int, default=32)
ap.add_argument("--n", type=int, default=1000)
ap.add_argument("--max-tokens", type=int, default=256)
ap.add_argument("--threads", type=int, default=4)
ap.add_argument("--query-prefix", default="task: search result | query: ")
ap.add_argument("--doc-prefix", default="title: {title} | text: ")
ap.add_argument("--sts-prefix", default="task: sentence similarity | query: ")
ap.add_argument("--tag", default="")
ap.add_argument("--cache-mb", type=int, default=256, help="MLX buffer cache limit")
ap.add_argument("--probe-per-lang", type=int, default=50)
ap.add_argument("--save-vectors", action="store_true", help="save the sanity vectors for cross-runtime comparison")
args = ap.parse_args()


def footprint_gb():
    """macOS phys_footprint (current, lifetime max) in GB; this counts Metal/unified memory, unlike RSS."""
    try:
        buf = (ctypes.c_uint64 * 64)()
        if ctypes.CDLL("/usr/lib/libproc.dylib").proc_pid_rusage(os.getpid(), 4, ctypes.byref(buf)) != 0:
            return None, None
        # rusage_info_v4: 16 bytes uuid (2 x u64), then u64 fields; phys_footprint is field 9, lifetime max is field 29.
        return buf[2 + 7] / 1e9, buf[2 + 28] / 1e9
    except Exception:
        return None, None


STAGES = []


def stage(name):
    cur, peak = footprint_gb()
    STAGES.append({"stage": name, "footprint_gb": None if cur is None else round(cur, 3), "lifetime_peak_gb": None if peak is None else round(peak, 3)})


stage("start")
t_load = time.time()
if args.runtime == "mlx":
    import mlx.core as mx

    mx.set_memory_limit(3 << 30)
    mx.set_cache_limit(args.cache_mb << 20)
    if args.device == "cpu":
        mx.set_default_device(mx.cpu)
    from mlx_embeddings import load

    model, tokenizer = load(args.model)
    tok = getattr(tokenizer, "_tokenizer", tokenizer)

    def embed(texts, batch=args.batch):
        out = np.zeros((len(texts), 0), dtype=np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vecs = [None] * len(texts)
        for s in range(0, len(order), batch):
            idx = order[s : s + batch]
            enc = tok([texts[i] for i in idx], padding=True, truncation=True, max_length=args.max_tokens, return_tensors="np")
            o = model(mx.array(enc["input_ids"]), mx.array(enc["attention_mask"]))
            e = np.array(o.text_embeds.astype(mx.float32))
            for i, v in zip(idx, e):
                vecs[i] = v
        out = np.stack(vecs)
        return out

    def peak_extra():
        return {"mlx_peak_gb": round(mx.get_peak_memory() / 1e9, 3), "mlx_active_gb": round(mx.get_active_memory() / 1e9, 3)}

else:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    so = ort.SessionOptions()
    so.intra_op_num_threads = args.threads
    sess = ort.InferenceSession(os.path.join(args.model, args.onnx_file), so, providers=["CPUExecutionProvider"])
    tk = Tokenizer.from_file(os.path.join(args.model, "tokenizer.json"))
    tk.enable_truncation(max_length=args.max_tokens)
    tk.enable_padding(pad_id=tk.token_to_id("<pad>") or 0, pad_token="<pad>")
    out_names = [o.name for o in sess.get_outputs()]
    in_names = [i.name for i in sess.get_inputs()]

    def embed(texts, batch=args.batch):
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vecs = [None] * len(texts)
        for s in range(0, len(order), batch):
            idx = order[s : s + batch]
            encs = tk.encode_batch([texts[i] for i in idx])
            feed = {"input_ids": np.array([e.ids for e in encs], dtype=np.int64), "attention_mask": np.array([e.attention_mask for e in encs], dtype=np.int64)}
            if "token_type_ids" in in_names:
                feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
            feed = {k: v for k, v in feed.items() if k in in_names}
            res = dict(zip(out_names, sess.run(None, feed)))
            e = res.get("sentence_embedding")
            if e is None:  # e5-style export: mean pool the last hidden state
                h = res[out_names[0]]
                m = feed["attention_mask"][..., None].astype(np.float32)
                e = (h * m).sum(1) / m.sum(1)
            e = e / np.linalg.norm(e, axis=1, keepdims=True)
            for i, v in zip(idx, e.astype(np.float32)):
                vecs[i] = v
        return np.stack(vecs)

    def peak_extra():
        return {"onnx_inputs": in_names, "onnx_outputs": out_names, "threads": args.threads}


load_s = time.time() - t_load
stage("model_loaded")
report = {"runtime": args.runtime, "model": args.model, "device": args.device if args.runtime == "mlx" else "cpu", "batch": args.batch, "load_seconds": round(load_s, 2)}
if args.runtime == "onnx":
    report["onnx_file"] = args.onnx_file

# ---- 1. cross-lingual sanity ------------------------------------------------------------------------------
EN = "I was bumped from an oversold flight and arrived three hours late"
FI = "Minut jätettiin pois ylibuukatulta lennolta ja saavuin kolme tuntia myöhässä"
DE = "Ich wurde von einem überbuchten Flug ausgeschlossen und kam drei Stunden später an"
UNRELATED = [
    "The recipe calls for two cups of flour and a pinch of salt",
    "Our bank charged a late fee on the mortgage payment last month",
    "Resepti vaatii kaksi kupillista jauhoja ja hyppysellisen suolaa",
    "Pankki peri myöhästymismaksun asuntolainan lyhennyksestä viime kuussa",
    "Das Rezept verlangt zwei Tassen Mehl und eine Prise Salz",
    "Die Bank hat letzten Monat eine Verzugsgebühr für die Hypothek berechnet",
]
DOC = "Passengers denied boarding involuntarily from an oversold flight are entitled to denied boarding compensation of 200% of the fare, up to $775, if the carrier's alternate transportation arrives more than one hour but less than two hours late"
sanity = {}
conventions = {
    "raw_no_prefix": ("", ""),
    "sts_prefix_both": (args.sts_prefix, args.sts_prefix),
    "query_prefix_both": (args.query_prefix, args.query_prefix),
}
vec_dump = {}
for name, (pa, pb) in conventions.items():
    v = embed([pa + EN, pa + FI, pa + DE] + [pb + u for u in UNRELATED])
    en, fi, de, un = v[0], v[1], v[2], v[3:]
    row = {
        "fi_en": float(fi @ en), "de_en": float(de @ en), "fi_de": float(fi @ de),
        "en_unrelated_max": float((un @ en).max()), "fi_unrelated_max": float((un @ fi).max()), "de_unrelated_max": float((un @ de).max()),
    }
    row["pass"] = bool(row["fi_en"] > row["fi_unrelated_max"] and row["de_en"] > row["de_unrelated_max"] and min(row["fi_en"], row["de_en"]) > row["en_unrelated_max"])
    sanity[name] = {k: (round(x, 4) if isinstance(x, float) else x) for k, x in row.items()}
    vec_dump[name] = v
# Retrieval convention: queries with the query prefix, one real-looking document with the document prefix.
dp = args.doc_prefix.format(title="Amount of denied boarding compensation") if "{title}" in args.doc_prefix else args.doc_prefix
dp_none = args.doc_prefix.format(title="none") if "{title}" in args.doc_prefix else args.doc_prefix
v = embed([args.query_prefix + EN, args.query_prefix + FI, args.query_prefix + DE, dp + DOC] + [dp_none + u for u in UNRELATED])
d, un = v[3], v[4:]
sanity["retrieval_query_vs_document"] = {
    "en_doc": round(float(v[0] @ d), 4), "fi_doc": round(float(v[1] @ d), 4), "de_doc": round(float(v[2] @ d), 4),
    "en_unrelated_doc_max": round(float((un @ v[0]).max()), 4), "fi_unrelated_doc_max": round(float((un @ v[1]).max()), 4), "de_unrelated_doc_max": round(float((un @ v[2]).max()), 4),
}
sanity["retrieval_query_vs_document"]["pass"] = bool(
    v[0] @ d > (un @ v[0]).max() and v[1] @ d > (un @ v[1]).max() and v[2] @ d > (un @ v[2]).max()
)
vec_dump["retrieval"] = v
report["dim"] = int(v.shape[1])
report["norm_check"] = round(float(np.linalg.norm(v[0])), 4)
report["sanity"] = sanity
report["works"] = bool(sanity["query_prefix_both"]["pass"] and sanity["retrieval_query_vs_document"]["pass"])
if args.save_vectors:
    tag = args.tag or args.runtime
    np.savez(os.path.join(ROOT, "bench/catalog/out", f"scout_vectors.{tag}.npz"), **vec_dump)

stage("sanity_done")

# ---- 2. throughput on real short documents ----------------------------------------------------------------
import pyarrow as pa
import pyarrow.parquet as pq

# Keys first (three small columns), then only the needed rows of the text columns.
t = pq.read_table(f"{DATA}/clauses.parquet", columns=["title", "year", "section"])
ti, yr, sec = t["title"].to_pylist(), t["year"].to_pylist(), t["section"].to_pylist()
del t
newest = {}
for a, y in zip(ti, yr):
    newest[a] = max(newest.get(a, 0), y)
first = {}
for i, (a, y, s) in enumerate(zip(ti, yr, sec)):
    if y == newest[a] and (a, s) not in first:
        first[(a, s)] = i
del ti, yr, sec
t = pq.read_table(f"{DATA}/clauses.parquet", columns=["title", "section", "subject", "context", "clause"])
rows = t.take(pa.array(list(first.values()))).to_pylist()
del t
pa.default_memory_pool().release_unused()
stage("parquet_done")


def doc_text(r, words=60):
    body = " ".join(((r["context"] or "") + " " + (r["clause"] or "")).split()[:words])
    head = (r["subject"] or "none").strip() or "none"
    if "{title}" in args.doc_prefix:
        return args.doc_prefix.format(title=head) + body
    return args.doc_prefix + head + ". " + body


# Benchmark items whose gold section is in the newest edition: 20 per language go into the probe.
keys = set()
with open(os.path.join(ROOT, "bench/exa_study/discovery.jsonl")) as f:
    for line in f:
        if line.strip():
            keys.add(json.loads(line)["key"])
probe, per_lang, seen = [], collections.Counter(), set()
with open(os.path.join(ROOT, "bench/exa_study/all-situations.jsonl")) as f:
    for line in f:
        if not line.strip():
            continue
        it = json.loads(line)
        k = f'{it["gid"]}|{it["question"].encode("utf-16-le")[:160].decode("utf-16-le", errors="ignore")}'
        if it.get("attack") or k not in keys or k in seen or it["ref"]["source"] != "ecfr":
            continue
        seen.add(k)
        g = (int(it["ref"]["title"]), str(it["ref"]["section"]))
        if g in first and per_lang[it["lang"]] < args.probe_per_lang:
            per_lang[it["lang"]] += 1
            probe.append((it["lang"], it["question"], g))
must = {g for _, _, g in probe} | {(14, "250.5")}
keyed = {(r["title"], r["section"]): r for r in rows}
chosen = [g for g in must if g in keyed]
stride = max(1, len(rows) // args.n)
for r in rows[::stride]:
    g = (r["title"], r["section"])
    if len(chosen) >= args.n:
        break
    if g not in must:
        chosen.append(g)
docs = [doc_text(keyed[g]) for g in chosen]
wc = sorted(len(d.split()) for d in docs)
report["throughput_docs"] = {"n": len(docs), "words_median": wc[len(wc) // 2], "words_max": wc[-1], "candidate_sections_newest": len(rows)}
embed(docs[: args.batch])  # warm up (shader/graph compilation, page-in)
t0 = time.time()
dv = embed(docs)
dt = time.time() - t0
stage("throughput_done")
report["seconds_per_1000_docs"] = round(dt * 1000 / len(docs), 2)
report["docs_per_second"] = round(len(docs) / dt, 1)

# ---- 3. indicative retrieval probe on the 1,000 documents (not the index) ----------------------------------
qs = [args.query_prefix + q for _, q, _ in probe] + [args.query_prefix + s for s in (EN, FI, DE)]
t0 = time.time()
qv = embed(qs)
report["seconds_per_query_batch_avg"] = round((time.time() - t0) / len(qs), 4)
sims = qv @ dv.T
pos = {g: i for i, g in enumerate(chosen)}
hit = collections.defaultdict(lambda: [0, 0, 0, 0])  # n, top1, top5, same part in top5
for (lang, _, g), row in zip(probe, sims[: len(probe)]):
    top = np.argsort(-row)[:5]
    h = hit[lang]
    h[0] += 1
    h[1] += int(top[0] == pos[g])
    h[2] += int(pos[g] in top)
    gp = (g[0], keyed[g]["section"].split(".")[0])
    h[3] += int(any((chosen[j][0], chosen[j][1].split(".")[0]) == gp for j in top))
report["probe_note"] = f"indicative only: {len(docs)} newest-edition sections as candidates, gold guaranteed present, up to {args.probe_per_lang} benchmark questions per language"
report["probe"] = {lang: {"n": h[0], "top1": h[1], "top5": h[2], "part_top5": h[3]} for lang, h in hit.items()}
if (14, "250.5") in pos:
    report["bumped_flight_rank_of_14cfr250.5"] = {
        name: int(np.where(np.argsort(-sims[len(probe) + j]) == pos[(14, "250.5")])[0][0]) + 1 for j, name in enumerate(["en", "fi", "de"])
    }
    report["bumped_flight_top3"] = {
        name: [f"{chosen[i][0]} CFR {chosen[i][1]}" for i in np.argsort(-sims[len(probe) + j])[:3]] for j, name in enumerate(["en", "fi", "de"])
    }

stage("end")
report["stages"] = STAGES
cur, peak = footprint_gb()
report["peak_memory"] = {
    "phys_footprint_peak_gb": None if peak is None else round(peak, 3),
    "phys_footprint_now_gb": None if cur is None else round(cur, 3),
    "max_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3),
    **peak_extra(),
}
out = os.path.join(ROOT, "bench/catalog/out", f"scout_embed.{args.tag or args.runtime + '-' + report['device']}.json")
with open(out, "w") as f:
    json.dump(report, f, indent=1)
print(json.dumps(report, indent=1))
