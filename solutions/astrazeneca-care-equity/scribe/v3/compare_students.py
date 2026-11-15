"""Compare the round-2 students with the frozen version-2 selection on the same held-out notes.

Reads the per-note test evaluations written by scribe/v2/evaluate.py (copied from the GPU box to
data/scribe/v3/student/) and writes data/scribe/v3/student/compare-v1.json. Standard library only.

The comparisons and the multiplicity rule were fixed in data/scribe/v3/student/preregistration.json
before any of these runs had a result. All notes are SYNTHETIC; nothing here is for clinical use.

    python3 scribe/v3/compare_students.py
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[2]
STUDENT = ROOT / "data/scribe/v3/student"
DATASET = ROOT / "data/scribe/v3/dataset"
OUT = STUDENT / "compare-v1.json"
SPLITS = ("test_nemotron", "test_haiku")

REFERENCE = ("A-270m-lora-r16", STUDENT / "v2-selected/A-270m-lora-r16--test_nemotron+test_haiku--off.json")
PREREGISTERED = [
    ("V3-270m-nemotron", STUDENT / "V3-270m-nemotron/eval-test.json", "primary: + round-2 notes accepted by the Jev gate"),
    ("V3-270m-all", STUDENT / "V3-270m-all/eval-test.json", "secondary: + round-2 notes + version-2 Haiku notes"),
    ("C-270m-all-v2data", STUDENT / "C-270m-all-v2data/eval-test.json", "secondary: version-2 data with the Haiku notes"),
]
POSTHOC = [
    ("S-1b-lora-r16", STUDENT / "S-1b-lora-r16/eval-test.json",
     "size ladder, Gemma 3 1B: evaluated on test because it beat the reference on validation (pre-registered rule p < 0.05)"),
]


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def holm(pvalues):
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted = [None] * len(pvalues)
    running = 0.0
    m = len(pvalues)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def kinds():
    """id -> kind, read from the held-out parquet files (pyarrow if available)."""
    try:
        import pyarrow.parquet as pq
    except ImportError:  # pragma: no cover
        return {}
    out = {}
    for split in SPLITS:
        t = pq.read_table(DATASET / f"{split}.parquet", columns=["id", "kind"])
        out.update(zip(t.column("id").to_pylist(), t.column("kind").to_pylist()))
    return out


def load(path):
    d = json.loads(path.read_text())
    res = {}
    for split in SPLITS:
        m = d["splits"][split]["metrics"]
        res[split] = {
            "outcomes": dict(zip(m["ids"], m["outcomes"])),
            "exact": m["note_exact_match"],
            "event_f1": m.get("event_f1"),
            "route_accuracy": m.get("route_accuracy"),
            "invalid_output": m.get("invalid_output"),
        }
    return d, res


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarise(res, kind_of):
    out = {}
    pooled_k = pooled_n = 0
    for split in SPLITS:
        r = res[split]
        k = sum(1 for v in r["outcomes"].values() if v)
        n = len(r["outcomes"])
        pooled_k += k
        pooled_n += n
        by_kind = {}
        for i, v in r["outcomes"].items():
            kk = kind_of.get(i, "unknown")
            a = by_kind.setdefault(kk, [0, 0])
            a[0] += 1 if v else 0
            a[1] += 1
        out[split] = {
            "note_exact_match": {"k": k, "n": n, "value": k / n, "wilson95": wilson(k, n)},
            "event_f1": r["event_f1"],
            "route_accuracy": r["route_accuracy"],
            "invalid_output": r["invalid_output"],
            "by_kind": {kk: {"k": a[0], "n": a[1], "value": a[0] / a[1], "wilson95": wilson(a[0], a[1])} for kk, a in sorted(by_kind.items())},
        }
    out["pooled"] = {"note_exact_match": {"k": pooled_k, "n": pooled_n, "value": pooled_k / pooled_n, "wilson95": wilson(pooled_k, pooled_n)}}
    return out


def paired(ref, new):
    out = {}
    pooled_b = pooled_c = 0
    for split in SPLITS + ("pooled",):
        if split == "pooled":
            b, c = pooled_b, pooled_c
            n = sum(len(ref[s]["outcomes"]) for s in SPLITS)
        else:
            ro, no = ref[split]["outcomes"], new[split]["outcomes"]
            ids = [i for i in ro if i in no]
            if len(ids) != len(ro) or len(ids) != len(no):
                raise SystemExit(f"{split}: the two systems were not evaluated on the same notes")
            b = sum(1 for i in ids if no[i] and not ro[i])
            c = sum(1 for i in ids if ro[i] and not no[i])
            n = len(ids)
            pooled_b += b
            pooled_c += c
        out[split] = {"n": n, "only_new_correct": b, "only_reference_correct": c, "exact_mcnemar_p": mcnemar_exact(b, c),
                      "difference_in_exact_match": (b - c) / n}
    return out


def main():
    kind_of = kinds()
    ref_doc, ref = load(REFERENCE[1])
    result = {
        "schema": "scribe-v3-student-compare-v1",
        "synthetic": True,
        "not_for_clinical_use": True,
        "preregistration": {"file": "data/scribe/v3/student/preregistration.json", "sha256": sha256(STUDENT / "preregistration.json")},
        "decoding": "unconstrained greedy, tolerant parsing (the frozen version-2 setting)",
        "reference": {"run": REFERENCE[0], "file": str(REFERENCE[1].relative_to(ROOT)), "sha256": sha256(REFERENCE[1]), "summary": summarise(ref, kind_of)},
        "comparisons": [],
        "posthoc": [],
        "missing": [],
    }
    pre = []
    for name, path, what in PREREGISTERED:
        if not path.exists():
            result["missing"].append({"run": name, "reason": f"{path.relative_to(ROOT)} does not exist"})
            continue
        _, new = load(path)
        entry = {"run": name, "what": what, "file": str(path.relative_to(ROOT)), "sha256": sha256(path),
                 "summary": summarise(new, kind_of), "paired_vs_reference": paired(ref, new)}
        result["comparisons"].append(entry)
        pre.append(entry)
    adj = holm([e["paired_vs_reference"]["pooled"]["exact_mcnemar_p"] for e in pre])
    for e, a in zip(pre, adj):
        e["paired_vs_reference"]["pooled"]["holm_adjusted_p"] = a
    result["multiplicity"] = f"Holm over the {len(pre)} pre-registered comparisons that were run (pooled endpoint)"
    for name, path, what in POSTHOC:
        if not path.exists():
            result["missing"].append({"run": name, "reason": f"{path.relative_to(ROOT)} does not exist"})
            continue
        _, new = load(path)
        result["posthoc"].append({"run": name, "what": what, "file": str(path.relative_to(ROOT)), "sha256": sha256(path),
                                  "summary": summarise(new, kind_of), "paired_vs_reference": paired(ref, new)})
    OUT.write_text(json.dumps(result, indent=1) + "\n")
    for e in [{"run": REFERENCE[0], "summary": result["reference"]["summary"]}] + result["comparisons"] + result["posthoc"]:
        s = e["summary"]
        line = " | ".join(f"{sp} {s[sp]['note_exact_match']['k']}/{s[sp]['note_exact_match']['n']}" for sp in SPLITS + ("pooled",))
        p = e.get("paired_vs_reference", {}).get("pooled", {})
        print(f"{e['run']}: {line}" + (f" | pooled McNemar p {p['exact_mcnemar_p']:.4g}" + (f", Holm {p['holm_adjusted_p']:.4g}" if 'holm_adjusted_p' in p else "") if p else ""))
    if result["missing"]:
        print("missing:", result["missing"], file=sys.stderr)


if __name__ == "__main__":
    main()
