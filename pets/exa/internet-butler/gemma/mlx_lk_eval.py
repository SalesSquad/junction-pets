#!/usr/bin/env python3
"""On-device (MLX) version of the listwise judge, scored exactly like the torch judge (PROTOCOL amendment 6).

The PEFT LoRA trained on the bf16 HF model (r 16, alpha 32, rsLoRA -> scale alpha/sqrt(r) = 8, targets
q/k/v/o/gate/up/down of every text layer; vision-tower adapters are ignored) is applied to the MLX 4-bit base:
  --mode unfused : LoRALinear on top of the quantized layers (lora_a = A^T, lora_b = B^T)
  --mode fused   : merged into the weights and re-quantized (one deployable 4-bit model)
Scoring = gpu train_list evaluate(): same prompt (mlx_list.user_text + chat template), same option orders
(identity, reversed, seeded shuffles with salt "5|<question>"), letter log-softmax over the shown options,
averaged per clause; prune-then-listwise for k > m on B0's top-m clauses (as bench/situations/listwise/prune_sets.py).
Usage (from the repository root): python gemma/mlx_lk_eval.py --model models/gemma-3-4b-it-4bit --peft adapters/lk2_peft --mode fused --split valid
         --m 5 --perms 4 --out runs/mlx_lk2p_fused/valid_scores.jsonl [--limit 0] [--save-fused DIR]
Valid prints accuracy and agreement with the torch scores (--torch FILE); test prints accuracy (descriptive).

v2: --mlx-adapter DIR loads an adapter trained natively in MLX (gemma/mlx_list_train.py, mlx_lm format) instead of a
PEFT one; --ms 3,4,5 scores every prune size in one pass (each group's unpruned scores once, plus one pruned
scoring per m < k) and writes <out>_none.jsonl and <out>_m<m>.jsonl.
"""
import argparse, json, math, os, random, re, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mlx_list import SEP, LETTERS, user_text  # the listwise prompt (gemma/mlx_list.py)

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--peft", default="")
ap.add_argument("--mlx-adapter", default=""); ap.add_argument("--ms", default="")
ap.add_argument("--mode", choices=["unfused", "fused"], default="fused")
ap.add_argument("--split", required=True); ap.add_argument("--data", default="bench/datasets/out/training")
ap.add_argument("--b0", default="runs/b0"); ap.add_argument("--m", type=int, default=5)
ap.add_argument("--perms", type=int, default=4); ap.add_argument("--seed", type=int, default=5)
ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--torch", default="", help="torch scores of the same judge for the drift report")
ap.add_argument("--save-fused", default="")
a = ap.parse_args()

import mlx.core as mx
import mlx.nn as nn
from mlx_lm import load as mload
from mlx_lm.tuner.lora import LoRALinear

model, tok = mload(a.model, adapter_path=a.mlx_adapter or None)
n = 0; skipped = 0; layers = model.language_model.model.layers
if a.mlx_adapter:
    a.peft = ""
cfg = json.load(open(os.path.join(a.peft, "adapter_config.json"))) if a.peft else {"r": 1, "lora_alpha": 1}
r = cfg["r"]; scale = cfg["lora_alpha"] / (math.sqrt(r) if cfg.get("use_rslora") else r)
W = mx.load(os.path.join(a.peft, "adapter_model.safetensors")) if a.peft else {}
pat = re.compile(r"layers\.(\d+)\.(self_attn|mlp)\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)\.lora_([AB])\.weight$")
pairs = {}
for k, v in W.items():
    if "vision" in k or "multi_modal" in k:
        skipped += 1; continue
    m_ = pat.search(k)
    if not m_:
        skipped += 1; continue
    pairs.setdefault((int(m_.group(1)), m_.group(2), m_.group(3)), {})[m_.group(4)] = v
for (li, blk, proj), ab in sorted(pairs.items()):
    parent = getattr(layers[li], blk)
    base = getattr(parent, proj)
    lora = LoRALinear.from_base(base, r=r, dropout=0.0, scale=scale)
    lora.lora_a = ab["A"].T.astype(mx.float32)
    lora.lora_b = ab["B"].T.astype(mx.float32)
    setattr(parent, proj, lora.fuse(dequantize=False) if a.mode == "fused" else lora)
    n += 1
mx.eval(model.parameters())
print(json.dumps({"lora_modules": n, "text_layers": len(layers), "skipped_keys": skipped, "scale": scale, "mode": a.mode}), flush=True)
assert a.mlx_adapter or n == 7 * len(layers), f"expected {7 * len(layers)} LoRA modules, got {n}"
if a.save_fused and a.mode == "fused":
    from mlx_lm.utils import save_model, save_config
    os.makedirs(a.save_fused, exist_ok=True)
    save_model(a.save_fused, model)
    cfgm = json.load(open(os.path.join(a.model, "config.json")))
    save_config(cfgm, os.path.join(a.save_fused, "config.json"))
    for f in os.listdir(a.model):
        if f.startswith("tokenizer") or f in ("special_tokens_map.json", "chat_template.json", "chat_template.jinja", "generation_config.json", "processor_config.json", "preprocessor_config.json"):
            open(os.path.join(a.save_fused, f), "wb").write(open(os.path.join(a.model, f), "rb").read())
    print(json.dumps({"saved_fused": a.save_fused}), flush=True)

ids = [tok.encode(L, add_special_tokens=False)[0] for L in LETTERS]
own = lambda c: c.split(SEP)[-1]
rows = [json.loads(l) for l in open(f"{a.data}/{a.split}.jsonl") if l.strip()]
if a.limit:
    rows = rows[: a.limit]
