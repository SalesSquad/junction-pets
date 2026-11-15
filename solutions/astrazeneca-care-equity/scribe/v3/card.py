"""Write data/scribe/v3/dataset/CARD.md from dataset-stats.json and gate-v1.json (no number is typed by hand).

  scribe/.venv/bin/python scribe/v3/card.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import AUDIT, CURRICULA, DATASET_V3, GATE, log  # noqa: E402

FILES = ("train", "val", "test_nemotron", "test_haiku", "rejected")


def f(x):
    return f"{x['numerator']}/{x['denominator']}"


def audit_lines():
    """The audit paragraph, read from audit-v1.json."""
    p = AUDIT / "audit-v1.json"
    if not p.exists():
        return ["- No human has read these notes. The audit (`data/scribe/v3/audit/`) has not been scored; the label-error rate of round 2 is not measured."]
    a = json.loads(p.read_text())
    g = lambda x: f"{x['numerator']}/{x['denominator']} ({x['share']:.3f}; Wilson 95% {x['wilson95'][0]:.3f} to {x['wilson95'][1]:.3f})"
    acc, rej = a["by_status"]["accepted"], a["by_status"]["rejected"]
    return [
        "- No human has read these notes. The audit (`data/scribe/v3/audit/audit-v1.json`) was made by language-model readers (Claude Haiku) who saw the claimed labels:",
        f"  accepted notes (sample of {acc['notes_in_sample']}): wrong label {g(acc['wrong_label'])}; wrong label or route not supported {g(acc['wrong_label_or_route_not_ok'])}; clean in the strict sense {g(acc['clean_strict'])}.",
        f"  Notes the rule rejected (sample of {rej['notes_in_sample']}): wrong label {g(rej['wrong_label'])}; wrong label or route not supported {g(rej['wrong_label_or_route_not_ok'])}; clean in the strict sense {g(rej['clean_strict'])}.",
        "  The intervals overlap: this sample does not show that the rule separates wrong-label notes from good ones, and it rejected mostly good notes. Quote the per-status rows, not the pooled row.",
    ]


def main():
    s = json.loads((DATASET_V3 / "dataset-stats.json").read_text())
    g = json.loads((GATE / "gate-v1.json").read_text())
    r2, o, th = s["round2"], g["overall"], g["policy"]["thresholds"]["jev"]
    t = o["readback_vs_rule"]
    lines = [
        "# SAMA pathway scribe dataset v3",
        "",
        "SYNTHETIC ONLY. Every note is invented text written by a language model from a sampled answer key.",
        "No real patients, clinicians or patient text. A research artefact, not a medical device, and not for clinical use.",
        "",
        "Version 3 = version 2 plus the notes of teaching round 2: NVIDIA Nemotron 3.5 Super VL (served on Verda)",
        "wrote one note per specification in five curricula, read each note back blind, and rewrote it once when the",
        "code check failed or the read-back disagreed with the answer key. A note enters `train` when its kept version",
        "passed the round-2 code check and the",
        "judge rule below. The held-out files are the version-2 files, byte for byte, so a version-3 student is",
        "compared with the version-2 student on the same notes.",
        "",
        "## Files",
        "",
        "| file | rows | of which version 2 | round 2 | byte-identical to version 2 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for n in FILES:
        x = s["files"][n]
        lines.append(f"| `{n}.parquet` | {x['rows']} | {x['v2_rows']} | {x['round2_rows']} | {'yes' if x['byte_identical_to_v2'] else 'no'} |")
    lines += [
        "",
        f"- `train` = the {s['checks']['train_rows_from_v2']} version-2 train rows, unchanged and first, then the "
        f"{s['checks']['train_rows_from_round2']} accepted round-2 notes.",
        "- `val`, `test_nemotron`, `test_haiku` = copies of the version-2 files (same SHA-256).",
        f"- `rejected` = the version-2 rejected rows, then {r2['added_to_rejected']} round-2 notes "
        f"(`reject_stage` code_check {r2['rejected_by_stage'].get('code_check', 0)}, verifier {r2['rejected_by_stage'].get('verifier', 0)}). Not for training.",
        f"- `round2.jsonl` = side file with one line per round-2 specification ({r2['side_file_rows']}), keyed by `id`: `round`, `curriculum`, `kind`, `focus`,",
        "  `code_check_passed`, `readback_consistent`, `repaired`, `told_order`, `words`, `rule`, `rule_pass`, `decisions_pass`, `file`.",
        "  The parquet files keep exactly the version-2 columns and types, so `round` and `curriculum` live here.",
        "- `dataset-stats.json` = the counts, the SHA-256 of every file and the results of the checks.",
        "",
        "The build (`scribe/v3/build_dataset.py`) asserts that no id of `train` occurs in `val` or a test file, that no note",
        "text occurs on both sides or twice in `train`, that no id occurs in two files, and that every expression target",
        "resolves to its `target_json`. For a note with events the id is the SHA-256 of its answer key.",
        "",
        "## Columns",
        "",
        "The same as version 2, in the same order: " + ", ".join(f"`{c}`" for c in s["columns"]) + ".",
        "For round-2 rows `verifier_probabilities` holds the Jev answers of the gate (`event_<i>`, `unlisted`, `route` =",
        "probability of the claimed route); `writer` and `teacher_model` are `nemotron-3.5-super-vl`; `kind` is",
        "`standard` for the curricula hard_standard, long_multi_visit and terse.",
        "",
        "## The gate of round 2",
        "",
        f"Rule (`{g['policy']['file']}`): TypeSafe Jev alone, question set {g['policy']['jev_question_set']} (code adds each",
        f"date's day offset to the question). A note passes when every event probability is at least {th['event_min']}, the",
        f"probability of an unlisted event is below {th['unlisted_max']} and the chosen route is the claimed one.",
        "",
        "| curriculum | candidates | code check | read-back consistent | accepted by Jev = rule | accepted by Decisions (prefix only) | in train |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, b in [("all", o)] + [(c, g["per_curriculum"][c]) for c in CURRICULA]:
        lines.append(
            f"| {name} | {b['candidates']} | {f(b['code_check_pass'])} | {f(b['readback_consistent'])} | {f(b['jev']['accepted'])} | "
            f"{f(b['decisions']['accepted'])} | {b['rule']['accepted_of_candidates']['numerator']} |"
        )
    lines += [
        "",
        "Read-back against the rule, over the notes that passed the code check: consistent and accepted "
        f"{t['readback_consistent_rule_accept']}, consistent and rejected {t['readback_consistent_rule_reject']}, inconsistent and accepted "
        f"{t['readback_inconsistent_rule_accept']}, inconsistent and rejected {t['readback_inconsistent_rule_reject']}.",
        "",
        "## Known limits",
        "",
        f"- {r2['added_to_train_readback_inconsistent']} accepted round-2 notes have a read-back that disagrees with the answer key. They are in `train`",
        "  because the rule accepted them; `round2.jsonl` (`readback_consistent`) lets a trainer leave them out.",
        "- The rule's thresholds were chosen on notes with 2 to 8 events. No no_event, terse or long note was in that",
        "  benchmark, so the rule is not calibrated for those curricula. For a no_event note it reduces to the unlisted-event",
        f"  question and the route; it accepted {g['per_curriculum']['no_event']['jev']['accepted']['numerator']} of {g['per_curriculum']['no_event']['jev']['accepted']['denominator']} no_event notes, while the teacher's own read-back agreed with",
        f"  the empty answer for {g['per_curriculum']['no_event']['readback_consistent']['numerator']} of {g['per_curriculum']['no_event']['readback_consistent']['denominator']}.",
        f"- OpenAI Decisions is not part of the rule. It was asked for the first {o['decisions']['asked']} notes of a fixed hash order only.",
        "- The round-2 code check allows 110-260 words for long_multi_visit and 25-90 for terse; version 2 used 60-140.",
        f"- {r2['added_to_train_starts_with_style_label']} accepted round-2 notes begin with the literal style label (for example 'Lähetekirje'), a formatting artefact "
        f"that no version-2 train note and no held-out note has (by curriculum: {r2['added_to_train_starts_with_style_label_by_curriculum']}). The code check and the rule do not catch it, and "
        "  `train.parquet` still holds them, unchanged, because a student run was pre-registered against this file. `round2.jsonl` (`starts_with_style_label`) lets a trainer leave them out. "
        "A student can learn a label-to-route shortcut from them; the held-out files cannot reveal that.",
        "- The held-out files are the version-2 files: all notes have 60 to 135 words. Round-2 terse notes have 25 to 49 words and long_multi_visit notes 110 to 260, so these files cannot measure what the new curricula teach. No held-out set for terse or long notes exists yet.",
        "- The benchmark behind the rule used clean notes that the version-2 Jev gate had already accepted, so its false-reject share is biased low and its noise_after figures are not a property of this data. See `scribe/judges/RESULTS.md`.",
        *audit_lines(),
        f"Generated {s['generated']} from `data/scribe/v3/gate/gate-v1.json` and `dataset-stats.json`.",
        "",
    ]
    (DATASET_V3 / "CARD.md").write_text("\n".join(lines))
    log("card", inputs=["data/scribe/v3/dataset/dataset-stats.json", "data/scribe/v3/gate/gate-v1.json"], outputs=["data/scribe/v3/dataset/CARD.md"], metrics=dict(lines=len(lines)), cost_usd=0, status="ok")


if __name__ == "__main__":
    main()
