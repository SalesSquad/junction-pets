"""Post hoc: what a two-reader rule achieves with local readers only, compared with Gemma 1B + Nemotron.

Reads the stored outputs that scribe/v4/eval8.py scored (no model is run, no network). All notes are SYNTHETIC.
This was computed on 15 November 2026 after every result in data/scribe/v4/eval/results-v1.json existed, so it is
post hoc and was not preregistered. Nemotron wrote the stress notes, so its stress figures are optimistic.

    python3 scribe/v4/local_pairs.py      # writes data/scribe/v4/eval/local-pairs-posthoc-v1.json
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data/scribe/v4/eval/local-pairs-posthoc-v1.json"
sys.path.insert(0, str(ROOT / "scribe/v4"))
_spec = importlib.util.spec_from_file_location("eval8", ROOT / "scribe/v4/eval8.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

PAIRS = [
    ("C", "nemotron", None, "Gemma 3 1B + Nemotron 3.5 Super VL (the chosen rule)"),
    ("C", "A'", None, "local only: Gemma 3 1B + Gemma 3 270M with the frozen Finnish lexicon resolver"),
    ("C", "A'", "A'", "local only, as above, and the lexicon's vague-phrase flag sends the note to a person"),
    ("C", "B", None, "local only: Gemma 3 1B + Gemma 3 270M expression format"),
]


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k, n):
    return {"k": k, "n": n, "value": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def main():
    result = {"schema": "scribe-v4-local-pairs-posthoc-v1", "synthetic": True, "post_hoc": True,
              "person_confirms": "A person confirms every event; pre-filled means one-click confirmation, not skipped review.",
              "source": "stored outputs scored by scribe/v4/eval8.py (data/scribe/v4/eval/outputs, the Nemotron v3 cache)",
              "caveat": "Nemotron wrote the stress notes, so its stress figures are optimistic.", "sets": {}}
    for split in ("test", "stress"):
        rows = E.load_rows(split)
        preds, _missing = E.predictions(split, rows)
        ids = [r["id"] for r in rows]
        exact = {s: dict(zip(ids, E.exact_list(rows, p))) for s, p in preds.items()}
        res = {"notes": len(rows),
               "alone_exact": {s: rate(sum(exact[s].values()), len(rows)) for s in ("C", "A'", "nemotron")},
               "gemma_1b_alone_all_prefilled_wrong": rate(sum(not v for v in exact["C"].values()), len(rows)),
               "pairs": []}
        for a, b, block, what in PAIRS:
            agreed = [i for i in ids if preds[a][i]["pred"] is not None and preds[a][i]["pred"] == preds[b][i]["pred"]
                      and not (block and preds[block][i]["flag"])]
            wrong = sum(1 for i in agreed if not exact[a][i])
            res["pairs"].append({"readers": [a, b], "flag_blocks": block, "what": what,
                                 "prefilled": rate(len(agreed), len(rows)), "wrong_among_prefilled": rate(wrong, len(agreed))})
        result["sets"][split] = res
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    for split, res in result["sets"].items():
        for p in res["pairs"]:
            print(f"{split}: {'+'.join(p['readers'])}{' (flag blocks)' if p['flag_blocks'] else ''}: "
                  f"pre-filled {p['prefilled']['k']}/{p['prefilled']['n']}, wrong {p['wrong_among_prefilled']['k']}")


if __name__ == "__main__":
    main()
