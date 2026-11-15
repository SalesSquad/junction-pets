"""Step 4.3: the agreement rule between the Gemma scribe (plus the code date resolver) and Nemotron.

Rule, fixed in NVIDIA_OPTIONS.md section 3.2 step 4 before any number here was computed: a note is
pre-filled for one-click confirmation only when Gemma + resolver and Nemotron give exactly the same
canonical answer; otherwise it is flagged as needing editing. A person confirms every note either way.
The rule has no threshold, so nothing is tuned: validation and test are both reported, test once.

Inputs (read only):
  Gemma:    data/scribe/v3/student/C-270m-all-v2data/{val-records.json, eval-test.json}, re-dated by
            runs/diagnose/resolve_relative.py repair() (imported, not copied)
  Nemotron: data/scribe/nemotron/cache/<version>/<split>/ written by scribe/nemotron/reader.py
SYNTHETIC notes only.

    scribe/.venv/bin/python scribe/nemotron/cascade_agreement.py --version v3
"""

from __future__ import annotations

import argparse
import collections
import json
import sys

import common as C
import reader as R
from metrics import wilson
from protocol import classify

sys.path.insert(0, str(C.ROOT / "runs" / "diagnose"))
import resolve_relative  # noqa: E402  runs/diagnose/resolve_relative.py: repair(row, pred)

STUDENT = C.ROOT / "data/scribe/v3/student/C-270m-all-v2data"
BASELINE_JEV = "263/700 notes in the 'no edit needed' group with 7 errors (scribe/TEACHING.md, Jev scores at a 5% error target)"


def rate(k, n):
    w = wilson(k, n)
    return {"k": k, "n": n, "value": round(w["value"], 4) if n else None, "ci95": [round(x, 4) if x is not None else None for x in w["ci95"]]}


def gemma_predictions():
    out = {}
    for rec in json.loads((STUDENT / "val-records.json").read_text()):
        out[rec["id"]] = rec["prediction"]
    test = json.loads((STUDENT / "eval-test.json").read_text())
    for split in ("test_nemotron", "test_haiku"):
        for rec in test["splits"][split]["records"]:
            out[rec["id"]] = rec["prediction"]
    return out


def _label(x):
    """An event's type, or a route name for a wrong_route difference."""
    return x.get("type") if isinstance(x, dict) else x


