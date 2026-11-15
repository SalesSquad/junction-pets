"""Apple-silicon (MLX) fallback for the pathway scribe, used only when the CUDA box is unreachable.

SYNTHETIC data only; research artefact, not a medical device. Same prompts (prompts.messages),
greedy decoding, 384 new tokens and metrics (evaluate.evaluate) as the CUDA path.

  prepare            parquet -> chat JSONL for `python -m mlx_lm lora --mask-prompt`
  infer              greedy extraction with the base model or base+adapter -> predictions JSONL
  merge              base + adapter predictions -> eval JSON
  curve              mlx_lm training log -> loss-curve JSON
"""

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from prompts import messages, parse_output  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data/scribe"


def load_rows(dataset, extra, subset=0, seed=20261114, split="test", complement=False):
    """Rows of one split. subset: the seeded random subset used by the first evaluation;
    complement: the rows of the split that are NOT in that subset (to finish the split later)."""
    import random

    import pyarrow.parquet as pq

    rows = pq.read_table(pathlib.Path(dataset) / f"{split}.parquet").to_pylist()
    if subset:  # seeded random subset of the split when time does not allow all of it
        keep = set(random.Random(seed).sample(range(len(rows)), subset))
        rows = [r for i, r in enumerate(rows) if (i in keep) != complement]
    for r in rows:
        r["_set"] = split
    more = []
    if extra:
        more = [
            json.loads(x)
            for x in pathlib.Path(extra).read_text().splitlines()
            if x.strip()
        ]
        for r in more:
            r["_set"] = "extra"
    return rows, more


