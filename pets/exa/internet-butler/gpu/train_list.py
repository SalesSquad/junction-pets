#!/usr/bin/env python3
"""Listwise clause judge: the model sees ALL sibling tiers of a provision at once and answers with a letter.

Why: the pointwise judge (gpu/train_group.py) scores each clause alone, so it cannot compare tiers that
differ only by a threshold; its test accuracy falls from 83% on 2-clause groups to 31% on 6-clause groups.
Here one prompt carries the situation, the provision context shared by all siblings (once), and every
sibling's distinguishing text as option A, B, C, ...; the score of option i is the next-token logit of
its letter at the answer position (one forward pass per group, not per clause).

Training: listwise cross-entropy over the letters of the group (multi-gold via logsumexp), with the option
order re-shuffled every time a group is seen (no position shortcut), LoRA on a causal LM.
Inference: test-time permutation averaging -- each group is scored under P orders (identity, reversed and
P-2 seeded shuffles); per-clause log-probabilities are averaged back in clause order.
Temperature is fitted on valid only. Writes valid and test scores, so ensembles can be tuned on valid.

Usage:
  python train_list.py --train train.jsonl --valid valid.jsonl --test test.jsonl --model /path/gemma-3-4b-it \
      --out runs/list4b --epochs 2 --perms 4
"""
import argparse, json, math, os, random, time
import torch
import torch.nn.functional as F

ap = argparse.ArgumentParser()
ap.add_argument("--train", default=""); ap.add_argument("--valid", default=""); ap.add_argument("--test", required=True)
ap.add_argument("--model", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--epochs", type=float, default=2.0); ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--lora-r", type=int, default=16); ap.add_argument("--grad-ckpt", action="store_true")
ap.add_argument("--max-len", type=int, default=2048, help="token cap per group prompt (raises if reached)")
ap.add_argument("--tokens-per-step", type=int, default=12000, help="approximate prompt tokens per optimizer step")
ap.add_argument("--perms", type=int, default=4, help="test-time permutations (1 = identity only)")
ap.add_argument("--inconsistent-weight", type=float, default=0.5)
ap.add_argument("--label-smoothing", type=float, default=0.0)
ap.add_argument("--limit-train", type=int, default=0); ap.add_argument("--limit-eval", type=int, default=0)
ap.add_argument("--seed", type=int, default=5)
ap.add_argument("--time-budget-min", type=float, default=0, help="shrink the schedule so training ends within this many minutes")
ap.add_argument("--save-every", type=int, default=100)
ap.add_argument("--budget-chars", type=int, default=3993, help="character budget for all options of one group")
ap.add_argument("--eval-only", action="store_true"); ap.add_argument("--adapter", default="")
ap.add_argument("--device", default="cuda")
ap.add_argument("--teacher", default="", help="teacher jsonl rows {question, clauses, lp} (per-clause log-probs) for distillation")
ap.add_argument("--beta", type=float, default=0.5, help="weight of the KL(teacher || student) term when --teacher is given")
ap.add_argument("--teacher-temp", type=float, default=1.0)
ap.add_argument("--kd-skip-lang", default="", help="comma-separated r['lang'] values that get no distillation term (gold CE only)")
ap.add_argument("--extra-train", action="append", default=[], help="extra training rows (jsonl, same schema), e.g. translated groups")
ap.add_argument("--subset-prob", type=float, default=0.0, help="probability that a group with k>=4 is trained on a random option subset")
ap.add_argument("--subset-max", type=int, default=5, help="largest subset size (subsets keep at least one gold option)")
ap.add_argument("--probe-every", type=int, default=0, help="steps between quick valid probes (identity order, --probe-n groups)")
ap.add_argument("--probe-n", type=int, default=200)
a = ap.parse_args()
random.seed(a.seed); torch.manual_seed(a.seed)
os.makedirs(a.out, exist_ok=True)
dev = a.device
LETTERS = [chr(ord("A") + i) for i in range(26)]
QUESTION = ("Which option sets the amount, rate, limit or time limit that applies to the person in the situation "
            "(the same kind of case, party and circumstances)? Answer with the option letter only.")
SEP = " … "


def split_common(clauses):
    """Shared leading context segments (the parent chain) and each clause's distinguishing remainder."""
    parts = [c.split(SEP) for c in clauses]
    common = []
    for segs in zip(*parts):
        if all(s == segs[0] for s in segs) and len(common) < min(len(p) for p in parts) - 1:
            common.append(segs[0])
        else:
            break
    rest = [SEP.join(p[len(common):]) for p in parts]
    return SEP.join(common), rest


