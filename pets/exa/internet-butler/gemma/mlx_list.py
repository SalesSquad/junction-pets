#!/usr/bin/env python3
"""Listwise clause judge on Apple silicon (MLX): data builder and permutation-averaged scorer.

Same prompt as gpu/train_list.py (situation, shared provision text once, options A, B, C ... with each
sibling's distinguishing text; answer = the option letter). MLX training uses mlx_lm.lora on the chat
rows this script writes (--mask-prompt, so the loss is the answer letter only); every training row gets
its own seeded random option order, so position carries no signal.

The prompt definitions (SEP, LETTERS, QUESTION, BUDGET, split_common, clip, user_text) are also imported by the
cloud teachers in bench/situations/listwise/teachers/. Trained adapters and teacher labels depend on the exact
text: do not change it (gpu/prompting.py is the pointwise/choice prompt of the other judges, not this one).

  build:  mlx_list.py build --data DIR --out DIR/mlx-list [--copies 1] [--seed 5]
  score:  mlx_list.py score --model M --adapter A --data DIR --split valid|test --perms 4 --out FILE
"""
import argparse, json, math, os, random, sys, time

SEP = " … "
LETTERS = [chr(ord("A") + i) for i in range(26)]
QUESTION = ("Which option sets the amount, rate, limit or time limit that applies to the person in the situation "
            "(the same kind of case, party and circumstances)? Answer with the option letter only.")
BUDGET = 3993


def split_common(clauses):
    parts = [c.split(SEP) for c in clauses]
    common = []
    for segs in zip(*parts):
        if all(s == segs[0] for s in segs) and len(common) < min(len(p) for p in parts) - 1:
            common.append(segs[0])
        else:
            break
    return SEP.join(common), [SEP.join(p[len(common):]) for p in parts]


def clip(text, n):
    if len(text) <= n:
        return text
    own = text.split(SEP)[-1]
    if len(own) >= n - 40:
        return own[:n]
    return text[: n - len(own) - 3].rstrip() + SEP + own


def user_text(situation, clauses, order):
    common, rest = split_common(clauses)
    per = max(160, BUDGET // max(1, len(clauses)))
    lines = [f"situation: {situation}", "", "These options are the alternative tiers of one legal provision."]
    if common:
        lines.append(f"Shared provision text: {clip(common, 700)}")
    for slot, ci in enumerate(order):
        lines.append(f"{LETTERS[slot]}) {clip(rest[ci], per)}")
    lines += ["", f"question: {QUESTION}"]
    return "\n".join(lines)


def load(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    own = lambda c: c.split(SEP)[-1]
    for r in rows:
        g = own(r["clauses"][r["target"]])
        r["gold"] = [i for i, c in enumerate(r["clauses"]) if own(c) == g]
    return rows


def build(a):
    os.makedirs(a.out, exist_ok=True)
    rng = random.Random(a.seed)
    for split, copies in (("train", a.copies), ("valid", 1)):
        rows = load(f"{a.data}/{split}.jsonl")
        out = []
        for _ in range(copies):
            for r in rows:
                o = list(range(len(r["clauses"])))
                if split == "train":
                    rng.shuffle(o)
                gold_slot = min(slot for slot, ci in enumerate(o) if ci in r["gold"])
                out.append({"messages": [{"role": "user", "content": user_text(r["question"], r["clauses"], o)},
                                         {"role": "assistant", "content": LETTERS[gold_slot]}]})
        if split == "train":
            rng.shuffle(out)
        with open(f"{a.out}/{split}.jsonl", "w", encoding="utf-8") as f:
            for x in out:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        print(split, len(out))


def orders_for(k, perms, salt):
    rng = random.Random(salt)
    out = [list(range(k))]
    if perms > 1 and k > 1:
        out.append(list(reversed(range(k))))
    while len(out) < perms:
        o = list(range(k)); rng.shuffle(o); out.append(o)
    return out[:max(1, perms)]


def score(a):
    import mlx.core as mx
    from mlx_lm import load as mload
    model, tok = mload(a.model, adapter_path=a.adapter or None)
    ids = []
    for L in LETTERS:
        t = tok.encode(L, add_special_tokens=False)
        assert len(t) == 1, (L, t)
        ids.append(t[0])
    rows = load(f"{a.data}/{a.split}.jsonl")
    if a.limit:
        rows = rows[: a.limit]
    t0 = time.time()
    ok = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for n, r in enumerate(rows):
            k = len(r["clauses"])
            acc = [0.0] * k
            P = orders_for(k, a.perms, f"{a.seed}|{r['question']}")
            for o in P:
                prompt = tok.apply_chat_template([{"role": "user", "content": user_text(r["question"], r["clauses"], o)}],
                                                 tokenize=False, add_generation_prompt=True)
                x = mx.array(tok.encode(prompt, add_special_tokens=False))[None]
                logits = model(x)[0, -1].astype(mx.float32)
                sel = [logits[ids[s]].item() for s in range(k)]
                m = max(sel); z = m + math.log(sum(math.exp(v - m) for v in sel))
                for slot, ci in enumerate(o):
                    acc[ci] += (sel[slot] - z) / len(P)
            ok += max(range(k), key=lambda i: acc[i]) in r["gold"]
            f.write(json.dumps({"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "lp": acc}, ensure_ascii=False) + "\n")
            if n % 100 == 0:
                msg = {"n": n, "of": len(rows), "sec": round(time.time() - t0)}
                if a.split != "test":
                    msg["acc_so_far"] = round(ok / (n + 1), 4)
                print(json.dumps(msg), flush=True)
    res = {"split": a.split, "n": len(rows), "perms": a.perms, "sec": round(time.time() - t0)}
    if a.split != "test":  # test accuracy stays sealed until the fusion rule is fixed
        res["acc"] = round(ok / len(rows), 4)
    print(json.dumps(res), flush=True)


if __name__ == "__main__":  # importable: the teachers reuse the prompt definitions above
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--data", required=True); b.add_argument("--out", required=True)
    b.add_argument("--copies", type=int, default=1); b.add_argument("--seed", type=int, default=5)
    s = sub.add_parser("score"); s.add_argument("--model", required=True); s.add_argument("--adapter", default="")
    s.add_argument("--data", required=True); s.add_argument("--split", required=True); s.add_argument("--perms", type=int, default=4)
    s.add_argument("--out", required=True); s.add_argument("--limit", type=int, default=0); s.add_argument("--seed", type=int, default=5)
    a = ap.parse_args()
    build(a) if a.cmd == "build" else score(a)
