#!/usr/bin/env python3
"""Nemotron 3.5 Super VL (Verda-hosted) as a listwise teacher/judge for the clause task.

The key comes from the environment variable VERDA_INFERENCE_KEY or, when that is unset, from this Mac's Keychain
at run time (same item as opencode-nemotron); it is only placed in the request header, never printed or written.
Prompts reuse gemma/mlx_list.py user_text().

Run from the repository root:
  probe:  python3 bench/situations/listwise/teachers/nemo.py probe --split valid --n 5
  label:  python3 bench/situations/listwise/teachers/nemo.py label --split train|valid|test --out runs/teachers/SPLIT.nemo.jsonl
          [--workers 8] [--perms 2]
Output rows: {"question", "clauses", "lp": [per-clause averaged log-prob over orders], "orders": P}
"""
import argparse, ctypes, getpass, json, math, os, random, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from ctypes import c_void_p, c_uint32, c_int32, POINTER, byref

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "gemma"))
from mlx_list import LETTERS, SEP, user_text  # noqa: E402  (the listwise prompt; must stay byte-identical)

BASE = "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1"
MODEL = "nemotron-3.5-super-vl"


def load_key():
    lib = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    find = lib.SecKeychainFindGenericPassword
    find.argtypes = [c_void_p, c_uint32, ctypes.c_char_p, c_uint32, ctypes.c_char_p, POINTER(c_uint32), POINTER(c_void_p), POINTER(c_void_p)]
    find.restype = c_int32
    lib.SecKeychainItemFreeContent.argtypes = [c_void_p, c_void_p]
    service, account = b"verda-nemotron-inference", getpass.getuser().encode()
    size, data = c_uint32(), c_void_p()
    if find(None, len(service), service, len(account), account, byref(size), byref(data), None) != 0:
        raise RuntimeError("Keychain access failed")
    try:
        return ctypes.string_at(data, size.value).decode()
    finally:
        lib.SecKeychainItemFreeContent(None, data)


KEY = None


def chat(prompt, k, timeout=120):
    body = {"model": MODEL, "messages": [{"role": "system", "content": "/no_think"},
                                          {"role": "user", "content": prompt}],
            "max_tokens": 1, "temperature": 0, "logprobs": True, "top_logprobs": 20,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.load(r)
            break
        except Exception:  # transient serverless errors: back off
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    ch = j["choices"][0]
    top = {}
    try:
        for t in ch["logprobs"]["content"][0]["top_logprobs"]:
            tok = t["token"].strip()
            if tok in LETTERS[:k] and tok not in top:
                top[tok] = t["logprob"]
    except (KeyError, IndexError, TypeError):
        pass
    text = (ch.get("message") or {}).get("content") or ""
    return top, text


def score_row(r, perms):
    k = len(r["clauses"])
    rng = random.Random("nemo|" + r["question"])
    orders = [list(range(k))]
    if perms > 1 and k > 1:
        orders.append(list(reversed(range(k))))
    while len(orders) < perms:
        o = list(range(k)); rng.shuffle(o); orders.append(o)
    acc = [0.0] * k
    texts = []
    for o in orders:
        top, text = chat(user_text(r["question"], r["clauses"], o), k)
        texts.append(text)
        floor = min(top.values()) - 2.0 if top else -20.0  # letters outside top-20 get a low floor
        lp = [top.get(LETTERS[s], floor) for s in range(k)]
        m = max(lp); z = m + math.log(sum(math.exp(v - m) for v in lp))
        for s, ci in enumerate(o):
            acc[ci] += (lp[s] - z) / len(orders)
    return {"gid": r.get("gid"), "question": r["question"], "clauses": r["clauses"], "lp": acc, "orders": len(orders), "texts": texts}


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "label"])
    ap.add_argument("--split", default="valid"); ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out", default=""); ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--perms", type=int, default=2); ap.add_argument("--data", default="bench/datasets/out/training")
    a = ap.parse_args()
    KEY = os.environ.get("VERDA_INFERENCE_KEY") or load_key()
    rows = [json.loads(l) for l in open(f"{a.data}/{a.split}.jsonl") if l.strip()]
    own = lambda c: c.split(SEP)[-1]
    if a.cmd == "probe":
        t0 = time.time()
        for r in rows[: a.n]:
            res = score_row(r, 1)
            gold = {i for i, c in enumerate(r["clauses"]) if own(c) == own(r["clauses"][r["target"]])}
            pick = max(range(len(res["lp"])), key=lambda i: res["lp"][i])
            print(json.dumps({"k": len(r["clauses"]), "gold": sorted(gold), "pick": pick, "ok": pick in gold,
                              "text": res["texts"][0][:20], "lp": [round(x, 2) for x in res["lp"]]}), flush=True)
        print(json.dumps({"sec_per_call": round((time.time() - t0) / a.n, 2)}))
        return
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["question"] for l in open(a.out) if l.strip()}
    todo = [r for r in rows if r["question"] not in done]
    print(json.dumps({"split": a.split, "todo": len(todo), "done": len(done)}), flush=True)
    t0, n, ok = time.time(), 0, 0
    with open(a.out, "a", encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as ex:
        for res, r in zip(ex.map(lambda r: score_row(r, a.perms), todo), todo):
            gold = {i for i, c in enumerate(r["clauses"]) if own(c) == own(r["clauses"][r["target"]])}
            if a.split != "test":
                ok += max(range(len(res["lp"])), key=lambda i: res["lp"][i]) in gold
            res.pop("texts", None)
            f.write(json.dumps(res, ensure_ascii=False) + "\n"); f.flush(); n += 1
            if n % 100 == 0:
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
