"""Derived figures quoted in TRAINING.md that no other script writes.

Reads only files already in the repository and writes data/scribe/v2/training-figures-v1.json.
Standard library plus pyarrow. Nothing is trained, sent or downloaded. All notes are SYNTHETIC;
nothing here is for clinical use.

    scribe/.venv/bin/python scribe/v2/training_figures.py

What it computes, each with the files it read:

- paired validation comparisons of the post-ablation students with the frozen version-2 selection
  and with each other (exact two-sided McNemar on note-level exact match, 310 validation notes);
- note-for-note agreement between the in-process test evaluation of the selected adapter and the
  vLLM smoke test on the same 100 held-out notes;
- epochs implied by the fixed 324 optimisation steps for each training set;
- GPU seconds recorded by each training run, and the gap between two recorded GPU jobs;
- the API spend that the ledgers record, and which spend no file records.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data/scribe/v2/training-figures-v1.json"
STUDENT = ROOT / "data/scribe/v3/student"
ABLATION = ROOT / "data/scribe/v2/ablation-v1.json"

RUNS = {  # run name -> result.json written on the GPU box by scribe/v2
    "A-270m-lora-r16 (reference)": STUDENT / "v2-selected/result.json",
    "S-1b-lora-r16": STUDENT / "S-1b-lora-r16/result.json",
    "V3-270m-nemotron": STUDENT / "V3-270m-nemotron/result.json",
    "V3-270m-all": STUDENT / "V3-270m-all/result.json",
    "C-270m-all-v2data": STUDENT / "C-270m-all-v2data/result.json",
}
ABLATION_RUN_FILES = {  # the two non-selected ablation arms, copied back from the GPU box
    "A-270m-full-finetune": ROOT / "data/scribe/v2/ablation-runs/A-270m-full-finetune-7d4b9047c4f5/result.json",
    "v1-recipe-270m": ROOT / "data/scribe/v2/ablation-runs/v1-recipe-270m-60677a6fc706/result.json",
}


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def holm(pvalues):
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted = [None] * len(pvalues)
    running = 0.0
    m = len(pvalues)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def load(path):
    return json.loads(pathlib.Path(path).read_text())


def rel(path):
    return str(pathlib.Path(path).resolve().relative_to(ROOT))


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def val_outcomes(path):
    m = load(path)["val"]
    m = m.get("metrics", m)
    return dict(zip(m["ids"], m["outcomes"]))


def writer_of_val():
    import pyarrow.parquet as pq

    t = pq.read_table(ROOT / "data/scribe/v2/dataset/val.parquet", columns=["id", "writer"])
    return dict(zip(t.column("id").to_pylist(), t.column("writer").to_pylist()))


def pair(a, b, ids):
    only_a = sum(1 for i in ids if a[i] and not b[i])
    only_b = sum(1 for i in ids if b[i] and not a[i])
    return {"n": len(ids), "only_first_correct": only_a, "only_second_correct": only_b,
            "first_exact": sum(1 for i in ids if a[i]) / len(ids),
            "second_exact": sum(1 for i in ids if b[i]) / len(ids),
            "exact_mcnemar_p": mcnemar_exact(only_a, only_b)}


def validation_pairs():
    outcomes = {name: val_outcomes(p) for name, p in RUNS.items()}
    ids = sorted(outcomes["A-270m-lora-r16 (reference)"])
    for name, o in outcomes.items():
        if sorted(o) != ids:
            raise SystemExit(f"{name}: not scored on the same validation notes as the reference")
    writer = writer_of_val()
    names = list(RUNS)
    out = {"n_validation_notes": len(ids), "writers": {}, "pairs": []}
    for w in sorted(set(writer[i] for i in ids)):
        out["writers"][w] = sum(1 for i in ids if writer[i] == w)
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            a, b = names[y], names[x]  # later run first, reference or earlier run second
            row = {"first": a, "second": b, "all": pair(outcomes[a], outcomes[b], ids)}
            for w in out["writers"]:
                wid = [i for i in ids if writer[i] == w]
                row[w] = pair(outcomes[a], outcomes[b], wid)
            out["pairs"].append(row)
    adjusted = holm([p["all"]["exact_mcnemar_p"] for p in out["pairs"]])
    for p, h in zip(out["pairs"], adjusted):
        p["all"]["holm_adjusted_p_over_all_pairs"] = h
    out["validation_exact_match"] = {
        name: {"k": sum(1 for v in o.values() if v), "n": len(o),
               "value": sum(1 for v in o.values() if v) / len(o),
               "wilson95": wilson(sum(1 for v in o.values() if v), len(o))}
        for name, o in outcomes.items()
    }
    out["note"] = ("exact McNemar p-values per pair, and a Holm adjustment over all pairs of the 'all' rows; these "
                   "validation comparisons were not pre-registered and are given to show which differences are within noise")
    return out


def serving_parity():
    ab = load(ABLATION)
    inproc = {}
    for split in ("test_nemotron", "test_haiku"):
        s = ab["test"]["systems"]["selected"]["splits"][split]
        inproc.update(zip(s["ids"], s["outcomes"]))
    notes = {}
    for line in (ROOT / "serve/smoke/heldout-v2-100.jsonl").read_text().splitlines():
        r = json.loads(line)
        notes[r["id"]] = r
    out = {"notes_file": "serve/smoke/heldout-v2-100.jsonl",
           "notes_sha256": sha256(ROOT / "serve/smoke/heldout-v2-100.jsonl"),
           "in_process_source": "data/scribe/v2/ablation-v1.json test.systems.selected (unconstrained greedy, Transformers)",
           "exact_rule": "served canonical answer equal to target_json (key order ignored)"}
    out["by_split"] = {}
    for r in notes.values():
        out["by_split"][r["split"]] = out["by_split"].get(r["split"], 0) + 1
    out["in_process_exact"] = sum(1 for i in notes if inproc[i])
    for mode, path in (("structured_outputs", "serve/smoke/smoke-guided-results.jsonl"),
                       ("plain", "serve/smoke/smoke-plain-results.jsonl")):
        table = {"both_exact": 0, "both_wrong": 0, "only_in_process_exact": 0, "only_served_exact": 0}
        served = 0
        for line in (ROOT / path).read_text().splitlines():
            r = json.loads(line)
            target = json.loads(notes[r["id"]]["target_json"])
            got = r.get("canonical")
            e = got is not None and json.dumps(got, sort_keys=True) == json.dumps(target, sort_keys=True)
            served += e
            a = bool(inproc[r["id"]])
            key = "both_exact" if a and e else "both_wrong" if not a and not e else (
                "only_in_process_exact" if a else "only_served_exact")
            table[key] += 1
        out[mode] = {"file": path, "served_exact": served, "agreement": table,
                     "same_verdict_on_every_note": table["only_in_process_exact"] == 0 and table["only_served_exact"] == 0}
        # Answer-level agreement, per split, from serve/smoke/tools/compare_offline.py (review finding 9).
        import subprocess
        import sys
        offline = "data/scribe/v2/ablation-runs/evaluations/A-270m-lora-r16--test_nemotron+test_haiku--off.json"
        cmp_out = subprocess.run([sys.executable, str(ROOT / "serve/smoke/tools/compare_offline.py"),
                                  str(ROOT / "serve/smoke/heldout-v2-100.jsonl"), str(ROOT / path), str(ROOT / offline), mode],
                                 capture_output=True, text=True, check=True).stdout
        cmp = json.loads(cmp_out)
        smoke = load(ROOT / path.replace("-results.jsonl", ".json"))
        out[mode]["compare_offline"] = {
            "command": f"python serve/smoke/tools/compare_offline.py serve/smoke/heldout-v2-100.jsonl {path} {offline} {mode}",
            "same_prediction": cmp["pooled"]["same_prediction"], "same_raw_text": cmp["pooled"]["same_raw_text"],
            "n": cmp["pooled"]["n"], "agreement_same_outcome": cmp["agreement_same_outcome"],
            "by_split": {sp: {k: v[k] for k in ("n", "same_prediction", "served_exact", "offline_exact",
                                                 "served_invalid", "offline_invalid")} for sp, v in cmp["by_split"].items()},
            "offline_max_new_tokens": sorted({d["max_new_tokens"] for d in cmp["offline_decoding"].values()}),
            "served_max_tokens": smoke["settings"]["max_tokens"],
        }
    return out


def epochs():
    out = {}
    for name, p in RUNS.items():
        r = load(p)
        rows = sum(v["rows"] for v in r["data"]["train"].values())
        steps, batch = r["config"]["max_steps"], r["config"]["batch_size"] * r["config"]["grad_accum"]
        out[name] = {"train_rows": rows, "steps": steps, "effective_batch": batch,
                     "examples_drawn": steps * batch, "epochs": steps * batch / rows}
    return out


def gpu_seconds():
    ab = load(ABLATION)
    runs = {}
    for name, r in ab["runs"].items():
        runs[f"ablation {name}"] = {"train_seconds": r["train"]["train_seconds"], "total_seconds": r["seconds"]["total"],
                                    "peak_gpu_memory_gib": r["train"]["peak_gpu_memory_bytes"] / 2 ** 30,
                                    "source": "data/scribe/v2/ablation-v1.json"}
    for name, p in RUNS.items():
        if name.startswith("A-270m-lora-r16"):
            continue  # the same run as the ablation's A-270m-lora-r16
        r = load(p)
        runs[f"post-ablation {name}"] = {"train_seconds": r["train"]["train_seconds"], "total_seconds": r["seconds"]["total"],
                                         "peak_gpu_memory_gib": r["train"]["peak_gpu_memory_bytes"] / 2 ** 30,
                                         "source": rel(p)}
    out = {"runs": runs,
           "sum_train_seconds": sum(v["train_seconds"] for v in runs.values()),
           "sum_total_seconds": sum(v["total_seconds"] for v in runs.values()),
           "not_included": ["test evaluations (logged in gpu-logs/ as start and exit times only)",
                            "three Gemma 3 4B attempts that produced no result (gpu-logs/s4b*.log, queue3.log)",
                            "the vLLM smoke test (serve/smoke/)", "the Evo 2 genomics scoring on the same machine"],
           "ablation_budget": {"minutes": ab["budget"]["minutes"], "elapsed_seconds": ab["budget"]["elapsed_seconds"],
                               "started_utc": ab["started_utc"], "finished_utc": ab["finished_utc"]}}
    plan = {p["item"]: p for p in ab["planning"]}
    one_b = load(RUNS["S-1b-lora-r16"])
    out["planner_estimate_vs_measured_1b"] = {
        "planned_estimate_seconds": plan["A-1b-lora-r16"]["estimate_seconds"],
        "estimate_basis": plan["A-1b-lora-r16"]["estimate_basis"],
        "reserve_seconds_if_selected": plan["A-1b-lora-r16"]["reserve_seconds"],
        "seconds_left_after_reserve": plan["A-1b-lora-r16"]["seconds_left_after_reserve"],
        "measured_train_seconds": one_b["train"]["train_seconds"],
        "measured_total_seconds": one_b["seconds"]["total"],
        "measured_source": rel(RUNS["S-1b-lora-r16"]),
    }
    # GPU idle gap: the Evo 2 scoring stopped by itself, the next recorded GPU step is the v2 set-up
    evo = load(ROOT / "data/genomics/brca1-evo2-v1.json")
    evo_end = None
    for key in ("gpu_host", "run", "scoring"):
        blob = json.dumps(evo.get(key, {}))
        if "2026-11-14T17:27:31" in blob:
            evo_end = "2026-11-14T17:27:31Z"
    if evo_end is None and "2026-11-14T17:27:31" in json.dumps(evo):
        evo_end = "2026-11-14T17:27:31Z"
    first_v2 = json.loads((ROOT / "data/scribe/v2/gpu-runs/v2-ablation.jsonl").read_text().splitlines()[0])
    out["gap_between_recorded_gpu_jobs"] = {
        "previous_job_end_utc": evo_end,
        "previous_job_source": "data/genomics/brca1-evo2-v1.json (Evo 2 scoring stopped by itself at its time budget)",
        "next_job_start_utc": first_v2["ts"],
        "next_job_source": "data/scribe/v2/gpu-runs/v2-ablation.jsonl, first line (" + first_v2["step"] + ")",
        "minutes": None if evo_end is None else (utc(first_v2["ts"]) - utc(evo_end)).total_seconds() / 60,
        "note": "no run log in runs/ or data/ records a GPU step on the machine between these two times; "
                "the cause is not recorded in the repository",
    }
    return out


def machine_cost():
    line = None
    for raw in (ROOT / "runs/v2-ops.jsonl").read_text().splitlines():
        r = json.loads(raw)
        if r.get("step") == "verda_readonly_shape_check":
            line = r
    listed = line["outputs"]["machine_listed"]
    price = line["metrics"]["listed_machine_price_per_hour_usd"]
    created = listed["created_at"]
    deleted = "2026-11-14T19:27:00Z"  # minute precision: data/scribe/v3/student/RUNS.md, written by the coordinator
    hours = (utc(deleted) - utc(created)).total_seconds() / 3600
    return {
        "machine": listed["hostname"], "instance_type": listed["instance_type"], "spot": listed["is_spot"],
        "price_per_hour_usd_listed": price, "price_source": "runs/v2-ops.jsonl step verda_readonly_shape_check",
        "created_utc": created, "created_source": "runs/v2-ops.jsonl step verda_readonly_shape_check",
        "deleted_utc_minute_precision": deleted, "deleted_source": "data/scribe/v3/student/RUNS.md (no JSON record of the delete)",
        "hours": hours, "list_price_times_hours_usd": price * hours,
        "limit": "list price times wall time; the Verda invoice was not read, and the price may exclude or include the OS volume",
    }


def api_spend():
    v1 = load(ROOT / "data/scribe/dataset-stats.json")
    v2_ledger = None
    control = 0.0
    for raw in (ROOT / "runs/v2-data.jsonl").read_text().splitlines():
        r = json.loads(raw)
        m = r.get("metrics") or {}
        if r.get("step") == "verify_notes" and "ledger_cost_usd" in m:
            v2_ledger = m["ledger_cost_usd"]
        if r.get("step") == "no_event_gate_positive_control":
            control += r.get("cost_usd") or 0.0
    v3 = load(ROOT / "data/scribe/v3/judges/usage-typesafe.json")
    oa = load(ROOT / "data/scribe/v3/judges/usage-openai.json")
    haiku_v1 = None
    for raw in (ROOT / "runs/train.jsonl").read_text().splitlines():
        r = json.loads(raw)
        if r.get("step") == "haiku_write_notes":
            haiku_v1 = r["cost_usd"]
    haiku_pilot = None
    for raw in (ROOT / "runs/v2-data.jsonl").read_text().splitlines():
        r = json.loads(raw)
        if r.get("step") == "haiku_pilot_cost":
            haiku_pilot = r["cost_usd"]
    typesafe = {"v1_dataset": v1["typesafe_cost_usd"], "v2_dataset": v2_ledger + control, "v3_judges_and_gate": v3["cost_usd"]}
    return {
        "typesafe_usd": typesafe,
        "typesafe_usd_total": sum(typesafe.values()),
        "typesafe_sources": ["data/scribe/dataset-stats.json typesafe_cost_usd",
                             "runs/v2-data.jsonl last verify_notes ledger_cost_usd + no_event_gate_positive_control",
                             "data/scribe/v3/judges/usage-typesafe.json cost_usd"],
        "openai_decisions": {"tokens": oa["tokens"], "requests": oa["requests"],
                             "usd_at_list_rate_0.10_per_million_input": oa["tokens"] * 0.10 / 1e6,
                             "source": "data/scribe/v3/judges/usage-openai.json; rate from scribe/TEACHING.md section 8"},
        "haiku_recorded_usd": {"v1_independent_test_notes": haiku_v1, "v2_writer_pilot_reported": haiku_pilot},
        "not_recorded": ["Nemotron teacher on Verda: 4,500 requests (round 1) and 4,042 (round 2), no price read",
                         "Haiku writing of the 1,198 version-2 notes beyond the pilot",
                         "Haiku audit of round 2 (data/scribe/v3/audit)",
                         "the first GPU machine az-equity-gpu-20261114 (price and lifetime not in the repository)"],
        "teacher_requests": {"round_1": load(ROOT / "data/scribe/usage.json")["teacher_requests"],
                             "round_2": load(ROOT / "data/scribe/v3/teacher/ledger.json")["teacher_requests"]},
    }


def main():
    out = {
        "schema": "scribe-training-figures-v1",
        "synthetic": True,
        "not_for_clinical_use": True,
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scribe/v2/training_figures.py",
        "inputs_sha256": {rel(p): sha256(p) for p in [ABLATION, *RUNS.values(), *ABLATION_RUN_FILES.values()]},
        "validation_pairs": validation_pairs(),
        "serving_parity": serving_parity(),
        "epochs": epochs(),
        "gpu": gpu_seconds(),
        "machine_cost": machine_cost(),
        "api_spend": api_spend(),
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {rel(OUT)}")


if __name__ == "__main__":
    main()