def clip(text, n):
    """Shorten to n characters keeping the clause's own last part (the tier itself)."""
    if len(text) <= n:
        return text
    own = text.split(SEP)[-1]
    if len(own) >= n - 40:
        return own[:n]
    return text[: n - len(own) - 3].rstrip() + SEP + own


def build(situation, clauses, order, tok, budget_chars):
    common, rest = split_common(clauses)
    per = max(160, budget_chars // max(1, len(clauses)))
    lines = [f"situation: {situation}", "",
             "These options are the alternative tiers of one legal provision."]
    if common:
        lines.append(f"Shared provision text: {clip(common, 700)}")
    for slot, ci in enumerate(order):
        lines.append(f"{LETTERS[slot]}) {clip(rest[ci], per)}")
    lines += ["", f"question: {QUESTION}"]
    msgs = [{"role": "user", "content": "\n".join(lines)}]
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def load(path, limit=0):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if path else []
    own = lambda c: c.split(SEP)[-1]
    for r in rows:
        g = own(r["clauses"][r["target"]])
        r["gold"] = [i for i, c in enumerate(r["clauses"]) if own(c) == g]
    return rows[:limit] if limit else rows


train = load(a.train, a.limit_train)
for _p in a.extra_train:
    train += load(_p, a.limit_train)
valid, test = load(a.valid, a.limit_eval), load(a.test, a.limit_eval)
assert max(len(r["clauses"]) for r in train + valid + test) <= 26, "more than 26 options"
teacher = {}
skip_lang = {x for x in a.kd_skip_lang.split(",") if x}
if a.teacher:
    for l in open(a.teacher, encoding="utf-8"):
        j = json.loads(l)
        teacher[(j["question"], tuple(j["clauses"]))] = j["lp"]
    miss = sum((r["question"], tuple(r["clauses"])) not in teacher for r in train)
    print(json.dumps({"teacher_rows": len(teacher), "train_without_teacher": miss,
                      "kd_skip_lang": sorted(skip_lang), "train_kd_skipped": sum(r.get("lang") in skip_lang for r in train)}), flush=True)

from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, PeftModel, get_peft_model
tok = AutoTokenizer.from_pretrained(a.model)
tok.pad_token = tok.pad_token or tok.eos_token
tok.padding_side = "left"
letter_ids = []
for L in LETTERS:
    ids = tok(L, add_special_tokens=False).input_ids
    assert len(ids) == 1, ("letter must be one token", L, ids)
    letter_ids.append(ids[0])
assert len(set(letter_ids)) == 26
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
                                             device_map={"": 0} if dev == "cuda" else None)
if a.grad_ckpt:
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
if a.adapter:
    model = PeftModel.from_pretrained(model, a.adapter, is_trainable=not a.eval_only)
else:
    model = get_peft_model(model, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.05, use_rslora=True,
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                                             task_type="CAUSAL_LM"))
base = model.get_base_model()
backbone = getattr(base, base.base_model_prefix)
head = base.get_output_embeddings()
W = head.weight[letter_ids]  # (26, hidden) rows of the output embedding; no full-vocabulary logits
budget_chars = a.budget_chars


def encode(texts):
    enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=a.max_len, add_special_tokens=False)
    # a truncated prompt would lose the question and the answer position; refuse silently-wrong scores
    long = (enc.attention_mask.sum(1) >= a.max_len).nonzero().flatten().tolist()
    if long:
        raise ValueError(f"{len(long)} prompts reach max_len={a.max_len}; lower the per-option budget")
    return enc.to(dev)


def letter_logits(texts):
    enc = encode(texts)
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=dev == "cuda"):
        h = backbone(input_ids=enc.input_ids, attention_mask=enc.attention_mask).last_hidden_state[:, -1, :]
    return (h.to(W.dtype) @ W.T).float()  # (B, 26)


def orders_for(k, perms, salt):
    rng = random.Random(salt)
    out = [list(range(k))]
    if perms > 1 and k > 1:
        out.append(list(reversed(range(k))))
    while len(out) < perms:
        o = list(range(k)); rng.shuffle(o)
        out.append(o)
    return out[:max(1, perms)]


