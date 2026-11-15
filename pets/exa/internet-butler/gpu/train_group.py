#!/usr/bin/env python3
"""Group-wise training of our own decision model (CUDA).

The task at test time is "which of this provision's tiers applies?", so the model is trained on exactly that.

  --mode point   every sibling clause is scored on its own: score = logit("yes") - logit("no") after the
                 generation prompt (causal LM with LoRA) or the single logit of a cross-encoder. The loss is a
                 softmax over the siblings (listwise) plus a pointwise yes/no term that keeps each score usable
                 as P(yes) for the typed Decisions interface (src/decide/decide.ts).
  --mode choice  all siblings are lettered options in one prompt and the model answers with a letter; the loss
                 is cross-entropy over the letter logits. Options are shuffled every epoch. The clauses can
                 attend to each other, which matters for residual tiers ("not falling under (a) or (b)").

Only the needed rows of the output embedding are used, on the last position and in float32 (bf16 differences
are quantised to 0.125 and create ties). Gemma's final-logit soft cap is applied so P matches any runtime.

Gold is the target clause (identical full clause text counts as the same answer). Items are weighted by how
well their label is verified: generator blind pass and a second model family (recovers2).

Outputs under --out: adapter/ or model/, metrics.json (valid and each test file: accuracy by attack,
jurisdiction, language and label tier; calibration fitted on valid), judgments-<file>.jsonl
("student|situation|clause" -> p) for bench/situations/tournament.mjs --student=...; with --dump-scores also
valid_scores.jsonl and <file>_scores.jsonl (raw per-clause scores for bench/situations/listwise/select_policy.py).

Usage:
  python train_group.py --train train.jsonl --valid valid.jsonl --test test.jsonl --model /root/models/qwen3-1.7b \
      --kind causal --out runs/q17-group --epochs 3
"""
import argparse, json, math, os, random, time
import torch
import torch.nn.functional as F
from prompting import LETTERS, answer_ids, chat, choice_content, fit, user_content

ap = argparse.ArgumentParser()
ap.add_argument("--train", required=True); ap.add_argument("--valid", default=""); ap.add_argument("--test", required=True, help="one or more files, comma separated")
ap.add_argument("--model", required=True); ap.add_argument("--kind", choices=["causal", "encoder"], default="causal"); ap.add_argument("--out", required=True)
ap.add_argument("--mode", choices=["point", "choice"], default="point")
ap.add_argument("--epochs", type=float, default=2.0); ap.add_argument("--lr", type=float, default=0.0)
ap.add_argument("--max-len", type=int, default=1024); ap.add_argument("--pairs-per-step", type=int, default=24, help="point: clause rows per step; choice: groups per step = this / 4")
ap.add_argument("--lora-r", type=int, default=16); ap.add_argument("--qlora", action="store_true"); ap.add_argument("--grad-ckpt", action="store_true")
ap.add_argument("--rslora", action="store_true", help="rank-stabilised scaling (alpha/sqrt(r)); needs a lower learning rate: at 2e-4 the loss diverged")
ap.add_argument("--lam", type=float, default=0.5, help="point mode: weight of the pointwise yes/no term")
ap.add_argument("--teacher", default="", help="judgments cache (jsonl with k='<judge>|situation|clause', p) from OPEN models only")
ap.add_argument("--beta", type=float, default=0.0, help="weight of the distillation term")
ap.add_argument("--w-half", type=float, default=0.5, help="weight of items verified by one of the two blind passes")
ap.add_argument("--w-none", type=float, default=0.15, help="weight of items neither blind pass recovered")
ap.add_argument("--ablate", choices=["", "situation", "clause"], default="", help="shortcut control: withhold one side of the input")
ap.add_argument("--limit-train", type=int, default=0); ap.add_argument("--seed", type=int, default=5)
ap.add_argument("--eval-only", action="store_true"); ap.add_argument("--adapter", default="")
ap.add_argument("--dump-scores", action="store_true", help="also write the raw per-clause scores: valid_scores.jsonl and <test file>_scores.jsonl "
                "(rows {gid, question, clauses, score}) for bench/situations/listwise/select_policy.py")
a = ap.parse_args()
random.seed(a.seed); torch.manual_seed(a.seed)
os.makedirs(a.out, exist_ok=True)
dev = "cuda"
lr = a.lr or (1e-4 if a.kind == "causal" else 2e-5)

def load(path, limit=0):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if path else []
    for r in rows:
        r["gold"] = [i for i, c in enumerate(r["clauses"]) if c == r["clauses"][r["target"]]]
        g, v = bool(r.get("generatorRecovers", True)), r.get("recovers2")
        r["tier"] = "clean" if g and v is not False else "half" if g or v else "none"
        r["w"] = 1.0 if r["tier"] == "clean" else a.w_half if r["tier"] == "half" else a.w_none
    return rows[:limit] if limit else rows

