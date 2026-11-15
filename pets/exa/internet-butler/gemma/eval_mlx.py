#!/usr/bin/env python3
"""Evaluate a local Gemma (MLX) clause judge on the TimeLaw-Situations test split.

pointwise: P(yes) per (situation, clause) from the next-token logits after the chat prompt; written in the
           tournament's cache format ("student|situation|clause") so bench/situations/tournament.mjs --student=...
           scores Gemma next to Jev, Luna and the Qwen student, with and without code and Luna escalation.
listwise:  greedy answer (the clause number) vs the gold clause; accuracy by attack type.

Usage:
  .venv-mlx/bin/python gemma/eval_mlx.py --model mlx-community/gemma-3-4b-it-4bit --adapter adapters/gemma4b \
      --data bench/datasets/out/training --task pointwise --out bench/datasets/out/training/gemma4b.judgments.jsonl
"""
import argparse, json, math, time
import mlx.core as mx
from mlx_lm import load, generate
import pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--adapter", default=None)
ap.add_argument("--data", required=True); ap.add_argument("--task", choices=["pointwise", "listwise"], default="pointwise")
ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()

model, tok = load(a.model, adapter_path=a.adapter)
QUESTION = "Does `clause` set the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)?"

def fit(clause, n=900):
    """Shorten a clause to n characters by trimming its context chain, never the clause itself (the last " … " part)."""
    if len(clause) <= n:
        return clause
    own = clause.split(" … ")[-1]
    if len(own) >= n - 40:
        return own[:n]
    return clause[: n - len(own) - 3].rstrip() + " … " + own

def ids(text):
    return tok.encode(text, add_special_tokens=False)
yes_ids = {ids(" yes")[0], ids("yes")[0], ids("Yes")[0]}
no_ids = {ids(" no")[0], ids("no")[0], ids("No")[0]}

def prompt(content):
    return tok.apply_chat_template([{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)

t0 = time.time()
if a.task == "pointwise":
    pairs = [p for p in pq.read_table(f"{a.data}/pairs.parquet").to_pylist() if p["split"] == "test"]
    if a.limit:
        pairs = pairs[: a.limit]
    with open(a.out, "w") as f:
        for i, p in enumerate(pairs):
            text = prompt(f"situation: {p['situation']}\nclause: {fit(p['clause'])}\nquestion: {QUESTION}\nAnswer yes or no.")
            logits = model(mx.array(ids(text))[None])[0, -1].astype(mx.float32)
            lp = logits - mx.logsumexp(logits)
            y = math.log(sum(math.exp(lp[t].item()) for t in yes_ids))
            n = math.log(sum(math.exp(lp[t].item()) for t in no_ids))
            pyes = 1 / (1 + math.exp(n - y))
            f.write(json.dumps({"k": f"student|{p['situation']}|{p['clause']}", "p": pyes, "ms": 0, "tokens": 0}) + "\n")
            if i % 200 == 0:
                print(f"{i}/{len(pairs)} {time.time() - t0:.0f}s", flush=True)
    print(json.dumps({"task": "pointwise", "pairs": len(pairs), "seconds": round(time.time() - t0)}))
else:
    rows = [json.loads(l) for l in open(f"{a.data}/mlx-listwise/test.jsonl")]
    sit = [r for r in pq.read_table(f"{a.data}/situations.parquet").to_pylist() if r["split"] == "test"]
    if a.limit:
        rows, sit = rows[: a.limit], sit[: a.limit]
    ok, by = 0, {}
    with open(a.out, "w") as f:
        for r in rows:
            out = generate(model, tok, prompt=prompt(r["messages"][0]["content"]), max_tokens=4, verbose=False).strip()
            right = out.split()[0].strip(".[]") == r["messages"][1]["content"] if out else False
            ok += right
            f.write(json.dumps({"gold": r["messages"][1]["content"], "answer": out, "ok": right}) + "\n")
    print(json.dumps({"task": "listwise", "items": len(rows), "accuracy": round(ok / max(1, len(rows)), 3), "seconds": round(time.time() - t0)}))
