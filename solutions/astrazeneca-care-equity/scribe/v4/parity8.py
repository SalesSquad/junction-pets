"""Step 8 engine parity: batched MLX decoding (scribe/v4/binfer.py) against step 3's single-sequence outputs on the
same 310 SYNTHETIC validation notes, before any test or stress output is read.

Compares, per arm: identical raw text, identical code-resolved prediction, and exact match under each engine.
Writes data/scribe/v4/eval/parity-v1.json and one line to runs/laneA-step8.jsonl.

  scribe/.venv/bin/python scribe/v4/parity8.py
"""

from __future__ import annotations

import json
import sys

import eval8 as E


def main():
    rows = E.load_rows("val")
    doc = {"schema": "scribe-v4-engine-parity-v1", "synthetic": True, "created_utc": E.now(),
           "question": "Does batched MLX decoding reproduce step 3's single-sequence validation outputs?", "arms": {}}
    for arm in E.MLX_ARMS:
        single = E.read_outputs(E.STEP3_OUT / arm / "val.jsonl")
        batch = E.read_outputs(E.EVAL / "parity" / arm / "val-batch.jsonl")
        same_raw = same_pred = ex_s = ex_b = 0
        diffs = []
        for row in rows:
            s, b = single[row["id"]], batch[row["id"]]
            ps = E.primary(E.parse_arm(arm, s["raw"], row))
            pb = E.primary(E.parse_arm(arm, b["raw"], row))
            gold = json.loads(row["target_json"])
            same_raw += s["raw"] == b["raw"]
            same_pred += ps == pb
            ex_s += ps == gold
            ex_b += pb == gold
            if ps != pb:
                diffs.append({"id": row["id"][:16], "single_exact": ps == gold, "batch_exact": pb == gold})
        doc["arms"][arm] = {"notes": len(rows), "same_raw_text": same_raw, "same_resolved_prediction": same_pred,
                            "exact_single": ex_s, "exact_batch": ex_b, "differing_predictions": diffs}
    E.save_json(E.EVAL / "parity-v1.json", doc)
    E.log("parity", "scribe/.venv/bin/python scribe/v4/parity8.py",
          inputs={"single": "data/scribe/v4/mlx/outputs/<arm>/val.jsonl", "batch": "data/scribe/v4/eval/parity/<arm>/val-batch.jsonl"},
          outputs={"file": "data/scribe/v4/eval/parity-v1.json"},
          metrics={a: {k: v for k, v in r.items() if k != "differing_predictions"} for a, r in doc["arms"].items()})
    print(json.dumps({a: {k: v for k, v in r.items() if k != "differing_predictions"} for a, r in doc["arms"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
