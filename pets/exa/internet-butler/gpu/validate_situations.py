#!/usr/bin/env python3
"""TimeLaw-Situations, cross-family validation (GPU): a model from a different family than the generator
reads each generated situation blind and says which clause applies. The result is stored as recovers2.

Why: the generator's own blind pass shares the generator's habits. An item that a second family also recovers
is much more likely to have a correct gold label; an item neither recovers is likely mislabelled or
under-specified. Benchmarks report accuracy on all items and on the cross-family-consistent subset.

Usage (on the VM): python3 validate_situations.py situations.jsonl out.jsonl --model /root/models/gemma-4-12b
"""
import argparse, json, re
from vllm import LLM, SamplingParams

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("--model", required=True)
ap.add_argument("--max-model-len", type=int, default=8192); ap.add_argument("--name", default="")
a = ap.parse_args()
own = lambda c: c.split(" … ")[-1]

def fit(clause, n=700):
    if len(clause) <= n:
        return clause
    o = own(clause)
    return o[:n] if len(o) >= n - 40 else clause[: n - len(o) - 3].rstrip() + " … " + o

rows = [json.loads(l) for l in open(a.inp, encoding="utf-8") if l.strip()]
def prompt(r):
    listing = "\n".join(f"[{i}] {fit(c)}" for i, c in enumerate(r["clauses"]))
    return [{"role": "user", "content": f"""Clauses of the law as in force on {r['date']}:

{listing}

A person writes: "{r['question']}"

Which single clause sets the amount that applies to this person? Answer with JSON only: {{"clause": <number>}}"""}]

llm = LLM(model=a.model, max_model_len=a.max_model_len, gpu_memory_utilization=0.92)
# Thinking models (Gemma 4 12B and larger) would spend the 40 tokens on a thought block: switch it off.
outs = llm.chat([prompt(r) for r in rows], SamplingParams(temperature=0.0, max_tokens=40), chat_template_kwargs={"enable_thinking": False})
n = 0
with open(a.out, "w", encoding="utf-8") as f:
    for r, o in zip(rows, outs):
        m = re.search(r"\{.*?\}", o.outputs[0].text, re.S)
        try:
            c = json.loads(m.group(0))["clause"] if m else None
        except Exception:
            c = None
        ok = isinstance(c, int) and 0 <= c < len(r["clauses"]) and r["clauses"][c] == r["clauses"][r["target"]]
        r["recovers2"], r["validator2"] = bool(ok), a.name or a.model.rstrip("/").split("/")[-1]
        n += ok
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(json.dumps({"items": len(rows), "recovers2": n, "both": sum(1 for r in rows if r["recovers2"] and r.get("generatorRecovers")), "neither": sum(1 for r in rows if not r["recovers2"] and not r.get("generatorRecovers"))}))
