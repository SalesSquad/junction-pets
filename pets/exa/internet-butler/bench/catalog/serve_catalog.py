#!/usr/bin/env python3
"""The semantic catalog as a local search service: which provision sets the amount for this situation?

EmbeddingGemma (MLX) embeds the person's message as written, in any language, and the service returns the
nearest amount-bearing provisions among those that exist in the event's year. Vectors and rows are loaded
once from bench/catalog/out/ (build_catalog.py). It listens on 127.0.0.1 only: the message never leaves the
machine, which is what lets private mode find provisions beyond the built-in list.

  POST /search  {"query": "...", "k": 5, "year": 2021}
             -> {"results": [{"title": 14, "part": "250", "section": "250.5", "subject": "...", "score": 0.61, "years": [first, last], "text": "..."}],
                 "registry": [{"title": "...", "jurisdiction": "EU", "ref": {...}, "also": [], "about": "...", "score": 0.55}], "ms": 12}
  GET  /health  {"ok": true, "rows": 5924, "model": "..."}

  .venv-catalog/bin/python bench/catalog/serve_catalog.py [--port 8791] [--recipe clauses1200]
"""
import argparse, json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedder import DOC_PREFIX_TITLED, QUERY_PREFIX, MODEL_ID, load_embedder, out_path

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8791); ap.add_argument("--recipe", default="clauses1200")
ap.add_argument("--max-tokens", type=int, default=512)
a = ap.parse_args()
tag = "" if a.recipe == "clauses1200" else a.recipe
rows = [json.loads(l) for l in open(out_path("catalog.jsonl", tag), encoding="utf-8")]
vecs = np.load(out_path("embeddings.npy", tag)).astype(np.float32)
assert len(rows) == vecs.shape[0], "catalog rows and vectors differ in length"
years = [set(r["years"]) for r in rows]
emb = load_embedder("mlx")
emb.embed([QUERY_PREFIX + "warm up"], max_tokens=32)
# The app's built-in rights (export_registry.mjs), embedded by their descriptions: a few entries from several
# countries, matched in any language. Returned apart from the CFR rows, with their own scores.
REG_PATH = out_path("registry.json")
registry = json.load(open(REG_PATH, encoding="utf-8")) if os.path.exists(REG_PATH) else []
reg_vecs = emb.embed([DOC_PREFIX_TITLED.format(title=r["title"]) + r["about"] for r in registry], max_tokens=256) if registry else None
MAX_BODY, MAX_QUERY = 64 * 1024, 4000

def search(query, k, year):
    q = emb.embed([QUERY_PREFIX + query], max_tokens=a.max_tokens)[0]
    reg = []
    if reg_vecs is not None:
        rs = reg_vecs @ q
        reg = [{"title": registry[i]["title"], "jurisdiction": registry[i]["jurisdiction"], "ref": registry[i]["ref"], "also": registry[i]["also"], "about": registry[i]["about"], "score": round(float(rs[i]), 4)} for i in np.argsort(-rs)[:3]]
    scores = vecs @ q
    if year is not None:
        mask = np.fromiter((year in y for y in years), dtype=bool, count=len(rows))
        if mask.any():  # a year outside the editions (before 1996, or the current year not printed yet): search all
            scores = np.where(mask, scores, -1.0)
    top = np.argsort(-scores)[:k]
    return [{"title": rows[i]["title"], "part": rows[i]["part"], "section": rows[i]["section"], "subject": rows[i]["subject"], "score": round(float(scores[i]), 4),
             "years": [min(rows[i]["years"]), max(rows[i]["years"])], "text": rows[i]["text"][:400]} for i in top if scores[i] > -1.0], reg

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # no request logging: bodies hold the person's situation
        pass

    def send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, {"ok": True, "rows": len(rows), "registry": len(registry), "model": MODEL_ID, "recipe": a.recipe})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/search":
            return self.send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("content-length") or 0)
            if n <= 0 or n > MAX_BODY:
                return self.send(413, {"error": "body too large or empty"})
            d = json.loads(self.rfile.read(n))
            query, k, year = d.get("query"), d.get("k", 5), d.get("year")
            if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
                return self.send(400, {"error": f"query: text of at most {MAX_QUERY} characters"})
            if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 20:
                return self.send(400, {"error": "k: an integer from 1 to 20"})
            if year is not None and (not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2100):
                return self.send(400, {"error": "year: an integer year or null"})
            t0 = time.time()
            results, reg = search(query, k, year)
            self.send(200, {"results": results, "registry": reg, "ms": round((time.time() - t0) * 1000)})
        except (ValueError, KeyError, TypeError) as e:
            self.send(400, {"error": f"bad request: {type(e).__name__}"})
        except Exception as e:
            print(f"search failed: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr, flush=True)
            self.send(500, {"error": f"search failed: {type(e).__name__}"})

print(json.dumps({"listening": f"http://127.0.0.1:{a.port}", "rows": len(rows), "model": MODEL_ID}), flush=True)
# Single-threaded on purpose: MLX evaluates on the thread that loaded the model.
HTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
