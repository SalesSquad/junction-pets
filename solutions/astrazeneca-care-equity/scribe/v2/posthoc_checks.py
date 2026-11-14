"""Post-hoc checks of the finished version-2 ablation, from files already in the repository.

Written for the version-2 review (runs/review-findings-v2.json). Nothing is trained or decoded; every
figure is recomputed from saved per-note records. All notes are SYNTHETIC; not for clinical use.

    scribe/.venv/bin/python scribe/v2/posthoc_checks.py            # writes data/scribe/v2/posthoc-checks-v1.json
    scribe/.venv/bin/python scribe/v2/posthoc_checks.py --resummarise

--resummarise re-runs run_ablation.test_summary on the saved test evaluation files and replaces the
test summaries in data/scribe/v2/ablation-v1.json (finding 6: the in-sample risk_coverage figure is
dropped; finding 4: unparsable answers are split by cause). It refuses to write if any other field of
a regenerated summary differs from the stored one, so no reported number can change.

posthoc-checks-v1.json holds:
- decoding_check_audit (finding 3): how the two arms of the constrained-decoding check were decoded,
  how many raw answers differ, and how many notes the constraint could have changed at most;
- v1_overlap (finding 7): exact match on the test_nemotron notes that version 1 had already scored,
  and on the others.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib

import _paths  # noqa: F401  (puts scribe/ and scribe/v2 on sys.path)
import run_ablation as ra

ROOT = pathlib.Path(__file__).resolve().parents[2]
ABLATION = ROOT / "data/scribe/v2/ablation-v1.json"
EVALS = ROOT / "data/scribe/v2/ablation-runs/evaluations"
OUT = ROOT / "data/scribe/v2/posthoc-checks-v1.json"
# The in-process (train.py) validation records of the selected run, copied back from the GPU box.
SELECTED_VAL_RECORDS = ROOT / "data/scribe/v3/student/v2-selected/val-records.json"
SELECTED_RESULT = ROOT / "data/scribe/v3/student/v2-selected/result.json"
V1_EVAL = ROOT / "data/scribe/eval-v1.json"


def load(path):
    return json.loads(pathlib.Path(path).read_text())


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def rel(path):
    return str(pathlib.Path(path).resolve().relative_to(ROOT))


def eval_file(name, splits, mode):
    return EVALS / f"{name}--{'+'.join(splits)}--{mode}.json"


def resummarise():
    out = load(ABLATION)
    test = out["test"]
    changed = {}
    for label, system in test["systems"].items():
        path = eval_file(system["system"]["name"], list(system["splits"]), test["decoding"])
        evaluation = load(path)
        for split, stored in system["splits"].items():
            fresh = ra.test_summary(evaluation["splits"][split])
            for key, value in fresh.items():
                if key == "unparsable_by_cause":
                    continue
                if stored.get(key) != value:
                    raise SystemExit(f"{label}/{split}: field {key!r} would change; nothing written")
            dropped = sorted(set(stored) - set(fresh))
            system["splits"][split] = fresh
            changed[f"{label}/{split}"] = {"source": rel(path), "source_sha256": sha(path), "dropped": dropped,
                                           "added": ["unparsable_by_cause"]}
    test["resummarised"] = {
        "utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": "scribe/v2/posthoc_checks.py --resummarise (review findings 4 and 6)",
        "rule": "run_ablation.test_summary re-run on the saved evaluation files; every retained field is identical "
                "to the stored value; risk_coverage (chosen on the reported notes themselves) removed; "
                "unparsable_by_cause added",
        "splits": changed,
    }
    ABLATION.write_text(json.dumps(out, indent=1) + "\n")
    return changed


def decoding_check_audit():
    unconstrained = {r["id"]: r for r in load(SELECTED_VAL_RECORDS)}
    result = load(SELECTED_RESULT)
    m = result["val"]["metrics"]
    free_ok = dict(zip(m["ids"], m["outcomes"]))
    path = eval_file("A-270m-lora-r16", ["val_nemotron", "val_haiku"], "auto")
    constrained_eval = load(path)
    constrained, con_ok, con_cap = {}, {}, {}
    for split, block in constrained_eval["splits"].items():
        for rec in block["records"]:
            constrained[rec["id"]] = rec
        con_ok.update(zip(block["metrics"]["ids"], block["metrics"]["outcomes"]))
        con_cap[split] = block["decoding"]["max_new_tokens"]
    ids = sorted(unconstrained)
    if sorted(constrained) != ids:
        raise SystemExit("the two arms were not decoded on the same validation notes")
    differ = [i for i in ids if unconstrained[i]["raw"] != constrained[i]["raw"]]
    free_invalid = [i for i in ids if unconstrained[i]["prediction"] is None]
    differ_free_valid = [i for i in differ if unconstrained[i]["prediction"] is not None and unconstrained[i]["parse_mode"] == "strict"]
    return {
        "unconstrained_arm": {"decoder": "scribe/v2/train.py in-process generation after training",
                              "records": rel(SELECTED_VAL_RECORDS), "max_new_tokens": result.get("max_new_tokens")},
        "constrained_arm": {"decoder": "scribe/v2/evaluate.py, one call per validation split",
                            "file": rel(path), "max_new_tokens_by_split": con_cap},
        "n": len(ids),
        "raw_identical": len(ids) - len(differ),
        "raw_differ": len(differ),
        "raw_differ_although_unconstrained_answer_was_valid_strict_json": len(differ_free_valid),
        "unconstrained_unparsable": len(free_invalid),
        "max_notes_the_constraint_could_change": len(free_invalid),
        "max_notes_note": "with greedy decoding the constraint only alters an answer that the unconstrained model "
                          "would make invalid; every other difference comes from the decoder, batching or token cap",
        "differing_notes_correct_unconstrained": sum(1 for i in differ if free_ok[i]),
        "differing_notes_correct_constrained": sum(1 for i in differ if con_ok[i]),
        "unparsable_unconstrained_correct_under_constraint": sum(1 for i in free_invalid if con_ok[i]),
        "discordant": {"only_constrained_correct": sum(1 for i in ids if con_ok[i] and not free_ok[i]),
                       "only_unconstrained_correct": sum(1 for i in ids if free_ok[i] and not con_ok[i])},
    }


def v1_overlap():
    out = load(ABLATION)
    seen = {p["id"] for p in load(V1_EVAL)["predictions"]}
    res = {"v1_scored_ids": len(seen), "source": rel(V1_EVAL), "systems": {}}
    for label, system in out["test"]["systems"].items():
        block = system["splits"]["test_nemotron"]
        pairs = list(zip(block["ids"], block["outcomes"]))
        inside = [o for i, o in pairs if i in seen]
        outside = [o for i, o in pairs if i not in seen]
        res["systems"][label] = {
            "test_nemotron_n": len(pairs),
            "scored_by_v1": {"k": sum(inside), "n": len(inside), "wilson95": ra_wilson(sum(inside), len(inside))},
            "never_scored_before": {"k": sum(outside), "n": len(outside), "wilson95": ra_wilson(sum(outside), len(outside))},
        }
    return res


def ra_wilson(k, n):
    from metrics import wilson  # scribe/metrics.py

    w = wilson(k, n)
    return w.get("ci95") if isinstance(w, dict) else w


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resummarise", action="store_true")
    a = ap.parse_args()
    if a.resummarise:
        changed = resummarise()
        print(f"resummarised {len(changed)} test splits in {rel(ABLATION)}")
    report = {
        "schema": "scribe-v2-posthoc-checks-v1",
        "synthetic": True,
        "not_for_clinical_use": True,
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scribe/v2/posthoc_checks.py",
        "ablation_sha256": sha(ABLATION),
        "decoding_check_audit": decoding_check_audit(),
        "v1_overlap": v1_overlap(),
    }
    OUT.write_text(json.dumps(report, indent=1) + "\n")
    print(f"wrote {rel(OUT)}")


if __name__ == "__main__":
    main()
