#!/usr/bin/env python3
"""Listwise clause judge, MLX training loop with the objective that actually fits the task.

Why the plain mlx_lm.lora run stayed at chance: it trained full-vocabulary cross-entropy on the completion
"<letter><end_of_turn>\n" with batch 1, so most of the loss was formatting tokens and every step saw one
noisy decision. Here, as in the torch train_list.py:
- the score of option i is the last-position hidden state times the embedding row of its letter, and the loss
  is softmax cross-entropy over the k letters of the group only (multi-gold via logsumexp);
- gradients are accumulated over --accum groups per update (an effective batch), with warmup + cosine lr;
- the option order is re-shuffled every time a group is seen;
- LoRA on all layers (rank --rank);
- optional distillation: KL(teacher || student) over the k options, from Nemotron log-probs (--teacher FILE).
The adapter is saved in mlx_lm format, so gemma/mlx_lk_eval.py --mlx-adapter (or gemma/mlx_list.py score) loads it unchanged.

Round-4 additions (LK3 on Apple silicon, mirroring gpu train_list3.py): --extra-train rows (Haiku-translated Finnish
situations), --kd-skip-lang (no Nemotron distillation on Finnish rows), option-subset augmentation (--subset-prob,
--subset-max; a subset keeps one gold option, the teacher follows the subset), LoRA on all seven projections with
the torch run's effective scale (rsLoRA alpha/sqrt(r) = 8), and a wall-clock budget (--time-budget-min) that shrinks
the cosine schedule after 20 updates, as train_list.py does.
"""
import argparse, json, math, os, random, sys, time
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_flatten, tree_map
from mlx_lm import load
from mlx_lm.tuner.utils import linear_to_lora_layers

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mlx_list import SEP, LETTERS, user_text  # the listwise prompt (gemma/mlx_list.py)

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--epochs", type=float, default=1.0); ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--accum", type=int, default=8); ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--scale", type=float, default=20.0); ap.add_argument("--layers", type=int, default=0, help="0 = all")
ap.add_argument("--teacher", default=""); ap.add_argument("--beta", type=float, default=0.5); ap.add_argument("--teacher-temp", type=float, default=1.0)
ap.add_argument("--inconsistent-weight", type=float, default=0.5)
ap.add_argument("--probe-every", type=int, default=150, help="updates between quick valid probes")
ap.add_argument("--probe-n", type=int, default=120); ap.add_argument("--max-tokens", type=int, default=2048)
ap.add_argument("--seed", type=int, default=5); ap.add_argument("--limit-train", type=int, default=0)
ap.add_argument("--extra-train", action="append", default=[]); ap.add_argument("--kd-skip-lang", default="")
ap.add_argument("--subset-prob", type=float, default=0.0); ap.add_argument("--subset-max", type=int, default=5)
ap.add_argument("--time-budget-min", type=float, default=0)
ap.add_argument("--no-grad-ckpt", action="store_true", help="disable per-layer gradient checkpointing (on by default: same math, far less activation memory)")
ap.add_argument("--cache-limit-gb", type=float, default=2.0, help="cap MLX's buffer cache so the process does not push the Mac into swap")
ap.add_argument("--keys", default="self_attn.q_proj,self_attn.k_proj,self_attn.v_proj,self_attn.o_proj,mlp.gate_proj,mlp.up_proj,mlp.down_proj")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
random.seed(a.seed); mx.random.seed(a.seed)
own = lambda c: c.split(SEP)[-1]


def load_rows(p, limit=0):
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    for r in rows:
        g = own(r["clauses"][r["target"]])
        r["gold"] = [i for i, c in enumerate(r["clauses"]) if own(c) == g]
    return rows[:limit] if limit else rows


train = load_rows(f"{a.data}/train.jsonl", a.limit_train)
for _p in a.extra_train:
    train += load_rows(_p, a.limit_train)
skip_lang = {x for x in a.kd_skip_lang.split(",") if x}
valid = load_rows(f"{a.data}/valid.jsonl")
teacher = {}
if a.teacher:
    for l in open(a.teacher, encoding="utf-8"):
        j = json.loads(l); teacher[(j["question"], tuple(j["clauses"]))] = j["lp"]
print(json.dumps({"train": len(train), "valid": len(valid), "teacher_rows": len(teacher), "kd_skip_lang": sorted(skip_lang),
                  "train_kd_skipped": sum(r.get("lang") in skip_lang for r in train)}), flush=True)

model, tok = load(a.model)
model.freeze()
n_layers = len(model.layers)
use = n_layers if a.layers <= 0 else a.layers
KEYS = [k for k in a.keys.split(",") if k]
linear_to_lora_layers(model, use, {"rank": a.rank, "scale": a.scale, "dropout": 0.0, "keys": KEYS})
if not a.no_grad_ckpt:
    from mlx_lm.tuner.trainer import grad_checkpoint
    grad_checkpoint(model.layers[0])  # patches the decoder-layer class: every layer recomputes its activations
try:
    mx.set_cache_limit(int(a.cache_limit_gb * 1024 ** 3))
except AttributeError:
    mx.metal.set_cache_limit(int(a.cache_limit_gb * 1024 ** 3))
