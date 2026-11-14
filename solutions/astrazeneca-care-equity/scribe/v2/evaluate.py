"""Greedy decoding and scoring for version 2.

Decoding is greedy, optionally constrained to the output format's JSON schema (constrained.py). The
engine actually used is recorded; when none is available the output is parsed tolerantly instead.
Scoring reuses the version-1 metrics (scribe/metrics.py) on the absolute form: for the expression
format every prediction is first resolved to absolute dates by scribe/v2/data_tools.py.
Confidence of a note is the mean log-probability of its generated tokens (stop token included) under
the model's unconstrained distribution; an unparsable output has no confidence and is never accepted.

The scoring functions are pure Python. Only generate(), predict() and main() need torch.

Guard: this script refuses to read a test split unless it is given the frozen selection file that
run_ablation.py writes after every choice has been made on validation data.
"""

from __future__ import annotations

import argparse
import collections
import math
import pathlib
import time

import _paths  # noqa: F401
import constrained
import data_iface
import formats
from core import load_json, log, save_json, versions
from metrics import mcnemar, risk_coverage, summary, wilson

MISSING_SCORE = -1e30  # stands in for "no confidence" where a float is required
DEFAULT_MAX_NEW_TOKENS = 192
# A constrained output is only well-formed if it is allowed to finish. With the Gemma tokenizer the
# longest label of 300 sampled notes (four events) took 117 tokens in the absolute format and 136 in
# the expression format; the schemas allow eight events.
CONSTRAINED_MIN_NEW_TOKENS = 320
CONFIDENCE = "mean log-probability of the generated tokens including the stop token, unconstrained distribution"


# ---- pure scoring --------------------------------------------------------------------------------


def mean_logprob(values):
    values = [v for v in values if v is not None]
    if not values or any(math.isnan(v) for v in values):
        return None
    return sum(values) / len(values)


def make_record(row, fmt, text, token_logprobs, stopped):
    """One note's result: the absolute prediction (or None), how it was parsed, and its confidence."""
    prediction, mode, error = formats.interpret(fmt, text, row)
    confidence = mean_logprob(token_logprobs) if prediction is not None else None
    return {
        "id": row["id"],
        "raw": text,
        "prediction": prediction,
        "parse_mode": mode,
        "parse_error": error,
        "confidence": confidence,
        # Diagnostics, kept for unparsable outputs too; only "confidence" is used for auto-acceptance.
        "mean_token_logprob": mean_logprob(token_logprobs),
        "min_token_logprob": min(token_logprobs) if token_logprobs else None,
        "tokens": len(token_logprobs),
        "stopped": bool(stopped),
    }


def _compact(rows, predictions):
    full = summary(rows, predictions)
    n = len(rows)
    return full, {
        "n": n,
        "note_exact_match": full["note_exact_match"],
        "event_precision": full["precision"],
        "event_recall": full["recall"],
        "event_f1": full["f1"],
        "type_only_f1": full["type_only_f1"],
        "route_accuracy": full["route_accuracy"],
        "distractor_extraction": full["distractor_extraction"],
        "invalid_output": wilson(sum(p is None for p in predictions), n),
    }


def _groups(rows, key):
    out = collections.defaultdict(list)
    for i, row in enumerate(rows):
        values = row.get(key)
        for value in values if isinstance(values, (list, tuple)) else [values]:
            out[str(value if value is not None else "unknown")].append(i)
    return {k: sorted(set(v)) for k, v in sorted(out.items())}