def evaluate(rows, gemma, nemo):
    c = collections.Counter()
    by_writer = collections.defaultdict(collections.Counter)
    for row in rows:
        truth = json.loads(row["target_json"])
        g = resolve_relative.repair(row, gemma.get(row["id"]))
        n = nemo.get(row["id"])
        agree = g is not None and g == n
        w = "haiku_written" if row["writer"] == "claude-haiku-5-5" else "nemotron_written"
        for bucket in (c, by_writer[w]):
            bucket["notes"] += 1
            bucket["gemma_resolver_exact"] += g == truth
            bucket["nemotron_exact"] += n == truth
            bucket["prefilled"] += agree
            bucket["prefilled_correct"] += agree and g == truth
            bucket["prefilled_wrong"] += agree and g != truth
            bucket["flagged"] += not agree
            bucket["flagged_nemotron_exact"] += (not agree) and n == truth
            bucket["flagged_gemma_exact"] += (not agree) and g == truth
        if agree and g != truth:
            for d in classify(truth, g):
                c[f"agreed_wrong:{d['class']}:{_label(d['expected'])}->{_label(d['got'])}:{w}"] += 1

    def summary(x):
        return dict(
            notes=x["notes"],
            gemma_resolver_exact=rate(x["gemma_resolver_exact"], x["notes"]),
            nemotron_exact=rate(x["nemotron_exact"], x["notes"]),
            prefilled_for_one_click_confirmation=rate(x["prefilled"], x["notes"]),
            prefilled_and_correct=rate(x["prefilled_correct"], x["notes"]),
            error_among_prefilled=rate(x["prefilled_wrong"], x["prefilled"]),
            flagged_needs_editing=rate(x["flagged"], x["notes"]),
            flagged_where_nemotron_answer_is_exact=rate(x["flagged_nemotron_exact"], x["flagged"]),
            flagged_where_gemma_answer_is_exact=rate(x["flagged_gemma_exact"], x["flagged"]),
            per_100_notes_prefilled_correct=round(100 * x["prefilled_correct"] / x["notes"], 1) if x["notes"] else None,
        )

    agreed_wrong = {k.split(":", 1)[1]: v for k, v in sorted(c.items()) if k.startswith("agreed_wrong:")}
    return dict(all=summary(c), by_writer={w: summary(v) for w, v in sorted(by_writer.items())}, agreed_but_wrong_differences=agreed_wrong)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--version", default="v3")
    a = p.parse_args(argv)
    gemma = gemma_predictions()
    result = dict(
        title="Cascade agreement: Gemma 3 270M (C-270m-all-v2data) + code date resolver vs Nemotron 3.5 Super VL reader",
        synthetic="All notes are SYNTHETIC. A person confirms every note: agreement only decides whether the answer is pre-filled for one-click confirmation or flagged as needing editing.",
        rule="pre-filled for one-click confirmation when the two canonical answers are identical; otherwise flagged as needing editing (no threshold, nothing tuned)",
        nemotron_version=a.version,
        baseline_today=BASELINE_JEV,
        generated_utc=C.now().isoformat(timespec="seconds"),
    )
    for split in ("val", "test"):
        rows = R.load(split)
        nemo = {}
        for row in rows:
            path = R.cache_path(a.version, split, row["id"])
            if path.exists():
                nemo[row["id"]] = json.loads(path.read_text())["prediction"]
        missing = sum(r["id"] not in gemma for r in rows)
        result[split] = dict(missing_gemma=missing, missing_nemotron=len(rows) - len(nemo), **evaluate(rows, gemma, nemo))
    t = result["test"]["all"]
    h = result["test"]["by_writer"].get("haiku_written")
    result["statement"] = (
        f"Test (700 SYNTHETIC notes, rule fixed in advance): {t['prefilled_for_one_click_confirmation']['k']}/{t['notes']} notes are pre-filled for one-click confirmation "
        f"because Gemma + resolver and Nemotron agree; {t['error_among_prefilled']['k']} of those are wrong "
        f"({100 * (t['error_among_prefilled']['value'] or 0):.1f}%, Wilson {100 * t['error_among_prefilled']['ci95'][0]:.1f}-{100 * t['error_among_prefilled']['ci95'][1]:.1f}). "
        f"That is {t['per_100_notes_prefilled_correct']} of every 100 notes pre-filled correctly; the person still confirms each one. "
        f"The other {t['flagged_needs_editing']['k']} notes need editing; Nemotron's answer is exact on {t['flagged_where_nemotron_answer_is_exact']['k']} of them. "
        + (f"Haiku-written notes: {h['prefilled_for_one_click_confirmation']['k']}/{h['notes']} pre-filled, {h['error_among_prefilled']['k']} wrong among them. " if h else "")
        + f"Baseline today: {BASELINE_JEV}."
    )
    C.save(C.OUT / "cascade-agreement-v1.json", result)
    C.log(
        "4_cascade_agreement",
        command="scribe/.venv/bin/python scribe/nemotron/cascade_agreement.py " + " ".join(argv if argv is not None else sys.argv[1:]),
        inputs={"gemma": "data/scribe/v3/student/C-270m-all-v2data (+ runs/diagnose/resolve_relative.py repair)", "nemotron": f"data/scribe/nemotron/cache/{a.version}/"},
        outputs=["data/scribe/nemotron/cascade-agreement-v1.json"],
        metrics=dict(
            val_gemma_resolver_exact=result["val"]["all"]["gemma_resolver_exact"]["k"],
            test_gemma_resolver_exact=t["gemma_resolver_exact"]["k"],
            test_prefilled=t["prefilled_for_one_click_confirmation"]["k"],
            test_prefilled_wrong=t["error_among_prefilled"]["k"],
            val_prefilled=result["val"]["all"]["prefilled_for_one_click_confirmation"]["k"],
            val_prefilled_wrong=result["val"]["all"]["error_among_prefilled"]["k"],
        ),
        cost_usd=0,
    )
    print(result["statement"])
    print(json.dumps({s: {k: v for k, v in result[s]["all"].items()} for s in ("val", "test")}, indent=1))


if __name__ == "__main__":
    main()