lm = model.language_model
emb = lm.model.embed_tokens
letter_ids = mx.array([tok.encode(L, add_special_tokens=False)[0] for L in LETTERS])
ntrain = sum(v.size for _, v in tree_flatten(model.trainable_parameters()))
print(json.dumps({"layers": n_layers, "lora_layers": use, "trainable": ntrain}), flush=True)


def encode(question, clauses, order):
    p = tok.apply_chat_template([{"role": "user", "content": user_text(question, clauses, order)}], tokenize=False, add_generation_prompt=True)
    ids = tok.encode(p, add_special_tokens=False)
    if len(ids) >= a.max_tokens:
        raise ValueError(f"prompt of {len(ids)} tokens reaches max_tokens")
    return mx.array(ids)[None]


def letter_scores(x, k):
    h = lm.model(x)[0, -1]
    W = emb(letter_ids[:k])
    return (W.astype(mx.float32) @ h.astype(mx.float32))


def loss_fn(model, x, k, gold_slots, t_slots, w):
    lg = letter_scores(x, k)
    lp = lg - mx.logsumexp(lg)
    ce = -mx.logsumexp(lp[gold_slots])
    if t_slots is not None:
        tp = mx.softmax(t_slots / a.teacher_temp)
        kl = mx.sum(tp * (mx.log(tp + 1e-9) - lp))
        loss = (1 - a.beta) * ce + a.beta * kl
    else:
        loss = ce
    return w * loss


vg = nn.value_and_grad(model, loss_fn)
updates_per_epoch = math.ceil(len(train) / a.accum)
total = max(1, int(updates_per_epoch * a.epochs))
warm = max(1, int(0.05 * total))
sched = lambda s: a.lr * min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total)))
opt = optim.Adam(learning_rate=a.lr)


def probe(n):
    ok = 0
    for r in valid[:n]:
        k = len(r["clauses"])
        s = letter_scores(encode(r["question"], r["clauses"], list(range(k))), k)
        ok += int(mx.argmax(s).item()) in r["gold"]
    return ok / n


def save(tag=""):
    mx.save_safetensors(f"{a.out}/adapters{tag}.safetensors", dict(tree_flatten(model.trainable_parameters())))
    cfg = {"fine_tune_type": "lora", "num_layers": use,
           "lora_parameters": {"rank": a.rank, "scale": a.scale, "dropout": 0.0, "keys": KEYS}, "model": a.model}
    json.dump(cfg, open(f"{a.out}/adapter_config.json", "w"), indent=1)


print(json.dumps({"updates": total, "accum": a.accum, "probe_at_start": round(probe(a.probe_n), 3)}), flush=True)
step, t0, run, seen = 0, time.time(), 0.0, 0
order = []
while step < total:
    if not order:
        order = list(range(len(train))); random.shuffle(order)
    acc_g, loss_sum, wsum = None, 0.0, 0.0
    for _ in range(a.accum):
        if not order:
            break
        r = train[order.pop()]
        t = teacher.get((r["question"], tuple(r["clauses"])))
        if r.get("lang") in skip_lang:
            t = None
        k = len(r["clauses"])
        if k >= 4 and random.random() < a.subset_prob:
            size = random.randint(2, min(k - 1, a.subset_max))
            gsel = random.choice(r["gold"])
            idx = sorted([gsel] + random.sample([i for i in range(k) if i != gsel], size - 1))
            r = {**r, "clauses": [r["clauses"][i] for i in idx], "gold": [j for j, i in enumerate(idx) if i in r["gold"]]}
            t = [t[i] for i in idx] if t is not None else None
            k = len(idx)
        o = list(range(k)); random.shuffle(o)
        gold_slots = mx.array([s for s, ci in enumerate(o) if ci in r["gold"]])
        t_slots = mx.array([t[ci] for ci in o]) if t is not None else None
        w = 1.0 if r.get("generatorRecovers", True) else a.inconsistent_weight
        loss, g = vg(model, encode(r["question"], r["clauses"], o), k, gold_slots, t_slots, w)
        acc_g = g if acc_g is None else tree_map(lambda x, y: x + y, acc_g, g)
        mx.eval(acc_g, loss)
        loss_sum += loss.item(); wsum += w; seen += 1
    acc_g = tree_map(lambda x: x / max(wsum, 1e-6), acc_g)
    opt.learning_rate = sched(step)
    opt.update(model, acc_g)
    mx.eval(model.parameters(), opt.state)
    step += 1; run += loss_sum / max(wsum, 1e-6)
    if step == 20 and a.time_budget_min:
        per = (time.time() - t0) / 20
        fit = int(a.time_budget_min * 60 / per)
        if fit < total:
            total = max(40, fit)
        print(json.dumps({"sec_per_update": round(per, 1), "planned_updates": total,
                          "planned_epochs": round(total * a.accum / len(train), 2)}), flush=True)
    if step % 25 == 0:
        print(json.dumps({"update": step, "of": total, "loss": round(run / 25, 4), "lr": round(sched(step), 7),
                          "groups": seen, "min": round((time.time() - t0) / 60, 1)}), flush=True)
        run = 0.0
    if a.probe_every and step % a.probe_every == 0:
        print(json.dumps({"update": step, "valid_probe": round(probe(a.probe_n), 3)}), flush=True)
        save()
save()
print(json.dumps({"done": True, "updates": step, "min": round((time.time() - t0) / 60, 1), "valid_probe": round(probe(a.probe_n), 3)}), flush=True)