def score(rows, records, curve=False):
    """Metrics for one system on one set of notes, with per-writer and per-kind breakdowns."""
    if len(rows) != len(records):
        raise ValueError("rows and records differ in length")
    if any(r["id"] != rec["id"] for r, rec in zip(rows, records)):
        raise ValueError("rows and records are not aligned by id")
    predictions = [rec["prediction"] for rec in records]
    full, out = _compact(rows, predictions)
    out["date_error_histogram"] = {str(k): v for k, v in full["date_error_histogram"].items()}
    out["parse_modes"] = dict(collections.Counter(rec["parse_mode"] for rec in records))
    out["stopped"] = wilson(sum(rec["stopped"] for rec in records), len(records))
    for label, key in (("by_writer", "writer"), ("by_kind", "kind"), ("by_date_form", "date_forms")):
        out[label] = {
            value: _compact([rows[i] for i in idx], [predictions[i] for i in idx])[1]
            for value, idx in _groups(rows, key).items()
        }
    out["by_date_form_note"] = "a note is counted under every date form it contains, so these groups overlap"
    out["ids"] = [r["id"] for r in rows]
    out["outcomes"] = [bool(x) for x in full["outcomes"]]
    out["confidences"] = [rec["confidence"] for rec in records]
    rc = risk_coverage([MISSING_SCORE if c is None else c for c in out["confidences"]], out["outcomes"])
    out["risk_coverage"] = {
        "largest_empirical_coverage": rc["largest_empirical_coverage"],
        "limit": rc["limit"],
        # Review finding 6: the threshold behind this figure is chosen on the very notes it is reported on.
        "in_sample": True,
        "use": "diagnostic only; never quote as coverage at an error rate; the held-out check is risk_control",
    }
    if curve:
        out["risk_coverage"]["curve"] = rc["curve"]
    return out


def paired_test(ids_a, outcomes_a, ids_b, outcomes_b):
    """Exact two-sided McNemar test on notes scored for both systems (aligned by id)."""
    if list(ids_a) != list(ids_b):
        index = {i: o for i, o in zip(ids_b, outcomes_b)}
        common = [i for i in ids_a if i in index]
        outcomes_a = [o for i, o in zip(ids_a, outcomes_a) if i in index]
        outcomes_b = [index[i] for i in common]
    a_only = sum(a and not b for a, b in zip(outcomes_a, outcomes_b))
    b_only = sum(b and not a for a, b in zip(outcomes_a, outcomes_b))
    return {
        "n": len(outcomes_a),
        "a_only_correct": a_only,
        "b_only_correct": b_only,
        "exact_p": mcnemar(a_only, b_only),
    }


# ---- decoding (torch) ----------------------------------------------------------------------------


def stop_token_ids(tok, model=None):
    ids = set()
    eos = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    if eos is not None:
        ids |= set(eos if isinstance(eos, (list, tuple)) else [eos])
    if tok.eos_token_id is not None:
        ids.add(tok.eos_token_id)
    eot = tok.convert_tokens_to_ids("<end_of_turn>")
    if isinstance(eot, int) and eot >= 0 and eot != tok.unk_token_id:
        ids.add(eot)
    return sorted(int(i) for i in ids)


def _recorder():
    import torch
    from transformers import LogitsProcessor

    class RawLogprobRecorder(LogitsProcessor):
        """Records log p(chosen token) under the unmodified model distribution, one step behind.

        It must be the first processor: at step t it stores the raw log-softmax, and at step t+1 it
        reads which token was chosen from the last input id. Memory stays at one step.
        """

        def __init__(self):
            self.previous = None
            self.columns = []

        def __call__(self, input_ids, scores):
            if self.previous is not None:
                self.columns.append(self.previous.gather(1, input_ids[:, -1:]))
            self.previous = torch.log_softmax(scores.float(), dim=-1)
            return scores

        def finish(self, sequences):
            if self.previous is not None and sequences.shape[1] > len(self.columns):
                self.columns.append(self.previous.gather(1, sequences[:, -1:]))
            if not self.columns:
                return torch.zeros((sequences.shape[0], 0))
            return torch.cat(self.columns, 1).float().cpu()

    return RawLogprobRecorder()