b0 = {(j["question"], tuple(j["clauses"])): j["score"] for j in map(json.loads, open(f"{a.b0}/{a.split}_scores.jsonl"))}


def orders_for(k, perms, salt):
    rng = random.Random(salt)
    out = [list(range(k))]
    if perms > 1 and k > 1:
        out.append(list(reversed(range(k))))
    while len(out) < perms:
        o = list(range(k)); rng.shuffle(o); out.append(o)
    return out[:max(1, perms)]


def score_clauses(question, clauses):
    k = len(clauses)
    acc = [0.0] * k
    P = orders_for(k, a.perms, f"{a.seed}|{question}")
    for o in P:
        prompt = tok.apply_chat_template([{"role": "user", "content": user_text(question, clauses, o)}], tokenize=False, add_generation_prompt=True)
        x = mx.array(tok.encode(prompt, add_special_tokens=False))[None]
        logits = model(x)[0, -1].astype(mx.float32)
        sel = logits[mx.array(ids[:k])]
        lp = (sel - mx.logsumexp(sel)).tolist()
        for slot, ci in enumerate(o):
            acc[ci] += lp[slot] / len(P)
    return acc


tor = {}
if a.torch:
    tor = {(j["question"], tuple(j["clauses"])): j["lp"] for j in map(json.loads, open(a.torch))}
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
if a.ms:
    MS = [int(x) for x in a.ms.split(",")]
    base = a.out[:-6] if a.out.endswith(".jsonl") else a.out
    outs = {"none": open(f"{base}_none.jsonl", "w", encoding="utf-8")}
    outs.update({m: open(f"{base}_m{m}.jsonl", "w", encoding="utf-8") for m in MS})
    okm = {k: 0 for k in outs}; t0 = time.time(); times = []
    for i, rw in enumerate(rows):
        q, cs = rw["question"], rw["clauses"]; k = len(cs); t1 = time.time()
        gold = {j for j, c in enumerate(cs) if own(c) == own(cs[rw["target"]])}
        full = score_clauses(q, cs)
        res_rows = {"none": full}
        s = b0[(q, tuple(cs))]
        for m in MS:
            if k > m:
                keep = sorted(sorted(range(k), key=lambda j: -s[j])[:m])
                sub = score_clauses(q, [cs[j] for j in keep])
                lp = [min(sub) - 5.0] * k
                for slot, j in enumerate(keep):
                    lp[j] = sub[slot]
                res_rows[m] = lp
            else:
                res_rows[m] = full
        times.append(time.time() - t1)
        for key, lp in res_rows.items():
            okm[key] += max(range(k), key=lambda j: lp[j]) in gold
            outs[key].write(json.dumps({"gid": rw.get("gid"), "question": q, "clauses": cs, "lp": lp}, ensure_ascii=False) + "\n")
        if (i + 1) % 50 == 0:
            msg = {"n": i + 1, "of": len(rows), "sec_per_group": round(statistics.mean(times), 2)}
            if a.split != "test":
                msg["acc"] = {str(k2): round(v / (i + 1), 4) for k2, v in okm.items()}
            print(json.dumps(msg), flush=True)
    for fh in outs.values():
        fh.close()
    res = {"split": a.split, "n": len(rows), "perms": a.perms, "minutes": round((time.time() - t0) / 60, 1),
           "sec_per_group_mean": round(statistics.mean(times), 3)}
    if a.split != "test":
        res["acc"] = {str(k2): round(v / len(rows), 4) for k2, v in okm.items()}
    print(json.dumps(res), flush=True)
    raise SystemExit
t0 = time.time(); times = []; ok = agree = 0
with open(a.out, "w", encoding="utf-8") as f:
    for i, rw in enumerate(rows):
        q, cs = rw["question"], rw["clauses"]
        k = len(cs)
        t1 = time.time()
        if k > a.m:
            s = b0[(q, tuple(cs))]
            keep = sorted(sorted(range(k), key=lambda j: -s[j])[: a.m])
            sub = score_clauses(q, [cs[j] for j in keep])
            lp = [min(sub) - 5.0] * k
            for slot, j in enumerate(keep):
                lp[j] = sub[slot]
        else:
            lp = score_clauses(q, cs)
        times.append(time.time() - t1)
        gold = {j for j, c in enumerate(cs) if own(c) == own(cs[rw["target"]])}
        pick = max(range(k), key=lambda j: lp[j])
        ok += pick in gold
        tl = tor.get((q, tuple(cs)))
        if tl is not None:
            agree += pick == max(range(k), key=lambda j: tl[j])
        f.write(json.dumps({"gid": rw.get("gid"), "question": q, "clauses": cs, "lp": lp}, ensure_ascii=False) + "\n")
        if (i + 1) % 50 == 0:
            print(json.dumps({"n": i + 1, "of": len(rows), "acc": round(ok / (i + 1), 4), "sec_per_group": round(statistics.mean(times), 2)}), flush=True)
res = {"split": a.split, "mode": a.mode, "n": len(rows), "acc": round(ok / len(rows), 4), "perms": a.perms, "m": a.m,
       "sec_per_group_mean": round(statistics.mean(times), 3), "sec_per_group_p50": round(statistics.median(times), 3),
       "sec_per_group_p95": round(sorted(times)[int(0.95 * (len(times) - 1))], 3), "minutes": round((time.time() - t0) / 60, 1)}
if tor:
    res["argmax_agreement_with_torch"] = round(agree / len(rows), 4)
print(json.dumps(res), flush=True)
