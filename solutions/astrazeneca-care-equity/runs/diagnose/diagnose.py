"""Where does the Gemma pathway scribe fail?  SYNTHETIC notes only; read-only over the repository.

Reads the stored per-note predictions of five student runs and the gold answer keys, classifies every
wrong note, computes counterfactual exact match under oracle levers and two code-only post-filters, and
writes per-interval date errors for the product analysis (simulate.py).  Writes only into runs/diagnose/.

Run: scribe/.venv/bin/python runs/diagnose/diagnose.py
"""
import collections
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "diagnose"
DS = ROOT / "data/scribe/v3/dataset"
ST = ROOT / "data/scribe/v3/student"
RUNS = {
    "v2-selected": dict(test=ST / "v2-selected/A-270m-lora-r16--test_nemotron+test_haiku--off.json",
                        val=ST / "v2-selected/val-records.json"),
    "V3-270m-nemotron": dict(test=ST / "V3-270m-nemotron/eval-test.json", val=ST / "V3-270m-nemotron/val-records.json"),
    "V3-270m-all": dict(test=ST / "V3-270m-all/eval-test.json", val=ST / "V3-270m-all/val-records.json"),
    "C-270m-all-v2data": dict(test=ST / "C-270m-all-v2data/eval-test.json", val=ST / "C-270m-all-v2data/val-records.json"),
    "S-1b-lora-r16": dict(test=ST / "S-1b-lora-r16/eval-test.json", val=ST / "S-1b-lora-r16/val-records.json"),
}
FORM_GROUP = {"numeric": "absolute_day", "long": "absolute_day", "month": "month_only", "days": "relative_days",
              "weeks": "relative_weeks", "no_year": "no_year"}
RELATIVE = {"days", "weeks"}
RESOLVER_FORMS = {"days", "weeks", "no_year", "month"}  # what a code resolver handles from the right span
DATE_TYPES = {"type_ok_date_wrong", "precision_only"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def d(s):
    return dt.date.fromisoformat(s)


def wilson(k, n):
    if not n:
        return [None, None]
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0, c - h), 4), round(min(1, c + h), 4)]