train, valid = load(a.train, a.limit_train), load(a.valid)
tests = {os.path.basename(p).replace(".jsonl", ""): load(p) for p in a.test.split(",") if p}
teacher = {}
if a.teacher and a.beta > 0:
    acc = {}
    for line in open(a.teacher, encoding="utf-8"):
        j = json.loads(line)
        acc.setdefault(j["k"].split("|", 1)[1], []).append(min(max(j["p"], 1e-4), 1 - 1e-4))
    teacher = {k: sum(v) / len(v) for k, v in acc.items()}
    cover = sum(all(f"{r['question']}|{c}" in teacher for c in r["clauses"]) for r in train)
    print(json.dumps({"teacher_groups_covered": cover, "of": len(train)}), flush=True)
    assert cover > 0, "no train group has teacher labels: check the teacher file"

# ---------- model ----------
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(a.adapter if (a.adapter and a.kind == "encoder") else a.model)
truncated = [0, 0]
if a.kind == "causal":
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    tok.pad_token = tok.pad_token or tok.eos_token
    tok.padding_side = "left"
    tok.truncation_side = "left"  # if a prompt is too long, the question and the answer slot at the end survive
    kw = dict(dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa")
    if a.qlora:
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, **kw)
    if a.qlora:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=a.grad_ckpt)
    elif a.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()  # checkpointed blocks need an input that requires grad when only LoRA trains
    if a.adapter:
        model = PeftModel.from_pretrained(model, a.adapter, is_trainable=not a.eval_only)
    else:
        # LoRA on the language model only (multimodal Gemma 4 also has vision and audio towers with the same layer names).
        SUFFIX = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")
        names = [n for n, m in model.named_modules() if isinstance(m, torch.nn.Linear) and n.endswith(SUFFIX)]
        if any("language_model" in n for n in names):
            names = [n for n in names if "language_model" in n]
        model = get_peft_model(model, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.05, use_rslora=a.rslora, target_modules=names, task_type="CAUSAL_LM"))
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    backbone = getattr(base, base.base_model_prefix)  # the transformer without the LM head (LoRA is injected in place)
    head = base.get_output_embeddings()
    softcap = getattr(getattr(base.config, "text_config", base.config), "final_logit_softcapping", None)
    yes_id, no_id = answer_ids(tok)
    letter_ids = answer_ids(tok, tuple(LETTERS))

    def last_logits(texts, ids):
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=a.max_len, add_special_tokens=False).to(dev)
        truncated[0] += int((enc.attention_mask.sum(1) >= a.max_len).sum()); truncated[1] += len(texts)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            h = backbone(input_ids=enc.input_ids, attention_mask=enc.attention_mask).last_hidden_state[:, -1, :]
        with torch.autocast("cuda", enabled=False):
            z = h.float() @ head.weight[ids].float().T
            return torch.tanh(z / softcap) * softcap if softcap else z

    def point_scores(pairs):
        z = last_logits([chat(tok, user_content(s, c, a.ablate)) for s, c in pairs], [yes_id, no_id])
        return z[:, 0] - z[:, 1]

    def choice_logits(groups, orders):
        return last_logits([chat(tok, choice_content(r["question"], r["clauses"], o, a.ablate)) for r, o in zip(groups, orders)], letter_ids)
else:
    from transformers import AutoModelForSequenceClassification
    assert a.mode == "point", "encoders score one clause at a time"
    model = AutoModelForSequenceClassification.from_pretrained(a.adapter or a.model, num_labels=1).to(dev)

    def point_scores(pairs):
        enc = tok(["(withheld)" if a.ablate == "situation" else s for s, _ in pairs], ["(withheld)" if a.ablate == "clause" else fit(c) for _, c in pairs], return_tensors="pt", padding=True, truncation="only_first", max_length=a.max_len).to(dev)
        truncated[0] += int((enc.attention_mask.sum(1) >= a.max_len).sum()); truncated[1] += len(pairs)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            return model(**enc).logits.squeeze(-1).float()

trainable = [p for p in model.parameters() if p.requires_grad]
tiers = {t: sum(1 for r in train if r["tier"] == t) for t in ("clean", "half", "none")}
print(json.dumps({"model": a.model, "kind": a.kind, "mode": a.mode, "ablate": a.ablate, "trainable_params": sum(p.numel() for p in trainable), "train": len(train), "train_tiers": tiers, "valid": len(valid), "tests": {k: len(v) for k, v in tests.items()}, "lr": lr}), flush=True)

