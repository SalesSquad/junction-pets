#!/usr/bin/env python3
"""Our own Decisions API: the trained judge behind the same typed contract the app uses for TypeSafe Jev and
OpenAI Luna (src/decide/decide.ts).

  POST /v1/decisions  {"state": {"situation": "...", "clause": "..."}, "questions": [{"kind": "yesno", "name": "applies", ...}]}
   ->                 {"model": "...", "answers": [{"name": "applies", "kind": "yesno", "p": 0.93}], "ms": 12}
  POST /v1/score      {"pairs": [["situation", "clause"], ...]} -> {"p": [...], "score": [...]}
  GET  /health

Concurrent requests are micro-batched (up to --batch pairs or --wait-ms) into one forward pass, because the
client asks one question per clause in parallel. P(yes) = sigmoid(score / T) with the temperature fitted on
the validation split at training time (metrics.json).

Usage (on the VM, reached from the Mac through an SSH tunnel; it binds to localhost only):
  python serve_decide.py --model /root/models/qwen3-1.7b --kind causal --adapter runs/q17-group/adapter --metrics runs/q17-group/metrics.json --port 8000
"""
import argparse, asyncio, json, math, time
import torch
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--kind", choices=["causal", "encoder"], default="causal")
ap.add_argument("--adapter", default=""); ap.add_argument("--metrics", default=""); ap.add_argument("--qlora", action="store_true")
ap.add_argument("--max-len", type=int, default=1024); ap.add_argument("--batch", type=int, default=64); ap.add_argument("--wait-ms", type=float, default=8.0)
ap.add_argument("--port", type=int, default=8000); ap.add_argument("--name", default="")
a = ap.parse_args()
_cal = (json.load(open(a.metrics)).get("calibration") or {}) if a.metrics else {}
T, B = _cal.get("T", 1.0), _cal.get("b", 0.0)  # P(yes) = sigmoid((score - b) / T), fitted on the validation split
NAME = a.name or (a.adapter or a.model).rstrip("/").split("/")[-2 if a.adapter else -1]
from prompting import answer_ids, chat, fit, user_content

from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(a.adapter or a.model)
if a.kind == "causal":
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from peft import PeftModel
    tok.pad_token = tok.pad_token or tok.eos_token
    tok.padding_side = "left"
    kw = dict(dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa")
    if a.qlora:
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, **kw)
    if a.adapter:
        model = PeftModel.from_pretrained(model, a.adapter)
        if not a.qlora:
            model = model.merge_and_unload()
    backbone = getattr(model, model.base_model_prefix)
    head = model.get_output_embeddings()
    softcap = getattr(getattr(model.config, "text_config", model.config), "final_logit_softcapping", None)
    yes_id, no_id = answer_ids(tok)
    tok.truncation_side = "left"

    @torch.no_grad()
    def scores(pairs):
        enc = tok([chat(tok, user_content(s, c)) for s, c in pairs], return_tensors="pt", padding=True, truncation=True, max_length=a.max_len, add_special_tokens=False).to("cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            h = backbone(input_ids=enc.input_ids, attention_mask=enc.attention_mask).last_hidden_state[:, -1, :]
        with torch.autocast("cuda", enabled=False):  # float32: bf16 differences are quantised to 0.125
            two = h.float() @ head.weight[[yes_id, no_id]].float().T
            if softcap:
                two = torch.tanh(two / softcap) * softcap
        return (two[:, 0] - two[:, 1]).tolist()
else:
    from transformers import AutoModelForSequenceClassification
    model = AutoModelForSequenceClassification.from_pretrained(a.adapter or a.model, num_labels=1).to("cuda")

    @torch.no_grad()
    def scores(pairs):
        enc = tok([s for s, _ in pairs], [fit(c) for _, c in pairs], return_tensors="pt", padding=True, truncation="only_first", max_length=a.max_len).to("cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            return model(**enc).logits.squeeze(-1).float().tolist()
model.eval()

app = FastAPI()
queue: asyncio.Queue = asyncio.Queue()

async def batcher():
    while True:
        first = await queue.get()
        batch = [first]
        deadline = time.monotonic() + a.wait_ms / 1000
        while len(batch) < a.batch and (left := deadline - time.monotonic()) > 0:
            try:
                batch.append(await asyncio.wait_for(queue.get(), left))
            except asyncio.TimeoutError:
                break
        try:
            out = await asyncio.to_thread(scores, [p for p, _ in batch])
            for (_, fut), s in zip(batch, out):
                fut.set_result(s)
        except Exception as e:  # one bad request must not kill the loop
            for _, fut in batch:
                if not fut.done():
                    fut.set_exception(e)

@app.on_event("startup")
async def start():
    asyncio.create_task(batcher())

async def score_one(situation: str, clause: str) -> float:
    fut = asyncio.get_running_loop().create_future()
    await queue.put(((situation, clause), fut))
    return await fut

class Decisions(BaseModel):
    state: dict
    questions: list[dict]

class Pairs(BaseModel):
    pairs: list[list[str]]

@app.get("/health")
def health():
    return {"ok": True, "model": NAME, "kind": a.kind, "temperature": T, "bias": B}

@app.post("/v1/decisions")
async def decisions(d: Decisions):
    t0 = time.monotonic()
    situation, clause = str(d.state.get("situation", "")), str(d.state.get("clause", ""))
    answers = []
    for q in d.questions:
        if q.get("kind") != "yesno" or not situation or not clause:
            return {"error": "this judge answers yes/no questions over a state with `situation` and `clause`"}
        s = await score_one(situation, clause)
        answers.append({"name": q.get("name", "applies"), "kind": "yesno", "p": 1 / (1 + math.exp(-(s - B) / T)), "score": s})
    return {"provider": "local", "model": NAME, "answers": answers, "ms": round((time.monotonic() - t0) * 1000, 1)}

@app.post("/v1/score")
async def score(p: Pairs):
    s = await asyncio.gather(*[score_one(x[0], x[1]) for x in p.pairs])
    return {"model": NAME, "score": s, "p": [1 / (1 + math.exp(-(v - B) / T)) for v in s]}

uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
