#!/usr/bin/env python3
"""Finnish clause judge with Claude Haiku 5.5 (owner: "do not use Nemotron in Finnish; use TypeSafe, DeepSeek
or Haiku"). Same listwise prompt as gemma/mlx_list.py: situation, shared provision text, options A, B, ...
The model returns the answer letter and a percentage for every option (structured output, json_schema).
Two orders (identity and reversed, as nemo.py); per-clause log-probabilities are averaged back in clause
order (percentages floored at 0.5 and renormalised). Only rows whose lang is Finnish are judged.

Key: the environment variable ANTHROPIC_API_KEY or, when that is unset, the macOS Keychain item
"Anthropic API Key" (account "anthropic"), read at run time and passed to the client only; never printed or
written. Test accuracy is never printed. Needs the `anthropic` package.
Usage (from the repository root): python3 bench/situations/listwise/teachers/fi_haiku.py --split valid|test
       --out runs/teachers/SPLIT.haiku_fi.jsonl [--workers 8] [--perms 2] [--n 0]
"""
import argparse, json, math, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "gemma"))
from mlx_list import LETTERS, SEP, user_text  # noqa: E402  (the listwise prompt; must stay byte-identical)

MODEL = "claude-haiku-5-5"
SYSTEM = ("You judge which tier of a legal provision applies to a person's situation. Read the situation and "
          "every option carefully; the options differ only in the case, party or circumstances they cover. "
          "Give your answer letter and your probability (0-100) for every option, in option order.")


def key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    return subprocess.run(["security", "find-generic-password", "-s", "Anthropic API Key", "-a", "anthropic", "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()


def ask(client, prompt, k):
    schema = {"type": "object",
              "properties": {"answer": {"type": "string", "enum": LETTERS[:k]},
                             "percents": {"type": "array", "items": {"type": "number"}}},
              "required": ["answer", "percents"], "additionalProperties": False}
    for attempt in range(5):
        try:
            r = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM,
                                       messages=[{"role": "user", "content": prompt}],
                                       output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}})
            if r.stop_reason == "refusal":
                return None
            text = next((b.text for b in r.content if b.type == "text"), "")
            return json.loads(text)
        except Exception as e:  # SDK retries 429/5xx itself; this covers parse errors and exhausted retries
            if attempt == 4:
                print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)
                return None
            time.sleep(2 ** attempt)


def score_row(client, r, perms):
    k = len(r["clauses"])
    orders = [list(range(k))] + ([list(reversed(range(k)))] if perms > 1 and k > 1 else [])
    acc, answers = [0.0] * k, []
    for o in orders:
        res = ask(client, user_text(r["question"], r["clauses"], o), k)
        if res and len(res.get("percents", [])) == k:
            p = [max(0.5, float(x)) for x in res["percents"]]
        elif res and res.get("answer") in LETTERS[:k]:
            p = [90.0 if LETTERS[s] == res["answer"] else 10.0 / max(1, k - 1) for s in range(k)]
        else:
            p = [1.0] * k
        z = sum(p)
        answers.append(res.get("answer") if res else None)
        for s, ci in enumerate(o):
            acc[ci] += math.log(p[s] / z) / len(orders)
    return {"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "lp": acc,
            "orders": len(orders), "answers": answers, "model": MODEL}


def main():
    import anthropic
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--perms", type=int, default=2)
    ap.add_argument("--n", type=int, default=0); ap.add_argument("--data", default="bench/datasets/out/training")
    a = ap.parse_args()
    client = anthropic.Anthropic(api_key=key(), max_retries=6)
    rows = [json.loads(l) for l in open(f"{a.data}/{a.split}.jsonl") if l.strip()]
    rows = [r for r in rows if r.get("lang") == "Finnish"]
    if a.n:
        rows = rows[: a.n]
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["question"] for l in open(a.out) if l.strip()}
    todo = [r for r in rows if r["question"] not in done]
    print(json.dumps({"split": a.split, "finnish": len(rows), "todo": len(todo)}), flush=True)
    own = lambda c: c.split(SEP)[-1]
    t0, n, ok = time.time(), 0, 0
    with open(a.out, "a", encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as ex:
        for res, r in zip(ex.map(lambda r: score_row(client, r, a.perms), todo), todo):
            gold = {i for i, c in enumerate(r["clauses"]) if own(c) == own(r["clauses"][r["target"]])}
            ok += max(range(len(res["lp"])), key=lambda i: res["lp"][i]) in gold
            f.write(json.dumps(res, ensure_ascii=False) + "\n"); f.flush(); n += 1
            if n % 50 == 0:
                msg = {"n": n, "of": len(todo), "min": round((time.time() - t0) / 60, 1)}
                if a.split != "test":
                    msg["acc"] = round(ok / n, 4)
                print(json.dumps(msg), flush=True)
    msg = {"done": n, "min": round((time.time() - t0) / 60, 1)}
    if a.split != "test":
        msg["acc"] = round(ok / max(1, n), 4)
    print(json.dumps(msg), flush=True)


if __name__ == "__main__":
    main()
