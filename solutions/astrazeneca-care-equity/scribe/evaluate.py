import argparse
import json
import pathlib

from common import DATA, log, save
from metrics import mcnemar, risk_coverage, summary
from prompts import messages, parse_output
from train_lora import load_model


def infer(model, tok, rows, batch_size=16):
    """Greedy decoding. Repair 2026-11-14: batched (left padding, prompts sorted by length)
    and the generated ids are cut at the first stop token before parsing and scoring."""
    import time

    import torch

    n = len(rows)
    predictions = [None] * n
    scores = [-1e30] * n
    raw = [""] * n
    model.eval()
    prompts = [
        tok.apply_chat_template(messages(r), tokenize=False, add_generation_prompt=True)
        for r in rows
    ]
    stop = model.generation_config.eos_token_id
    stop = set(stop if isinstance(stop, (list, tuple)) else [stop])
    stop.add(tok.eos_token_id)
    eot = tok.convert_tokens_to_ids("<end_of_turn>")
    if isinstance(eot, int) and eot != tok.unk_token_id:
        stop.add(eot)
    special = set(tok.all_special_ids)
    order = sorted(range(n), key=lambda i: len(prompts[i]))
    t0 = time.monotonic()
    for lo in range(0, n, batch_size):
        chunk = order[lo : lo + batch_size]
        x = tok(
            [prompts[i] for i in chunk],
            return_tensors="pt",
            add_special_tokens=False,
            padding=True,
        ).to(model.device)
        with torch.inference_mode():
            o = model.generate(
                **x,
                do_sample=False,
                max_new_tokens=384,
                return_dict_in_generate=True,
                output_scores=True,
                pad_token_id=tok.pad_token_id,
            )
        seqs = o.sequences[:, x["input_ids"].shape[1] :]
        # Log-probability of each generated token, one column per decoding step.
        tlp = torch.cat(
            [
                torch.log_softmax(o.scores[k].float(), -1).gather(1, seqs[:, k : k + 1])
                for k in range(seqs.shape[1])
            ],
            1,
        ).cpu()
        for j, i in enumerate(chunk):
            ids = seqs[j].tolist()
            ids = ids[: next((k for k, t in enumerate(ids) if t in stop), len(ids))]
            text = tok.decode(ids, skip_special_tokens=True)
            raw[i] = text
            try:
                predictions[i] = parse_output(text)
            except (ValueError, KeyError, TypeError, AttributeError):
                predictions[i] = None
            # Score exactly the generated JSON token span (exclude fences and end tokens).
            start = text.find("{")
            end = text.rfind("}")
            vals = []
            if start >= 0 and end >= start:
                before = 0
                for k, token in enumerate(ids):
                    after = len(tok.decode(ids[: k + 1], skip_special_tokens=True))
                    if after > start and before <= end and token not in special:
                        vals.append(tlp[j, k].item())
                    before = after
            scores[i] = (
                sum(vals) / len(vals)
                if vals and predictions[i] is not None
                else -1e30
            )
        del o, tlp
        print(
            f"PROGRESS infer {min(lo + batch_size, n)}/{n} seconds={time.monotonic() - t0:.0f}",
            flush=True,
        )
    return predictions, scores, raw


def evaluate(rows, base, adapter, bs, ads):
    bm = summary(rows, base)
    am = summary(rows, adapter)
    b = sum(x and not y for x, y in zip(bm["outcomes"], am["outcomes"]))
    c = sum(y and not x for x, y in zip(bm["outcomes"], am["outcomes"]))
    breakdown = {}
    for f in sorted({f for r in rows for f in r.get("date_forms", [])}):
        ix = [i for i, r in enumerate(rows) if f in r.get("date_forms", [])]
        breakdown[f] = {
            "base": summary([rows[i] for i in ix], [base[i] for i in ix]),
            "adapter": summary([rows[i] for i in ix], [adapter[i] for i in ix]),
        }
    return {
        "base": bm,
        "adapter": am,
        "mcnemar": {
            "base_only_correct": b,
            "adapter_only_correct": c,
            "exact_p": mcnemar(b, c),
        },
        "by_date_form": breakdown,
        "risk_coverage": {
            "base": risk_coverage(bs, bm["outcomes"]),
            "adapter": risk_coverage(ads, am["outcomes"]),
        },
    }


def main():
    import pyarrow.parquet as pq
    from peft import PeftModel
    from transformers import AutoTokenizer

    p = argparse.ArgumentParser()
    p.add_argument("--adapter", default=str(DATA / "adapter-v1"))
    p.add_argument("--dataset", default=str(DATA / "dataset-v1"))
    p.add_argument("--extra-test")
    p.add_argument("--output", default=str(DATA / "eval-v1.json"))
    p.add_argument("--batch-size", type=int, default=16)
    args = p.parse_args()
    config = json.loads(
        (pathlib.Path(args.adapter) / "training-config.json").read_text()
    )
    name = config["base_model"]
    tok = AutoTokenizer.from_pretrained(args.adapter)
    tok.padding_side = "left"
    model = load_model(name).cuda()
    rows = pq.read_table(pathlib.Path(args.dataset) / "test.parquet").to_pylist()
    for r in rows:
        if isinstance(r.get("verifier_probabilities"), list):
            r["verifier_probabilities"] = dict(r["verifier_probabilities"])
    extra = []
    if args.extra_test:
        extra = [
            json.loads(x)
            for x in pathlib.Path(args.extra_test).read_text().splitlines()
            if x.strip()
        ]
        for r in extra:
            if "target_json" not in r:
                r["target_json"] = json.dumps(
                    {"entry_route": r["entry_route"], "events": r["events"]}
                )
    allrows = rows + extra
    import time

    import torch

    t0 = time.monotonic()
    b, bs, br = infer(model, tok, allrows, args.batch_size)
    t1 = time.monotonic()
    model = PeftModel.from_pretrained(model, args.adapter)
    a, ads, ar = infer(model, tok, allrows, args.batch_size)
    t2 = time.monotonic()
    n = len(rows)
    result = {
        "base_model": name,
        "decoding": "greedy",
        "max_new_tokens": 384,
        "batch_size": args.batch_size,
        "synthetic": True,
        "counts": {"test": n, "extra_test": len(extra)},
        "seconds": {"base": t1 - t0, "adapter": t2 - t1},
        "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
        "test": evaluate(rows, b[:n], a[:n], bs[:n], ads[:n]),
        "predictions": [
            {
                "id": r.get("id", str(i)),
                "base": b[i],
                "adapter": a[i],
                "base_raw": br[i],
                "adapter_raw": ar[i],
                "base_mean_json_logprob": bs[i],
                "adapter_mean_json_logprob": ads[i],
            }
            for i, r in enumerate(allrows)
        ],
    }
    if extra:
        result["extra_test"] = evaluate(extra, b[n:], a[n:], bs[n:], ads[n:])
    save(pathlib.Path(args.output), result)
    log(
        "evaluate",
        inputs={"base_model": name, "adapter": args.adapter, "test_n": n},
        outputs=[args.output],
    )


if __name__ == "__main__":
    main()