# ---------- scoring a set of items: one score per clause ----------
@torch.no_grad()
def evaluate(rows):
    model.eval()
    if a.mode == "choice":
        out = [None] * len(rows)
        order = sorted(range(len(rows)), key=lambda i: sum(len(c) for c in rows[i]["clauses"]))
        bs = max(2, a.pairs_per_step // 2)
        for i in range(0, len(order), bs):
            idx = order[i:i + bs]
            z = choice_logits([rows[k] for k in idx], [list(range(len(rows[k]["clauses"]))) for k in idx])
            for k, zz in zip(idx, z.tolist()):
                out[k] = zz[: len(rows[k]["clauses"])]
    else:
        flat = [(r["question"], c) for r in rows for c in r["clauses"]]
        order = sorted(range(len(flat)), key=lambda i: len(flat[i][0]) + len(flat[i][1]))
        s = [0.0] * len(flat)
        bs = max(8, a.pairs_per_step * 2)
        for i in range(0, len(order), bs):
            idx = order[i:i + bs]
            for j, v in zip(idx, point_scores([flat[k] for k in idx]).tolist()):
                s[j] = v
        out, pos = [], 0
        for r in rows:
            k = len(r["clauses"]); out.append(s[pos:pos + k]); pos += k
    model.train()
    return out

def accuracy(rows, sc):
    """Ties share the credit (a tie between two clauses, one of them gold, counts one half)."""
    by = {}
    for r, x in zip(rows, sc):
        m = max(x); tops = [i for i, v in enumerate(x) if v == m]
        o = sum(1 for i in tops if i in r["gold"]) / len(tops)
        for key in ("all", f"tier:{r['tier']}", f"attack:{r.get('attack') or 'none'}", f"jur:{r.get('jurisdiction')}", f"lang:{r.get('lang')}"):
            n, c = by.get(key, (0, 0.0)); by[key] = (n + 1, c + o)
    return {k: {"n": n, "acc": round(c / n, 4)} for k, (n, c) in sorted(by.items())}

def dump_scores(name, rows, sc):
    """--dump-scores: the raw per-clause scores of one split (no calibration applied), one row per group."""
    with open(f"{a.out}/{name}_scores.jsonl", "w", encoding="utf-8") as f:
        for r, x in zip(rows, sc):
            f.write(json.dumps({"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "score": x}, ensure_ascii=False) + "\n")

def fit_calibration(rows, sc):
    """Listwise temperature (NLL over siblings) and, for point mode, a pointwise sigmoid((s - b) / T) fitted with BCE."""
    def nll(T):
        return sum(-torch.logsumexp(torch.log_softmax(torch.tensor(x) / T, 0)[r["gold"]], 0).item() for r, x in zip(rows, sc)) / max(1, len(rows))
    Tl = min((0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0), key=nll)
    cal = {"T_list": Tl}
    if a.mode == "point":
        s = torch.tensor([v for x in sc for v in x]); y = torch.tensor([1.0 if i in r["gold"] else 0.0 for r, x in zip(rows, sc) for i in range(len(x))])
        T = torch.nn.Parameter(torch.tensor(1.0)); b = torch.nn.Parameter(torch.tensor(0.0))
        opt = torch.optim.LBFGS([T, b], lr=0.5, max_iter=100)
        def closure():
            opt.zero_grad(); loss = F.binary_cross_entropy_with_logits((s - b) / T.clamp(min=0.05), y); loss.backward(); return loss
        opt.step(closure)
        cal.update({"T": float(T.clamp(min=0.05)), "b": float(b)})
    return cal

# ---------- training ----------
if not a.eval_only:
    opt = torch.optim.AdamW(trainable, lr=lr, weight_decay=0.01)
    budget = a.pairs_per_step if a.mode == "point" else max(1, a.pairs_per_step // 4)
    def batches():
        order = list(range(len(train))); random.shuffle(order)
        cur, n = [], 0
        for i in order:
            k = len(train[i]["clauses"]) if a.mode == "point" else 1
            if cur and n + k > budget:
                yield cur; cur, n = [], 0
            cur.append(train[i]); n += k
        if cur:
            yield cur
    steps_per_epoch = sum(1 for _ in batches())
    total = int(steps_per_epoch * a.epochs)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / max(1, int(0.05 * total))) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / max(1, total)))))
    step, t0, run = 0, time.time(), {"list": 0.0, "point": 0.0, "kd": 0.0}
    model.train()
    done = False
    while not done:
        for groups in batches():
            loss_list = loss_point = loss_kd = 0.0
            wsum = 0.0
            if a.mode == "choice":
                orders = [random.sample(range(len(r["clauses"])), len(r["clauses"])) for r in groups]
                z = choice_logits(groups, orders)
                for r, o, zz in zip(groups, orders, z):
                    k = len(o); x = zz[:k]
                    gold_pos = [p for p, i in enumerate(o) if i in r["gold"]]
                    loss_list = loss_list + r["w"] * -torch.logsumexp(torch.log_softmax(x, 0)[gold_pos], 0)
                    wsum += r["w"]
            else:
                s = point_scores([(r["question"], c) for r in groups for c in r["clauses"]])
                pos = 0
                for r in groups:
                    k = len(r["clauses"]); x = s[pos:pos + k]; pos += k
                    y = torch.zeros(k, device=dev); y[r["gold"]] = 1.0
                    loss_list = loss_list + r["w"] * -torch.logsumexp(torch.log_softmax(x, 0)[r["gold"]], 0)
                    loss_point = loss_point + r["w"] * F.binary_cross_entropy_with_logits(x, y)
                    if teacher:
                        tp = [teacher.get(f"{r['question']}|{c}") for c in r["clauses"]]
                        if all(v is not None for v in tp):
                            loss_kd = loss_kd + r["w"] * F.kl_div(torch.log_softmax(x, 0), torch.softmax(torch.logit(torch.tensor(tp, device=dev)), 0), reduction="sum")
                    wsum += r["w"]
            loss = (loss_list + a.lam * loss_point + a.beta * loss_kd) / max(wsum, 1e-6)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
            run["list"] += float(loss_list) / max(wsum, 1e-6); run["point"] += float(loss_point) / max(wsum, 1e-6); run["kd"] += float(loss_kd) / max(wsum, 1e-6) if teacher else 0.0
            step += 1
            if step % 25 == 0:
                print(json.dumps({"step": step, "of": total, "list": round(run["list"] / 25, 4), "point": round(run["point"] / 25, 4), "kd": round(run["kd"] / 25, 4), "lr": sched.get_last_lr()[0], "min": round((time.time() - t0) / 60, 1), "truncated": f"{truncated[0]}/{truncated[1]}"}), flush=True)
                run = {"list": 0.0, "point": 0.0, "kd": 0.0}
            if valid and step % steps_per_epoch == 0:
                print(json.dumps({"epoch": round(step / steps_per_epoch, 2), "valid": accuracy(valid, evaluate(valid))["all"]}), flush=True)
            if step >= total:
                done = True
                break
    model.save_pretrained(f"{a.out}/{'adapter' if a.kind == 'causal' else 'model'}")
    tok.save_pretrained(f"{a.out}/{'adapter' if a.kind == 'causal' else 'model'}")

