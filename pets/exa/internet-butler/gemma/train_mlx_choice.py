#!/usr/bin/env python3
"""Train a small on-device clause judge with MLX: LoRA on the listwise choice question, answer position only.

The judge reads a situation and every tier of a provision as lettered options and is scored by the logits of
the option letters at the first answer position (gemma/mlx_judge.py, shared with the scorer and the server). So the loss needs one position, not the sequence:

  hidden states for the prompt -> last position -> output head -> cross-entropy over the option letters

mlx_lm.lora computes the 262k-wide output for every token of a ~1,100-token prompt (about 7 s per step on an
M5 Pro, 24 GB); this takes the head at one position instead (about 0.6 s per step, 10 GB peak).

Labels are the clauses known by construction, from the `clean` tier (the writer's model family and every other
family asked recover the clause blind). No output of a hosted judge is used as a label.

  .venv-mlx/bin/python gemma/train_mlx_choice.py --model mlx-community/gemma-4-e2b-it-4bit \
      --data bench/datasets/out/training-v3 --out adapters/gemma4-e2b-choice --max-minutes 150
"""
import argparse, json, math, os, random, sys, time
import mlx.core as mx, mlx.nn as nn, mlx.optimizers as optim
from mlx.utils import tree_flatten, tree_map
from mlx_lm import load
from mlx_lm.tuner.utils import linear_to_lora_layers

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mlx_judge import LETTERS, letter_ids as letter_ids_of, option_logits_train, render

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--tiers", default="clean", help="comma-separated label tiers to train on")
ap.add_argument("--epochs", type=float, default=2.0); ap.add_argument("--max-minutes", type=float, default=0)
ap.add_argument("--lr", type=float, default=1e-4); ap.add_argument("--accumulate", type=int, default=8)
ap.add_argument("--num-layers", type=int, default=16); ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--scale", type=float, default=20.0); ap.add_argument("--dropout", type=float, default=0.05)
ap.add_argument("--max-tokens", type=int, default=1536); ap.add_argument("--eval-every", type=int, default=1000)
ap.add_argument("--memory-gb", type=float, default=10.0)
ap.add_argument("--thinking", choices=["on", "off"], default="off", help="Gemma's thinking switch in the prompt; recorded in adapter_config.json so scoring uses the same")
ap.add_argument("--eval-items", type=int, default=200); ap.add_argument("--limit", type=int, default=0); ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()
random.seed(a.seed); mx.random.seed(a.seed)
# Prompts differ in length, so MLX's buffer cache grows without bound (17 GB and swapping on a 24 GB Mac in the
# first attempt). The cache cap is what bounds it; MLX's memory limit is a guideline, not a hard stop.
mx.set_cache_limit(1 << 30)
mx.set_memory_limit(int(a.memory_gb * (1 << 30)))

model, tok = load(a.model)
lm = model.language_model
model.freeze()
lora = {"rank": a.rank, "scale": a.scale, "dropout": a.dropout}
linear_to_lora_layers(model, a.num_layers, lora)
os.makedirs(a.out, exist_ok=True)
thinking = a.thinking == "on"
json.dump({"fine_tune_type": "lora", "num_layers": a.num_layers, "lora_parameters": lora, "model": a.model, "objective": "choice letter at the answer position, uncapped float32 logits", "tiers": a.tiers, "enable_thinking": thinking}, open(f"{a.out}/adapter_config.json", "w"), indent=1)
letter_ids = letter_ids_of(tok)

def read(split):
    rows = [json.loads(l) for l in open(f"{a.data}/{split}.jsonl", encoding="utf-8")]
    return [r for r in rows if len(r["clauses"]) <= len(LETTERS) and r["tier"] in a.tiers.split(",")]
train, valid_all = read("train"), read("valid")
# A seeded sample of the whole validation split (attacked items included), from its own generator so the training
# shuffle is unchanged. The first run took the first 200 rows, none of which was an attacked message.
valid = random.Random(a.seed).sample(valid_all, min(a.eval_items, len(valid_all))) if a.eval_items else valid_all
if a.limit:
    train = train[: a.limit]

def encode(r, order):
    return mx.array(render(tok, r["question"], r["clauses"], order, thinking, a.max_tokens))[None]

def option_logits(ids, k):
    return option_logits_train(lm, ids, letter_ids, k)

def loss_fn(ids, k, target):
    return nn.losses.cross_entropy(option_logits(ids, k)[None], mx.array([target])).mean()

def accuracy(rows):
    model.eval()
    ok = 0
    for r in rows:
        ls = option_logits(encode(r, list(range(len(r["clauses"])))), len(r["clauses"]))
        ok += int(mx.argmax(ls).item() == r["target"])
    model.train()
    return ok / max(1, len(rows))

def save(name="adapters.safetensors"):
    mx.save_safetensors(f"{a.out}/{name}", dict(tree_flatten(model.trainable_parameters())))

total = int(len(train) * a.epochs)
updates = max(1, total // a.accumulate)
warm = min(100, updates // 10)
decay = optim.cosine_decay(a.lr, updates - warm, a.lr * 0.05)
schedule = decay if warm == 0 else optim.join_schedules([optim.linear_schedule(1e-6, a.lr, warm), decay], [warm])
opt = optim.AdamW(learning_rate=schedule, weight_decay=0.01)
grad_fn = nn.value_and_grad(model, loss_fn)
n_train = sum(v.size for _, v in tree_flatten(model.trainable_parameters()))
print(json.dumps({"train": len(train), "valid": len(valid), "steps": total, "updates": updates, "trainable": n_train, "layers": a.num_layers, "of": len(model.layers)}), flush=True)

t0, acc, seen, run_loss, best = time.time(), None, 0, 0.0, -1.0
model.train()
order_of = list(range(len(train)))
stop = False
while seen < total and not stop:
    random.shuffle(order_of)
    for i in order_of:
        if seen >= total:
            break
        r = train[i]
        o = random.sample(range(len(r["clauses"])), len(r["clauses"]))  # shuffled options: the letter carries no prior
        loss, grads = grad_fn(encode(r, o), len(o), o.index(r["target"]))
        acc = grads if acc is None else tree_map(lambda x, y: x + y, acc, grads)
        mx.eval(loss, acc)
        run_loss += loss.item(); seen += 1
        if seen % a.accumulate == 0:
            opt.update(model, tree_map(lambda g: g / a.accumulate, acc))
            mx.eval(model.parameters(), opt.state)
            acc = None
        if seen % 10 == 0:
            mx.clear_cache()
        if seen % 100 == 0:
            print(json.dumps({"step": seen, "loss": round(run_loss / 100, 4), "lr": float(opt.learning_rate.item()), "min": round((time.time() - t0) / 60, 1), "sec_per_step": round((time.time() - t0) / seen, 2), "peak_gb": round(mx.get_peak_memory() / (1 << 30), 1)}), flush=True)
            run_loss = 0.0
        if seen % a.eval_every == 0 or seen == total:
            va = accuracy(valid)
            save("last.safetensors")
            if va >= best:  # a later checkpoint wins a tie
                best = va; save()
            print(json.dumps({"step": seen, "valid_acc": round(va, 4), "best": round(best, 4)}), flush=True)
        if a.max_minutes and (time.time() - t0) / 60 > a.max_minutes:
            stop = True
            break
va = accuracy(valid)
save("last.safetensors")
if va >= best:
    best = va; save()
print(json.dumps({"done": True, "steps": seen, "valid_acc": round(va, 4), "best": round(best, 4), "minutes": round((time.time() - t0) / 60, 1)}), flush=True)