def rate(k, n):
    return {"k": k, "n": n, "value": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def load_gold():
    gold = {}
    for split in ("val", "test_nemotron", "test_haiku"):
        for r in pq.read_table(DS / f"{split}.parquet").to_pylist():
            r["_split"] = split
            gold[r["id"]] = r
    return gold


def size_bucket(x):
    a = abs(x)
    if a == 0:
        return "0"
    for lo, hi, lab in ((1, 3, "1-3"), (4, 7, "4-7"), (8, 31, "8-31"), (32, 90, "32-90"), (91, 364, "91-364")):
        if lo <= a <= hi:
            return lab
    return ">=365"


def multiset_take(lst, pred):
    for i, x in enumerate(lst):
        if pred(x):
            return lst.pop(i)
    return None


def analyse(row, rec):
    """Return dict with error categories and event-level details for one note."""
    g = json.loads(row["target_json"])
    facts = row["facts"] or []
    fact_by = collections.defaultdict(list)
    for f in facts:
        fact_by[(f["type"], f["date"], f["precision"])].append(f)
    gold_ev = []
    for e in g["events"]:
        f = fact_by[(e["type"], e["date"], e["precision"])]
        f = f.pop(0) if f else {"form": "unknown", "expression": None}
        gold_ev.append(dict(e, form=f["form"], expression=f["expression"]))
    note_date = d(row["note_date"])
    distractor_dates = {x["date"]: x["kind"] for x in (row["distractors"] or [])}
    gold_dates = {e["date"] for e in gold_ev}
    p = rec["prediction"]
    out = dict(id=row["id"], split=row["_split"], writer="haiku" if "haiku" in row["writer"] else "nemotron",
               kind=row["kind"], focus=row["focus"], style=row["style"], words=len(row["note_text"].split()),
               chars=len(row["note_text"]), n_gold=len(gold_ev), forms=sorted({e["form"] for e in gold_ev}),
               n_distractors=len(row["distractors"] or []), distractor_kinds=sorted(set(distractor_dates.values())),
               tokens_out=rec.get("tokens"), stopped=rec.get("stopped"), confidence=rec.get("confidence"),
               gold_route=g["entry_route"], cats=collections.Counter(), events=[], extras=[], confusions=[],
               note_date=row["note_date"])
    if p is None:
        err = rec.get("parse_error", "")
        if not rec.get("stopped", True):
            sub = "truncated_no_stop"
        elif "date" in err or "month" in err.lower() or "day is out of range" in err:
            sub = "invalid_date"
        elif "schema" in err or "route" in err:
            sub = "schema_or_route_enum"
        else:
            sub = "json_syntax"
        out["cats"]["parse_failure"] += 1
        out["parse_sub"] = sub
        out["day_gold_events"] = sum(1 for e in gold_ev if e["form"] != "month")
        out["parse_error"] = err[:160]
        out["pred_route"] = None
        out["pred_n"] = 0
        out["exact"] = False
        return out
    out["pred_route"] = p["entry_route"]
    out["pred_n"] = len(p["events"])
    if p["entry_route"] != g["entry_route"]:
        out["cats"]["route_wrong"] += 1
        out["route_confusion"] = f'{g["entry_route"]}->{p["entry_route"]}'
    # raw order / duplicates (do not affect the canonical comparison except duplicates)
    try:
        raw = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", rec["raw"].strip()))
        rev = [(e.get("date"), e.get("type")) for e in raw.get("events", [])]
        out["raw_unsorted"] = rev != sorted(rev)
    except Exception:
        out["raw_unsorted"] = None
    keys = collections.Counter((e["type"], e["date"]) for e in p["events"])
    out["duplicates"] = sum(v - 1 for v in keys.values() if v > 1)
    G = list(range(len(gold_ev)))
    P = [dict(e) for e in p["events"]]
    # 1 exact
    rem_g = []
    for i in G:
        e = gold_ev[i]
        m = multiset_take(P, lambda q: (q["type"], q["date"], q["precision"]) == (e["type"], e["date"], e["precision"]))
        if m is not None:
            out["events"].append(dict(gi=i, status="exact", form=e["form"], type=e["type"], gold=e["date"], pred=m["date"],
                                      gold_prec=e["precision"], pred_prec=m["precision"], err=0))
        else:
            rem_g.append(i)
    # 2 precision only
    rem2 = []
    for i in rem_g:
        e = gold_ev[i]
        m = multiset_take(P, lambda q: (q["type"], q["date"]) == (e["type"], e["date"]))
        if m is not None:
            out["cats"]["precision_only"] += 1
            out["events"].append(dict(gi=i, status="precision_only", form=e["form"], type=e["type"], gold=e["date"],
                                      pred=m["date"], gold_prec=e["precision"], pred_prec=m["precision"], err=0))
        else:
            rem2.append(i)
    # 3 same type, different date: pair by sorted date within type
    rem3 = []
    by_type = collections.defaultdict(list)
    for i in rem2:
        by_type[gold_ev[i]["type"]].append(i)
    for typ, idx in by_type.items():
        idx = sorted(idx, key=lambda i: gold_ev[i]["date"])
        cands = sorted([q for q in P if q["type"] == typ], key=lambda q: q["date"])
        for i, q in zip(idx, cands):
            P.remove(q)
            e = gold_ev[i]
            err = (d(q["date"]) - d(e["date"])).days
            if q["date"] in distractor_dates:
                span = "distractor:" + distractor_dates[q["date"]]
            elif q["date"] in gold_dates:
                span = "other_event_date"
            elif d(q["date"]) > note_date:
                span = "after_note_date"
            else:
                span = "misresolved"
            out["cats"]["type_ok_date_wrong"] += 1
            out["events"].append(dict(gi=i, status="date_wrong", form=e["form"], expression=e["expression"], type=typ,
                                      gold=e["date"], pred=q["date"], gold_prec=e["precision"], pred_prec=q["precision"],
                                      err=err, span=span))
        rem3.extend(idx[len(cands):])
    # 4 same date, different type
    rem4 = []
    for i in rem3:
        e = gold_ev[i]
        m = multiset_take(P, lambda q: q["date"] == e["date"])
        if m is not None:
            out["cats"]["wrong_type"] += 1
            out["confusions"].append(f'{e["type"]}->{m["type"]}')
            out["events"].append(dict(gi=i, status="wrong_type", form=e["form"], type=e["type"], pred_type=m["type"],
                                      gold=e["date"], pred=m["date"], gold_prec=e["precision"], pred_prec=m["precision"], err=0))
        else:
            rem4.append(i)
    # 5 type and date both wrong (nearest within 31 days)
    rem5 = []
    for i in rem4:
        e = gold_ev[i]
        best = None
        for q in P:
            diff = abs((d(q["date"]) - d(e["date"])).days)
            if diff <= 31 and (best is None or diff < best[0]):
                best = (diff, q)
        if best:
            q = best[1]
            P.remove(q)
            out["cats"]["type_and_date_wrong"] += 1
            out["confusions"].append(f'{e["type"]}->{q["type"]}')
            out["events"].append(dict(gi=i, status="type_and_date_wrong", form=e["form"], type=e["type"], pred_type=q["type"],
                                      gold=e["date"], pred=q["date"], err=(d(q["date"]) - d(e["date"])).days))
        else:
            rem5.append(i)
    for i in rem5:
        e = gold_ev[i]
        out["cats"]["missing_event"] += 1
        out["events"].append(dict(gi=i, status="missing", form=e["form"], type=e["type"], gold=e["date"]))
    for q in P:
        if q["date"] in distractor_dates:
            why = "distractor:" + distractor_dates[q["date"]]
        elif d(q["date"]) > note_date:
            why = "after_note_date"
        elif q["date"] in gold_dates:
            why = "duplicate_of_gold_date"
        else:
            why = "other"
        out["cats"]["extra_event"] += 1
        out["extras"].append(dict(type=q["type"], date=q["date"], why=why))
    out["exact"] = not out["cats"]
    return out


# ---------------- counterfactual levers ----------------
def fixed_by(note, lever):
    """Would the note be exact if the lever removed its error categories?"""
    c = note["cats"]
    if not c:
        return True
    if "parse_failure" in c:
        return False
    rest = collections.Counter(c)
    if lever.get("route"):
        rest.pop("route_wrong", None)
    if lever.get("type"):
        rest.pop("wrong_type", None)
    if lever.get("date_all"):
        rest.pop("type_ok_date_wrong", None)
        rest.pop("precision_only", None)
    if lever.get("date_forms"):
        forms = lever["date_forms"]
        bad = [e for e in note["events"] if e["status"] == "date_wrong" and e["form"] not in forms]
        badp = [e for e in note["events"] if e["status"] == "precision_only" and e["form"] not in forms]
        if not bad:
            rest.pop("type_ok_date_wrong", None)
        if not badp and lever.get("precision", True):
            rest.pop("precision_only", None)
    if lever.get("type") and lever.get("date_all"):
        rest.pop("type_and_date_wrong", None)
    if lever.get("events"):
        rest.pop("missing_event", None)
        rest.pop("extra_event", None)
    if lever.get("extras_nonfuture_distractor"):
        if all(x["why"].startswith("distractor") or x["why"] == "after_note_date" for x in note["extras"]):
            rest.pop("extra_event", None)
    return not rest


LEVERS = {
    "a_dates_all_code_resolved_from_right_span": dict(date_all=True),
    "a1_relative_days_weeks_only": dict(date_forms=RELATIVE, precision=False),
    "a2_resolver_forms_rel_noyear_month": dict(date_forms=RESOLVER_FORMS),
    "b_types_correct": dict(type=True),
    "c_route_correct": dict(route=True),
    "a+b": dict(date_all=True, type=True),
    "a+b+c": dict(date_all=True, type=True, route=True),
    "a+b+c+distractor_and_future_extras_removed": dict(date_all=True, type=True, route=True, extras_nonfuture_distractor=True),
    "a+b+c+all_event_detection": dict(date_all=True, type=True, route=True, events=True),
}


def code_postfilter(row, rec, drop_future=True, dedupe=True):
    """Deterministic post-filters that need no gold: drop events dated after the note date, drop exact duplicates."""
    p = rec["prediction"]
    if p is None:
        return None
    ev = p["events"]
    if drop_future:
        ev = [e for e in ev if d(e["date"]) <= d(row["note_date"])]
    if dedupe:
        seen, out = set(), []
        for e in ev:
            k = (e["type"], e["date"], e["precision"])
            if k not in seen:
                seen.add(k)
                out.append(e)
        ev = out
    return dict(entry_route=p["entry_route"], events=sorted(ev, key=lambda e: (e["date"], e["type"])))


# ---------------- intervals for the product ----------------
def intervals(note):
    """All within-note gold event pairs (i earlier than j, both DAY precision), with whether both endpoints were
    found with the right type and DAY precision, and the signed interval error (pred span - true span)."""
    if "parse_failure" in note["cats"]:
        return None
    ev = {e["gi"]: e for e in note["events"]}
    out = []
    n = note["n_gold"]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ev[i], ev[j]
            # gold MONTH precision <=> form "month"; the detector tests DAY-precision pairs only
            if a["form"] == "month" or b["form"] == "month":
                continue
            if d(a["gold"]) > d(b["gold"]):
                a, b = b, a
            true = (d(b["gold"]) - d(a["gold"])).days
            ok = all(x["status"] in ("exact", "date_wrong", "precision_only") and x.get("pred_prec") == "DAY" for x in (a, b))
            rec = dict(types=f'{a["type"]}->{b["type"]}', forms=f'{a["form"]}->{b["form"]}', true_days=true, found=ok)
            if ok:
                rec["pred_days"] = (d(b["pred"]) - d(a["pred"])).days
                rec["err"] = rec["pred_days"] - true
                rec["e_a"] = a["err"]
                rec["e_b"] = b["err"]
            out.append(rec)
    return out


def quant(xs, qs=(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)):
    s = sorted(xs)
    if not s:
        return {}
    return {str(q): s[min(len(s) - 1, int(round(q * (len(s) - 1))))] for q in qs}


def summarise_run(name, notes):
    wrong = [n for n in notes if not n["exact"]]
    res = dict(run=name, n=len(notes), exact=rate(sum(n["exact"] for n in notes), len(notes)), wrong=len(wrong))
    # multi-label categories among wrong notes
    cat_notes = collections.Counter()
    cat_events = collections.Counter()
    for n in wrong:
        for c, k in n["cats"].items():
            cat_notes[c] += 1
            cat_events[c] += k
    res["category_notes_multilabel"] = {c: rate(v, len(wrong)) for c, v in cat_notes.most_common()}
    res["category_event_counts"] = dict(cat_events.most_common())
    # sole cause: wrong notes with exactly one category
    sole = collections.Counter(next(iter(n["cats"])) for n in wrong if len(n["cats"]) == 1)
    res["sole_cause_notes"] = dict(sole.most_common())
    res["multi_cause_notes"] = sum(1 for n in wrong if len(n["cats"]) > 1)
    # hierarchical primary cause (first in a fixed order)
    order = ["parse_failure", "type_ok_date_wrong", "precision_only", "missing_event", "extra_event", "wrong_type",
             "type_and_date_wrong", "route_wrong"]
    prim = collections.Counter(next(c for c in order if c in n["cats"]) for n in wrong)
    res["primary_cause_hierarchical"] = {"order": order, "counts": dict(prim)}
    res["parse_failure_sub"] = dict(collections.Counter(n.get("parse_sub") for n in notes if "parse_failure" in n["cats"]))
    res["route_confusions"] = dict(collections.Counter(n["route_confusion"] for n in notes if "route_confusion" in n).most_common(10))
    res["type_confusions"] = dict(collections.Counter(c for n in notes for c in n["confusions"]).most_common(12))
    res["extra_event_why"] = dict(collections.Counter(x["why"] for n in notes for x in n["extras"]).most_common())
    res["extra_event_types"] = dict(collections.Counter(x["type"] for n in notes for x in n["extras"]).most_common())
    res["missing_by_form"] = dict(collections.Counter(e["form"] for n in notes for e in n["events"] if e["status"] == "missing"))
    res["missing_by_type"] = dict(collections.Counter(e["type"] for n in notes for e in n["events"] if e["status"] == "missing").most_common())
    res["duplicates_notes"] = sum(1 for n in notes if n.get("duplicates"))
    res["raw_unsorted_notes"] = sum(1 for n in notes if n.get("raw_unsorted"))
    res["raw_unsorted_note"] = "the scorer canonicalises (sorts) predictions, so output order never causes an error"
    # per-event status by form
    by_form = collections.defaultdict(collections.Counter)
    for n in notes:
        if "parse_failure" in n["cats"]:
            for e in range(n["n_gold"]):
                pass
        for e in n["events"]:
            by_form[e["form"]][e["status"]] += 1
    res["gold_events_status_by_form"] = {f: dict(c) for f, c in sorted(by_form.items())}
    res["date_exact_given_type_found_by_form"] = {
        f: rate(c["exact"] + c["wrong_type"], c["exact"] + c["wrong_type"] + c["date_wrong"] + c["precision_only"])
        for f, c in sorted(by_form.items())}
    # date errors (type found, date wrong) by form group and size
    derr = [e for n in notes for e in n["events"] if e["status"] == "date_wrong"]
    res["date_wrong_events"] = len(derr)
    res["date_wrong_by_form"] = dict(collections.Counter(e["form"] for e in derr).most_common())
    res["date_wrong_by_form_group"] = dict(collections.Counter(FORM_GROUP.get(e["form"], e["form"]) for e in derr).most_common())
    res["date_wrong_span_source"] = dict(collections.Counter(e["span"] for e in derr).most_common())
    sz = collections.defaultdict(collections.Counter)
    for e in derr:
        sz[e["form"]][size_bucket(e["err"])] += 1
    res["date_wrong_size_by_form"] = {f: dict(c) for f, c in sz.items()}
    res["date_wrong_abs_median_by_form"] = {f: sorted(abs(e["err"]) for e in derr if e["form"] == f)[len([e for e in derr if e["form"] == f]) // 2]
                                            for f in {e["form"] for e in derr}}
    # specific patterns
    pat = collections.Counter()
    for e in derr:
        a = abs(e["err"])
        if e["form"] == "no_year" and a in (365, 366):
            pat["no_year_off_by_one_year"] += 1
        if e["form"] == "weeks" and a % 7 == 0:
            pat["weeks_err_multiple_of_7"] += 1
        if e["form"] == "month" and e.get("gold_prec") == "MONTH" and e.get("pred_prec") == "MONTH":
            pat["month_wrong_month"] += 1
        if e["form"] in ("numeric", "long") and a in (365, 366):
            pat["absolute_off_by_one_year"] += 1
        if e["form"] in ("numeric", "long") and a <= 3:
            pat["absolute_off_by_1_3_days"] += 1
        if e["form"] in ("numeric", "long"):
            gd, pd_ = d(e["gold"]), d(e["pred"])
            if gd.day == pd_.month and gd.month == pd_.day:
                pat["absolute_day_month_swapped"] += 1
            if gd.day == pd_.day and gd.year == pd_.year and gd.month != pd_.month:
                pat["absolute_month_digit_wrong"] += 1
    res["date_wrong_patterns"] = dict(pat)
    # relative-date arithmetic: predicted offset vs stated offset
    rel = []
    for n in notes:
        nd = d(n["note_date"])
        for e in n["events"]:
            if e["status"] == "date_wrong" and e["form"] in RELATIVE and e.get("expression"):
                m = re.search(r"(\d+)", e["expression"])
                if not m:
                    continue
                k = int(m.group(1))
                stated = k * (7 if e["form"] == "weeks" else 1)
                pred_off = (nd - d(e["pred"])).days
                rel.append(dict(form=e["form"], k=k, stated_days=stated, pred_offset=pred_off, ratio=round(pred_off / stated, 3) if stated else None))
    res["relative_wrong_count"] = len(rel)
    res["relative_wrong_pred_offset_over_stated_quantiles"] = quant([r["ratio"] for r in rel if r["ratio"] is not None])
    res["relative_wrong_weeks_pred_offset_equals_k_days"] = sum(1 for r in rel if r["form"] == "weeks" and r["pred_offset"] == r["k"])
    res["relative_wrong_weeks_pred_offset_equals_k_times_30"] = sum(1 for r in rel if r["form"] == "weeks" and abs(r["pred_offset"] - 30 * r["k"]) <= 2)
    res["relative_wrong_weeks_pred_offset_k_months"] = sum(1 for r in rel if r["form"] == "weeks" and abs(r["pred_offset"] - round(30.44 * r["k"])) <= 3)
    res["relative_wrong_by_k_bucket"] = dict(collections.Counter(
        (r["form"] + ":" + ("<=7" if r["k"] <= 7 else "8-30" if r["k"] <= 30 else ">30")) for r in rel))
    rel_all = collections.Counter()
    for n in notes:
        for e in n["events"]:
            if e["form"] in RELATIVE and e.get("expression") is not None and e["status"] in ("exact", "date_wrong", "precision_only", "wrong_type"):
                m = re.search(r"(\d+)", e.get("expression") or "")
                if m:
                    k = int(m.group(1))
                    b = e["form"] + ":" + ("<=7" if k <= 7 else "8-30" if k <= 30 else ">30")
                    rel_all[b + ":" + ("ok" if e["status"] in ("exact", "wrong_type") else "wrong")] += 1
    res["relative_found_by_k_bucket_ok_vs_wrong"] = dict(sorted(rel_all.items()))
    # counterfactual levers
    cf = {}
    for lname, lev in LEVERS.items():
        k = sum(fixed_by(n, lev) for n in notes)
        gained = k - res["exact"]["k"]
        cf[lname] = dict(exact=rate(k, len(notes)), notes_fixed=gained,
                         share_of_wrong_notes_removed=round(gained / len(wrong), 4) if wrong else None)
    res["counterfactual"] = cf
    # strata
    def strat(key, f):
        g = collections.defaultdict(list)
        for n in notes:
            g[f(n)].append(n["exact"])
        return {str(k): rate(sum(v), len(v)) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}
    res["by_writer"] = strat("writer", lambda n: n["writer"])
    res["by_kind"] = strat("kind", lambda n: n["writer"] + ":" + n["kind"])
    res["by_n_gold"] = strat("n_gold", lambda n: n["n_gold"])
    res["by_words"] = strat("words", lambda n: "60-69" if n["words"] < 70 else "70-79" if n["words"] < 80 else "80-89" if n["words"] < 90 else "90+")
    res["by_has_relative"] = strat("rel", lambda n: bool(RELATIVE & set(n["forms"])))
    res["by_has_relative_or_noyear"] = strat("rel", lambda n: bool((RELATIVE | {"no_year"}) & set(n["forms"])))
    res["by_forms_absolute_only"] = strat("abs", lambda n: "absolute_or_month_only" if n["forms"] and set(n["forms"]) <= {"numeric", "long", "month"} else ("no_events" if not n["forms"] else "has_relative_or_no_year"))
    res["by_style"] = strat("style", lambda n: n["style"])
    res["by_n_distractors"] = strat("nd", lambda n: n["n_distractors"])
    res["by_focus_haiku"] = {k: v for k, v in strat("focus", lambda n: n["focus"]).items() if k != "sampler_v1"}
    # no_event notes: what the model added
    ne = [n for n in notes if n["kind"] == "no_event"]
    res["no_event_notes"] = dict(n=len(ne), exact=sum(n["exact"] for n in ne),
                                 extra_why=dict(collections.Counter(x["why"] for n in ne for x in n["extras"])),
                                 extra_types=dict(collections.Counter(x["type"] for n in ne for x in n["extras"])))
    # truncation risk
    res["stopped_false"] = sum(1 for n in notes if n["stopped"] is False)
    res["max_tokens_out"] = max((n["tokens_out"] or 0) for n in notes)
    return res


def logistic(rows, names):
    """Tiny IRLS logistic regression, pure python (no numpy here). rows: list of (y, [x...])."""
    k = len(names) + 1
    beta = [0.0] * k
    X = [[1.0] + x for _, x in rows]
    Y = [y for y, _ in rows]
    for _ in range(50):
        H = [[0.0] * k for _ in range(k)]
        gvec = [0.0] * k
        for xi, yi in zip(X, Y):
            z = sum(b * v for b, v in zip(beta, xi))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            w = p * (1 - p)
            for a in range(k):
                gvec[a] += (yi - p) * xi[a]
                for b in range(k):
                    H[a][b] += w * xi[a] * xi[b]
        for a in range(k):
            H[a][a] += 1e-6
        step = solve(H, gvec)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    inv = invert(H)
    se = [math.sqrt(max(inv[i][i], 0)) for i in range(k)]
    return {nm: dict(coef=round(b, 3), se=round(s, 3), odds_ratio=round(math.exp(b), 3), z=round(b / s, 2) if s else None)
            for nm, b, s in zip(["intercept"] + names, beta, se)}


def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def invert(A):
    n = len(A)
    cols = []
    for j in range(n):
        e = [0.0] * n
        e[j] = 1.0
        cols.append(solve(A, e))
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def main():
    gold = load_gold()
    report = dict(schema="scribe-diagnose-v1", synthetic=True, not_for_clinical_use=True,
                  generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  sources={str(p.relative_to(ROOT)): sha(p) for p in [DS / "val.parquet", DS / "test_nemotron.parquet", DS / "test_haiku.parquet"]},
                  runs={})
    all_notes = {}
    for name, files in RUNS.items():
        report["sources"][str(files["test"].relative_to(ROOT))] = sha(files["test"])
        report["sources"][str(files["val"].relative_to(ROOT))] = sha(files["val"])
        t = json.loads(files["test"].read_text())
        notes = []
        for split in ("test_nemotron", "test_haiku"):
            blk = t["splits"][split]
            stored = dict(zip(blk["metrics"]["ids"], blk["metrics"]["outcomes"]))
            for rec in blk["records"]:
                n = analyse(gold[rec["id"]], rec)
                assert n["exact"] == stored[rec["id"]], (name, rec["id"], n["cats"])
                notes.append(n)
        val = json.loads(files["val"].read_text())
        vnotes = [analyse(gold[rec["id"]], rec) for rec in val]
        all_notes[name] = dict(test=notes, val=vnotes)
        rr = dict(test=summarise_run(name, notes), val=summarise_run(name, vnotes))
        # code-only post-filter, measured (no gold used by the filter)
        for part, recs_src in (("test", [(gold[r["id"]], r) for s in ("test_nemotron", "test_haiku") for r in t["splits"][s]["records"]]),
                               ("val", [(gold[r["id"]], r) for r in val])):
            k0 = k1 = k2 = 0
            for row, rec in recs_src:
                g = json.loads(row["target_json"])
                k0 += rec["prediction"] == g
                k1 += code_postfilter(row, rec, drop_future=True, dedupe=False) == g
                k2 += code_postfilter(row, rec, drop_future=True, dedupe=True) == g
            rr[part]["code_postfilter_measured"] = dict(baseline=rate(k0, len(recs_src)), drop_after_note_date=rate(k1, len(recs_src)),
                                                        drop_after_note_date_and_dedupe=rate(k2, len(recs_src)))
        # logistic regression of error on note features (test)
        rows = []
        for n in notes:
            rows.append((0 if n["exact"] else 1, [n["words"] / 10.0, float(n["n_gold"]), 1.0 if n["writer"] == "haiku" else 0.0,
                                                  1.0 if RELATIVE & set(n["forms"]) else 0.0, 1.0 if "no_year" in n["forms"] else 0.0,
                                                  float(n["n_distractors"]), 1.0 if n["kind"] != "standard" else 0.0]))
        rr["test"]["logit_error"] = logistic(rows, ["words_per10", "n_gold_events", "writer_haiku", "has_relative_date",
                                                     "has_no_year_date", "n_distractors", "kind_not_standard"])
        # intervals for the product
        iv = []
        for n in notes:
            x = intervals(n)
            if x is None:
                # a parse failure loses every pair of the note
                ng = n["day_gold_events"]
                iv.extend(dict(found=False, parse_failure=True, writer=n["writer"]) for _ in range(ng * (ng - 1) // 2))
                continue
            for r in x:
                r["writer"] = n["writer"]
                r["note"] = n["id"][:12]
            iv.extend(x)
        rr["test"]["intervals"] = interval_summary(iv)
        (OUT / f"intervals-{name}.json").write_text(json.dumps(iv))
        report["runs"][name] = rr
        print(name, rr["test"]["exact"], rr["val"]["exact"], file=sys.stderr)
    # paired: which notes fail in every run (hard core)
    ids = [n["id"] for n in all_notes["C-270m-all-v2data"]["test"]]
    fails = collections.Counter()
    for name in RUNS:
        for n in all_notes[name]["test"]:
            if not n["exact"]:
                fails[n["id"]] += 1
    report["fail_count_across_5_runs_test"] = dict(sorted(collections.Counter(fails.get(i, 0) for i in ids).items()))
    always = [n for n in all_notes["C-270m-all-v2data"]["test"] if fails.get(n["id"], 0) == 5]
    report["always_wrong_profile_C"] = dict(n=len(always), cats=dict(collections.Counter(c for n in always for c in n["cats"]).most_common()),
                                           has_relative=sum(1 for n in always if RELATIVE & set(n["forms"])))
    (OUT / "diagnose-v1.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    # per-note table for the two best runs
    for name in ("C-270m-all-v2data", "V3-270m-all"):
        with open(OUT / f"notes-{name}.jsonl", "w") as fh:
            for n in all_notes[name]["test"]:
                m = {k: v for k, v in n.items() if k not in ("events",)}
                m["cats"] = dict(n["cats"])
                m["events"] = n["events"]
                fh.write(json.dumps(m, ensure_ascii=False, default=str) + "\n")


def interval_summary(iv):
    out = {}
    for w in ("all", "nemotron", "haiku"):
        sel = [r for r in iv if w == "all" or r["writer"] == w]
        found = [r for r in sel if r.get("found")]
        errs = [r["err"] for r in found]
        out[w] = dict(pairs_day_precision=len(sel), found_both_endpoints=rate(len(found), len(sel)),
                      exact_interval=rate(sum(1 for e in errs if e == 0), len(errs)),
                      mean_err=round(sum(errs) / len(errs), 2) if errs else None,
                      median_err=quant(errs).get("0.5") if errs else None,
                      sd_err=round(math.sqrt(sum((e - sum(errs) / len(errs)) ** 2 for e in errs) / max(1, len(errs) - 1)), 2) if errs else None,
                      mean_abs_err=round(sum(abs(e) for e in errs) / len(errs), 2) if errs else None,
                      quantiles=quant(errs),
                      abs_size=dict(collections.Counter(size_bucket(e) for e in errs)),
                      negative_pred_span=sum(1 for r in found if r["pred_days"] < 0),
                      # correlation of endpoint errors inside a note
                      both_endpoints_wrong=sum(1 for r in found if r["e_a"] != 0 and r["e_b"] != 0),
                      both_wrong_same_error=sum(1 for r in found if r["e_a"] != 0 and r["e_a"] == r["e_b"]),
                      endpoint_error_corr=corr([r["e_a"] for r in found], [r["e_b"] for r in found]))
    return out


def corr(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb), 3)


if __name__ == "__main__":
    main()
