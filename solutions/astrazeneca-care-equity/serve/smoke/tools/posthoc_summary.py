#!/usr/bin/env python3
"""Summarise the post-hoc validation-only runs with the ablation's own functions (run_summary, val_view,
compare). Reads result.json files only; never touches a test split. Run from /root/scribe-v2."""
import json
import pathlib
import sys

sys.path.insert(0, "scribe/v2")
import run_ablation as ra  # noqa: E402

art = pathlib.Path("scribe/v2/artifacts")
control_dir = pathlib.Path(sys.argv[1])
control = json.loads((control_dir / "result.json").read_text())
out = {"control": control["config"]["name"], "control_val_exact_match": control["val"]["metrics"]["note_exact_match"],
       "runs": {}}
for d in sorted((art / "posthoc").glob("*")):
    if not d.is_dir():
        continue
    rp = d / "result.json"
    name = d.name
    if not rp.exists():
        tail = (d / "train.log").read_text(errors="replace")[-600:] if (d / "train.log").exists() else ""
        out["runs"][name] = {"status": "no result.json (cut by the deadline or failed)", "log_tail": tail}
        continue
    r = json.loads(rp.read_text())
    s = ra.run_summary(r)
    if s.get("val"):
        s["val"].pop("outcomes", None)
    entry = {"summary": s, "eligible": ra.eligible(r)}
    if ra.eligible(r):
        try:
            entry["paired_vs_control"] = ra.compare(ra.val_view(r), ra.val_view(control))
        except ValueError as e:
            entry["paired_vs_control"] = {"error": str(e)}
    out["runs"][name] = entry
print(json.dumps(out, indent=2, ensure_ascii=False))
