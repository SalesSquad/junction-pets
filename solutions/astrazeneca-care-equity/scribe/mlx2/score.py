"""Score the step 3 arms on the 310 SYNTHETIC validation notes and write data/scribe/v4/mlx/validation-v1.json.

Exact match = the code-resolved prediction equals the canonical label (route, every event type, date and precision).
  absolute arm: model JSON -> canonicalise -> scribe/v3/resolve.py repair() with resolver arm A' (product default)
                and A; "off" is the model as is.
  expression arm: model JSON -> scribe/v2/data_tools.resolve_expression (code computes every date).
A parse failure is an output that does not survive that path; it counts as wrong. Wilson 95% intervals, exact
McNemar between arms on the same notes, groups by date form (groups overlap) and by writer.

Also writes outputs/<arm>/val-records.jsonl per arm for the cascade: id, writer, date_forms, exact, parse_failed,
prediction (code-resolved), expression (expression arms), model_prediction (absolute arms, before the resolver),
confidence (mean token log-probability), min_logprob, new_tokens.

Reads only val. Test and stress sets are scored once by step 8.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys

import m2common as C

import data_tools as DT
import resolve as RV  # scribe/v3/resolve.py (frozen; hashes in data/scribe/v4/resolver/freeze.json)
from formats import tolerant_json
from metrics import mcnemar, wilson
from prompts import canonicalise

ARM_FORMATS = {"A-270m-abs": "absolute", "B-270m-expr-aug": "expression", "C-1b-expr-aug": "expression"}
RELATIVE_FORMS = {"days", "weeks"}


def parse(fmt, raw, row):
    """-> (variants {name: prediction or None}, expression or None, model_prediction or None, mode, error)."""
    try:
        value, mode = tolerant_json(raw)
        if fmt == "expression":
            pred = DT.resolve_expression(value, row["note_date"])
            return {"code": pred}, value, None, mode, ""
        model = canonicalise(value)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        none = {"code": None} if fmt == "expression" else {"off": None, "A": None, "A'": None}
        return none, None, None, "failed", f"{type(e).__name__}: {e}"
    return ({"off": model,
             "A": RV.repair(model, row["note_text"], row["note_date"], "A"),
             "A'": RV.repair(model, row["note_text"], row["note_date"], "A'")},
            None, model, mode, "")


def rate(k, n):
    w = wilson(k, n)
    return {"k": k, "n": n, "value": round(w["value"], 4) if n else None, "ci95": [round(x, 4) for x in w["ci95"]] if n else None}


def groups(rows, outcomes):
    by_form, by_writer = collections.defaultdict(list), collections.defaultdict(list)
    rel, absolute = [], []
    for r, ok in zip(rows, outcomes):
        for f in r.get("date_forms") or []:
            by_form[f].append(ok)
        by_writer["haiku" if "haiku" in (r.get("writer") or "") else "nemotron"].append(ok)
        (rel if RELATIVE_FORMS & set(r.get("date_forms") or []) else absolute).append(ok)
    return {
        "by_date_form": {k: rate(sum(v), len(v)) for k, v in sorted(by_form.items())},
        "by_writer": {k: rate(sum(v), len(v)) for k, v in sorted(by_writer.items())},
        "with_relative_date": rate(sum(rel), len(rel)),
        "absolute_dates_only": rate(sum(absolute), len(absolute)),
    }


def score_arm(arm, rows, path):
    fmt = ARM_FORMATS[arm]
    recs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["id"]] = r
    missing = [r["id"] for r in rows if r["id"] not in recs]
    if missing:
        return {"status": "incomplete", "outputs": len(recs), "missing": len(missing)}, None
    labels = [json.loads(r["target_json"]) for r in rows]
    per = []
    variants_out = collections.defaultdict(list)
    modes = collections.Counter()
    for row, gold in zip(rows, labels):
        o = recs[row["id"]]
        variants, expression, model, mode, err = parse(fmt, o["raw"], row)
        modes[mode] += 1
        for name, pred in variants.items():
            variants_out[name].append(pred == gold)
        primary = variants["code"] if fmt == "expression" else variants["A'"]
        per.append({"id": row["id"], "writer": row["writer"], "date_forms": list(row.get("date_forms") or []),
                    "exact": primary == gold, "parse_failed": mode == "failed", "parse_error": err or None,
                    "prediction": primary, "expression": expression, "model_prediction": model,
                    "confidence": o["confidence"], "min_logprob": o["min_logprob"], "new_tokens": o["new_tokens"],
                    "hit_max_tokens": o["hit_max_tokens"], "seconds": o["seconds"]})
    primary_name = "code" if fmt == "expression" else "A'"
    res = {
        "status": "ok", "format": fmt, "primary_variant": primary_name,
        "resolution": ("scribe/v2/data_tools.resolve_expression" if fmt == "expression"
                       else "scribe/v3/resolve.py repair(); A' = product default, A = digits only, off = model as is"),
        "exact_match": {name: rate(sum(v), len(v)) for name, v in variants_out.items()},
        "parse": {"strict": modes["strict"], "tolerant": modes["tolerant"], "failed": modes["failed"],
                  "failure_rate": round(modes["failed"] / len(rows), 4)},
        **groups(rows, variants_out[primary_name]),
        "hit_max_tokens": sum(o["hit_max_tokens"] for o in recs.values()),
        "mean_new_tokens": round(sum(o["new_tokens"] for o in recs.values()) / len(recs), 1),
        "seconds_per_note": round(sum(o["seconds"] for o in recs.values()) / len(recs), 3),
    }
    if fmt == "absolute":
        res["by_writer_off"] = groups(rows, variants_out["off"])["by_writer"]
        res["with_relative_date_off"] = groups(rows, variants_out["off"])["with_relative_date"]
    return res, per


def compare(a_name, a, b_name, b):
    ao = sum(x and not y for x, y in zip(a, b))
    bo = sum(y and not x for x, y in zip(a, b))
    return {"a": a_name, "b": b_name, "a_only_correct": ao, "b_only_correct": bo, "exact_p": round(mcnemar(ao, bo), 6),
            "difference_points": round(100 * (sum(b) - sum(a)) / len(a), 2)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arms", nargs="*", default=list(ARM_FORMATS))
    args = ap.parse_args(argv)
    rows = C.load_split("val")
    arms, outcomes = {}, {}
    for arm in args.arms:
        path = C.OUT / "outputs" / arm / "val.jsonl"
        train = C.ART / arm / "train-result.json"
        if not path.exists():
            arms[arm] = {"status": "not run"}
            continue
        res, per = score_arm(arm, rows, path)
        if train.exists():
            t = json.loads(train.read_text())
            res["training"] = {k: t.get(k) for k in ("base", "batch", "grad_accumulation_steps", "optimizer_steps",
                                                     "training_examples", "wall_seconds", "peak_memory_gb_reported",
                                                     "adapter", "adapter_sha256", "killed", "returncode")}
        arms[arm] = res
        if per is not None:
            out = C.OUT / "outputs" / arm / "val-records.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for p in per:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")
            res["records"] = C.rel(out)
            outcomes[arm] = [p["exact"] for p in per]
    comparisons = []
    if "A-270m-abs" in outcomes:
        a = outcomes["A-270m-abs"]
        for other in ("B-270m-expr-aug", "C-1b-expr-aug"):
            if other in outcomes:
                comparisons.append(compare("A-270m-abs (resolver A')", a, other, outcomes[other]))
    if "B-270m-expr-aug" in outcomes and "C-1b-expr-aug" in outcomes:
        comparisons.append(compare("B-270m-expr-aug", outcomes["B-270m-expr-aug"], "C-1b-expr-aug", outcomes["C-1b-expr-aug"]))
    b = arms.get("B-270m-expr-aug", {})
    b_val = b.get("exact_match", {}).get("code", {}).get("value") if b.get("status") == "ok" else None
    a_val = arms.get("A-270m-abs", {}).get("exact_match", {}).get("A'", {}).get("value") if arms.get("A-270m-abs", {}).get("status") == "ok" else None

    def success(arm):
        r = arms.get(arm, {})
        if r.get("status") != "ok" or a_val is None:
            return None
        v = r["exact_match"]["code"]["value"]
        c = next((x for x in comparisons if x["b"] == arm and x["a"].startswith("A-270m-abs")), None)
        sig = c is not None and c["exact_p"] < 0.05
        direction = None if c is None else ("better than A" if c["b_only_correct"] > c["a_only_correct"] else
                                            "worse than A" if c["b_only_correct"] < c["a_only_correct"] else "tied")
        base_ok = v >= 0.90 and (a_val - v) <= 0.03 and r["parse"]["failure_rate"] < 0.01
        return {"at_least_0.90": v >= 0.90, "within_3_points_of_A": (a_val - v) <= 0.03,
                "mcnemar_not_significant": not sig if c else None, "mcnemar_direction": direction,
                "parse_failures_under_1pct": r["parse"]["failure_rate"] < 0.01,
                "met": base_ok and not sig,
                "met_reading_as_not_worse_than_A": base_ok and not (sig and direction == "worse than A"),
                "note": "'met' reads the plan literally (McNemar not significant in either direction). The criterion "
                        "guards against an arm worse than A; an arm significantly better than A fails the literal "
                        "reading and passes 'met_reading_as_not_worse_than_A'."}

    doc = {
        "schema": "scribe-v4-mlx-validation-v1", "synthetic": True, "created_utc": C.now(),
        "role": "validation = selection evidence (310 SYNTHETIC notes: 250 Nemotron-written, 60 Haiku-written). "
                "No test or stress note was read; step 8 scores those once.",
        "scoring": __doc__.strip().split("\n\n")[1],
        "arms": arms,
        "comparisons": comparisons,
        "rules": {
            "C_gate": "train arm C only if arm B reaches at least 0.80 exact match on validation",
            "B_at_least_0.80": None if b_val is None else b_val >= 0.80,
            "success_preregistered_in_NVIDIA_OPTIONS_step3": "B or C >= 0.90 on validation with code resolution, within 3 "
                                                             "points of A, McNemar not significant, under 1% parse failures",
            "success_B": success("B-270m-expr-aug"),
            "success_C": success("C-1b-expr-aug"),
        },
        "person_confirms": "Every extracted event is a proposal: pre-filled for one-click confirmation or flagged as "
                           "needing editing. A person confirms every event.",
    }
    timing = C.OUT / "timing-v1.json"
    if timing.exists():
        doc["inference_timing_20_val_notes_base_models"] = json.loads(timing.read_text())["results"]
    C.save_json(C.OUT / "validation-v1.json", doc)
    summary = {a: (r.get("exact_match"), r.get("parse")) for a, r in arms.items()}
    C.log("score-validation", "scribe/.venv/bin/python scribe/mlx2/score.py " + " ".join(args.arms),
          inputs={"val": C.rel(C.DATASET / "val.parquet"), "outputs": [C.rel(C.OUT / "outputs" / a / "val.jsonl") for a in args.arms]},
          outputs={"file": C.rel(C.OUT / "validation-v1.json")},
          metrics={"exact_match": {a: r.get("exact_match") for a, r in arms.items()}, "comparisons": comparisons,
                   "B_at_least_0.80": doc["rules"]["B_at_least_0.80"]})
    print(json.dumps(summary, indent=1))
    print(json.dumps(comparisons, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
