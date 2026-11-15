"""Step 8 of NVIDIA_OPTIONS.md: the preregistered evaluation (data/scribe/stress/preregistration.json) and the cascade
recalibration. SYNTHETIC notes only. Research artefact, not a medical device: every extracted event is a proposal,
pre-filled for one-click confirmation or flagged as needing editing, and a person confirms every event.

Systems (one generation per Gemma arm and set; parsing and date code are deterministic):
  A        Gemma 3 270M, absolute format (step 3 arm A-270m-abs) + frozen resolver arm A (digits only)
  A'       the same generation + frozen resolver arm A' (digits + Finnish lexicon fi-relative-lexicon-v1)
  B        Gemma 3 270M, expression format, augmented (B-270m-expr-aug); code computes dates (resolve_expression)
  C        Gemma 3 1B, expression format, augmented (C-1b-expr-aug); code computes dates
  nemotron Nemotron 3.5 Super VL reader, Lane B's validation-selected version v3 (secondary system)

Sets: validation (310, selection evidence, step 3 single-sequence outputs, recomputed here), test (700, read once by
each Gemma arm here; already seen in earlier work, so post hoc/confirmatory), stress (308, frozen, primary, read once).

  scribe/.venv/bin/python scribe/v4/eval8.py verify     hashes of the stress set, preregistration, resolver, adapters
  scribe/.venv/bin/python scribe/v4/eval8.py score      writes data/scribe/v4/eval/results-v1.json and scribe/v4/RESULTS.md
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib
import json
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scribe" / "mlx2"))

import m2common as M  # noqa: E402  (puts scribe, scribe/v2, scribe/v3 on sys.path)
import score as S  # noqa: E402  scribe/mlx2/score.py: parse() is the step 3 scoring path, reused unchanged

import data_tools as DT  # noqa: E402,F401
import resolve as RV  # noqa: E402  scribe/v3/resolve.py (frozen)
from metrics import mcnemar, wilson  # noqa: E402


def _load_cascade():
    """scribe/v3/cascade.py for its leak guard and threshold rule. It imports `core` from scribe/judges; data_tools
    already holds scribe/v2/core.py under that name, so swap it out for the import and put it back."""
    saved = sys.modules.pop("core", None)
    try:
        sys.path.insert(0, str(ROOT / "scribe" / "v3"))
        return importlib.import_module("cascade")
    finally:
        if saved is not None:
            sys.modules["core"] = saved


CASCADE = _load_cascade()

EVAL = ROOT / "data/scribe/v4/eval"
STEP3_OUT = ROOT / "data/scribe/v4/mlx/outputs"
DATASET = ROOT / "data/scribe/v2/dataset"
STRESS = ROOT / "data/scribe/stress/stress-v1.parquet"
PREREG = ROOT / "data/scribe/stress/preregistration.json"
STRESS_SHA256 = "ae16f7474a8734bbc108d5e2f5c66bce698cbd0e4c88f60ffd4b742908184dfa"
PREREG_SHA256 = "d34a627bcd7e22061dbc667df8cb868c3ad2b058369bc7653fbcadf3c4df675f"  # pinned at 23:42 UTC before scoring
RESOLVER_FREEZE_SHA256 = "0e8e4d70dc879bee3009ae16418e6edd7b551bee24703ff73c527d5aeb9b29c3"
NEMO_CACHE = {"val": ROOT / "data/scribe/nemotron/cache/v3/val", "test": ROOT / "data/scribe/nemotron/cache/v3/test",
              "stress": EVAL / "nemotron/cache/v3/stress"}
RUNLOG = ROOT / "runs/laneA-step8.jsonl"
RESULTS = EVAL / "results-v1.json"
RESULTS_MD = HERE / "RESULTS.md"

MLX_ARMS = ("A-270m-abs", "B-270m-expr-aug", "C-1b-expr-aug")
SYSTEMS = ("A", "A'", "B", "C", "nemotron")
SYSTEM_ARM = {"A": "A-270m-abs", "A'": "A-270m-abs", "B": "B-270m-expr-aug", "C": "C-1b-expr-aug"}
SYSTEM_VARIANT = {"A": "A", "A'": "A'", "B": "code", "C": "code"}
ALPHA_PCT = 5
BASELINE = {"prefilled": 263, "wrong": 7, "notes": 700,
            "source": "Jev scores of the earlier student at a 5% validation error target (NVIDIA_OPTIONS.md section 1.4; scribe/TEACHING.md)"}


# ---- small helpers ----------------------------------------------------------------------------------------------


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, obj):
    M.save_json(path, obj)


def log(step, command, inputs=None, outputs=None, metrics=None, cost_usd=0, status="ok"):
    RUNLOG.parent.mkdir(exist_ok=True)
    line = dict(ts=now(), step=step, command=command, inputs=inputs or {}, outputs=outputs or {}, metrics=metrics or {},
                cost_usd=cost_usd, status=status)
    with RUNLOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def rate(k, n):
    w = wilson(k, n)
    return {"k": k, "n": n, "value": round(w["value"], 4) if n else None,
            "ci95": [round(x, 4) for x in w["ci95"]] if n else None}


def load_rows(split):
    import pyarrow.parquet as pq

    if split == "val":
        return pq.read_table(DATASET / "val.parquet").to_pylist()
    if split == "test":
        return pq.read_table(DATASET / "test_haiku.parquet").to_pylist() + pq.read_table(DATASET / "test_nemotron.parquet").to_pylist()
    if split == "stress":
        return pq.read_table(STRESS).to_pylist()
    raise ValueError(split)


def read_outputs(path):
    out = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = r
    return out


def parse_arm(arm, raw, row):
    return S.parse(S.ARM_FORMATS[arm], raw, row)


def primary(parsed):
    variants = parsed[0]
    return variants["code"] if "code" in variants else variants["A'"]


def writer_of(row):
    w = row.get("writer") or row.get("teacher_model") or ""
    return "haiku" if "haiku" in w else "nemotron"


def gold_of(row):
    return json.loads(row["target_json"])


# ---- predictions per system ---------------------------------------------------------------------------------------


def gemma_outputs(arm, split, engine):
    """engine 'single' = step 3's outputs (validation only); 'batch' = this step's batched outputs."""
    if split == "val":
        path = STEP3_OUT / arm / "val.jsonl" if engine == "single" else EVAL / "parity" / arm / "val-batch.jsonl"
    else:
        path = EVAL / "outputs" / arm / f"{split}.jsonl"
    return read_outputs(path) if path.exists() else None


def predictions(split, rows, engine="batch"):
    """{system: {id: {pred, parse_failed, flag, flag_phrases, confidence, engine}}}; a system without complete
    outputs on this split is left out (and reported as not run)."""
    out, missing = {}, {}
    for system in ("A", "A'", "B", "C"):
        arm = SYSTEM_ARM[system]
        outs = gemma_outputs(arm, split, engine)
        if outs is None or any(r["id"] not in outs for r in rows):
            missing[system] = "no outputs" if outs is None else f"{sum(r['id'] not in outs for r in rows)} notes missing"
            continue
        per = {}
        for row in rows:
            o = outs[row["id"]]
            variants, _expr, _model, mode, err = parse_arm(arm, o["raw"], row)
            spans = RV.needs_person_spans(row["note_text"], "A'") if system == "A'" else []
            per[row["id"]] = dict(pred=variants[SYSTEM_VARIANT[system]], parse_failed=mode == "failed", error=err or None,
                                  flag=bool(spans), flag_phrases=[s["phrase"] for s in spans],
                                  confidence=o.get("confidence"), engine=o.get("engine", "mlx-single"),
                                  hit_max_tokens=o.get("hit_max_tokens"))
        out[system] = per
    if split in ("val", "test"):
        recs = v2data_records(split)
        per = {}
        for row in rows:
            rec = recs.get(row["id"])
            model = rec["prediction"] if rec else None
            pred = RV.repair(model, row["note_text"], row["note_date"], "A'") if model is not None else None
            spans = RV.needs_person_spans(row["note_text"], "A'")
            per[row["id"]] = dict(pred=pred, parse_failed=pred is None, error=None, flag=bool(spans),
                                  flag_phrases=[x["phrase"] for x in spans], confidence=rec.get("confidence") if rec else None,
                                  engine="stored-cuda-greedy")
        out["v2data"] = per
    else:
        missing["v2data"] = "not run on this set (not in the preregistration)"
    cache = NEMO_CACHE[split]
    if cache.exists() and all((cache / f"{r['id']}.json").exists() for r in rows):
        per = {}
        for row in rows:
            n = json.loads((cache / f"{row['id']}.json").read_text())
            per[row["id"]] = dict(pred=n["prediction"], parse_failed=n["prediction"] is None, error=None,
                                  flag=bool(n.get("flagged")), flag_phrases=[], confidence=None, engine="nemotron-v3",
                                  calls=n.get("calls"), latency=n.get("latency"))
        out["nemotron"] = per
    else:
        missing["nemotron"] = "no cache" if not cache.exists() else f"{sum(not (cache / (r['id'] + '.json')).exists() for r in rows)} notes missing"
    return out, missing


def v2data_records(split):
    """Stored greedy outputs of the earlier product adapter C-270m-all-v2data (CUDA run, data/scribe/v3/student)."""
    d = ROOT / "data/scribe/v3/student/C-270m-all-v2data"
    if split == "val":
        recs = json.loads((d / "val-records.json").read_text())
    else:
        t = json.loads((d / "eval-test.json").read_text())
        recs = t["splits"]["test_haiku"]["records"] + t["splits"]["test_nemotron"]["records"]
    return {r["id"]: r for r in recs}


# ---- scoring ----------------------------------------------------------------------------------------------------


def date_errors(rows, per):
    """Per gold event whose type the system also output: |predicted - gold| in days (nearest predicted date of that
    type). Pathway intervals: consecutive gold events (date order) whose two types were both output; the error is
    |predicted interval - gold interval| in days. Parse failures count as missing types."""
    ev, iv = [], []
    missing = total = 0
    for row in rows:
        gold = gold_of(row)["events"]
        pred = (per[row["id"]]["pred"] or {}).get("events") or []
        by_type = collections.defaultdict(list)
        for e in pred:
            try:
                by_type[e["type"]].append(dt.date.fromisoformat(e["date"]))
            except (KeyError, TypeError, ValueError):
                continue
        matched = {}
        for g in gold:
            total += 1
            gd = dt.date.fromisoformat(g["date"])
            if not by_type.get(g["type"]):
                missing += 1
                continue
            pd = min(by_type[g["type"]], key=lambda d: abs((d - gd).days))
            ev.append(abs((pd - gd).days))
            matched[g["type"]] = (gd, pd)
        gs = sorted(gold, key=lambda g: g["date"])
        for a, b in zip(gs, gs[1:]):
            if a["type"] in matched and b["type"] in matched and a["type"] != b["type"]:
                (ga, pa), (gb, pb) = matched[a["type"]], matched[b["type"]]
                iv.append(abs((pb - pa).days - (gb - ga).days))

    def summ(xs):
        if not xs:
            return {"n": 0}
        s = sorted(xs)
        return {"n": len(xs), "mean_days": round(statistics.fmean(xs), 2), "median_days": statistics.median(xs),
                "p90_days": s[max(0, -(-9 * len(s) // 10) - 1)], "exact_0_days": rate(sum(x == 0 for x in xs), len(xs)),
                "within_7_days": rate(sum(x <= 7 for x in xs), len(xs))}

    return {"gold_events": total, "type_missing": missing, "event_date_error": summ(ev), "pathway_interval_error": summ(iv)}


def exact_list(rows, per):
    return [per[r["id"]]["pred"] == gold_of(r) for r in rows]


def subset(rows, outcomes, keep):
    xs = [ok for r, ok in zip(rows, outcomes) if keep(r)]
    return rate(sum(xs), len(xs))


def groups_common(rows, outcomes):
    by_form, by_writer = collections.defaultdict(list), collections.defaultdict(list)
    for r, ok in zip(rows, outcomes):
        for f in set(r.get("date_forms") or []):
            by_form[f].append(ok)
        by_writer[writer_of(r)].append(ok)
    return {"by_date_form (notes with at least one fact in that form; groups overlap)": {k: rate(sum(v), len(v)) for k, v in sorted(by_form.items())},
            "by_writer": {k: rate(sum(v), len(v)) for k, v in sorted(by_writer.items())}}


STRESS_SLICES = {
    "heldout": lambda r: bool(r["has_heldout"]) and not r["has_vague"],
    "standard": lambda r: r["kind"] == "standard" and not r["has_heldout"] and not r["has_vague"],
    "vague": lambda r: bool(r["has_vague"]),
    "no_event": lambda r: r["kind"] == "no_event",
    "no_event_with_heldout_distractor": lambda r: r["kind"] == "no_event" and bool(r["distractor_heldout"]),
}


def stress_groups(rows, outcomes):
    res = {"slices": {k: subset(rows, outcomes, f) for k, f in STRESS_SLICES.items()}}
    res["by_curriculum"] = {c: subset(rows, outcomes, lambda r, c=c: r["curriculum"] == c)
                            for c in sorted({r["curriculum"] for r in rows})}
    held = STRESS_SLICES["heldout"]
    fams = sorted({f for r in rows for f in (r["heldout_families"] or [])})
    res["heldout_slice_by_family"] = {f: subset(rows, outcomes, lambda r, f=f: held(r) and f in (r["heldout_families"] or []))
                                      for f in fams}
    return res


def compare(a_name, a, b_name, b):
    ao = sum(x and not y for x, y in zip(a, b))
    bo = sum(y and not x for x, y in zip(a, b))
    return {"a": a_name, "b": b_name, "n": len(a), "a_correct": sum(a), "b_correct": sum(b), "a_only_correct": ao,
            "b_only_correct": bo, "exact_mcnemar_p": float(f"{mcnemar(ao, bo):.3g}"),  # 3 significant digits: tiny p stays > 0
            "difference_b_minus_a_points": round(100 * (sum(b) - sum(a)) / len(a), 2) if a else None}


def vague_outcomes(rows, per, system):
    """Per vague fact (preregistered categories). A' flags a phrase when resolve().needs_person contains it; Nemotron
    v3 flags a note when its validator still finds a problem after the repair; A, B and C have no flag. A parse
    failure leaves no prediction: counted on its own, since the note then goes to manual entry."""
    c = collections.Counter()
    precise = []
    for row in rows:
        if not row["has_vague"]:
            continue
        p = per[row["id"]]
        gold = gold_of(row)
        vague = json.loads(row["vague_json"])
        vtypes = {v["type"] for v in vague}
        gtypes = {e["type"] for e in gold["events"]}
        pred = p["pred"]
        if pred is None:
            c["parse_failed"] += len(vague)
            precise.append(False)
            continue
        for v in vague:
            phrase = v["phrase"].lower()
            flagged = p["flag"] if system == "nemotron" else any(phrase in fp.lower() or fp.lower() in phrase for fp in p["flag_phrases"])
            evs = [e for e in pred["events"] if e["type"] == v["type"]]
            if flagged:
                c["sent_to_person"] += 1
            elif any(e.get("precision") == "DAY" for e in evs):
                c["invented_precise_date"] += 1
            elif evs:
                c["month_without_flag"] += 1
            else:
                c["dropped"] += 1
        kept = [e for e in pred["events"] if e["type"] not in vtypes or e["type"] in gtypes]
        precise.append(pred["entry_route"] == gold["entry_route"] and kept == gold["events"])
    n = sum(c.values())
    return {"facts": n, **{k: rate(c[k], n) for k in ("sent_to_person", "invented_precise_date", "month_without_flag", "dropped", "parse_failed")},
            "precise_part_exact": rate(sum(precise), len(precise))}


def score_split(split, rows, preds):
    res = {}
    outcomes = {}
    for system, per in preds.items():
        ex = exact_list(rows, per)
        outcomes[system] = ex
        r = {"exact_match": rate(sum(ex), len(ex)),
             "parse_failures": rate(sum(per[x["id"]]["parse_failed"] for x in rows), len(rows)),
             "notes_flagged_for_a_person": rate(sum(per[x["id"]]["flag"] for x in rows), len(rows)),
             "errors_in_days": date_errors(rows, per)}
        r.update(groups_common(rows, ex))
        if split == "stress":
            r.update(stress_groups(rows, ex))
            r["vague_outcome"] = vague_outcomes(rows, per, system)
        else:
            rel = lambda x: bool({"days", "weeks"} & set(x.get("date_forms") or []))  # noqa: E731
            r["with_relative_date"] = subset(rows, ex, rel)
            r["absolute_dates_only"] = subset(rows, ex, lambda x: not rel(x))
        engines = collections.Counter(per[x["id"]]["engine"] for x in rows)
        r["engine"] = dict(engines)
        res[system] = r
    return res, outcomes


# ---- cascade ------------------------------------------------------------------------------------------------------

CASCADE_GEMMA = ("A'", "B", "C", "v2data")
SIGNALS = ("agreement", "agreement+gemma_confidence", "agreement+nemotron_not_flagged", "gemma_confidence_alone")


def cascade_scores(signal, rows, gemma, nemo):
    """Per note: (score or None, the pre-filled answer). None never pre-fills. Agreement = the code-resolved Gemma answer
    equals the Nemotron answer exactly (both parsed)."""
    out = []
    for row in rows:
        g, n = gemma[row["id"]], nemo[row["id"]]
        agree = g["pred"] is not None and g["pred"] == n["pred"]
        if signal == "agreement":
            s = 1.0 if agree else None
        elif signal == "agreement+gemma_confidence":
            s = g["confidence"] if agree and g["confidence"] is not None else None
        elif signal == "agreement+nemotron_not_flagged":
            s = 1.0 if agree and not n["flag"] else None
        else:  # gemma_confidence_alone: the v3 student-confidence cascade on the code-resolved answer, no Nemotron
            s = g["confidence"] if g["pred"] is not None and g["confidence"] is not None else None
        out.append((s, g["pred"]))
    return out


def differences(row, pred):
    """What an agreed-but-wrong answer got wrong: route, missing and extra (type, date, precision) events."""
    gold = gold_of(row)
    g = {(e["type"], e["date"], e["precision"]) for e in gold["events"]}
    q = {(e["type"], e["date"], e["precision"]) for e in pred["events"]}
    return {"id": row["id"][:16], "writer": writer_of(row), "route_wrong": pred["entry_route"] != gold["entry_route"],
            "missing": sorted("/".join(x) for x in g - q), "extra": sorted("/".join(x) for x in q - g)}


def cascade(val_rows, val_preds, test_rows, test_preds, stress_rows=None, stress_preds=None):
    """Thresholds on validation only, through scribe/v3/cascade.py select_threshold() and its leak guard
    assert_validation_only(); then applied unchanged to test (and stress, descriptive)."""
    test_ids = {r["id"] for r in test_rows} | ({r["id"] for r in stress_rows} if stress_rows else set())
    configs = []
    for gname in CASCADE_GEMMA:
        if gname not in val_preds or "nemotron" not in val_preds:
            continue
        for signal in SIGNALS:
            vs = cascade_scores(signal, val_rows, val_preds[gname], val_preds["nemotron"])
            notes = [{"id": r["id"], "split": "val", "outcome": p == gold_of(r)} for r, (_s, p) in zip(val_rows, vs)]
            sel = CASCADE.select_threshold(notes, [s for s, _ in vs], ALPHA_PCT, test_ids)
            configs.append({"gemma": gname, "signal": signal, "validation": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in sel.items()}})
    # Selection rule, fixed before test is read: the largest validation coverage among feasible configurations that
    # pre-fill only on agreement; ties go to fewer signals (agreement alone), then to the smaller model.
    order = {"agreement": 0, "agreement+nemotron_not_flagged": 1, "agreement+gemma_confidence": 2}
    size = {"A'": 0, "B": 0, "C": 1, "v2data": 0}
    feasible = [c for c in configs if c["validation"].get("threshold") is not None and c["signal"] in order]
    chosen = max(feasible, key=lambda c: (c["validation"]["accepted"], -order[c["signal"]], -size[c["gemma"]]), default=None)

    def apply(c, rows, preds):
        if c["gemma"] not in preds or "nemotron" not in preds:
            return None
        t = c["validation"].get("threshold")
        sc = cascade_scores(c["signal"], rows, preds[c["gemma"]], preds["nemotron"])
        acc = [(r, p) for r, (s, p) in zip(rows, sc) if t is not None and s is not None and s >= t]
        wrong = [r for r, p in acc if p != gold_of(r)]
        res = {"notes": len(rows), "prefilled_for_one_click_confirmation": rate(len(acc), len(rows)),
               "prefilled_and_correct": rate(len(acc) - len(wrong), len(rows)),
               "error_among_prefilled": rate(len(wrong), len(acc)),
               "needs_editing": rate(len(rows) - len(acc), len(rows)),
               "per_100_notes_prefilled_correctly": round(100 * (len(acc) - len(wrong)) / len(rows), 1) if rows else None}
        res["wrong_among_prefilled_differences"] = [differences(r, p) for r, p in acc if p != gold_of(r)]
        hw = [r for r in rows if writer_of(r) == "haiku"]
        if hw and len(hw) != len(rows):
            ha = [(r, p) for r, p in acc if writer_of(r) == "haiku"]
            res["haiku_written"] = {"notes": len(hw), "prefilled": len(ha), "wrong_among_prefilled": sum(p != gold_of(r) for r, p in ha)}
        return res

    for c in configs:
        c["test"] = apply(c, test_rows, test_preds)
        if stress_rows is not None and stress_preds is not None:
            c["stress"] = apply(c, stress_rows, stress_preds)
    return {"alpha_pct": ALPHA_PCT, "min_accepted": CASCADE.MIN_ACCEPTED,
            "leak_guard": "scribe/v3/cascade.py assert_validation_only() runs inside select_threshold(); every test and stress id is passed as forbidden",
            "rule": "A note is pre-filled for one-click confirmation only when the code-resolved Gemma answer and the Nemotron v3 answer agree exactly "
                    "(and, for the threshold signals, its score is at or above the validation threshold). Otherwise it needs editing. A person confirms every note.",
            "selection_rule": "largest validation coverage among agreement-gated configurations with validation error <= 5% and >= 20 accepted notes; "
                              "ties: agreement alone first, then the 270M model",
            "gemma_answers": "batched MLX outputs (scribe/v4/binfer.py) on validation, test and stress, so thresholds and scores come from one engine",
            "chosen": {"gemma": chosen["gemma"], "signal": chosen["signal"]} if chosen else None,
            "configurations": configs, "baseline_today": BASELINE}


# ---- verify -------------------------------------------------------------------------------------------------------


def verify():
    checks = {
        "stress_parquet_sha256": (sha_file(STRESS), STRESS_SHA256),
        "preregistration_sha256": (sha_file(PREREG), PREREG_SHA256),
        "resolver_freeze_sha256": (sha_file(ROOT / "data/scribe/v4/resolver/freeze.json"), RESOLVER_FREEZE_SHA256),
    }
    frozen = json.loads((ROOT / "data/scribe/v4/resolver/freeze.json").read_text())
    for rel_path, want in frozen["files"].items():
        checks[rel_path] = (sha_file(ROOT / rel_path), want)
    adapters = json.loads((ROOT / "data/scribe/v4/mlx/adapters-v1.json").read_text())
    res = {k: {"now": a, "expected": b, "ok": a == b} for k, (a, b) in checks.items()}
    res["adapters"] = {}
    for arm in MLX_ARMS:
        path = M.ART / arm / "adapter" / "adapters.safetensors"
        want = None
        for key, val in (adapters.get("arms") or adapters).items() if isinstance(adapters, dict) else []:
            if key == arm and isinstance(val, dict):
                want = val.get("adapter_sha256") or val.get("mlx_adapter_sha256")
        got = sha_file(path) if path.exists() else None
        res["adapters"][arm] = {"now": got, "expected": want, "ok": want is None or got == want}
    res["all_ok"] = all(v["ok"] for k, v in res.items() if k not in ("adapters",)) and all(v["ok"] for v in res["adapters"].values())
    return res


# ---- main ---------------------------------------------------------------------------------------------------------


def cmd_score(_a):
    ver = verify()
    if not ver["all_ok"]:
        raise SystemExit("hash check failed; refusing to score: " + json.dumps(ver))
    prereg = json.loads(PREREG.read_text())
    doc = {"schema": "scribe-v4-step8-results-v1", "synthetic": True, "created_utc": now(),
           "person_confirms": "Every extracted event is a proposal: pre-filled for one-click confirmation or flagged as needing editing. A person confirms every event.",
           "verify": ver, "preregistration": {"file": str(PREREG.relative_to(ROOT)), "sha256": PREREG_SHA256, "primary": prereg["primary"],
                               "frozen_utc": prereg["frozen_utc"],
                               "file_mtime_utc": dt.datetime.fromtimestamp(PREREG.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "hash_note": "no sha256 of this file was recorded at its freeze; step 8 pinned it at 23:42 UTC, before any system read a stress note"},
           "systems": {"A": "Gemma 3 270M absolute format (A-270m-abs, MLX) + frozen resolver arm A (digits only)",
                       "A'": "the same generation + frozen resolver arm A' (digits + Finnish lexicon fi-relative-lexicon-v1)",
                       "B": "Gemma 3 270M expression format, augmented (B-270m-expr-aug, MLX); code computes dates",
                       "C": "Gemma 3 1B expression format, augmented (C-1b-expr-aug, MLX); code computes dates",
                       "v2data": "for reference, not preregistered: the earlier product adapter C-270m-all-v2data (Gemma 3 270M, absolute format, CUDA greedy outputs stored in data/scribe/v3/student) + frozen resolver arm A'; validation and test only",
                       "nemotron": "Nemotron 3.5 Super VL reader v3 (Lane B, selected on validation); same model wrote the stress notes, so its stress score is optimistic"},
           "sets": {}, "comparisons": {}}
    parity = EVAL / "parity-v1.json"
    if parity.exists():
        doc["engine_parity_on_validation"] = {a: {k: v for k, v in r.items() if k != "differing_predictions"}
                                              for a, r in json.loads(parity.read_text())["arms"].items()}
    rows_by, preds_by, outs_by = {}, {}, {}
    for split, engine, role in (("val", "single", "selection evidence (step 3 single-sequence outputs, recomputed)"),
                                ("test", "batch", "700 notes read once by each Gemma arm here; the set was read in earlier work, so post hoc / confirmatory"),
                                ("stress", "batch", "frozen stress set, primary, read once by each system")):
        rows = load_rows(split)
        preds, missing = predictions(split, rows, engine)
        res, outcomes = score_split(split, rows, preds)
        doc["sets"][split] = {"role": role, "notes": len(rows), "not_scored": missing, "systems": res}
        rows_by[split], preds_by[split], outs_by[split] = rows, preds, outcomes
    # comparisons
    for split in ("val", "test", "stress"):
        oc = outs_by[split]
        pairs = [("A'", "B"), ("A'", "C"), ("B", "C"), ("A'", "nemotron"), ("A", "A'"), ("v2data", "A'")]
        doc["comparisons"][split] = [compare(a, oc[a], b, oc[b]) for a, b in pairs if a in oc and b in oc]
    srows, so = rows_by["stress"], outs_by["stress"]
    for name in ("heldout", "standard"):
        keep = [STRESS_SLICES[name](r) for r in srows]
        sub = {k: [x for x, m in zip(v, keep) if m] for k, v in so.items()}
        pairs = [("A'", "B"), ("A", "A'"), ("A'", "C"), ("B", "C"), ("A'", "nemotron"), ("B", "nemotron")]
        doc["comparisons"][f"stress_{name}"] = [compare(a, sub[a], b, sub[b]) for a, b in pairs if a in sub and b in sub]
    # primary verdict
    prim = next((c for c in doc["comparisons"]["stress_heldout"] if c["a"] == "A'" and c["b"] == "B"), None)
    b_std = doc["sets"]["stress"]["systems"].get("B", {}).get("slices", {}).get("standard")
    if prim and b_std:
        diff = prim["difference_b_minus_a_points"]
        met = diff >= 10 and prim["exact_mcnemar_p"] < 0.01 and b_std["value"] >= 0.85
        a_wins = prim["a_only_correct"] > prim["b_only_correct"]
        doc["primary_result"] = {
            "comparison": "B against A' on the stress held-out slice (exact McNemar, two-sided)", **prim,
            "B_standard_slice": b_std, "criterion": prereg["primary"]["success"], "met": met,
            "A_prime_wins": a_wins,
            "headline": ("a careful Finnish rule beats the learned reader on these phrasings" if a_wins else
                         "the learned reader (B) beats the frozen Finnish rule (A') on held-out phrasings, as preregistered" if met else
                         "the preregistered success criterion for B is not met"),
        }
    # cascade
    if all(s in preds_by["val"] for s in ("nemotron",)):
        val_b, _ = predictions("val", rows_by["val"], "batch")
        doc["cascade"] = cascade(rows_by["val"], val_b, rows_by["test"], preds_by["test"], srows, preds_by["stress"])
    save_json(RESULTS, doc)
    RESULTS_MD.write_text(render_md(doc), encoding="utf-8")
    log("score", "scribe/.venv/bin/python scribe/v4/eval8.py score",
        inputs={"stress": str(STRESS.relative_to(ROOT)), "sha256": STRESS_SHA256, "preregistration_sha256": PREREG_SHA256},
        outputs={"json": str(RESULTS.relative_to(ROOT)), "md": str(RESULTS_MD.relative_to(ROOT))},
        metrics={"exact": {s: {k: v["exact_match"] for k, v in d["systems"].items()} for s, d in doc["sets"].items()},
                 "primary": doc.get("primary_result"), "cascade_chosen": (doc.get("cascade") or {}).get("chosen")})
    print(json.dumps({s: {k: v["exact_match"]["k"] for k, v in d["systems"].items()} for s, d in doc["sets"].items()}))
    print(json.dumps(doc.get("primary_result"), indent=1))
    return 0


# ---- RESULTS.md (every number is read from the results dict) --------------------------------------------------------


def pc(x):
    return "n/a" if x is None or x.get("value") is None else f"{x['k']}/{x['n']} ({100 * x['value']:.1f}%, {100 * x['ci95'][0]:.1f}-{100 * x['ci95'][1]:.1f})"


def kn(x):
    return "n/a" if x is None else f"{x['k']}/{x['n']}"


def render_md(doc):
    from render8 import render

    return render(doc)


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    sub.add_parser("score")
    a = p.parse_args(argv)
    if a.cmd == "verify":
        v = verify()
        log("verify", "scribe/.venv/bin/python scribe/v4/eval8.py verify", metrics=v, status="ok" if v["all_ok"] else "failed")
        print(json.dumps(v, indent=1))
        return 0 if v["all_ok"] else 1
    return cmd_score(a)


if __name__ == "__main__":
    sys.exit(main())
