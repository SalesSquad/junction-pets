"""Greedy MLX inference for the step 3 arms. SYNTHETIC notes only; every output is a proposal a person confirms.

Writes one JSON line per note (resumable: ids already in the output file are skipped):
  id, writer, date_forms, format, raw (generated text), confidence (mean log-probability of the generated tokens,
  stop token excluded), min_logprob, new_tokens, prompt_tokens, seconds, hit_max_tokens.
Parsing, code resolution and scoring happen in score.py, so a stored output can be re-scored without MLX.

Step 3 runs it on val only (--split val). Step 8 runs the same command with --input <parquet|jsonl> for test or the
stress set; rows need id, note_date and note_text.

  scribe/artifacts/mlx-venv/bin/python scribe/mlx2/infer.py --base 270m --format expression \
      --adapter scribe/v4/artifacts/B-270m-expr-aug/adapter --split val --output data/scribe/v4/mlx/outputs/B/val.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import m2common as C


def messages_for(fmt, row):
    if fmt == "absolute":
        from prompts import messages

        return messages(row)
    import data_tools as DT

    return DT.expression_messages(row)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", choices=sorted(C.BASES), help="base model key (or --model)")
    ap.add_argument("--model", help="MLX model path or repo (overrides --base)")
    ap.add_argument("--adapter", help="MLX adapter directory (adapter_config.json + adapters.safetensors)")
    ap.add_argument("--format", required=True, choices=["absolute", "expression"])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--split", choices=C.ALLOWED_SPLITS)
    src.add_argument("--input", help="parquet or JSONL rows (step 8)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=384)
    ap.add_argument("--cache-limit-mb", type=int, default=512)
    args = ap.parse_args(argv)

    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.generate import generate_step
    from mlx_lm.models.cache import make_prompt_cache

    mx.set_cache_limit(args.cache_limit_mb * 1024**2)
    model_path = args.model or C.BASES[args.base]["mlx"]
    t_load = time.monotonic()
    model, tok = load(model_path, adapter_path=args.adapter)
    model.eval()
    load_s = time.monotonic() - t_load
    hf = tok._tokenizer
    stop = set(tok.eos_token_ids) | {hf.eos_token_id}
    eot = hf.convert_tokens_to_ids("<end_of_turn>")
    if isinstance(eot, int) and eot != hf.unk_token_id:
        stop.add(eot)

    rows = C.load_split(args.split) if args.split else C.load_rows(args.input)
    if args.limit:
        rows = rows[: args.limit]
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()}
    t0 = time.monotonic()
    n_new = tokens_total = 0
    with out.open("a", encoding="utf-8") as f:
        for i, row in enumerate(rows):
            rid = str(row.get("id") or i)
            if rid in done:
                continue
            ts = time.monotonic()
            prompt = hf.apply_chat_template(messages_for(args.format, row), tokenize=False, add_generation_prompt=True)
            ids_in = hf.encode(prompt, add_special_tokens=False)
            cache = make_prompt_cache(model)
            ids, lps = [], []
            hit_max = True
            for token, logprobs in generate_step(mx.array(ids_in), model, max_tokens=args.max_tokens, prompt_cache=cache):
                t = int(token.item() if hasattr(token, "item") else token)
                if t in stop:
                    hit_max = False
                    break
                ids.append(t)
                lps.append(float(logprobs[t].item()))
            text = hf.decode(ids, skip_special_tokens=True)
            rec = {
                "id": rid,
                "writer": row.get("writer") or row.get("teacher_model"),
                "date_forms": list(row.get("date_forms") or []),
                "format": args.format,
                "raw": text,
                "confidence": sum(lps) / len(lps) if lps else None,
                "min_logprob": min(lps) if lps else None,
                "new_tokens": len(ids),
                "prompt_tokens": len(ids_in),
                "seconds": round(time.monotonic() - ts, 4),
                "hit_max_tokens": hit_max,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            n_new += 1
            tokens_total += len(ids)
            del cache
            if n_new % 25 == 0:
                print(f"PROGRESS {n_new} notes, {time.monotonic() - t0:.0f} s", flush=True)
    wall = time.monotonic() - t0
    summary = {
        "model": model_path,
        "adapter": args.adapter,
        "format": args.format,
        "source": args.split or args.input,
        "notes": n_new,
        "load_seconds": round(load_s, 2),
        "wall_seconds": round(wall, 2),
        "seconds_per_note": round(wall / n_new, 3) if n_new else None,
        "generated_tokens": tokens_total,
        "tokens_per_second": round(tokens_total / wall, 1) if wall and n_new else None,
        "peak_memory_gb": round(mx.get_peak_memory() / 1e9, 3),
    }
    print("SUMMARY " + json.dumps(summary), flush=True)
    C.log("infer-" + (pathlib.Path(args.adapter).parent.name if args.adapter else f"base-{args.base}") + f"-{args.split or 'input'}",
          " ".join(["scribe/mlx2/infer.py"] + (argv if argv is not None else sys.argv[1:])),
          inputs={"model": C.rel(model_path), "adapter": C.rel(args.adapter) if args.adapter else None, "source": args.split or C.rel(args.input)},
          outputs={"file": C.rel(out)}, metrics={k: v for k, v in summary.items() if k not in ("model", "adapter")})
    return summary


if __name__ == "__main__":
    main()
    sys.exit(0)
