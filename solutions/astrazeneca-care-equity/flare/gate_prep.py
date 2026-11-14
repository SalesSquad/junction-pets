"""Comparability gate, step 1: per-county scribe error partitions (SYNTHETIC notes only; no model is run).

Reads the STORED per-note predictions of the scribe run C-270m-all-v2data
(data/scribe/v3/student/C-270m-all-v2data/eval-test.json, 700 SYNTHETIC test notes) and the gold keys
(data/scribe/v3/dataset/test_*.parquet). Two arms, both pure code over the stored predictions:
  raw      : the stored prediction as the scribe wrote it;
  resolver : the same prediction after runs/diagnose/resolve_relative.py `repair` (relative-date resolver).
Each note is analysed with runs/diagnose/diagnose.py `analyse` and `intervals`, the functions that produced
runs/diagnose/notes-*.jsonl and intervals-*.json, so the arm totals must equal the published 305/700 (raw)
and 651/700 (resolver) exact notes; the script stops if they do not.

County assignment (SYNTHETIC, deterministic): the notes carry no county. Notes are sorted by their SHA-256
id and note k goes to COUNTIES[k mod 23] (HVA01..HVA21, HVA90, HVA91), so every county gets 30 or 31
notes and the assignment does not depend on note content, writer or result.

Writes data/flare/gate-sites/county=<code>/scribe.json (one partition per simulated site) and
data/flare/gate-sites/assignment.json. Each partition holds, per arm:
  events    : one row per gold event, missed = 1 when the event was not found with its correct type
              (status missing, wrong_type, type_and_date_wrong, or the whole note failed to parse);
  intervals : one row per within-note pair of DAY-precision gold events whose two endpoints were found
              (diagnose.intervals found == True): true_days, pred_days, err = pred_days - true_days.

Run: flare/.venv/bin/python flare/gate_prep.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "runs" / "diagnose"))

COUNTIES = [f"HVA{i:02}" for i in range(1, 22)] + ["HVA90", "HVA91"]
RUN = "C-270m-all-v2data"
PRED = ROOT / "data/scribe/v3/student" / RUN / "eval-test.json"
OUT = ROOT / "data/flare/gate-sites"
FOUND = ("exact", "date_wrong", "precision_only")
EXPECTED_EXACT = {"raw": 305, "resolver": 651}  # runs/diagnose/resolve-relative-v1.json, C-270m-all-v2data test_pooled


def assign(ids):
    """Deterministic, content-blind county assignment: sorted id rank modulo 23."""
    return {i: COUNTIES[k % len(COUNTIES)] for k, i in enumerate(sorted(ids))}


def note_rows(note):
    """Event rows (missed flag) and found-interval rows for one analysed note (diagnose.analyse output)."""
    import diagnose as D

    if "parse_failure" in note["cats"]:
        events = [dict(missed=1, status="parse_failure") for _ in range(note["n_gold"])]
        return events, []
    events = [dict(missed=0 if e["status"] in FOUND else 1, status=e["status"]) for e in note["events"]]
    ivs = [dict(true_days=q["true_days"], pred_days=q["pred_days"], err=q["err"]) for q in D.intervals(note) if q["found"]]
    return events, ivs


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    import diagnose as D
    import resolve_relative as R

    gold = D.load_gold()
    t = json.loads(PRED.read_text())
    recs = [r for s in ("test_nemotron", "test_haiku") for r in t["splits"][s]["records"]]
    county = assign([r["id"] for r in recs])
    sites = {c: dict(notes=0, writers={}, arms={a: dict(events=[], intervals=[], exact_notes=0) for a in EXPECTED_EXACT}) for c in COUNTIES}
    exact = {a: 0 for a in EXPECTED_EXACT}
    for rec in recs:
        row = gold[rec["id"]]
        c = county[rec["id"]]
        s = sites[c]
        s["notes"] += 1
        w = "haiku" if "haiku" in row["writer"] else "nemotron"
        s["writers"][w] = s["writers"].get(w, 0) + 1
        for arm in EXPECTED_EXACT:
            rr = rec if arm == "raw" else dict(rec, prediction=R.repair(row, rec["prediction"]))
            note = D.analyse(row, rr)
            exact[arm] += bool(note["exact"])
            s["arms"][arm]["exact_notes"] += bool(note["exact"])
            ev, iv = note_rows(note)
            for x in ev + iv:
                x["note"] = rec["id"][:12]
            s["arms"][arm]["events"].extend(ev)
            s["arms"][arm]["intervals"].extend(iv)
    if exact != EXPECTED_EXACT:
        raise SystemExit(f"arm totals {exact} differ from the published {EXPECTED_EXACT}; stop")
    sources = {str(p.relative_to(ROOT)): sha256(p) for p in [PRED, ROOT / "data/scribe/v3/dataset/test_nemotron.parquet",
                                                              ROOT / "data/scribe/v3/dataset/test_haiku.parquet",
                                                              ROOT / "runs/diagnose/diagnose.py", ROOT / "runs/diagnose/resolve_relative.py"]}
    for c, s in sites.items():
        d = OUT / f"county={c}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "scribe.json").write_text(json.dumps(dict(synthetic=True, county=c, run=RUN, assignment="sorted-id rank mod 23",
                                                       sources_sha256=sources, **s)) + "\n")
    (OUT / "assignment.json").write_text(json.dumps(dict(
        synthetic=True, run=RUN, method="notes sorted by SHA-256 id; note k -> COUNTIES[k mod 23]",
        counties=COUNTIES, exact_notes=exact, sources_sha256=sources,
        notes_per_county={c: s["notes"] for c, s in sites.items()},
        writers_per_county={c: s["writers"] for c, s in sites.items()},
        note_to_county={i[:12]: c for i, c in sorted(county.items())}), indent=1) + "\n")
    print(json.dumps(dict(exact_notes=exact, notes=len(recs), counties=len(COUNTIES),
                          notes_per_county=[min(s["notes"] for s in sites.values()), max(s["notes"] for s in sites.values())])))


if __name__ == "__main__":
    main()