@torch.no_grad()
def evaluate(rows, perms):
    model.eval()
    jobs = []  # (row index, order, text)
    for ri, r in enumerate(rows):
        for o in orders_for(len(r["clauses"]), perms, f"{a.seed}|{r['question']}"):
            jobs.append((ri, o, build(r["question"], r["clauses"], o, tok, budget_chars)))
    jobs.sort(key=lambda j: len(j[2]))
    acc_lp = [torch.zeros(len(r["clauses"])) for r in rows]
    cnt = [0] * len(rows)
    bs = 16
    for i in range(0, len(jobs), bs):
        chunk = jobs[i:i + bs]
        lg = letter_logits([j[2] for j in chunk]).cpu()
        for (ri, o, _), row in zip(chunk, lg):
            k = len(o)
            lp = torch.log_softmax(row[:k], dim=0)  # slot log-probs over the k shown options
            back = torch.empty(k)
            for slot, ci in enumerate(o):
                back[ci] = lp[slot]
            acc_lp[ri] += back; cnt[ri] += 1
    model.train()
    return [(x / c).tolist() for x, c in zip(acc_lp, cnt)]


def accuracy(rows, sc):
    by = {}
    for r, x in zip(rows, sc):
        o = max(range(len(x)), key=lambda i: x[i]) in r["gold"]
        k = len(r["clauses"])
        for key in ("all", f"attack:{r.get('attack') or 'none'}", f"jur:{r.get('jurisdiction')}", f"lang:{r.get('lang')}",
                    f"k:{k if k < 6 else '6+'}"):
            n, c = by.get(key, (0, 0)); by[key] = (n + 1, c + o)
    return {k: {"n": n, "acc": round(c / n, 4)} for k, (n, c) in sorted(by.items())}


def nll_at(rows, sc, T):
    tot = 0.0
    for r, x in zip(rows, sc):
        lp = torch.log_softmax(torch.tensor(x) / T, dim=0)
        tot -= torch.logsumexp(lp[r["gold"]], dim=0).item()
    return tot / max(1, len(rows))


print(json.dumps({"model": a.model, "trainable_params": sum(p.numel() for p in model.parameters() if p.requires_grad),
                  "train": len(train), "valid": len(valid), "test": len(test), "perms": a.perms}), flush=True)

