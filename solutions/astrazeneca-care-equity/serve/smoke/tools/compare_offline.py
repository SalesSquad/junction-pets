#!/usr/bin/env python3
"""Compare served answers (serve/smoke_test.py --results-out) with the offline test evaluation of the
same system (scribe/v2/evaluate.py output), note by note. Standard library only.

usage: compare_offline.py notes.jsonl served-results.jsonl offline-eval.json [label]
"""
import json
import sys

notes = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
served = [json.loads(l) for l in open(sys.argv[2], encoding="utf-8") if l.strip()]
offline = json.load(open(sys.argv[3], encoding="utf-8"))
label = sys.argv[4] if len(sys.argv) > 4 else ""
assert len(notes) == len(served), (len(notes), len(served))
records = {}
decoding = {}
for split, block in offline["splits"].items():
    decoding[split] = {"constraint": block["decoding"]["constraint"], "max_new_tokens": block["decoding"]["max_new_tokens"]}
    for rec in block["records"]:
        records[rec["id"]] = rec
out = {"label": label, "n": len(notes), "offline_system": offline.get("system", {}).get("name"), "offline_decoding": decoding,
       "by_split": {}}
tot = {"n": 0, "same_prediction": 0, "served_exact": 0, "offline_exact": 0, "both_exact": 0, "served_only_exact": 0,
       "offline_only_exact": 0, "neither_exact": 0, "same_raw_text": 0, "served_invalid": 0, "offline_invalid": 0, "missing_offline": 0}
by = {}
differing = []
for note, res in zip(notes, served):
    assert note["id"] == res["id"], "served results are not aligned with the notes"
    t = by.setdefault(note["split"], dict.fromkeys(tot, 0))
    rec = records.get(note["id"])
    truth = json.loads(note["target_json"])
    for d in (tot, t):
        d["n"] += 1
    if rec is None:
        for d in (tot, t):
            d["missing_offline"] += 1
        continue
    s, o = res["canonical"], rec["prediction"]
    s_ok, o_ok = s == truth, o == truth
    flags = {"same_prediction": s == o, "served_exact": s_ok, "offline_exact": o_ok, "both_exact": s_ok and o_ok,
             "served_only_exact": s_ok and not o_ok, "offline_only_exact": o_ok and not s_ok,
             "neither_exact": not s_ok and not o_ok, "same_raw_text": (res.get("raw") or "").strip() == (rec.get("raw") or "").strip(),
             "served_invalid": s is None, "offline_invalid": o is None}
    for d in (tot, t):
        for k, v in flags.items():
            d[k] += bool(v)
    if s != o and len(differing) < 5:
        differing.append({"id": note["id"], "split": note["split"], "served_raw": res.get("raw"), "offline_raw": rec.get("raw")})
out["pooled"] = tot
out["by_split"] = by
n = tot["n"] - tot["missing_offline"]
out["agreement_same_prediction"] = tot["same_prediction"] / n if n else None
out["agreement_same_outcome"] = (tot["both_exact"] + tot["neither_exact"]) / n if n else None
out["served_exact_match"] = tot["served_exact"] / n if n else None
out["offline_exact_match_same_notes"] = tot["offline_exact"] / n if n else None
out["first_differing_notes"] = differing
print(json.dumps(out, indent=2, ensure_ascii=False))
