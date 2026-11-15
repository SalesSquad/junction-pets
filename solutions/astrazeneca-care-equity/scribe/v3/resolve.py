"""Relative-date resolver: "Gemma reads, code counts". A declared, fixed rule; the rule itself is standard library only.

Ported from runs/diagnose/resolve_relative.py (arm A is that rule, unchanged). It uses only the note text, the note
date and the model's proposed events, never an answer key:
  1. find every relative phrase in the note and resolve it against the note date
     (arm A: digits only, "N päivää sitten" / "N viikkoa sitten";
      arm A': the same plus the Finnish lexicon in scribe/v3/lexicon.py: number words one to six, "viikko sitten",
      "päivä sitten", "eilen"; month, year and vague phrases are reported for a person and never get a date);
  2. a proposed event whose date is not written anywhere in the note in an absolute form
     (d.m.yyyy, d.m., d. <month>kuuta [yyyy], <month>kuussa yyyy) is "unsupported";
  3. unsupported events are matched one to one to the resolved relative dates by the smallest total absolute day
     difference (exhaustive over permutations; notes carry at most 4 to 5 of either) and take that date with DAY
     precision.
The resolver proposes; a person confirms every extracted event. It never marks anything as confirmed.
SYNTHETIC notes only were used to design and measure it.

Interface (the rule):
  written_dates(note_text, note_date) -> set[str]
  relative_spans(note_text, note_date, arm="A") -> list[dict]      resolvable phrases, in text order
  needs_person_spans(note_text, arm="A") -> list[dict]             phrases that get no date (arm A' only)
  relative_dates(note_text, note_date, arm="A") -> list[str]
  resolve_events(events, note_text, note_date, arm="A") -> (list[dict], list[dict])   input order kept
  repair(prediction, note_text, note_date, arm="A") -> dict | None  the diagnose rule, events sorted (date, type)
  resolve(prediction, note_text, note_date, arm="A") -> dict        repair plus changes, phrases for a person, arm

Command line (writes only data/scribe/v4/resolver/ and runs/laneA-step1.jsonl):
  scribe/.venv/bin/python scribe/v3/resolve.py freeze      record sha256 of resolve.py and lexicon.py, once
  scribe/.venv/bin/python scribe/v3/resolve.py reproduce   stored outputs of the 5 student runs, arms A and A'
"""

import datetime as dt
import hashlib
import importlib.util
import itertools
import json
import re
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_lexicon():
    spec = importlib.util.spec_from_file_location("scribe_v3_lexicon", HERE / "lexicon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LEX = _load_lexicon()

RULE = "scribe-v3-relative-resolver-v1"
ARMS = ("A", "A'")
MONTHS = ["tammi", "helmi", "maalis", "huhti", "touko", "kesä", "heinä", "elo", "syys", "loka", "marras", "joulu"]

# Arm A: exactly the patterns of runs/diagnose/resolve_relative.py.
REL = re.compile(r"(\d+)\s+(päivää|viikkoa)\s+sitten")
NUM = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})?")
LONG = re.compile(r"(\d{1,2})\.\s+(" + "|".join(MONTHS) + r")kuuta(?:\s+(\d{4}))?")
MON = re.compile(r"(" + "|".join(MONTHS) + r")kuussa\s+(\d{4})")


def _alt(words):
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


_I = re.IGNORECASE
_UNITS = {**LEX.UNIT_DAYS, **LEX.SINGULAR_UNIT_DAYS}
_AGO = re.escape(LEX.AGO)
# Arm A': lexicon patterns, tried in this order; a later span never overlaps an earlier one.
LEX_NUMBER = re.compile(rf"\b({_alt(LEX.NUMBER_WORDS)})\s+({_alt(_UNITS)})\s+{_AGO}\b", _I)
LEX_VAGUE = re.compile(rf"\b({_alt(LEX.VAGUE_QUANTIFIERS)})\s+({_alt(_UNITS)})\s+{_AGO}\b", _I)
LEX_TO_PERSON_UNIT = re.compile(rf"\b({_alt(LEX.TO_PERSON_UNITS)})\s+{_AGO}\b", _I)
LEX_TO_PERSON_PHRASE = re.compile(rf"\b({_alt(LEX.TO_PERSON_PHRASES)})\b", _I)
LEX_SINGULAR = re.compile(rf"\b({_alt(LEX.SINGULAR_UNIT_DAYS)})\s+{_AGO}\b", _I)
LEX_ADVERB = re.compile(rf"\b({_alt(LEX.ADVERB_DAYS)})\b", _I)


def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _check_arm(arm):
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")


