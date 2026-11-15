"""Scores the reader cache and writes the per-note outputs and data/scribe/nemotron/reader-v1.json.

Every number here is computed from the cached answers and the SYNTHETIC answer keys in
data/scribe/v2/dataset. Exact match means the whole canonical answer (entry route and every event's
type, date and precision) equals the key, as in scribe/metrics.py summary().
"""

from __future__ import annotations

import collections
import hashlib
import json
import statistics

import common as C
import reader as R
from metrics import mcnemar, wilson
from protocol import classify

LADDER = (("v0", "v1"), ("v1", "v2"), ("v2", "v2g"), ("v2g", "v3"), ("v0", "v3"), ("v1", "v1rep"))
WHAT = {
    ("v0", "v1"): "expression format: Nemotron copies the date, code computes it",
    ("v1", "v2"): "local schema validation + one repair retry",
    ("v2", "v2g"): "grounding check (every date must be printed in the note) in the validator",
    ("v2g", "v3"): "enable_thinking on",
    ("v0", "v3"): "all changes together",
    ("v1", "v1rep"): "nothing (identical rerun: the noise floor at temperature 0)",
}
FORMS = ("numeric", "long", "no_year", "month", "days", "weeks")
WRITERS = {"nemotron-3.5-super-vl": "nemotron_written", "claude-haiku-5-5": "haiku_written"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rate(k, n):
    w = wilson(k, n)
    return {"k": k, "n": n, "value": round(w["value"], 4) if w["value"] is not None else None, "ci95": [round(x, 4) if x is not None else None for x in w["ci95"]]}


def target(row):
    return json.loads(row["target_json"])


def load_outputs(version, split):
    rows = R.load(split)
    out = []
    missing = 0
    for row in rows:
        p = R.cache_path(version, split, row["id"])
        if not p.exists():
            missing += 1
            continue
        o = json.loads(p.read_text())
        o["row"] = row
        o["exact"] = o["prediction"] == target(row)
        out.append(o)
    return out, missing


def tokens(o):
    t = collections.Counter()
    for a in o["attempts"]:
        u = a.get("usage") or {}
        t["prompt"] += int(u.get("prompt_tokens") or 0)
        t["completion"] += int(u.get("completion_tokens") or 0)
        t["reasoning"] += int(((u.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)
    return t


def score(outs, missing=0):
    n = len(outs)
    k = sum(o["exact"] for o in outs)
    by_writer = collections.defaultdict(list)
    by_kind = collections.defaultdict(list)
    by_split = collections.defaultdict(list)
    note_form = collections.defaultdict(list)
    event_form = collections.defaultdict(lambda: [0, 0])
    rel = collections.defaultdict(list)
    errors = collections.Counter()
    notes_with_error = collections.Counter()
    tok = collections.Counter()
    for o in outs:
        row = o["row"]
        by_writer[WRITERS.get(row["writer"], row["writer"])].append(o["exact"])
        by_kind[row["kind"]].append(o["exact"])
        by_split[row["split"]].append(o["exact"])
        forms = set(row["date_forms"] or [])
        for f in forms:
            note_form[f].append(o["exact"])
        rel["has_relative_date" if forms & {"days", "weeks"} else "no_relative_date"].append(o["exact"])
        got = collections.Counter((e["type"], e["date"], e["precision"]) for e in (o["prediction"] or {"events": []})["events"])
        for fact in row["facts"] or []:
            key = (fact["type"], fact["date"], fact["precision"])
            event_form[fact["form"]][1] += 1
            if got[key] > 0:
                got[key] -= 1
                event_form[fact["form"]][0] += 1
        if o["prediction"] is None:
            errors["parse_failure"] += 1
            notes_with_error["parse_failure"] += 1
        elif not o["exact"]:
            classes = [d["class"] for d in classify(target(row), o["prediction"])]
            errors.update(classes)
            notes_with_error.update(set(classes))
        tok.update(tokens(o))
    lat = sorted(o["latency"] for o in outs)
    first_parse_fail = sum(not o["attempts"][0]["parsed"] for o in outs)
    repaired = [o for o in outs if o["calls"] > 1]
    return dict(
        notes=n,
        missing_from_cache=missing,
        exact_match=rate(k, n),
        parse_failures_final=sum(o["prediction"] is None for o in outs),
        parse_failures_first_answer=first_parse_fail,
        repair=dict(
            attempted=len(repaired),
            repair_answer_kept=sum(o["selected_attempt"] == 1 for o in repaired),
            exact_after_repair=sum(o["exact"] for o in repaired),
            still_flagged_by_validator=sum(o["flagged"] for o in outs),
            flagged_and_wrong=sum(o["flagged"] and not o["exact"] for o in outs),
            wrong_but_not_flagged=sum((not o["flagged"]) and not o["exact"] for o in outs),
        ),
        by_writer={w: rate(sum(v), len(v)) for w, v in sorted(by_writer.items())},
        by_kind={w: rate(sum(v), len(v)) for w, v in sorted(by_kind.items())},
        by_split={w: rate(sum(v), len(v)) for w, v in sorted(by_split.items())},
        relative_date_slice={w: rate(sum(v), len(v)) for w, v in sorted(rel.items())},
        by_date_form_notes={f: rate(sum(note_form[f]), len(note_form[f])) for f in FORMS if note_form[f]},
        by_date_form_events={f: rate(*event_form[f]) for f in FORMS if event_form[f][1]},
        error_events_by_class=dict(errors.most_common()),
        notes_with_error_class=dict(notes_with_error.most_common()),
        calls_per_note=round(sum(o["calls"] for o in outs) / n, 3) if n else None,
        latency_seconds=dict(
            mean=round(statistics.fmean(lat), 2) if lat else None,
            p50=round(lat[len(lat) // 2], 2) if lat else None,
            p95=round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 2) if lat else None,
            note="sum of the call times for one note at this lane's concurrency of 8 on the shared endpoint",
        ),
        tokens_total=dict(tok),
        tokens_per_note={k2: round(v / n, 1) for k2, v in tok.items()} if n else {},
    )


def paired(a_outs, b_outs, subset=None):
    a = {o["id"]: o["exact"] for o in a_outs}
    b = {o["id"]: o["exact"] for o in b_outs}
    ids = sorted(set(a) & set(b))
    if subset:
        ids = [i for i in ids if subset(i)]
    only_a = sum(a[i] and not b[i] for i in ids)
    only_b = sum(b[i] and not a[i] for i in ids)
    return dict(
        notes=len(ids),
        before=sum(a[i] for i in ids),
        after=sum(b[i] for i in ids),
        gained=only_b,
        lost=only_a,
        change_points=round(100 * (sum(b[i] for i in ids) - sum(a[i] for i in ids)) / len(ids), 1) if ids else None,
        mcnemar_exact_p=float(f"{mcnemar(only_a, only_b):.3g}"),  # 3 significant digits: tiny p stays > 0
    )


def write_notes(outs, split, version):
    path = C.OUT / f"{split}-{version}.jsonl"
    with path.open("w") as f:
        for o in outs:
            row = o["row"]
            f.write(
                json.dumps(
                    dict(
                        id=o["id"],
                        split=row["split"],
                        writer=row["writer"],
                        kind=row["kind"],
                        date_forms=row["date_forms"],
                        note_date=row["note_date"],
                        version=version,
                        prediction=o["prediction"],
                        raw=o["raw"],
                        latency=o["latency"],
                        calls=o["calls"],
                        selected_attempt=o["selected_attempt"],
                        flagged_by_validator=o["flagged"],
                        exact=o["exact"],
                        parse_failure=o["prediction"] is None,
                        synthetic=True,
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
    return str(path.relative_to(C.ROOT))


def pval(p):
    return "<1e-6" if p < 1e-6 else f"={p:.2g}"


def sig(p):
    return "" if p < 0.05 else ", not significant at 0.05"


def pct(r):
    return f"{r['k']}/{r['n']} ({100 * r['value']:.1f}%, Wilson {100 * r['ci95'][0]:.1f}-{100 * r['ci95'][1]:.1f})"


def main(selected=None, command=""):
    val = {}
    files = []
    for v in R.VERSIONS:
        outs, missing = load_outputs(v, "val")
        if outs:
            val[v] = (outs, missing)
            files.append(write_notes(outs, "val", v))
    table = dict(
        title="Nemotron 3.5 Super VL as escalation reader: how we improved its outputs (step 4)",
        synthetic="All notes are SYNTHETIC. Not for clinical use. A person confirms every extracted event: an answer is pre-filled for one-click confirmation or flagged as needing editing.",
        generated_utc=C.now().isoformat(timespec="seconds"),
        model=C.MODEL,
        endpoint="event endpoint (VERDA_INFERENCE_BASE_URL), OpenAI-compatible chat/completions, temperature 0",
        code="scribe/nemotron/reader.py, scribe/nemotron/report.py",
        dataset={name: dict(path=f"data/scribe/v2/dataset/{name}.parquet", sha256=sha256(R.DATASET / f"{name}.parquet")) for name in ("val", "test_nemotron", "test_haiku")},
        prompts={fmt: hashlib.sha256(R.system_prompt(fmt).encode()).hexdigest() for fmt in ("absolute", "expression")},
        versions={v: dict(R.CONFIG[v], what=d) for v, d in (
            ("v0", "absolute dates: Nemotron does the date arithmetic"),
            ("v1", "expression format: Nemotron copies each date as printed; scribe/v2/data_tools.resolve_expression computes it"),
            ("v1rep", "v1 rerun unchanged (noise floor); not a selection candidate"),
            ("v2", "v1 + local validation (JSON, resolve_expression, serve/schema.json $defs/absolute, no event after the note date, no duplicate) + one repair retry"),
            ("v2g", "v2 + grounding check: every returned date must match a date string printed in the note"),
            ("v3", "v2g with enable_thinking on"),
        )},
        selection_rule="Recorded in runs/laneB-step4.jsonl before the full validation run: highest validation exact match among v0, v1, v2, v2g, v3; on an exact tie, fewer mean calls per note. The selected version read the 700 test notes once.",
        validation={v: score(o, m) for v, (o, m) in val.items()},
        validation_ladder={},
        validation_ladder_haiku_written={},
        validation_ladder_relative_dates={},
    )
    for a, b in LADDER:
        if a in val and b in val:
            key = f"{a}->{b}"
            rows = {o["id"]: o["row"] for o in val[a][0]}
            table["validation_ladder"][key] = dict(change=WHAT[(a, b)], **paired(val[a][0], val[b][0]))
            table["validation_ladder_haiku_written"][key] = paired(val[a][0], val[b][0], lambda i: rows[i]["writer"] == "claude-haiku-5-5")
            table["validation_ladder_relative_dates"][key] = paired(val[a][0], val[b][0], lambda i: bool(set(rows[i]["date_forms"] or []) & {"days", "weeks"}))
    candidates = [v for v in ("v0", "v1", "v2", "v2g", "v3") if v in val]
    best = max(candidates, key=lambda v: (table["validation"][v]["exact_match"]["k"], not R.CONFIG[v]["thinking"], -table["validation"][v]["calls_per_note"]))
    table["selected_by_rule"] = best
    if selected and selected != best:
        table["selected_note"] = f"--selected {selected} differs from the rule's choice {best}"
    sel = selected or best
    test_outs, test_missing = load_outputs(sel, "test")
    if test_outs:
        files.append(write_notes(test_outs, "test", sel))
        table["test"] = dict(version=sel, run_once=True, **score(test_outs, test_missing))
    # plain statement, every number from the tables above
    V = table["validation"]
    L = table["validation_ladder"]
    lines = []
    if "v0" in V and "v1" in V:
        lines.append(
            f"Biggest gain: letting code do the date arithmetic. With absolute dates (v0) Nemotron got {pct(V['v0']['exact_match'])} validation notes exactly right; "
            f"copying the date and computing it in code (v1) gave {pct(V['v1']['exact_match'])}, {L['v0->v1']['change_points']:+.1f} points "
            f"({L['v0->v1']['gained']} notes fixed, {L['v0->v1']['lost']} made worse, McNemar p{pval(L['v0->v1']['mcnemar_exact_p'])}). "
            f"On notes with a relative date: {pct(V['v0']['relative_date_slice']['has_relative_date'])} -> {pct(V['v1']['relative_date_slice']['has_relative_date'])}."
        )
    if "v1->v1rep" in L:
        lines.append(f"Noise floor: rerunning v1 unchanged moved {L['v1->v1rep']['gained'] + L['v1->v1rep']['lost']} notes ({L['v1->v1rep']['gained']} up, {L['v1->v1rep']['lost']} down); a change smaller than this is not distinguishable from rerun noise.")
    for a, b in (("v1", "v2"), ("v2", "v2g"), ("v2g", "v3")):
        k = f"{a}->{b}"
        if k in L:
            lines.append(f"{b} ({WHAT[(a, b)]}): {pct(V[b]['exact_match'])}, {L[k]['change_points']:+.1f} points over {a} ({L[k]['gained']} fixed, {L[k]['lost']} worse, McNemar p{pval(L[k]['mcnemar_exact_p'])}{sig(L[k]['mcnemar_exact_p'])}); parse failures {V[a]['parse_failures_final']} -> {V[b]['parse_failures_final']}; "
                f"{V[b]['tokens_per_note'].get('completion', 0):.0f} output tokens and {V[b]['latency_seconds']['mean']:.2f} s per note (was {V[a]['tokens_per_note'].get('completion', 0):.0f} and {V[a]['latency_seconds']['mean']:.2f}).")
    if "test" in table:
        T = table["test"]
        hw = T["by_writer"].get("haiku_written")
        nw = T["by_writer"].get("nemotron_written")
        lines.append(
            f"Test, selected version {sel}, run once: {pct(T['exact_match'])} overall; Haiku-written notes (primary slice, a writer other than Nemotron) {pct(hw) if hw else 'n/a'}; "
            f"Nemotron-written notes {pct(nw) if nw else 'n/a'}; parse failures {T['parse_failures_final']}."
        )
    table["statement"] = lines
    table["caveats"] = [
        "SYNTHETIC notes only, written from six date forms by code-controlled specifications; real notes would contain other phrasings (spelled-out numbers, 'eilen', weekdays) that neither the expression format nor the grounding check covers yet.",
        "Nemotron wrote 250 of 310 validation and 500 of 700 test notes itself; its score on its own notes is optimistic. Haiku-written notes are the primary slice, and they are small (60 validation, 200 test).",
        "The validation set chose the version, so validation numbers are selection results; the test set was read once by the selected version only, so there is no test-set ladder.",
        "The grounding check (v2g) and the schema check use the same six date forms that generated the notes; they pass by construction on well-formed answers to this data.",
        "Temperature 0 on a batched server is not bit-deterministic; v1rep measures that noise.",
        "Exact match is strict: one wrong date, type or route makes the whole note wrong, which is the unit a person confirms.",
        "Route 1 price is UNVERIFIED (event endpoint); cost_usd is recorded as null, not zero.",
    ]
    ledger = C.Ledger()
    table["requests_ledger"] = ledger.requests
    table["per_note_outputs"] = files
    C.save(C.OUT / "reader-v1.json", table)
    C.log(
        "4_report",
        command=command,
        inputs={"cache": "data/scribe/nemotron/cache/", "dataset": "data/scribe/v2/dataset"},
        outputs=["data/scribe/nemotron/reader-v1.json", *files],
        metrics=dict(
            validation_exact={v: V[v]["exact_match"]["k"] for v in V},
            selected=sel,
            test_exact=table.get("test", {}).get("exact_match"),
            test_by_writer=table.get("test", {}).get("by_writer"),
            requests_ledger=ledger.requests,
        ),
        cost_usd=None,
    )
    print("\n".join(lines))