def generate(model, tok, prompts, constraint=None, batch_size=16, max_new_tokens=DEFAULT_MAX_NEW_TOKENS, progress=True):
    """Greedy generation. Returns one (text, token_logprobs, stopped) per prompt, in input order."""
    import torch
    from transformers import LogitsProcessorList, PrefixConstrainedLogitsProcessor

    stop = stop_token_ids(tok, model)
    stop_set = set(stop)
    tok.padding_side = "left"  # batched generation only
    device = next(model.parameters()).device
    results = [None] * len(prompts)
    order = sorted(range(len(prompts)), key=lambda i: len(prompts[i]))
    model.eval()
    started = time.monotonic()
    for lo in range(0, len(order), batch_size):
        chunk = order[lo : lo + batch_size]
        enc = tok([prompts[i] for i in chunk], return_tensors="pt", add_special_tokens=False, padding=True).to(device)
        prompt_len = enc["input_ids"].shape[1]
        recorder = _recorder()
        processors = [recorder]
        if constraint is not None:
            constraint.start(len(chunk))
            processors.append(PrefixConstrainedLogitsProcessor(constraint.prefix_fn(prompt_len), num_beams=1))
        with torch.inference_mode():
            sequences = model.generate(
                **enc,
                do_sample=False,
                top_k=None,
                top_p=None,
                temperature=None,
                max_new_tokens=max_new_tokens,
                eos_token_id=stop,
                pad_token_id=tok.pad_token_id,
                logits_processor=LogitsProcessorList(processors),
                use_cache=True,
            )
        new = sequences[:, prompt_len:]
        logprobs = recorder.finish(new)
        if logprobs.shape[1] != new.shape[1]:
            raise RuntimeError(
                f"recorded {logprobs.shape[1]} decoding steps for {new.shape[1]} generated tokens; "
                "the generation loop does not call logits processors once per step as assumed"
            )
        for j, i in enumerate(chunk):
            ids = new[j].tolist()
            cut = next((k for k, t in enumerate(ids) if t in stop_set), None)
            stopped = cut is not None
            end = cut if stopped else len(ids)
            text = tok.decode(ids[:end], skip_special_tokens=True)
            kept = logprobs[j, : end + 1 if stopped else end].tolist()
            results[i] = (text, [max(v, -1e9) for v in kept], stopped)  # -inf would not survive JSON
        if progress:
            done = min(lo + batch_size, len(order))
            print(f"PROGRESS generate {done}/{len(order)} seconds={time.monotonic() - started:.0f}", flush=True)
    return results


def predict(model, tok, rows, fmt, constrained_mode="off", batch_size=16, max_new_tokens=DEFAULT_MAX_NEW_TOKENS):
    """Decode every note. Returns (records, decoding info)."""
    prompts = [tok.apply_chat_template(fmt.messages(r), tokenize=False, add_generation_prompt=True) for r in rows]
    stop = stop_token_ids(tok, model)
    schema = fmt.schema() if constrained_mode != "off" else None
    constraint, info = constrained.build_constraint(tok, schema, stop, tok.pad_token_id, constrained_mode)
    if constraint is not None:
        max_new_tokens = max(max_new_tokens, CONSTRAINED_MIN_NEW_TOKENS)
    started = time.monotonic()
    outputs = generate(model, tok, prompts, constraint, batch_size, max_new_tokens)
    seconds = time.monotonic() - started
    records = [make_record(row, fmt, *out) for row, out in zip(rows, outputs)]
    decoding = {
        "strategy": "greedy",
        "constraint": info,
        "max_new_tokens": max_new_tokens,
        "batch_size": batch_size,
        "confidence": CONFIDENCE,
        "seconds": seconds,
        "seconds_per_note": seconds / len(rows) if rows else None,
    }
    return records, decoding


# ---- command line --------------------------------------------------------------------------------