def safe(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def written_dates(note_text, note_date):
    """ISO dates written in the note in an absolute form (the four absolute forms of scribe/sample.py render)."""
    note = _as_date(note_date)
    out = set()
    for m in NUM.finditer(note_text):
        x = safe(m.group(3) or note.year, m.group(2), m.group(1))
        if x:
            out.add(x.isoformat())
    for m in LONG.finditer(note_text):
        x = safe(m.group(3) or note.year, MONTHS.index(m.group(2)) + 1, m.group(1))
        if x:
            out.add(x.isoformat())
    for m in MON.finditer(note_text):
        out.add(dt.date(int(m.group(2)), MONTHS.index(m.group(1)) + 1, 1).isoformat())
    return out


def _overlaps(span, taken):
    return any(span[0] < b and a < span[1] for a, b in taken)


def _scan(note_text, arm):
    """(resolvable, to_person) spans. Arm A: digits only, in text order, as the diagnose rule."""
    _check_arm(arm)
    resolvable, to_person, taken = [], [], []
    for m in REL.finditer(note_text):
        days = int(m.group(1)) * (7 if m.group(2) == "viikkoa" else 1)
        resolvable.append(dict(start=m.start(), end=m.end(), phrase=m.group(0), days=days, source="digits"))
        taken.append((m.start(), m.end()))
    if arm == "A":
        return resolvable, to_person
    passes = (
        (LEX_NUMBER, lambda m: LEX.NUMBER_WORDS[m.group(1).lower()] * _UNITS[m.group(2).lower()]),
        (LEX_VAGUE, None),
        (LEX_TO_PERSON_UNIT, None),
        (LEX_TO_PERSON_PHRASE, None),
        (LEX_SINGULAR, lambda m: LEX.SINGULAR_UNIT_DAYS[m.group(1).lower()]),
        (LEX_ADVERB, lambda m: LEX.ADVERB_DAYS[m.group(1).lower()]),
    )
    for pattern, days_of in passes:
        for m in pattern.finditer(note_text):
            span = (m.start(), m.end())
            if _overlaps(span, taken):
                continue
            taken.append(span)
            item = dict(start=m.start(), end=m.end(), phrase=m.group(0))
            if days_of is None:
                to_person.append(dict(item, reason="no single exact day; a person sets the date"))
            else:
                resolvable.append(dict(item, days=days_of(m), source="lexicon"))
    resolvable.sort(key=lambda s: s["start"])
    to_person.sort(key=lambda s: s["start"])
    return resolvable, to_person


def relative_spans(note_text, note_date, arm="A"):
    """Resolvable relative phrases in text order, each with its resolved ISO date."""
    note = _as_date(note_date)
    spans, _ = _scan(note_text, arm)
    return [dict(s, date=(note - dt.timedelta(days=s["days"])).isoformat()) for s in spans]


def needs_person_spans(note_text, arm="A"):
    """Relative phrases that cannot be placed on one exact day (arm A' only): a person sets these dates."""
    return _scan(note_text, arm)[1]


def relative_dates(note_text, note_date, arm="A"):
    return [s["date"] for s in relative_spans(note_text, note_date, arm)]


def _iso_or_none(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def resolve_events(events, note_text, note_date, arm="A"):
    """Re-date unsupported events from the note's relative phrases. Returns (events in input order, changes).

    Events are copied, never modified in place. An event whose date is not an ISO date is left as it is (the schema
    check downstream rejects it). changes lists every event whose date or precision the rule changed.
    """
    written = written_dates(note_text, note_date)
    spans = relative_spans(note_text, note_date, arm)
    rel = [s["date"] for s in spans]
    events = [dict(e) for e in events]
    unsupported = [i for i, e in enumerate(events) if e.get("date") not in written and _iso_or_none(e.get("date"))]
    changes = []
    if unsupported and rel:
        k = min(len(unsupported), len(rel))
        best = None
        for evs in itertools.combinations(unsupported, k):
            for rs in itertools.permutations(range(len(rel)), k):
                cost = sum(abs((dt.date.fromisoformat(events[i]["date"]) - dt.date.fromisoformat(rel[j])).days) for i, j in zip(evs, rs))
                if best is None or cost < best[0]:
                    best = (cost, evs, rs)
        for i, j in zip(best[1], best[2]):
            before = (events[i]["date"], events[i].get("precision"))
            events[i]["date"] = rel[j]
            events[i]["precision"] = "DAY"
            if before != (rel[j], "DAY"):
                changes.append(dict(index=i, type=events[i].get("type"), from_date=before[0], from_precision=before[1],
                                    to_date=rel[j], to_precision="DAY", phrase=spans[j]["phrase"], source=spans[j]["source"]))
    return events, changes


def repair(prediction, note_text, note_date, arm="A"):
    """The diagnose rule: None stays None; events re-dated, then sorted by (date, type)."""
    if prediction is None:
        return None
    events, _ = resolve_events(prediction["events"], note_text, note_date, arm)
    return dict(entry_route=prediction["entry_route"], events=sorted(events, key=lambda e: (e["date"], e["type"])))


def resolve(prediction, note_text, note_date, arm="A"):
    """repair() plus what changed and which phrases a person must date. The result is a proposal for a person."""
    _check_arm(arm)
    out = dict(rule=RULE, arm=arm, lexicon=LEX.VERSION if arm == "A'" else None, prediction=None, changes=[],
               needs_person=[dict(phrase=s["phrase"], start=s["start"], end=s["end"], reason=s["reason"])
                             for s in needs_person_spans(note_text, arm)])
    if prediction is None:
        return out
    events, changes = resolve_events(prediction["events"], note_text, note_date, arm)
    out["prediction"] = dict(entry_route=prediction["entry_route"], events=sorted(events, key=lambda e: (e["date"], e["type"])))
    out["changes"] = changes
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Command line: freeze and reproduce. Not part of the rule; only these use pyarrow.
# ---------------------------------------------------------------------------------------------------------------------

ROOT = HERE.parents[1]
OUT = ROOT / "data/scribe/v4/resolver"
FREEZE = OUT / "freeze.json"
RUNLOG = ROOT / "runs/laneA-step1.jsonl"
FROZEN_FILES = ("scribe/v3/resolve.py", "scribe/v3/lexicon.py")
DATASET = ROOT / "data/scribe/v3/dataset"
STUDENT = ROOT / "data/scribe/v3/student"
STORED_RUNS = {
    "v2-selected": dict(test=STUDENT / "v2-selected/A-270m-lora-r16--test_nemotron+test_haiku--off.json",
                        val=STUDENT / "v2-selected/val-records.json"),
    "V3-270m-nemotron": dict(test=STUDENT / "V3-270m-nemotron/eval-test.json", val=STUDENT / "V3-270m-nemotron/val-records.json"),
    "V3-270m-all": dict(test=STUDENT / "V3-270m-all/eval-test.json", val=STUDENT / "V3-270m-all/val-records.json"),
    "C-270m-all-v2data": dict(test=STUDENT / "C-270m-all-v2data/eval-test.json", val=STUDENT / "C-270m-all-v2data/val-records.json"),
    "S-1b-lora-r16": dict(test=STUDENT / "S-1b-lora-r16/eval-test.json", val=STUDENT / "S-1b-lora-r16/val-records.json"),
}
PRIMARY = "C-270m-all-v2data"
EXPECT_PRIMARY = dict(val=(289, 310), test=(651, 700))
SELECTION_RULE = (
    "Product default arm: A' only if, on the 310 SYNTHETIC validation notes of C-270m-all-v2data (stored predictions), "
    "A' exact match >= arm A exact match AND A' makes 0 notes worse than arm A; otherwise arm A. Test notes are not "
    "used for this choice (they were already seen; test numbers are post hoc).")


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


def log(step, command, inputs=None, outputs=None, metrics=None, cost_usd=0.0, status="ok", **kw):
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(ts=now(), step=step, host=socket.gethostname(), command=command, inputs=inputs, outputs=outputs,
               metrics=metrics, cost_usd=cost_usd, status=status, **kw)
    with RUNLOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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


def cmd_freeze(args):
    target = OUT / args.name
    if target.exists():
        raise SystemExit(f"{rel(target)} exists; a freeze is written once. Use --name freeze-v2.json and say why.")
    OUT.mkdir(parents=True, exist_ok=True)
    rec = dict(schema="scribe-v4-resolver-freeze-v1", synthetic=True, frozen_at_utc=now(), rule=RULE, arms=list(ARMS),
               lexicon_version=LEX.VERSION, files={f: sha256(ROOT / f) for f in FROZEN_FILES},
               selection_rule=SELECTION_RULE, reason=args.reason,
               held_out_from_lexicon="number words seven to twelve and the day-before-yesterday adverb (stress set)",
               note="Frozen after unit tests on constructed strings and before the rule saw any stored student output "
                    "or any stress note. A person confirms every extracted event.")
    target.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    log("freeze", f"scribe/.venv/bin/python scribe/v3/resolve.py freeze --name {args.name}", inputs=list(FROZEN_FILES),
        outputs=[rel(target)], metrics=dict(files=rec["files"], frozen_at_utc=rec["frozen_at_utc"]))
    print(json.dumps(rec, indent=1, ensure_ascii=False))


def check_frozen(name="freeze.json"):
    rec = json.loads((OUT / name).read_text())
    now_sha = {f: sha256(ROOT / f) for f in FROZEN_FILES}
    if now_sha != rec["files"]:
        raise SystemExit(f"frozen files changed since {name}: {now_sha} != {rec['files']}")
    return rec


def load_gold():
    import pyarrow.parquet as pq

    gold = {}
    for split in ("val", "test_nemotron", "test_haiku"):
        for r in pq.read_table(DATASET / f"{split}.parquet").to_pylist():
            r["_split"] = split
            gold[r["id"]] = r
    return gold


def _diagnose_repair():
    path = ROOT / "runs/diagnose/resolve_relative.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("diagnose_resolve_relative", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.repair


def cmd_reproduce(args):
    freeze = check_frozen(args.freeze)
    gold = load_gold()
    original = _diagnose_repair()
    reference = json.loads((ROOT / "runs/diagnose/resolve-relative-v1.json").read_text())["results"]
    inputs = sorted({rel(p) for f in STORED_RUNS.values() for p in f.values()}) + [
        "data/scribe/v3/dataset/{val,test_nemotron,test_haiku}.parquet", "runs/diagnose/resolve_relative.py",
        "runs/diagnose/resolve-relative-v1.json"]
    results, port_mismatch, lexicon_notes = {}, 0, {}
    for name, files in STORED_RUNS.items():
        t = json.loads(files["test"].read_text())
        parts = {"val": json.loads(files["val"].read_text())}
        for s in ("test_nemotron", "test_haiku"):
            parts[s] = t["splits"][s]["records"]
        r = {}
        for part, recs in parts.items():
            c = dict(n=len(recs), before=0, A=0, Aprime=0, A_helped=0, A_hurt=0, Aprime_helped=0, Aprime_hurt=0,
                     Aprime_better_than_A=0, Aprime_worse_than_A=0, Aprime_differs_from_A=0, port_equal=0)
            for rec in recs:
                row = gold[rec["id"]]
                g = json.loads(row["target_json"])
                p = rec["prediction"]
                a = repair(p, row["note_text"], row["note_date"], "A")
                a2 = repair(p, row["note_text"], row["note_date"], "A'")
                same = a == original(row, p)
                c["port_equal"] += same
                port_mismatch += not same
                b0, b1, b2 = p == g, a == g, a2 == g
                c["before"] += b0
                c["A"] += b1
                c["Aprime"] += b2
                c["A_helped"] += b1 and not b0
                c["A_hurt"] += b0 and not b1
                c["Aprime_helped"] += b2 and not b0
                c["Aprime_hurt"] += b0 and not b2
                c["Aprime_better_than_A"] += b2 and not b1
                c["Aprime_worse_than_A"] += b1 and not b2
                c["Aprime_differs_from_A"] += a != a2
            r[part] = c
        pooled = {k: r["test_nemotron"][k] + r["test_haiku"][k] for k in r["val"]}
        r["test_pooled"] = pooled
        ref = reference[name]
        r["matches_diagnose_v1"] = all(
            (r[p]["before"], r[p]["A"], r[p]["n"], r[p]["A_helped"], r[p]["A_hurt"])
            == (ref[p]["before"]["k"], ref[p]["after"]["k"], ref[p]["n"], ref[p]["helped"], ref[p]["hurt"])
            for p in ("val", "test_nemotron", "test_haiku", "test_pooled"))
        results[name] = r
        print(name, {p: (v["before"], v["A"], v["Aprime"], v["n"], v["A_hurt"], v["Aprime_hurt"]) for p, v in r.items()
                     if isinstance(v, dict)}, file=sys.stderr)
    # How often the lexicon fires on the SYNTHETIC note texts (counts only).
    for split in ("val", "test_nemotron", "test_haiku"):
        rows = [g for g in gold.values() if g["_split"] == split]
        res_lex = sum(any(s["source"] == "lexicon" for s in relative_spans(g["note_text"], g["note_date"], "A'")) for g in rows)
        person = sum(bool(needs_person_spans(g["note_text"], "A'")) for g in rows)
        lexicon_notes[split] = dict(notes=len(rows), with_lexicon_resolved_phrase=res_lex, with_phrase_for_a_person=person)
    prim = results[PRIMARY]
    val_k, val_n = prim["val"]["A"], prim["val"]["n"]
    test_k, test_n = prim["test_pooled"]["A"], prim["test_pooled"]["n"]
    reproduced = (val_k, val_n) == EXPECT_PRIMARY["val"] and (test_k, test_n) == EXPECT_PRIMARY["test"]
    hurt_any = sum(results[n][p]["A_hurt"] for n in results for p in ("val", "test_pooled"))
    v = prim["val"]
    aprime_selected = v["Aprime"] >= v["A"] and v["Aprime_worse_than_A"] == 0
    out = dict(
        schema="scribe-v4-resolver-reproduce-v1", synthetic=True, created_utc=now(), freeze=dict(file=f"data/scribe/v4/resolver/{args.freeze}",
        frozen_at_utc=freeze["frozen_at_utc"], files=freeze["files"]), rule=RULE,
        primary=dict(
            run=PRIMARY, arm="A",
            validation=dict(rate(val_k, val_n), role="selection result", before=rate(prim["val"]["before"], val_n)),
            test=dict(rate(test_k, test_n), role="already seen, post hoc", before=rate(prim["test_pooled"]["before"], test_n),
                      by_writer=dict(nemotron=rate(prim["test_nemotron"]["A"], prim["test_nemotron"]["n"]),
                                     haiku=rate(prim["test_haiku"]["A"], prim["test_haiku"]["n"]))),
            expected=dict(validation=list(EXPECT_PRIMARY["val"]), test=list(EXPECT_PRIMARY["test"])),
            reproduced_exactly=reproduced),
        notes_made_worse_arm_A_all_runs=hurt_any,
        port_identical_to_diagnose_rule=dict(notes_compared=sum(results[n][p]["n"] for n in results for p in ("val", "test_pooled")),
                                             mismatches=port_mismatch),
        all_runs_match_resolve_relative_v1=all(results[n]["matches_diagnose_v1"] for n in results),
        arm_Aprime=dict(
            lexicon=LEX.VERSION, selection_rule=SELECTION_RULE,
            validation_primary=dict(A=rate(v["A"], val_n), Aprime=rate(v["Aprime"], val_n), Aprime_better_than_A=v["Aprime_better_than_A"],
                                    Aprime_worse_than_A=v["Aprime_worse_than_A"], Aprime_differs_from_A=v["Aprime_differs_from_A"]),
            product_default_arm="A'" if aprime_selected else "A",
            notes_made_worse_vs_student_all_runs=sum(results[n][p]["Aprime_hurt"] for n in results for p in ("val", "test_pooled")),
            lexicon_firing_on_note_texts=lexicon_notes,
            caveat="The generator (scribe/sample.py) writes relative dates with digits only, so the lexicon fires only where a "
                   "model writer paraphrased a phrase. Its real test is the frozen stress set (step 5)."),
        runs=results,
        caveats=["SYNTHETIC notes and model-written labels; exact match of the whole answer.",
                 "Validation is the selection result. Test notes were read several times before: test numbers are post hoc.",
                 "A person confirms every extracted event; the resolver output is pre-filled for one-click confirmation "
                 "or needs editing."])
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / args.out
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    log("reproduce", f"scribe/.venv/bin/python scribe/v3/resolve.py reproduce --out {args.out}", inputs=inputs,
        outputs=[rel(target)], status="ok" if reproduced and hurt_any == 0 and port_mismatch == 0 else "failed",
        metrics=dict(validation=f"{val_k}/{val_n}", test_post_hoc=f"{test_k}/{test_n}", reproduced_exactly=reproduced,
                     notes_made_worse_arm_A=hurt_any, port_mismatches=port_mismatch,
                     aprime_validation=f"{v['Aprime']}/{val_n}", aprime_worse_than_A=v["Aprime_worse_than_A"],
                     product_default_arm=out["arm_Aprime"]["product_default_arm"]))
    print(json.dumps({k: out[k] for k in ("primary", "notes_made_worse_arm_A_all_runs", "port_identical_to_diagnose_rule",
                                          "all_runs_match_resolve_relative_v1")}, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out["arm_Aprime"].items() if k != "selection_rule"}, indent=1, ensure_ascii=False))
    if not reproduced or port_mismatch:
        raise SystemExit(2)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--name", default="freeze.json")
    f.add_argument("--reason", default="first freeze of arm A' (step 1)")
    f.set_defaults(func=cmd_freeze)
    r = sub.add_parser("reproduce")
    r.add_argument("--freeze", default="freeze.json")
    r.add_argument("--out", default="reproduce-v1.json")
    r.set_defaults(func=cmd_reproduce)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
