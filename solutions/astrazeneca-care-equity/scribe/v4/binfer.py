"""Step 8: batched greedy MLX inference for the step 3 arms (continuous batching, mlx_lm BatchGenerator).

Why: under GPU contention from another project's job, single-sequence decoding (scribe/mlx2/infer.py) ran at
4.6 s/note (15 tok/s) instead of the 0.94 s/note step 3 measured, which would not finish before the deadline.
Same model, adapter, prompt, chat template, stop tokens, max_tokens 384 and greedy argmax as infer.py; only the
batching differs. Batched decoding can differ from single decoding in rare tokens (bf16 arithmetic over padded
batches), so `parity` re-runs the 310 validation notes and compares with step 3's single-sequence outputs before
any test or stress output is read.

Writes one JSON line per note, resumable by id (ids already in the output file are skipped), with the fields of
infer.py: id, writer, date_forms, format, raw, confidence (mean token log-probability, stop token excluded),
min_logprob, new_tokens, prompt_tokens, seconds (batch wall time / notes), hit_max_tokens, plus engine.
SYNTHETIC notes only; every output is a proposal a person confirms.

  HF_HUB_OFFLINE=1 scribe/artifacts/mlx-venv/bin/python scribe/v4/binfer.py --arm B-270m-expr-aug \
      --io data/scribe/stress/stress-v1.parquet:data/scribe/v4/eval/outputs/B-270m-expr-aug/stress.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mlx2"))
sys.path.insert(0, str(HERE))

import m2common as C  # noqa: E402

C.RUNLOG = C.ROOT / "runs/laneA-step8.jsonl"

from infer import messages_for  # noqa: E402

ARMS = {
    "A-270m-abs": ("270m", "absolute"),
    "B-270m-expr-aug": ("270m", "expression"),
    "C-1b-expr-aug": ("1b", "expression"),
}


def run(model, hf, stop, fmt, rows, out, batch, max_tokens):
    import mlx.core as mx
    from mlx_lm.generate import BatchGenerator

    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()}
    todo = [r for r in rows if str(r["id"]) not in done]
    if not todo:
        return {"notes": 0, "skipped": len(done)}
    prompts = []
    for row in todo:
        text = hf.apply_chat_template(messages_for(fmt, row), tokenize=False, add_generation_prompt=True)
        prompts.append(hf.encode(text, add_special_tokens=False))
    gen = BatchGenerator(model, stop_tokens=[[t] for t in sorted(stop)], completion_batch_size=batch,
                         prefill_batch_size=min(8, batch))
    t0 = time.monotonic()
    uids = gen.insert(prompts, [max_tokens] * len(prompts))
    by_uid = {u: i for i, u in enumerate(uids)}
    toks = {u: [] for u in uids}
    lps = {u: [] for u in uids}
    finished = 0
    tokens_total = 0
    with out.open("a", encoding="utf-8") as f:
        while responses := gen.next_generated():
            for r in responses:
                if r.finish_reason != "stop":
                    t = int(r.token)
                    toks[r.uid].append(t)
                    lps[r.uid].append(float(r.logprobs[t].item()))
                if r.finish_reason is None:
                    continue
                i = by_uid[r.uid]
                row = todo[i]
                ids, lp = toks.pop(r.uid), lps.pop(r.uid)
                rec = {
                    "id": str(row["id"]),
                    "writer": row.get("writer") or row.get("teacher_model"),
                    "date_forms": list(row.get("date_forms") or []),
                    "format": fmt,
                    "raw": hf.decode(ids, skip_special_tokens=True),
                    "confidence": sum(lp) / len(lp) if lp else None,
                    "min_logprob": min(lp) if lp else None,
                    "new_tokens": len(ids),
                    "prompt_tokens": len(prompts[i]),
                    "seconds": None,
                    "hit_max_tokens": r.finish_reason == "length",
                    "engine": f"mlx-batch{batch}",
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                finished += 1
                tokens_total += len(ids)
                if finished % 50 == 0:
                    print(f"PROGRESS {out.name} {finished}/{len(todo)} {time.monotonic() - t0:.0f} s", flush=True)
    gen.close()
    wall = time.monotonic() - t0
    return {"notes": finished, "skipped": len(done), "wall_seconds": round(wall, 2),
            "seconds_per_note": round(wall / finished, 3) if finished else None,
            "generated_tokens": tokens_total, "tokens_per_second": round(tokens_total / wall, 1) if wall else None,
            "peak_memory_gb": round(mx.get_peak_memory() / 1e9, 3)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--io", action="append", required=True, help="input.parquet|jsonl:output.jsonl (repeatable)")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-tokens", type=int, default=384)
    ap.add_argument("--cache-limit-mb", type=int, default=512)
    args = ap.parse_args(argv)

    import mlx.core as mx
    from mlx_lm import load

    base, fmt = ARMS[args.arm]
    mx.set_cache_limit(args.cache_limit_mb * 1024**2)
    model_path = C.BASES[base]["mlx"]
    adapter = C.ART / args.arm / "adapter"
    model, tok = load(model_path, adapter_path=str(adapter))
    model.eval()
    hf = tok._tokenizer
    stop = set(tok.eos_token_ids) | {hf.eos_token_id}
    eot = hf.convert_tokens_to_ids("<end_of_turn>")
    if isinstance(eot, int) and eot != hf.unk_token_id:
        stop.add(eot)
    for pair in args.io:
        src, dst = pair.rsplit(":", 1)
        rows = C.load_rows(C.ROOT / src if not pathlib.Path(src).is_absolute() else src)
        res = run(model, hf, stop, fmt, rows, C.ROOT / dst, args.batch, args.max_tokens)
        print("SUMMARY " + json.dumps(dict(res, arm=args.arm, input=src)), flush=True)
        C.log(f"binfer-{args.arm}-{pathlib.Path(dst).stem}", "scribe/v4/binfer.py " + " ".join(argv or sys.argv[1:]),
              inputs={"model": C.rel(model_path), "adapter": C.rel(adapter), "source": src, "rows": len(rows),
                      "stop_tokens": sorted(stop)},
              outputs={"file": dst}, metrics=res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
