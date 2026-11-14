#!/usr/bin/env python3
"""Select, precompute and compare the 20 SYNTHETIC demo notes of the offline scribe demo (NVIDIA_OPTIONS.md step 7).

Run with scribe/.venv/bin/python (it needs pyarrow to read the validation split). The model runs in the persistent
worker (serve/demo/worker.py, serve/.venv), which this script starts and talks to over the same JSON-lines protocol as
web/serve.mjs, so every number here goes through the process the demo uses.

  select       write data/scribe/demo/demo-notes.json: 20 notes from the VALIDATION split (never test), chosen by a
               fixed rule (strata x sha256 order) that never looks at a model output. 17 are verbatim; 3 are rewritten
               by code so the demo shows phrases the synthetic notes never use ("kolme viikkoa sitten", a digit
               spelled out as a Finnish number word, "eilen"). The 20 validation notes used to choose the CPU decoding
               settings (fp32 merged vs unmerged vs bf16; first 20 of the validation order) are excluded.
  run          run the worker on the 20 demo notes and on the 3 unrewritten source notes; write the fallback outputs
               data/scribe/demo/demo-outputs.json and the comparison with the stored CUDA outputs
               data/scribe/demo/cpu-vs-cuda.json.
  compare-val  run the worker on all 310 validation notes; write data/scribe/demo/cpu-vs-cuda-val310.json.
  http-timing  start node web/serve.mjs (SAMA_SCRIBE_PRELOAD=1) and POST every demo note to /api/scribe; write
               data/scribe/demo/http-timing.json.

Stored CUDA outputs: data/scribe/v3/student/C-270m-all-v2data/val-records.json (A100, bfloat16, batch 16, greedy).
Every step appends one line to runs/laneC-step7.jsonl. No network, no hosted endpoint, no cost.
A person confirms every event the demo proposes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import socket
import statistics
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "data" / "scribe" / "demo"
NOTES = OUT / "demo-notes.json"
OUTPUTS = OUT / "demo-outputs.json"
COMPARE = OUT / "cpu-vs-cuda.json"
COMPARE_VAL = OUT / "cpu-vs-cuda-val310.json"
RUNLOG = ROOT / "runs" / "laneC-step7.jsonl"
CUDA_RECORDS = ROOT / "data" / "scribe" / "v3" / "student" / "C-270m-all-v2data" / "val-records.json"
WORKER = HERE / "worker.py"
WORKER_PYTHON = ROOT / "serve" / ".venv" / "bin" / "python"
SEED = "sama-demo-v1"
PROBE_COUNT = 20  # first validation notes, used to choose CPU float32 + merged LoRA; excluded from the demo
NUMBER_WORDS = {2: "kaksi", 3: "kolme", 4: "neljä", 5: "viisi", 6: "kuusi"}  # lexicon.py words used for rewrites
STRATA = (  # (writer, kind, has a digit relative phrase, count): 17 verbatim notes
    ("nemotron", "standard", True, 6),
    ("nemotron", "standard", False, 5),
    ("haiku", "standard", True, 2),
    ("haiku", "standard", False, 2),
    ("haiku", "no_event", None, 1),
    ("haiku", "careful", None, 1),
)

sys.path.insert(0, str(HERE))
import engine  # noqa: E402  (standard library half only; torch stays in the worker)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(path):
    return str(pathlib.Path(path).resolve().relative_to(ROOT))


def log(step, command, inputs=None, outputs=None, metrics=None, status="ok", **extra):
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(ts=now(), step=step, host=socket.gethostname(), command=command, inputs=inputs or [], outputs=outputs or [],
               metrics=metrics or {}, cost_usd=0.0, status=status, **extra)
    with RUNLOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def wilson(k, n, z=1.959963984540054):
    if not n:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / den
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k, n):
    return dict(k=k, n=n, value=round(k / n, 4) if n else None, wilson95=wilson(k, n))


def key(note_id):
    return hashlib.sha256(f"{SEED}:{note_id}".encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Validation rows
# --------------------------------------------------------------------------- #


def validation_rows():
    """The 310 validation rows in the order of the stored CUDA records (val_nemotron, then val_haiku)."""
    sys.path.insert(0, str(ROOT / "scribe" / "v2"))
    import _paths  # noqa: F401
    import data_iface

    rows, sources = [], {}
    for split in ("val_nemotron", "val_haiku"):
        part, source = data_iface.load_split(split)
        rows += part
        sources[split] = {"rows": len(part), "source": source}
    records = json.loads(CUDA_RECORDS.read_text(encoding="utf-8"))
    if [r["id"] for r in rows] != [r["id"] for r in records]:
        raise SystemExit("validation rows and stored CUDA records are not aligned by id")
    return rows, records, sources


def has_digit_relative(text, resolver):
    return bool(resolver.REL.search(text))


def latest_unique(row, fact):
    dates = sorted(e["date"] for e in row["events"])
    return dates and fact["date"] == dates[-1] and dates.count(fact["date"]) == 1


def rewrite(row, fact, new_phrase, new_date):
    """Copy of a row with one date phrase rewritten by code and its answer key moved to new_date (if given)."""
    text = row["note_text"].replace(fact["expression"], new_phrase, 1)
    events = [dict(e) for e in row["events"]]
    if new_date:
        for e in events:
            if e["type"] == fact["type"] and e["date"] == fact["date"]:
                e["date"] = new_date
                break
    answer = {"entry_route": row["entry_route"], "events": sorted(events, key=lambda e: (e["date"], e["type"]))}
    return text, answer, {"event_type": fact["type"], "from_phrase": fact["expression"], "to_phrase": new_phrase,
                          "from_date": fact["date"], "to_date": new_date or fact["date"]}


def pick_rewrites(rows, excluded, resolver):
    """Three code-written notes. Candidates are standard notes whose relative phrase occurs once and belongs to an event."""
    order = sorted(range(len(rows)), key=lambda i: key(rows[i]["id"]))
    chosen, used = [], set()

    def first(test):
        for i in order:
            if i in excluded or i in used or rows[i]["kind"] != "standard":
                continue
            for fact in rows[i]["facts"] or []:
                if fact["form"] in ("days", "weeks") and rows[i]["note_text"].count(fact["expression"]) == 1 and test(rows[i], fact):
                    used.add(i)
                    return i, fact
        raise SystemExit("no candidate for a rewrite")

    note_date = lambda r: dt.date.fromisoformat(r["note_date"])  # noqa: E731
    # 1. "kolme viikkoa sitten": a weeks phrase with N > 3 on the latest event, moved to three weeks before the note.
    i, f = first(lambda r, f: f["form"] == "weeks" and int(f["expression"].split()[0]) > 3 and latest_unique(r, f))
    new = (note_date(rows[i]) - dt.timedelta(days=21)).isoformat()
    chosen.append(("number_word_kolme", i, f, "kolme viikkoa sitten", new))
    # 2. "eilen": a days phrase on the latest event, moved to the day before the note.
    i, f = first(lambda r, f: f["form"] == "days" and int(f["expression"].split()[0]) > 1 and latest_unique(r, f))
    new = (note_date(rows[i]) - dt.timedelta(days=1)).isoformat()
    chosen.append(("eilen", i, f, "eilen", new))
    # 3. a digit from 2 to 6 spelled out as a number word; the date stays.
    i, f = first(lambda r, f: int(f["expression"].split()[0]) in NUMBER_WORDS)
    n, unit = f["expression"].split()[:2]
    chosen.append(("number_word_digit", i, f, f"{NUMBER_WORDS[int(n)]} {unit} sitten", None))
    return chosen


def cmd_select(args):
    c = engine.client()
    resolver = c.load_date_resolver()
    rows, records, sources = validation_rows()
    excluded = set(range(PROBE_COUNT))
    notes = []
    for label, i, fact, phrase, new_date in pick_rewrites(rows, excluded, resolver):
        row = rows[i]
        text, answer, change = rewrite(row, fact, phrase, new_date)
        spans_a = resolver.relative_spans(text, row["note_date"], "A")
        spans_ap = resolver.relative_spans(text, row["note_date"], "A'")
        gate = {
            "phrase_present_once": text.count(phrase) == 1,
            "arm_A_prime_resolves_to_key": any(s["phrase"] == phrase and s["date"] == change["to_date"] for s in spans_ap),
            "arm_A_resolves": any(s["phrase"] == phrase for s in spans_a),
        }
        if not (gate["phrase_present_once"] and gate["arm_A_prime_resolves_to_key"]) or gate["arm_A_resolves"]:
            raise SystemExit(f"rewrite gate failed for {label}: {gate}")
        notes.append(dict(rewritten_by_code=True, rewrite_kind=label, rewrite=change, rewrite_gate=gate, row=row, index=i,
                          note_text=text, answer_key=answer, source_note_text=row["note_text"]))
    excluded |= {n["index"] for n in notes}
    order = sorted(range(len(rows)), key=lambda i: key(rows[i]["id"]))
    for writer, kind, relative, count in STRATA:
        got = 0
        for i in order:
            r = rows[i]
            if got == count:
                break
            if i in excluded or r["writer"] != writer or r["kind"] != kind:
                continue
            if relative is not None and has_digit_relative(r["note_text"], resolver) != relative:
                continue
            excluded.add(i)
            got += 1
            notes.append(dict(rewritten_by_code=False, rewrite_kind=None, rewrite=None, rewrite_gate=None, row=r, index=i,
                              note_text=r["note_text"], answer_key=json.loads(r["target_json"]), source_note_text=None,
                              stratum=f"{writer}/{kind}/{'relative' if relative else 'no-relative' if relative is False else 'any'}"))
        if got != count:
            raise SystemExit(f"stratum {writer}/{kind}/{relative}: {got} of {count}")
    out = []
    for n, note in enumerate(notes, 1):
        r, rec = note["row"], records[note["index"]]
        out.append({
            "demo_id": f"demo-{n:02d}",
            "synthetic": True,
            "source_split": "val",
            "source_id": r["id"],
            "source_index": note["index"],
            "writer": r["writer"],
            "kind": r["kind"],
            "style": r.get("style"),
            "stratum": note.get("stratum") or "code-rewritten",
            "date_forms": r.get("date_forms"),
            "note_date": r["note_date"],
            "note_text": note["note_text"],
            "answer_key": note["answer_key"],
            "rewritten_by_code": note["rewritten_by_code"],
            "rewrite_kind": note["rewrite_kind"],
            "rewrite": note["rewrite"],
            "rewrite_gate": note["rewrite_gate"],
            "source_note_text": note["source_note_text"],
            "cuda": {"raw": rec["raw"], "same_text": not note["rewritten_by_code"],
                     "file": rel(CUDA_RECORDS), "note": "A100 bfloat16, batch 16, greedy; for a rewritten note this is the "
                     "output for the unrewritten source text"},
        })
    doc = {
        "schema": "sama-scribe-demo-notes-v1",
        "synthetic": True,
        "label": "SYNTHETIC notes written by language models (Nemotron 3.5 Super VL, Claude Haiku) from sampled answer keys; "
                 "3 of them rewritten by code. Not patient data.",
        "generated_utc": now(),
        "selection_rule": {
            "split": "validation only (val_nemotron + val_haiku, 310 notes); no test note is used",
            "excluded": f"the first {PROBE_COUNT} validation notes, used to choose CPU float32 with merged LoRA weights",
            "order": f"sha256('{SEED}:' + note id), ascending, within each stratum",
            "rewrites": [
                "kolme viikkoa sitten: first standard note with a once-occurring 'N viikkoa sitten' (N > 3) on its unique "
                "latest event; the phrase becomes 'kolme viikkoa sitten' and that event's key date note_date - 21",
                "eilen: first standard note with a once-occurring 'N päivää sitten' (N > 1) on its unique latest event; the "
                "phrase becomes 'eilen' and that event's key date note_date - 1",
                "number word: first standard note with a once-occurring event phrase 'N päivää/viikkoa sitten', N in 2..6; "
                "the digit becomes the Finnish number word, the date stays",
                "gate (code): the new phrase occurs once, resolver arm A' places it on the key date, arm A (digits only) "
                "does not see it",
            ],
            "strata": [dict(writer=w, kind=k, digit_relative_phrase=r, count=c) for w, k, r, c in STRATA],
            "never_looked_at": "any model output (CPU or CUDA) when choosing notes",
        },
        "sources": sources,
        "probe_ids": [rows[i]["id"] for i in range(PROBE_COUNT)],
        "notes": out,
        "person_confirms": engine.PERSON_CONFIRMS,
    }
    save(NOTES, doc)
    log("select", "scribe/.venv/bin/python serve/demo/precompute.py select", inputs=[rel(CUDA_RECORDS), "scribe/v2/data_iface.load_split(val_*)"],
        outputs=[rel(NOTES)], metrics={"notes": len(out), "rewritten": sum(n["rewritten_by_code"] for n in out),
                                        "writers": {w: sum(n["writer"] == w for n in out) for w in ("nemotron", "haiku")}})
    print(json.dumps({n["demo_id"]: [n["stratum"], n["rewrite_kind"], n["source_id"][:10]] for n in out}, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Worker client
# --------------------------------------------------------------------------- #


class Worker:
    def __init__(self, python=WORKER_PYTHON, threads=None):
        env = dict(os.environ)
        if threads:
            env["SAMA_SCRIBE_THREADS"] = str(threads)
        started = time.monotonic()
        self.proc = subprocess.Popen([str(python), str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
        ready = json.loads(self.proc.stdout.readline())
        self.cold_start_seconds = round(time.monotonic() - started, 3)
        if ready.get("event") != "ready":
            raise SystemExit(f"worker did not start: {ready}")
        self.ready = ready
        self.n = 0

    def call(self, **req):
        self.n += 1
        req["id"] = f"r{self.n}"
        started = time.monotonic()
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        resp = json.loads(self.proc.stdout.readline())
        wall = time.monotonic() - started
        if resp.get("id") != req["id"] or not resp.get("ok"):
            raise SystemExit(f"worker error: {resp}")
        return resp["result"], round(wall, 3)

    def close(self):
        try:
            self.call(op="shutdown")
        finally:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)


def compare_one(cpu_result, cuda_raw, note_text, note_date, arm, answer_key):
    """Same note, same text: CPU worker output against the stored CUDA raw output, through the same post-processing."""
    cuda = engine.postprocess(cuda_raw, note_text, note_date, arm)
    cpu_pred, cuda_pred = cpu_result["resolved"]["prediction"], cuda["resolved"]["prediction"]
    return {
        "raw_identical": cpu_result["model"]["raw"] == cuda_raw,
        "model_parse_identical": cpu_result["model"]["parsed"] == cuda["model"]["parsed"],
        "resolved_identical": cpu_pred == cuda_pred,
        "cpu_exact": cpu_pred == answer_key,
        "cuda_exact": cuda_pred == answer_key,
        "cpu_raw": None if cpu_result["model"]["raw"] == cuda_raw else cpu_result["model"]["raw"],
        "cuda_raw": None if cpu_result["model"]["raw"] == cuda_raw else cuda_raw,
    }


def summarise(items):
    n = len(items)
    out = {}
    for k in ("raw_identical", "model_parse_identical", "resolved_identical", "cpu_exact", "cuda_exact"):
        out[k] = rate(sum(i[k] for i in items), n)
    return out


def timing_stats(values, seconds=True):
    values = sorted(values)
    if not values:
        return None
    out = {"n": len(values), "median": round(statistics.median(values), 3), "p90": round(values[min(len(values) - 1, int(0.9 * len(values)))], 3),
           "max": round(values[-1], 3), "mean": round(statistics.fmean(values), 3)}
    if seconds:
        out["under_3s"] = sum(v < 3.0 for v in values)
    return out


def cmd_run(args):
    doc = json.loads(NOTES.read_text(encoding="utf-8"))
    worker = Worker(threads=args.threads)
    arm = worker.ready["provenance"]["resolver"]["arm"]
    results, rows, same_text, timings = {}, [], [], []
    try:
        for note in doc["notes"]:
            result, wall = worker.call(op="extract", note_text=note["note_text"], note_date=note["note_date"],
                                       note_id=note["demo_id"], synthetic=True)
            result["answer_key"] = note["answer_key"]
            result["exact_match_with_answer_key"] = result["resolved"]["prediction"] == note["answer_key"]
            result["demo"] = {k: note[k] for k in ("demo_id", "source_split", "source_id", "writer", "kind", "stratum",
                                                   "rewritten_by_code", "rewrite_kind", "rewrite")}
            results[note["demo_id"]] = result
            timings.append({"demo_id": note["demo_id"], "worker_wall_seconds": wall, **result["timing"]})
            row = {"demo_id": note["demo_id"], "text": "demo note" if not note["rewritten_by_code"] else "rewritten (no CUDA output for this text)"}
            if not note["rewritten_by_code"]:
                row.update(compare_one(result, note["cuda"]["raw"], note["note_text"], note["note_date"], arm, note["answer_key"]))
                same_text.append(row)
            else:
                src = worker.call(op="extract", note_text=note["source_note_text"], note_date=note["note_date"],
                                  note_id=note["demo_id"] + "-source", synthetic=True)[0]
                srow = {"demo_id": note["demo_id"] + "-source", "text": "unrewritten source of a rewritten demo note"}
                srow.update(compare_one(src, note["cuda"]["raw"], note["source_note_text"], note["note_date"], arm,
                                        json.loads(_source_key(note))))
                same_text.append(srow)
                row["cpu_exact"] = result["exact_match_with_answer_key"]
            rows.append(row)
    finally:
        worker.close()
    demo_same = [r for r in same_text if not r["demo_id"].endswith("-source")]
    outputs = {
        "schema": "sama-scribe-demo-outputs-v1",
        "synthetic": True,
        "label": "Precomputed fallback for POST /api/scribe: the persistent CPU worker's output on the 20 SYNTHETIC demo "
                 "notes. A person confirms every event.",
        "generated_utc": now(),
        "provenance": worker.ready["provenance"],
        "results": results,
    }
    save(OUTPUTS, outputs)
    comparison = {
        "schema": "sama-scribe-demo-cpu-vs-cuda-v1",
        "synthetic": True,
        "generated_utc": now(),
        "what": "CPU worker (float32, merged LoRA, batch 1) against the stored CUDA outputs (A100, bfloat16, batch 16) of "
                "the same run C-270m-all-v2data on the same note text, both post-processed by the same code with "
                f"resolver arm {arm}.",
        "cuda_file": rel(CUDA_RECORDS),
        "cpu_provenance": worker.ready["provenance"],
        "cold_start_seconds": worker.cold_start_seconds,
        "demo_notes_with_cuda_output": {"n": len(demo_same), **summarise(demo_same)},
        "same_text_all_20_sources": {"n": len(same_text), **summarise(same_text),
                                     "note": "the 17 verbatim demo notes plus the 3 unrewritten source notes of the rewritten ones"},
        "rewritten_notes_cpu_exact": {r["demo_id"]: r["cpu_exact"] for r in rows if r["text"].startswith("rewritten")},
        "demo_exact_match_cpu": rate(sum(r["exact_match_with_answer_key"] for r in results.values()), len(results)),
        "timing_demo_notes": {
            "generate_seconds": timing_stats([t["generate_seconds"] for t in timings]),
            "worker_total_seconds": timing_stats([t["total_seconds"] for t in timings]),
            "client_wall_seconds": timing_stats([t["worker_wall_seconds"] for t in timings]),
            "load_average_1m": timing_stats([t["load_average_1m"] for t in timings], seconds=False),
            "cpu_count": os.cpu_count(),
        },
        "per_note": same_text,
        "per_demo_note_timing": timings,
        "success_rule": "NVIDIA_OPTIONS.md step 7: at least 18 of 20 demo notes match the stored CUDA outputs where they "
                        "exist, under 3 s per note",
    }
    save(COMPARE, comparison)
    m = {
        "demo_raw_identical": comparison["demo_notes_with_cuda_output"]["raw_identical"],
        "demo_resolved_identical": comparison["demo_notes_with_cuda_output"]["resolved_identical"],
        "same_text_20_raw_identical": comparison["same_text_all_20_sources"]["raw_identical"],
        "same_text_20_resolved_identical": comparison["same_text_all_20_sources"]["resolved_identical"],
        "demo_exact_match_cpu": comparison["demo_exact_match_cpu"],
        "worker_total_seconds": comparison["timing_demo_notes"]["worker_total_seconds"],
        "cold_start_seconds": worker.cold_start_seconds,
        "arm": arm,
    }
    log("precompute", "scribe/.venv/bin/python serve/demo/precompute.py run", inputs=[rel(NOTES), rel(CUDA_RECORDS), "serve/demo/worker.py"],
        outputs=[rel(OUTPUTS), rel(COMPARE)], metrics=m)
    print(json.dumps(m, indent=1))


def _source_key(note):
    """Answer key of the unrewritten source note (the rewrite moved one event's date)."""
    key_ = json.loads(json.dumps(note["answer_key"]))
    change = note["rewrite"]
    for e in key_["events"]:
        if e["type"] == change["event_type"] and e["date"] == change["to_date"]:
            e["date"] = change["from_date"]
            break
    key_["events"].sort(key=lambda e: (e["date"], e["type"]))
    return json.dumps(key_)


def cmd_http_timing(args):
    """End to end through the real route: node web/serve.mjs (SAMA_SCRIBE_PRELOAD=1) and POST /api/scribe per demo note."""
    import re
    import urllib.request

    doc = json.loads(NOTES.read_text(encoding="utf-8"))
    stored = json.loads(OUTPUTS.read_text(encoding="utf-8"))["results"]
    env = dict(os.environ, PORT="0", SAMA_SCRIBE_PRELOAD="1")
    if args.threads:
        env["SAMA_SCRIBE_THREADS"] = str(args.threads)
    started = time.monotonic()
    server = subprocess.Popen(["node", str(ROOT / "web" / "serve.mjs")], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, env=env, cwd=str(ROOT))
    try:
        port = int(re.search(r"127\.0\.0\.1:(\d+)", server.stdout.readline()).group(1))

        def post(body):
            t = time.monotonic()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/scribe", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())
            return out, round(time.monotonic() - t, 3)

        first, first_wall = post({"demo_id": doc["notes"][0]["demo_id"]})
        first_since_start = round(time.monotonic() - started, 3)
        rows = []
        for note in doc["notes"]:
            out, wall = post({"demo_id": note["demo_id"]})
            res = out["result"]
            rows.append({"demo_id": note["demo_id"], "served": out["served"], "http_wall_seconds": wall,
                         "server_seconds": out.get("server_seconds"), "worker_total_seconds": res["timing"]["total_seconds"],
                         "new_tokens": res["timing"]["new_tokens"], "load_average_1m": res["timing"].get("load_average_1m"),
                         "exact_match_with_answer_key": res.get("exact_match_with_answer_key"),
                         "same_as_precomputed": res["resolved"] == stored[note["demo_id"]]["resolved"],
                         "raw_same_as_precomputed": res["model"]["raw"] == stored[note["demo_id"]]["model"]["raw"]})
    finally:
        server.terminate()
        server.wait(timeout=30)
    walls = [r["http_wall_seconds"] for r in rows]
    result = {
        "schema": "sama-scribe-demo-http-timing-v1",
        "synthetic": True,
        "generated_utc": now(),
        "what": "POST /api/scribe for each of the 20 SYNTHETIC demo notes through node web/serve.mjs and its persistent CPU "
                "process, after one first request that waits for the preloaded model",
        "first_request": {"served": first["served"], "http_wall_seconds": first_wall, "seconds_since_server_start": first_since_start},
        "served_live": sum(r["served"] == "live" for r in rows),
        "http_wall_seconds": timing_stats(walls),
        "load_average_1m": timing_stats([r["load_average_1m"] for r in rows if r["load_average_1m"] is not None], seconds=False),
        "cpu_count": os.cpu_count(),
        "exact_match_with_answer_key": rate(sum(bool(r["exact_match_with_answer_key"]) for r in rows), len(rows)),
        "resolved_same_as_precomputed": rate(sum(r["same_as_precomputed"] for r in rows), len(rows)),
        "raw_same_as_precomputed": rate(sum(r["raw_same_as_precomputed"] for r in rows), len(rows)),
        "per_note": rows,
    }
    out_path = OUT / "http-timing.json"
    save(out_path, result)
    m = {k: result[k] for k in ("first_request", "served_live", "http_wall_seconds", "load_average_1m", "exact_match_with_answer_key",
                                "resolved_same_as_precomputed", "raw_same_as_precomputed")}
    log("http_timing", "scribe/.venv/bin/python serve/demo/precompute.py http-timing", inputs=["web/serve.mjs", "serve/demo/worker.py", rel(NOTES)],
        outputs=[rel(out_path)], metrics=m)
    print(json.dumps(m, indent=1))


def cmd_compare_val(args):
    rows, records, sources = validation_rows()
    worker = Worker(threads=args.threads)
    arm = worker.ready["provenance"]["resolver"]["arm"]
    items, totals, gens = [], [], []
    rel_pattern = engine.client().load_date_resolver().REL
    started = time.monotonic()
    try:
        for row, rec in zip(rows[: args.limit or None], records):
            result, wall = worker.call(op="extract", note_text=row["note_text"], note_date=row["note_date"], note_id=row["id"], synthetic=True)
            item = compare_one(result, rec["raw"], row["note_text"], row["note_date"], arm, json.loads(row["target_json"]))
            item.update(id=row["id"], writer=row["writer"], relative=bool(rel_pattern.search(row["note_text"])),
                        total_seconds=result["timing"]["total_seconds"])
            items.append(item)
            item["load_average_1m"] = result["timing"]["load_average_1m"]
            totals.append(result["timing"]["total_seconds"])
            gens.append(result["timing"]["generate_seconds"])
    finally:
        worker.close()
    wall = time.monotonic() - started
    by = {}
    for label, test in (("digit_relative_phrase", lambda i: i["relative"]), ("no_digit_relative_phrase", lambda i: not i["relative"]),
                        ("nemotron", lambda i: i["writer"] == "nemotron"), ("haiku", lambda i: i["writer"] == "haiku")):
        part = [i for i in items if test(i)]
        by[label] = {"n": len(part), **summarise(part)}
    a_only = sum(i["cpu_exact"] and not i["cuda_exact"] for i in items)
    b_only = sum(i["cuda_exact"] and not i["cpu_exact"] for i in items)
    doc = {
        "schema": "sama-scribe-demo-cpu-vs-cuda-val310-v1",
        "synthetic": True,
        "generated_utc": now(),
        "what": "All validation notes through the persistent CPU worker, compared with the stored CUDA outputs of the same "
                f"run on the same text; both post-processed by the same code with resolver arm {arm}. Validation is the "
                "split the run was selected on.",
        "sources": sources,
        "cuda_file": rel(CUDA_RECORDS),
        "cpu_provenance": worker.ready["provenance"],
        "n": len(items),
        **summarise(items),
        "cpu_only_exact": a_only,
        "cuda_only_exact": b_only,
        "by": by,
        "timing": {"worker_total_seconds": timing_stats(totals), "generate_seconds": timing_stats(gens), "wall_seconds": round(wall, 1),
                   "load_average_1m": timing_stats([i["load_average_1m"] for i in items], seconds=False),
                   "note": "other agent lanes ran MLX training and CPU studies on the same Mac during this run"},
        "mismatches": [{k: i[k] for k in ("id", "writer", "relative", "raw_identical", "resolved_identical", "cpu_exact", "cuda_exact", "cpu_raw", "cuda_raw")}
                       for i in items if not i["raw_identical"]],
        "outcomes": {"ids": [i["id"] for i in items], "raw_identical": [i["raw_identical"] for i in items],
                     "resolved_identical": [i["resolved_identical"] for i in items], "cpu_exact": [i["cpu_exact"] for i in items],
                     "cuda_exact": [i["cuda_exact"] for i in items]},
    }
    save(COMPARE_VAL, doc)
    m = {k: doc[k] for k in ("n", "raw_identical", "resolved_identical", "cpu_exact", "cuda_exact", "cpu_only_exact", "cuda_only_exact")}
    m["worker_total_seconds"] = doc["timing"]["worker_total_seconds"]
    m["by_relative"] = {k: {"raw": v["raw_identical"]["k"], "resolved": v["resolved_identical"]["k"], "n": v["n"]} for k, v in by.items()}
    log("compare_val310", "scribe/.venv/bin/python serve/demo/precompute.py compare-val", inputs=[rel(CUDA_RECORDS), "serve/demo/worker.py"],
        outputs=[rel(COMPARE_VAL)], metrics=m)
    print(json.dumps(m, indent=1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    p = sub.add_parser("run")
    p.add_argument("--threads", type=int, default=None)
    p = sub.add_parser("compare-val")
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("http-timing")
    p.add_argument("--threads", type=int, default=None)
    args = parser.parse_args(argv)
    {"select": cmd_select, "run": cmd_run, "compare-val": cmd_compare_val, "http-timing": cmd_http_timing}[args.cmd](args)


if __name__ == "__main__":
    main()
