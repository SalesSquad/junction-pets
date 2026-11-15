#!/usr/bin/env python3
"""Our own Decisions API on the device: Gemma 4 E2B (MLX) with the clause-judge LoRA.

A typed judge behind the same contract as the hosted ones (src/decide/decide.ts: localDecisions). It answers one
kind of question: a choice among lettered options about a `situation`. The prompt is the training prompt
(gpu/prompting.py: choice_content), and the answer is read from the logits of the option letters at the first
answer position, so nothing is generated. Three rotations of the option order are averaged (three forward
passes, about 0.2 s).

  POST /v1/decisions  {"state": {"situation": "..."}, "questions": [{"kind": "choice", "name": "tier", "options": {"A": "...", "B": "..."}}]}
                   -> {"model": "...", "adapter": "...", "answers": [{"name": "tier", "kind": "choice", "choice": "B", "probabilities": {"A": 0.1, "B": 0.9}}], "ms": 140}
  GET  /health        {"ok": true, "model": "...", "adapter": "...", "kinds": ["choice"]}

It listens on 127.0.0.1 only. The situation never leaves this machine.

  .venv-mlx/bin/python gemma/serve_mlx_decide.py --adapter adapters/gemma4-e2b-choice [--port 8790]
"""
import argparse, json, math, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import mlx.core as mx
from mlx_lm import load

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mlx_judge import LETTERS, letter_ids as letter_ids_of, option_logits, render, thinking_of

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="mlx-community/gemma-4-e2b-it-4bit"); ap.add_argument("--adapter", default=None)
ap.add_argument("--port", type=int, default=8790); ap.add_argument("--max-tokens", type=int, default=1536)
ap.add_argument("--memory-gb", type=float, default=5.0)
ap.add_argument("--orders", type=int, default=3, help="rotations of the option order to average (three: validation accuracy 84.0 to 86.1, verified test 84.3 to 88.8)")
a = ap.parse_args()

mx.set_cache_limit(512 << 20)
mx.set_memory_limit(int(a.memory_gb * (1 << 30)))
adapter = a.adapter if a.adapter and os.path.exists(os.path.join(a.adapter, "adapters.safetensors")) else None
model, tok = load(a.model, adapter_path=adapter)
model.eval()
letter_ids = letter_ids_of(tok)
thinking = thinking_of(adapter)  # the prompt the adapter was trained on
lock = threading.Lock()  # one forward pass at a time
MAX_BODY, MAX_SITUATION, MAX_OPTION = 256 * 1024, 8000, 6000

def choose(situation, clauses):
    """Probability per clause, averaged over evenly spaced rotations of the option order: a small model prefers
    some letter positions, and rotating the options cancels that."""
    k = len(clauses)
    ps = [0.0] * k
    shifts = sorted({(j * k) // a.orders for j in range(max(1, a.orders))})
    with lock:
        for sh in shifts:
            order = [(i + sh) % k for i in range(k)]
            ls = option_logits(model, render(tok, situation, clauses, order, thinking, a.max_tokens), letter_ids, k)
            m = max(ls); z = sum(math.exp(x - m) for x in ls)
            for pos, ci in enumerate(order):
                ps[ci] += math.exp(ls[pos] - m) / z / len(shifts)
        mx.clear_cache()
    return ps

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # no request logging: bodies hold the person's situation
        pass

    def send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, {"ok": True, "model": a.model, "adapter": adapter, "kinds": ["choice"]})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/decisions":
            return self.send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("content-length") or 0)
            if n <= 0 or n > MAX_BODY:
                return self.send(413, {"error": "body too large or empty"})
            d = json.loads(self.rfile.read(n))
            situation = (d.get("state") or {}).get("situation")
            qs = d.get("questions")
            if not isinstance(situation, str) or not situation.strip() or len(situation) > MAX_SITUATION or not isinstance(qs, list) or not 1 <= len(qs) <= 4:
                return self.send(400, {"error": "state.situation (text) and 1-4 questions are required"})
            t0, answers = time.time(), []
            for q in qs:
                opts = q.get("options") if isinstance(q, dict) else None
                if not isinstance(q, dict) or q.get("kind") != "choice" or not isinstance(opts, dict) or not 2 <= len(opts) <= len(LETTERS) or not all(isinstance(v, str) and 0 < len(v) <= MAX_OPTION for v in opts.values()):
                    return self.send(400, {"error": f"only choice questions with 2-{len(LETTERS)} text options are supported"})
                labels = list(opts)
                ps = choose(situation, [opts[l] for l in labels])
                answers.append({"name": str(q.get("name", "choice"))[:64], "kind": "choice", "choice": labels[ps.index(max(ps))], "probabilities": dict(zip(labels, ps))})
            self.send(200, {"model": a.model, "adapter": adapter, "answers": answers, "ms": round((time.time() - t0) * 1000)})
        except (ValueError, KeyError, TypeError) as e:
            self.send(400, {"error": f"bad request: {type(e).__name__}"})
        except Exception as e:  # keep serving; say what failed without echoing the input
            print(f"judge failed: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr, flush=True)
            self.send(500, {"error": f"judge failed: {type(e).__name__}"})

choose("warm up: a flight was two hours late", ["(a) one amount", "(b) another amount", "(c) a third amount"])  # the first passes compile the graph; do them before a caller waits
print(json.dumps({"listening": f"http://127.0.0.1:{a.port}", "model": a.model, "adapter": adapter, "orders": a.orders}), flush=True)
# Single-threaded on purpose: MLX evaluates on the thread that loaded the model (its GPU stream is thread-local),
# and one forward pass at a time is all a shared laptop GPU should do.
HTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
