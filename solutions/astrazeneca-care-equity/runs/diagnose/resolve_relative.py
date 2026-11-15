"""Lever (a) measured, not assumed: a code post-processor that re-resolves relative dates.

Uses only the note text, the note date and the stored model prediction (never the gold answer):
  1. find every 'N päivää sitten' / 'N viikkoa sitten' in the note and resolve it against the note date;
  2. a predicted event whose date is not written anywhere in the note in an absolute form
     (d.m.yyyy, d.m., d. <month>kuuta [yyyy], <month>kuussa yyyy) is 'unsupported';
  3. unsupported events are matched one-to-one to resolved relative dates by the smallest total
     absolute day difference (exhaustive over permutations; notes have at most 4 to 5 of either),
     and take that date with DAY precision.
Rule designed on validation notes (val.parquet); applied unchanged to the test files.
SYNTHETIC notes only. Writes only into runs/diagnose/.

Run: scribe/.venv/bin/python runs/diagnose/resolve_relative.py
"""
import datetime as dt
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnose as D  # noqa: E402

MONTHS = ["tammi", "helmi", "maalis", "huhti", "touko", "kesä", "heinä", "elo", "syys", "loka", "marras", "joulu"]
REL = re.compile(r"(\d+)\s+(päivää|viikkoa)\s+sitten")
NUM = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})?")
LONG = re.compile(r"(\d{1,2})\.\s+(" + "|".join(MONTHS) + r")kuuta(?:\s+(\d{4}))?")
MON = re.compile(r"(" + "|".join(MONTHS) + r")kuussa\s+(\d{4})")


def safe(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def written_dates(text, note):
    out = set()
    for m in NUM.finditer(text):
        x = safe(m.group(3) or note.year, m.group(2), m.group(1))
        if x:
            out.add(x.isoformat())
    for m in LONG.finditer(text):
        x = safe(m.group(3) or note.year, MONTHS.index(m.group(2)) + 1, m.group(1))
        if x:
            out.add(x.isoformat())
    for m in MON.finditer(text):
        out.add(dt.date(int(m.group(2)), MONTHS.index(m.group(1)) + 1, 1).isoformat())
    return out


def relative_dates(text, note):
    out = []
    for m in REL.finditer(text):
        k = int(m.group(1)) * (7 if m.group(2) == "viikkoa" else 1)
        out.append((note - dt.timedelta(days=k)).isoformat())
    return out


def repair(row, pred):
    if pred is None:
        return None
    note = dt.date.fromisoformat(row["note_date"])
    text = row["note_text"]
    written = written_dates(text, note)
    rel = relative_dates(text, note)
    events = [dict(e) for e in pred["events"]]
    unsupported = [i for i, e in enumerate(events) if e["date"] not in written]
    if unsupported and rel:
        k = min(len(unsupported), len(rel))
        best = None
        for evs in itertools.combinations(unsupported, k):
            for rs in itertools.permutations(range(len(rel)), k):
                cost = sum(abs((dt.date.fromisoformat(events[i]["date"]) - dt.date.fromisoformat(rel[j])).days) for i, j in zip(evs, rs))
                if best is None or cost < best[0]:
                    best = (cost, evs, rs)
        for i, j in zip(best[1], best[2]):
            events[i]["date"] = rel[j]
            events[i]["precision"] = "DAY"
    return dict(entry_route=pred["entry_route"], events=sorted(events, key=lambda e: (e["date"], e["type"])))


def main():
    gold = D.load_gold()
    res = {}
    for name, files in D.RUNS.items():
        t = json.loads(files["test"].read_text())
        val = json.loads(files["val"].read_text())
        parts = {"val": val}
        for s in ("test_nemotron", "test_haiku"):
            parts[s] = t["splits"][s]["records"]
        r = {}
        for part, recs in parts.items():
            k0 = k1 = 0
            hurt = helped = 0
            for rec in recs:
                row = gold[rec["id"]]
                g = json.loads(row["target_json"])
                before = rec["prediction"] == g
                after = repair(row, rec["prediction"]) == g
                k0 += before
                k1 += after
                helped += after and not before
                hurt += before and not after
            r[part] = dict(n=len(recs), before=D.rate(k0, len(recs)), after=D.rate(k1, len(recs)), helped=helped, hurt=hurt)
        n = r["test_nemotron"]["n"] + r["test_haiku"]["n"]
        kb = r["test_nemotron"]["before"]["k"] + r["test_haiku"]["before"]["k"]
        ka = r["test_nemotron"]["after"]["k"] + r["test_haiku"]["after"]["k"]
        r["test_pooled"] = dict(n=n, before=D.rate(kb, n), after=D.rate(ka, n),
                                helped=r["test_nemotron"]["helped"] + r["test_haiku"]["helped"],
                                hurt=r["test_nemotron"]["hurt"] + r["test_haiku"]["hurt"])
        # residual error taxonomy and within-note intervals after the repair (test, both writers)
        notes, iv = [], []
        for s in ("test_nemotron", "test_haiku"):
            for rec in parts[s]:
                row = gold[rec["id"]]
                rr = dict(rec, prediction=repair(row, rec["prediction"]))
                nt = D.analyse(row, rr)
                notes.append(nt)
                x = D.intervals(nt)
                if x is None:
                    ng = nt["day_gold_events"]
                    iv.extend(dict(found=False, parse_failure=True, writer=nt["writer"]) for _ in range(ng * (ng - 1) // 2))
                    continue
                for q in x:
                    q["writer"] = nt["writer"]
                iv.extend(x)
        summ = D.summarise_run(name + "+resolver", notes)
        r["residual_after_resolver_test"] = {k: summ[k] for k in ("exact", "wrong", "category_notes_multilabel", "sole_cause_notes",
                                                                  "multi_cause_notes", "type_confusions", "extra_event_why", "extra_event_types",
                                                                  "missing_by_type", "missing_by_form", "by_writer", "by_kind", "by_n_gold",
                                                                  "date_wrong_by_form", "route_confusions", "parse_failure_sub", "no_event_notes")}
        r["intervals_after_resolver_test"] = D.interval_summary(iv)
        (D.OUT / f"intervals-{name}-resolved.json").write_text(json.dumps(iv))
        res[name] = r
        print(name, json.dumps({p: (v["before"]["k"], v["after"]["k"], v["n"], v["helped"], v["hurt"]) for p, v in r.items() if "before" in v}), file=sys.stderr)
    (D.OUT / "resolve-relative-v1.json").write_text(json.dumps(dict(schema="scribe-relative-resolver-v1", synthetic=True,
        rule=__doc__.strip().split("\n\n")[0], results=res), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