if not a.eval_only and train:
    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=a.lr, weight_decay=0.01)
    def subset_of(r):
        """With probability --subset-prob, a group with k >= 4 becomes a random subset of 2..min(k-1, subset_max)
        options that keeps one gold option (any other gold option that is drawn stays gold). The teacher's
        per-clause log-probs follow the subset (the KD term renormalises over the shown options)."""
        k = len(r["clauses"])
        if k < 4 or random.random() >= a.subset_prob:
            return r
        size = random.randint(2, min(k - 1, a.subset_max))
        g = random.choice(r["gold"])
        rest = [i for i in range(k) if i != g]
        idx = sorted([g] + random.sample(rest, size - 1))
        t = teacher.get((r["question"], tuple(r["clauses"])))
        sub = {**r, "clauses": [r["clauses"][i] for i in idx], "gold": [j for j, i in enumerate(idx) if i in r["gold"]]}
        if t is not None:
            sub["_t"] = [t[i] for i in idx]
        return sub

    est = {id(r): len(build(r["question"], r["clauses"], list(range(len(r["clauses"]))), tok, budget_chars)) // 3 for r in train}

    def batches():
        order = list(range(len(train))); random.shuffle(order)
        cur, n = [], 0
        for i in order:
            t = est[id(train[i])]
            if cur and n + t > a.tokens_per_step:
                yield cur; cur, n = [], 0
            cur.append(train[i]); n += t
        if cur:
            yield cur

    steps_per_epoch = sum(1 for _ in batches())
    if valid and a.probe_every:
        pv = valid[: a.probe_n]
        print(json.dumps({"step": 0, "valid_probe": accuracy(pv, evaluate(pv, 1))["all"]}), flush=True)
    plan = {'total': max(1, int(steps_per_epoch * a.epochs))}
    warm = max(1, int(0.05 * plan['total']))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / plan['total']))))
    step, t0, run = 0, time.time(), 0.0
    model.train()
    done = False
    while not done:
        for groups in batches():
            texts, orders = [], []
            groups = [subset_of(r) for r in groups]  # option-subset augmentation (matches pruned inference)
            for r in groups:
                o = list(range(len(r["clauses"]))); random.shuffle(o)  # fresh option order every time
                orders.append(o); texts.append(build(r["question"], r["clauses"], o, tok, budget_chars))
            lg = letter_logits(texts)
            loss, wsum = 0.0, 0.0
            for b, (r, o) in enumerate(zip(groups, orders)):
                k = len(o)
                lp = torch.log_softmax(lg[b, :k], dim=0)
                gold_slots = [slot for slot, ci in enumerate(o) if ci in r["gold"]]
                nll = -torch.logsumexp(lp[gold_slots], dim=0)
                if a.label_smoothing:
                    nll = (1 - a.label_smoothing) * nll - a.label_smoothing * lp.mean()
                t = r["_t"] if "_t" in r else teacher.get((r["question"], tuple(r["clauses"])))
                if t is not None and a.beta > 0 and r.get("lang") not in skip_lang:
                    ts = torch.tensor([t[ci] for ci in o], dtype=torch.float32, device=lp.device)
                    tp = torch.softmax(ts / a.teacher_temp, dim=0)
                    kl = torch.sum(tp * (torch.log(tp + 1e-9) - lp))
                    nll = (1 - a.beta) * nll + a.beta * kl
                w = 1.0 if r.get("generatorRecovers", True) else a.inconsistent_weight
                loss = loss + w * nll; wsum += w
            loss = loss / max(wsum, 1e-6)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
            run += float(loss); step += 1
            if step % 25 == 0:
                print(json.dumps({"step": step, "of": plan["total"], "loss": round(run / 25, 4), "lr": sched.get_last_lr()[0],
                                  "min": round((time.time() - t0) / 60, 1)}), flush=True)
                run = 0.0
            if valid and a.probe_every and step % a.probe_every == 0:
                pv = valid[: a.probe_n]
                print(json.dumps({"step": step, "valid_probe": accuracy(pv, evaluate(pv, 1))["all"]}), flush=True)
            if valid and step % steps_per_epoch == 0:
                print(json.dumps({"epoch": round(step / steps_per_epoch, 2), "valid_p1": accuracy(valid, evaluate(valid, 1))["all"]}), flush=True)
            if step == 20 and a.time_budget_min:
                per = (time.time() - t0) / 20
                fit_steps = int(a.time_budget_min * 60 / per)
                if fit_steps < plan['total']:
                    plan['total'] = max(40, fit_steps)
                print(json.dumps({'sec_per_step': round(per, 2), 'steps_per_epoch': steps_per_epoch, 'planned_steps': plan['total'],
                                  'planned_epochs': round(plan['total'] / steps_per_epoch, 2)}), flush=True)
            if a.save_every and step % a.save_every == 0:
                model.save_pretrained(f"{a.out}/adapter")
            if step >= plan['total']:
                done = True
                break
    model.save_pretrained(f"{a.out}/adapter")
    tok.save_pretrained(f"{a.out}/adapter")

T = 1.0
metrics = {"model": a.model, "epochs": a.epochs, "perms": a.perms, "train_items": len(train)}
if valid:
    sv = evaluate(valid, a.perms)
    metrics["valid"] = accuracy(valid, sv)
    T = min((0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0), key=lambda t: nll_at(valid, sv, t))
    metrics["temperature"] = T
    with open(f"{a.out}/valid_scores.jsonl", "w", encoding="utf-8") as f:
        for r, x in zip(valid, sv):
            f.write(json.dumps({"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "lp": x}, ensure_ascii=False) + "\n")
st = evaluate(test, a.perms)
metrics["test"] = accuracy(test, st)
with open(f"{a.out}/test_scores.jsonl", "w", encoding="utf-8") as f:
    for r, x in zip(test, st):
        f.write(json.dumps({"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "lp": x}, ensure_ascii=False) + "\n")
with open(f"{a.out}/judgments.jsonl", "w", encoding="utf-8") as f:
    for r, x in zip(test, st):
        p = torch.softmax(torch.tensor(x) / T, dim=0).tolist()
        for c, v, s in zip(r["clauses"], p, x):
            f.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": v, "score": s, "ms": 0, "tokens": 0}, ensure_ascii=False) + "\n")
sealed = {"test": metrics.pop("test")}
json.dump(sealed, open(f"{a.out}/test_metrics.sealed.json", "w"), indent=1)
json.dump(metrics, open(f"{a.out}/metrics.json", "w"), indent=1)
print(json.dumps({"final": True, "valid": metrics.get("valid", {}).get("all"), "temperature": T,
                  "valid_by_k": {k: v for k, v in metrics.get("valid", {}).items() if k.startswith("k:")}}), flush=True)
