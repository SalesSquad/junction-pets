#!/usr/bin/env python3
"""TimeLaw-Situations, step 4 (GPU): distil an on-device clause judge.

A small open model (default Qwen3-1.7B, about 1 GB at 4-bit, small enough for a phone or a laptop) is
LoRA-tuned to answer the library's question per clause: "does `clause` set the amount that applies to the
person in `situation`?" Labels come from construction (the target clause, or a clause with identical wording,
is "yes"; every sibling is "no"), not from another model.

Split by provision (title/section or UK/EU path), so test situations come from provisions the student never saw.
Writes the student's P(yes) for every (situation, clause) of the TEST split, in the tournament's cache format,
so bench/situations/tournament.mjs can score student, code+student and code+student→luna.

Usage (on the VM): python3 train_student.py situations.jsonl --model Qwen/Qwen3-1.7B --out student
"""
import argparse, hashlib, json, math, random
import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, DataCollatorForLanguageModeling

ap = argparse.ArgumentParser()
ap.add_argument("situations"); ap.add_argument("--model", default="Qwen/Qwen3-1.7B"); ap.add_argument("--out", default="student")
ap.add_argument("--epochs", type=float, default=2.0); ap.add_argument("--test-share", type=float, default=0.25)
ap.add_argument("--test", default="", help="a separate test file (the exported provision split); else hash split")
a = ap.parse_args()
random.seed(5)

own = lambda c: c.split(" … ")[-1]
rows = [json.loads(l) for l in open(a.situations) if l.strip()]
def provision(r):
    ref = r["ref"]
    return f"{ref.get('title')}-{ref.get('section')}" if ref.get("source") == "ecfr" else ref.get("path") or ref.get("celex")
test_of = lambda r: int(hashlib.sha1(provision(r).encode()).hexdigest(), 16) % 1000 < a.test_share * 1000
train, test = ([r for r in rows if not test_of(r)], [r for r in rows if test_of(r)]) if not a.test else (rows, [json.loads(l) for l in open(a.test) if l.strip()])

def fit(clause, n=900):
    """Shorten a clause to n characters by trimming its context chain, never the clause itself (the last " … " part)."""
    if len(clause) <= n:
        return clause
    own = clause.split(" … ")[-1]
    if len(own) >= n - 40:
        return own[:n]
    return clause[: n - len(own) - 3].rstrip() + " … " + own

QUESTION = "Does `clause` set the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)?"
def prompt(situation, clause):
    return f"situation: {situation}\nclause: {fit(clause)}\nquestion: {QUESTION}\nanswer (yes or no):"

tok = AutoTokenizer.from_pretrained(a.model)
tok.pad_token = tok.pad_token or tok.eos_token
pairs = []
for r in train:
    gold = own(r["clauses"][r["target"]])
    for c in r["clauses"]:
        pairs.append({"text": prompt(r["question"], c) + (" yes" if own(c) == gold else " no") + tok.eos_token})
# Balance: siblings outnumber the target, so repeat positives to roughly a third of the pairs.
pos = [p for p in pairs if p["text"].endswith(" yes" + tok.eos_token)]
neg = [p for p in pairs if not p["text"].endswith(" yes" + tok.eos_token)]
pairs = neg + pos * max(1, round(len(neg) / (2 * max(1, len(pos)))))
random.shuffle(pairs)
print(json.dumps({"train_items": len(train), "test_items": len(test), "train_pairs": len(pairs), "positives": len(pos)}))

model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, device_map="cuda")
model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], task_type="CAUSAL_LM"))
ds = Dataset.from_list(pairs).map(lambda b: tok(b["text"], truncation=True, max_length=768), batched=True, remove_columns=["text"])
Trainer(
    model=model,
    args=TrainingArguments(output_dir=a.out, num_train_epochs=a.epochs, per_device_train_batch_size=16, gradient_accumulation_steps=1, learning_rate=2e-4, lr_scheduler_type="cosine", warmup_steps=50, bf16=True, logging_steps=20, save_strategy="no", report_to=[]),
    train_dataset=ds,
    data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
).train()
model.save_pretrained(f"{a.out}/lora")

# P(yes) on the test split: compare the next-token logits of " yes" and " no" after the prompt.
model.eval()
yes_id, no_id = tok(" yes", add_special_tokens=False).input_ids[0], tok(" no", add_special_tokens=False).input_ids[0]
tok.padding_side = "left"
cache, correct = open(f"{a.out}/student.judgments.jsonl", "w"), 0
for r in test:
    texts = [prompt(r["question"], c) for c in r["clauses"]]
    probs = []
    for i in range(0, len(texts), 16):
        enc = tok(texts[i:i + 16], return_tensors="pt", padding=True, truncation=True, max_length=740).to("cuda")
        with torch.no_grad():
            logits = model(**enc).logits[:, -1, :].float()
        two = torch.stack([logits[:, yes_id], logits[:, no_id]], dim=1).softmax(dim=1)[:, 0]
        probs += two.tolist()
    for c, p in zip(r["clauses"], probs):
        cache.write(json.dumps({"k": f"student|{r['question']}|{c}", "p": p, "ms": 0, "tokens": 0}) + "\n")
    best = max(range(len(probs)), key=lambda i: probs[i])
    correct += own(r["clauses"][best]) == own(r["clauses"][r["target"]])
cache.close()
with open(f"{a.out}/test.jsonl", "w") as f:
    for r in test: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(json.dumps({"student_test_accuracy": f"{correct}/{len(test)}", "share": round(correct / max(1, len(test)), 3)}))