# ---------- final evaluation ----------
metrics = {"model": a.model, "kind": a.kind, "mode": a.mode, "ablate": a.ablate, "epochs": a.epochs, "lam": a.lam, "beta": a.beta, "train_items": len(train), "train_tiers": tiers}
cal = {"T_list": 1.0, "T": 1.0, "b": 0.0}
if valid:
    sv = evaluate(valid)
    metrics["valid"] = accuracy(valid, sv)
    if a.dump_scores:
        dump_scores("valid", valid, sv)
    cal.update(fit_calibration(valid, sv))
    with open(f"{a.out}/judgments-valid.jsonl", "w", encoding="utf-8") as f:
        for r, x in zip(valid, sv):
            pl = torch.softmax(torch.tensor(x) / cal["T_list"], 0).tolist()
            for c, v, q in zip(r["clauses"], x, pl):
                f.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": q if a.mode == "choice" else 1 / (1 + math.exp(-(v - cal["b"]) / cal["T"])), "score": v, "p_list": q, "ms": 0, "tokens": 0}, ensure_ascii=False) + "\n")
metrics["calibration"] = cal
metrics["temperature"] = cal.get("T", cal["T_list"])
for name, rows in tests.items():
    st = evaluate(rows)
    metrics[name] = accuracy(rows, st)
    if a.dump_scores:
        dump_scores(name, rows, st)
    with open(f"{a.out}/judgments-{name}.jsonl", "w", encoding="utf-8") as f:
        for r, x in zip(rows, st):
            pl = torch.softmax(torch.tensor(x) / cal["T_list"], 0).tolist()
            for c, v, q in zip(r["clauses"], x, pl):
                p = q if a.mode == "choice" else 1 / (1 + math.exp(-(v - cal["b"]) / cal["T"]))
                f.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": p, "score": v, "p_list": q, "ms": 0, "tokens": 0}, ensure_ascii=False) + "\n")
metrics["truncated_prompts"] = f"{truncated[0]}/{truncated[1]}"
json.dump(metrics, open(f"{a.out}/metrics.json", "w"), indent=1)
print(json.dumps({"final": True, "valid": metrics.get("valid", {}).get("all"), **{k: metrics[k]["all"] for k in tests}, "calibration": cal, "truncated": metrics["truncated_prompts"], "tiers": {k: {t: metrics[k].get(f"tier:{t}") for t in ("clean", "half", "none")} for k in tests}}), flush=True)
