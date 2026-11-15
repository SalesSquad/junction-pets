#!/usr/bin/env python3
"""Score an MLX model (with or without a LoRA adapter) as a listwise clause judge.

One prompt per situation with every tier as a lettered option (the training prompt, gpu/prompting.py). The
answer is read from the uncapped float32 logits of the option letters at the first answer position
(gemma/mlx_judge.py), so nothing is generated. An adapter is scored with the prompt it was trained on; the
untrained model is scored with Gemma's thinking switch off. Writes one row per (situation, clause) in the
tournament's student format ({"k": "student|<situation>|<clause>", "p": probability}) and prints accuracy
overall, by label tier, by attack type and by language, with the always-first-option rate for reference.

  .venv-mlx/bin/python gemma/eval_mlx_choice.py --model mlx-community/gemma-4-e2b-it-4bit \
      --adapter adapters/gemma4-e2b-choice --data bench/datasets/out/training-v3 --split test-indep \
      --out runs/gemma4-e2b-choice.indep.judgments.jsonl
"""
import argparse, json, math, os, sys, time
from collections import defaultdict
import mlx.core as mx
from mlx_lm import load

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mlx_judge import LETTERS, letter_ids, option_logits, render, thinking_of

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--adapter", default=None)
ap.add_argument("--data", required=True); ap.add_argument("--split", default="test")
ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--tier", default="", help="score only this label tier (clean, half, none)")
ap.add_argument("--thinking", choices=["on", "off", "auto"], default="auto", help="auto: as the adapter was trained; off without an adapter")
ap.add_argument("--max-tokens", type=int, default=1536)
ap.add_argument("--orders", type=int, default=1, help="score this many rotations of the option order and average (cancels position preference)")
a = ap.parse_args()

mx.set_cache_limit(1 << 30)  # prompts differ in length; without a cap MLX's buffer cache grows until the Mac swaps
model, tok = load(a.model, adapter_path=a.adapter)
model.eval()
thinking = thinking_of(a.adapter, a.thinking)
letters = letter_ids(tok)
items = [json.loads(l) for l in open(f"{a.data}/{a.split}.jsonl", encoding="utf-8")]
items = [r for r in items if len(r["clauses"]) <= len(LETTERS) and (not a.tier or r["tier"] == a.tier)]
if a.limit:
    items = items[: a.limit]

t0, ok, n = time.time(), defaultdict(int), defaultdict(int)
# Always a fresh file: a pass that stops early leaves a short file, which the tournament refuses, instead of
# rows from another model.
with open(a.out, "w", encoding="utf-8") as f:
    for i, r in enumerate(items):
        k = len(r["clauses"])
        ps = [0.0] * k
        shifts = sorted({(j * k) // a.orders for j in range(a.orders)})  # evenly spaced rotations, without repeats
        for sh in shifts:
            order = [(i + sh) % k for i in range(k)]
            ls = option_logits(model, render(tok, r["question"], r["clauses"], order, thinking, a.max_tokens), letters, k)
            m = max(ls); z = sum(math.exp(x - m) for x in ls)
            for pos, ci in enumerate(order):
                ps[ci] += math.exp(ls[pos] - m) / z / len(shifts)
        right = ps.index(max(ps)) == r["target"]
        for key in ("all", f"tier:{r['tier']}", f"attack:{r['attack'] or 'none'}", f"lang:{r['lang']}"):
            n[key] += 1; ok[key] += right
        n["first-option"] += 1; ok["first-option"] += r["target"] == 0
        for c, p in zip(r["clauses"], ps):
            f.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": p}, ensure_ascii=False) + "\n")
        if i % 20 == 0:
            mx.clear_cache()
        if i % 200 == 0:
            print(f"{i}/{len(items)} acc {ok['all'] / max(1, n['all']):.3f} {time.time() - t0:.0f}s", flush=True)
print(json.dumps({"model": a.model, "adapter": a.adapter, "thinking": thinking, "orders": a.orders, "split": a.split, "items": n["all"], "seconds": round(time.time() - t0),
                  "accuracy": {k: {"n": n[k], "acc": round(ok[k] / n[k], 4)} for k in sorted(n)}}, indent=1))