def prepare(args):
    import pyarrow.parquet as pq

    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for src, dst in [("train", "train"), ("val", "valid")]:
        rows = pq.read_table(pathlib.Path(args.dataset) / f"{src}.parquet").to_pylist()
        with (out / f"{dst}.jsonl").open("w") as f:
            for r in rows:
                f.write(
                    json.dumps(
                        {
                            "messages": messages(r)
                            + [{"role": "assistant", "content": r["target_json"]}]
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(dst, len(rows))


def infer(args):
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.models.cache import make_prompt_cache

    # Cap MLX's buffer cache: without it the per-token loop grew one process past 11 GB.
    mx.set_cache_limit(512 * 1024**2)
    model, tok = load(args.model, adapter_path=args.adapter)
    model.eval()
    hf = tok._tokenizer
    stop = set(tok.eos_token_ids) | {hf.eos_token_id}
    eot = hf.convert_tokens_to_ids("<end_of_turn>")
    if isinstance(eot, int) and eot != hf.unk_token_id:
        stop.add(eot)
    special = set(hf.all_special_ids)
    rows, more = load_rows(args.dataset, args.extra_test, args.test_subset, split=args.split, complement=args.complement)
    allrows = rows + more
    # Optional shard [skip, skip+limit) so several processes can share the work.
    allrows = allrows[args.skip :]
    if args.limit:
        allrows = allrows[: args.limit]
    done = 0
    out = pathlib.Path(args.output)
    if out.exists():
        done = len(out.read_text().splitlines())
    t0 = time.monotonic()
    with out.open("a") as f:
        for n, row in enumerate(allrows):
            if n < done:
                continue
            prompt = hf.apply_chat_template(
                messages(row), tokenize=False, add_generation_prompt=True
            )
            ids_in = hf.encode(prompt, add_special_tokens=False)
            cache = make_prompt_cache(model)
            logits = model(mx.array(ids_in)[None], cache=cache)[:, -1, :]
            ids, lps = [], []
            for _ in range(384):
                lp = logits.astype(mx.float32)
                lp = lp - mx.logsumexp(lp, axis=-1, keepdims=True)
                token = mx.argmax(lp, axis=-1)
                t = token.item()
                if t in stop:
                    break
                ids.append(t)
                lps.append(lp[0, t].item())
                logits = model(token[None], cache=cache)[:, -1, :]
            text = hf.decode(ids, skip_special_tokens=True)
            try:
                pred = parse_output(text)
            except (ValueError, KeyError, TypeError, AttributeError):
                pred = None
            # Score exactly the generated JSON token span (exclude fences and end tokens).
            start = text.find("{")
            end = text.rfind("}")
            vals = []
            if start >= 0 and end >= start:
                before = 0
                for k, t in enumerate(ids):
                    after = len(hf.decode(ids[: k + 1], skip_special_tokens=True))
                    if after > start and before <= end and t not in special:
                        vals.append(lps[k])
                    before = after
            score = sum(vals) / len(vals) if vals and pred is not None else -1e30
            f.write(
                json.dumps(
                    {
                        "id": row.get("id", str(n)),
                        "set": row["_set"],
                        "pred": pred,
                        "raw": text,
                        "score": score,
                        "new_tokens": len(ids),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.flush()
            del cache, logits
            if (n + 1) % 25 == 0:
                print(
                    f"PROGRESS infer {n + 1}/{len(allrows)} seconds={time.monotonic() - t0:.0f}",
                    flush=True,
                )
    print(f"DONE seconds={time.monotonic() - t0:.0f} peak_mem_gb={mx.get_peak_memory() / 1e9:.2f}")


def merge(args):
    from evaluate import evaluate

    rows, more = load_rows(args.dataset, args.extra_test, args.test_subset)
    allrows = rows + more
    def read(spec):  # comma-separated shard files, in row order
        return [
            json.loads(x)
            for f in spec.split(",")
            for x in pathlib.Path(f).read_text().splitlines()
        ]

    base = read(args.base)
    adapter = read(args.adapter)
    if not (len(base) == len(adapter) == len(allrows)):
        raise RuntimeError(f"incomplete predictions: {len(base)} {len(adapter)} {len(allrows)}")
    for r, b, a in zip(allrows, base, adapter):
        if not (r.get("id") == b["id"] == a["id"]):
            raise RuntimeError("prediction order mismatch")
    n = len(rows)
    b = [x["pred"] for x in base]
    a = [x["pred"] for x in adapter]
    bs = [x["score"] for x in base]
    ads = [x["score"] for x in adapter]
    result = json.loads(pathlib.Path(args.meta).read_text()) if args.meta else {}
    result.update(
        {
            "synthetic": True,
            "decoding": "greedy",
            "max_new_tokens": 384,
            "batch_size": 1,
            "counts": {"test": n, "extra_test": len(more)},
            "test": evaluate(rows, b[:n], a[:n], bs[:n], ads[:n]),
            "predictions": [
                {
                    "id": r.get("id", str(i)),
                    "base": b[i],
                    "adapter": a[i],
                    "base_raw": base[i]["raw"],
                    "adapter_raw": adapter[i]["raw"],
                    "base_mean_json_logprob": bs[i],
                    "adapter_mean_json_logprob": ads[i],
                }
                for i, r in enumerate(allrows)
            ],
        }
    )
    if more:
        result["extra_test"] = evaluate(more, b[n:], a[n:], bs[n:], ads[n:])
    def relative_split(part, pb, pa):
        """Notes that contain a relative date (N days/weeks ago) against notes with absolute dates only."""
        from metrics import summary

        rel = [i for i, r in enumerate(part) if {"days", "weeks"} & set(r.get("date_forms", []))]
        absolute = [i for i in range(len(part)) if i not in set(rel)]
        return {
            name: {
                "base": summary([part[i] for i in ix], [pb[i] for i in ix]),
                "adapter": summary([part[i] for i in ix], [pa[i] for i in ix]),
            }
            for name, ix in [("with_relative_date", rel), ("absolute_dates_only", absolute)]
        }

    result["by_relative_date"] = {"test": relative_split(rows, b[:n], a[:n])}
    if more:
        result["by_relative_date"]["extra_test"] = relative_split(more, b[n:], a[n:])
    braw = [x["raw"] for x in base]
    araw = [x["raw"] for x in adapter]
    result["lenient"] = {
        "definition": "Supplementary reading of the same outputs: code fences, a missing precision field, extra keys and a repeated events key are tolerated; an event counts when type and date match; a note matches when the route and the set of (type, date) pairs match.",
        "test": lenient_score(rows, braw[:n], araw[:n]),
    }
    if more:
        result["lenient"]["extra_test"] = lenient_score(more, braw[n:], araw[n:])
    pathlib.Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("wrote", args.output)


def lenient_parse(text):
    """Best-effort reading of an output for the supplementary score: tolerates code fences, a missing
    precision field, extra keys and a repeated "events" key (lists are concatenated)."""
    import datetime

    from sample import ROUTES, TYPES

    def hook(pairs):
        d = {}
        for k, v in pairs:
            if k == "events" and isinstance(v, list) and isinstance(d.get(k), list):
                d[k] = d[k] + v
            else:
                d[k] = v
        return d

    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    i = s.find("{")
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder(object_pairs_hook=hook).raw_decode(s[i:])
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    route = obj.get("entry_route")
    events = []
    if isinstance(obj.get("events"), list):
        for e in obj["events"]:
            if isinstance(e, dict) and e.get("type") in TYPES and isinstance(e.get("date"), str):
                try:
                    date = datetime.date.fromisoformat(e["date"]).isoformat()
                except ValueError:
                    continue
                events.append((e["type"], date))
    return {"entry_route": route if isinstance(route, str) and route in ROUTES else None, "events": events}


def lenient_score(rows, base_raw, adapter_raw):
    """Supplementary: event F1 on (type, date), route accuracy and note match ignoring the precision field."""
    import collections

    from metrics import mcnemar, wilson

    def one(raws):
        tp = fp = fn = route = exact = unreadable = 0
        outcomes = []
        for row, raw in zip(rows, raws):
            g = json.loads(row["target_json"])
            p = lenient_parse(raw)
            unreadable += p is None
            p = p or {"entry_route": None, "events": []}
            a = collections.Counter((e["type"], e["date"]) for e in g["events"])
            b = collections.Counter(p["events"])
            tp += sum((a & b).values())
            fp += sum((b - a).values())
            fn += sum((a - b).values())
            r = p["entry_route"] == g["entry_route"]
            route += r
            ok = r and a == b
            exact += ok
            outcomes.append(ok)
        return {
            "precision": wilson(tp, tp + fp),
            "recall": wilson(tp, tp + fn),
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
            "note_match_ignoring_precision": wilson(exact, len(rows)),
            "route_accuracy": wilson(route, len(rows)),
            "unreadable": unreadable,
            "outcomes": outcomes,
        }

    b, a = one(base_raw), one(adapter_raw)
    bo = sum(x and not y for x, y in zip(b["outcomes"], a["outcomes"]))
    ao = sum(y and not x for x, y in zip(b["outcomes"], a["outcomes"]))
    return {
        "base": b,
        "adapter": a,
        "mcnemar": {"base_only_correct": bo, "adapter_only_correct": ao, "exact_p": mcnemar(bo, ao)},
    }


def curve(args):
    """Parse the mlx_lm.lora progress table (ANSI colours stripped) into a loss curve."""
    train, val, saved = [], [], []
    text = re.sub(r"\x1b\[[0-9;]*m", "", pathlib.Path(args.log).read_text())
    for line in text.splitlines():
        m = re.match(r"\s+(\d+)\s+val\s+([\d.]+)\s+([\d.]+)s", line)
        if m:
            val.append({"iter": int(m[1]), "val_loss": float(m[2]), "seconds": float(m[3])})
            continue
        m = re.match(r"\s+(\d+)\s+([\d.]+)\s+\S?\s+([\d.]+)\s+([\d.]+)k", line)
        if m:
            train.append({"iter": int(m[1]), "train_loss": float(m[2]), "label_tokens_per_sec": float(m[3]), "label_tokens_k": float(m[4])})
            continue
        m = re.match(r"\s+save\s+(\d+)_adapters", line)
        if m:
            saved.append(int(m[1]))
    pathlib.Path(args.output).write_text(
        json.dumps({"train": train, "val": val, "saved_checkpoints": saved}, indent=1)
    )
    print("train points", len(train), "val points", len(val), "last", train[-1] if train else None)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--dataset", default=str(DATA / "dataset-v1"))
    a.add_argument("--output", required=True)
    a = sub.add_parser("infer")
    a.add_argument("--model", required=True)
    a.add_argument("--adapter")
    a.add_argument("--dataset", default=str(DATA / "dataset-v1"))
    a.add_argument("--extra-test")
    a.add_argument("--test-subset", type=int, default=0)
    a.add_argument("--output", required=True)
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--skip", type=int, default=0)
    a.add_argument("--split", default="test", choices=["test", "val"], help="which split of the dataset to read")
    a.add_argument("--complement", action="store_true", help="with --test-subset: the rows NOT in the seeded subset")
    a = sub.add_parser("merge")
    a.add_argument("--dataset", default=str(DATA / "dataset-v1"))
    a.add_argument("--extra-test")
    a.add_argument("--test-subset", type=int, default=0)
    a.add_argument("--base", required=True)
    a.add_argument("--adapter", required=True)
    a.add_argument("--meta")
    a.add_argument("--output", required=True)
    a = sub.add_parser("curve")
    a.add_argument("--log", required=True)
    a.add_argument("--output", required=True)
    args = p.parse_args()
    {"prepare": prepare, "infer": infer, "merge": merge, "curve": curve}[args.cmd](args)
