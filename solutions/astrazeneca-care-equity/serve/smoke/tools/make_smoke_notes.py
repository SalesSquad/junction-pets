#!/usr/bin/env python3
"""Write the 100 held-out notes of the serving smoke test: the first 50 rows of test_nemotron and the
first 50 rows of test_haiku, in file order (the same rows, loaded the same way, as the offline test
evaluation of scribe/v2/evaluate.py). Refuses to read a test split before the selection is frozen.

Run on the GPU box from /root/scribe-v2 with the training venv (needs pyarrow).
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path("/root/scribe-v2")
sys.path.insert(0, str(ROOT / "scribe" / "v2"))
frozen = json.loads((ROOT / "scribe/v2/artifacts/selection-frozen.json").read_text())
if not frozen.get("frozen"):
    sys.exit("selection is not frozen; test notes are not read")
import data_iface  # noqa: E402

PER_SPLIT = int(sys.argv[2]) if len(sys.argv) > 2 else 50
out = pathlib.Path(sys.argv[1])
lines, counts = [], {}
for split in ("test_nemotron", "test_haiku"):
    rows, source = data_iface.load_split(split)
    picked = rows[:PER_SPLIT]
    counts[split] = {"taken": len(picked), "of": len(rows), "source": source}
    for r in picked:
        lines.append(json.dumps({"id": r["id"], "split": split, "writer": r.get("writer"), "kind": r.get("kind"),
                                 "note_date": str(r["note_date"]), "note_text": r["note_text"],
                                 "target_json": r["target_json"], "distractors": r.get("distractors") or [],
                                 "date_forms": r.get("date_forms"), "synthetic": True}, ensure_ascii=False, default=str))
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"out": str(out), "n": len(lines), "splits": counts,
                  "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}))