def system_spec(text):
    """'base:<size>' or 'run:<run directory>' -> spec for modeling.load_system plus format and name."""
    kind, _, value = text.partition(":")
    if kind == "base":
        return {"name": f"base-{value}-zero-shot", "kind": "base", "base": value, "path": None, "format": "absolute"}
    if kind == "run":
        result = load_json(pathlib.Path(value) / "result.json")
        saved = result["artifacts"]["saved"]
        return {
            "name": result["config"]["name"],
            "kind": saved["kind"],
            "base": result["config"]["base"],
            "path": saved["path"],
            "format": result["config"]["output_format"],
            "max_new_tokens": result.get("max_new_tokens"),
            "config_id": result.get("config_id"),
        }
    raise ValueError(f"system must be base:<size> or run:<directory>, got {text!r}")


def check_test_access(splits, frozen_path):
    """Test splits may only be read once the selection has been frozen on validation data."""
    wanted = [s for s in splits if s.startswith("test")]
    if not wanted:
        return None
    if not frozen_path:
        raise PermissionError(f"refusing to read {wanted}: pass --selection-frozen with the frozen selection file")
    frozen = load_json(frozen_path)
    if not frozen.get("frozen"):
        raise PermissionError(f"refusing to read {wanted}: {frozen_path} is not marked frozen")
    return frozen


def evaluate_system(spec, splits, constrained_mode, batch_size, max_new_tokens, smoke=None, limit=0, curve=True):
    import modeling

    fmt = formats.get_format(spec["format"])
    model, tok = modeling.load_system(spec, smoke)
    out = {"system": spec, "splits": {}, "sources": {}}
    for name in splits:
        rows, source = data_iface.load_split(name)
        if limit:
            rows = rows[:limit]
        records, decoding = predict(model, tok, rows, fmt, constrained_mode, batch_size, max_new_tokens)
        out["splits"][name] = {"metrics": score(rows, records, curve=curve), "decoding": decoding, "records": records}
        out["sources"][name] = {"rows": len(rows), "source": source}
    return out


def main():
    p = argparse.ArgumentParser(description="Evaluate one system (base model or trained run) on named splits.")
    p.add_argument("--system", required=True, help="base:<270m|1b|4b> or run:<run directory>")
    p.add_argument("--splits", required=True, help="comma-separated, e.g. val_nemotron,val_haiku")
    p.add_argument("--constrained", default="off", choices=["off", "auto", "native", "lmfe"])
    p.add_argument("--format", default=None, help="output format for a base model (default absolute)")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--max-new-tokens", type=int, default=0)
    p.add_argument("--selection-frozen", default=None, help="frozen selection file; required for test splits")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=0, help="first N notes only (wiring tests)")
    p.add_argument("--smoke-tokenizer", default=None, help="wiring test: tiny random model with this local tokenizer")
    args = p.parse_args()

    splits = [s for s in args.splits.split(",") if s]
    check_test_access(splits, args.selection_frozen)
    spec = system_spec(args.system)
    if args.format:
        spec["format"] = args.format
    max_new = args.max_new_tokens or spec.get("max_new_tokens") or DEFAULT_MAX_NEW_TOKENS
    smoke = {"tokenizer": args.smoke_tokenizer} if args.smoke_tokenizer else None
    started = time.monotonic()
    result = evaluate_system(spec, splits, args.constrained, args.batch_size, max_new, smoke, args.limit)
    result.update(
        schema="scribe-v2-eval-v1",
        synthetic=True,
        smoke=bool(smoke),
        versions=versions(),
        seconds=time.monotonic() - started,
    )
    save_json(args.out, result)
    if not smoke:
        log(
            "v2_evaluate",
            command=f"evaluate.py --system {args.system} --splits {args.splits} --constrained {args.constrained}",
            inputs={"system": spec["name"], "splits": splits},
            outputs=[str(args.out)],
            metrics={
                name: {
                    "n": block["metrics"]["n"],
                    "note_exact_match": block["metrics"]["note_exact_match"]["value"],
                    "constraint": block["decoding"]["constraint"]["backend"],
                }
                for name, block in result["splits"].items()
            },
        )


if __name__ == "__main__":
    main()
