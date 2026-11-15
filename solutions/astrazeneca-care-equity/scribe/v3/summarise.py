"""Write data/scribe/v3/summary-v1.json: one flat file for the product's build step.

  scribe/.venv/bin/python scribe/v3/summarise.py

Every value is copied by code from the file named in `_sources`; nothing is typed by hand. A part whose source
file does not exist is null and has a reason under `_not_done`. Share objects {numerator, denominator, share|rate}
become three keys: <key>.n, <key>.d, <key>.share. All data are SYNTHETIC; nothing is for clinical use.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, CURRICULA, log, now, save_json  # noqa: E402

V3 = ROOT / "data/scribe/v3"
SOURCES = dict(
    teacher="data/scribe/v3/teacher/stats.json",
    teacher_ledger="data/scribe/v3/teacher/ledger.json",
    bench="data/scribe/v3/judges/benchmark-v1.json",
    policy="data/scribe/v3/judges/policy.json",
    gate="data/scribe/v3/gate/gate-v1.json",
    dataset="data/scribe/v3/dataset/dataset-stats.json",
    audit="data/scribe/v3/audit/audit-v1.json",
    ts="data/scribe/v3/judges/usage-typesafe.json",
    oa="data/scribe/v3/judges/usage-openai.json",
    student="data/scribe/v3/student/compare-v1.json",
    cascade="data/scribe/v3/cascade/cascade-v1.json",
)
STUDENT_RESULT = "data/scribe/v3/student/{}/result.json"
OUT, SRC, NOT_DONE, DOCS = {}, {}, {}, {}
_cache = {}


def load(name):
    if name not in _cache:
        p = ROOT / SOURCES[name]
        _cache[name] = json.loads(p.read_text()) if p.exists() else None
    return _cache[name]


def dig(obj, path):
    """Follow a dotted path; a key may itself contain dots (for example 'e=0.05'); a number indexes a list."""
    if not path:
        return obj
    parts = path.split(".")
    for i in range(1, len(parts) + 1):
        key = ".".join(parts[:i])
        if isinstance(obj, dict) and key in obj:
            try:
                return dig(obj[key], ".".join(parts[i:]))
            except KeyError:
                continue
        if isinstance(obj, list) and key.isdigit() and int(key) < len(obj):
            try:
                return dig(obj[int(key)], ".".join(parts[i:]))
            except KeyError:
                continue
    raise KeyError(path)


def put(key, src, path, doc=None):
    """Copy one value. A share object (numerator/denominator or k/n) is flattened."""
    data = load(src)
    if data is None:
        OUT[key] = None
        NOT_DONE[key] = f"source file {SOURCES[src]} does not exist"
        return
    try:
        v = dig(data, path)
    except (KeyError, TypeError):
        OUT[key] = None
        NOT_DONE[key] = f"{path} is not present in {SOURCES[src]}"
        return
    where = f"{SOURCES[src]}#{path}"
    if isinstance(v, dict) and {"numerator", "denominator"} <= set(v):
        OUT[key + ".n"], OUT[key + ".d"] = v["numerator"], v["denominator"]
        OUT[key + ".share"] = v.get("share", v.get("rate"))
        for s in (".n", ".d", ".share"):
            SRC[key + s] = where
        if "wilson95" in v:
            OUT[key + ".wilson95"] = v["wilson95"]
            SRC[key + ".wilson95"] = where
    elif isinstance(v, dict) and {"k", "n"} <= set(v):
        OUT[key + ".n"], OUT[key + ".d"] = v["k"], v["n"]
        OUT[key + ".share"] = v.get("share", v.get("value"))  # compare-v1.json names the share 'value'
        OUT[key + ".wilson95"] = v.get("wilson95")
        for s in (".n", ".d", ".share", ".wilson95"):
            SRC[key + s] = where
    else:
        OUT[key] = v
        SRC[key] = where
    if doc:
        DOCS[key] = doc


def null(key, reason):
    OUT[key] = None
    NOT_DONE[key] = reason


def main():
    OUT["synthetic_only"] = True
    SRC["synthetic_only"] = "constant: every note in this project is written by a language model from a sampled answer key"
    OUT["not_for_clinical_use"] = True
    OUT["generated_utc"] = now()

    # teacher round 2
    for k in ("specifications.built", "specifications.completed", "specifications.not_completed"):
        put("teacher." + k, "teacher", k)
    put("teacher.requests_ledger", "teacher", "requests.teacher_requests_ledger")
    put("teacher.requests_cap", "teacher", "requests.cap")
    put("teacher.wall_seconds_total", "teacher", "wall_seconds.total")
    for m in ("code_check_pass_first_attempt", "code_check_pass_final", "readback_consistent_first_attempt", "readback_consistent_final",
              "clean_first_attempt", "clean_final", "repair_attempted", "repair_success"):
        put(f"teacher.overall.{m}", "teacher", f"overall.{m}")
    put("teacher.overall.first_readback_difference_classes", "teacher", "overall.first_readback_difference_classes")
    put("teacher.overall.final_readback_difference_classes", "teacher", "overall.final_readback_difference_classes")
    for c in CURRICULA:
        for m in ("code_check_pass_first_attempt", "code_check_pass_final", "readback_consistent_final", "clean_final", "repair_success"):
            put(f"teacher.{c}.{m}", "teacher", f"per_curriculum.{c}.{m}")

    # judge benchmark (report half; paired subset of 160 pairs unless named)
    put("judges.policy.rule", "policy", "rule")
    put("judges.policy.jev_question_set", "policy", "jev_question_set")
    put("judges.policy.thresholds", "policy", "thresholds")
    put("judges.policy.chosen_on", "policy", "chosen_on")
    for rule in ("jev", "decisions", "both", "either", "jev_hint"):
        put(f"judges.report160.{rule}.caught", "bench", f"report.rules.{rule}.caught")
        put(f"judges.report160.{rule}.false_reject", "bench", f"report.rules.{rule}.false_reject")
        for e in ("e=0.05", "e=0.10", "e=0.20"):
            put(f"judges.report160.{rule}.noise_after.{e}", "bench", f"report.rules.{rule}.noise_after.{e}")
    for name, path in (("jev", "jev_alone_all_report_pairs"), ("jev_hint", "jev_hint_alone_all_report_pairs")):
        put(f"judges.report300.{name}.caught", "bench", f"report.{path}.caught")
        put(f"judges.report300.{name}.false_reject", "bench", f"report.{path}.false_reject")
        for e in ("e=0.05", "e=0.10", "e=0.20"):
            put(f"judges.report300.{name}.noise_after.{e}", "bench", f"report.{path}.noise_after.{e}")
        put(f"judges.report300.{name}.caught_by_kind", "bench", f"report.{path}.caught_by_kind")
    put("judges.agreement.cohen_kappa_pass_fail", "bench", "report.agreement.cohen_kappa_pass_fail")
    put("judges.agreement.cohen_kappa_on_corrupted", "bench", "report.agreement.cohen_kappa_on_corrupted")
    put("judges.agreement.cohen_kappa_on_clean", "bench", "report.agreement.cohen_kappa_on_clean")
    put("judges.agreement.table", "bench", "report.agreement.table")
    put("judges.agreement.corrupted_missed_by_both", "bench", "report.agreement.corrupted_missed_by_both")
    for j in ("jev", "jev_hint", "decisions"):
        put(f"judges.cost.{j}.usd_per_1000_notes", "bench", f"cost.{j}.usd_per_1000_notes")
        put(f"judges.cost.{j}.tokens_per_1000_notes", "bench", f"cost.{j}.tokens_per_1000_notes")
        put(f"judges.cost.{j}.latency_s_p50", "bench", f"cost.{j}.latency_s_p50")
        put(f"judges.cost.{j}.latency_s_p95", "bench", f"cost.{j}.latency_s_p95")
    DOCS["judges.report160.*"] = "pairs that both judges answered (80 corrupted, 80 clean). false_reject is measured on notes the version-2 Jev gate had already accepted, so it is biased low; see scribe/judges/RESULTS.md"
    DOCS["judges.report300.jev_hint.*"] = "the v2 question set was designed after both halves' v1 results were seen: not a clean hold-out"

    # gate
    for m in ("candidates", "code_check_pass", "readback_consistent"):
        put(f"gate.overall.{m}", "gate", f"overall.{m}")
    put("gate.overall.rule_accepted_of_judged", "gate", "overall.rule.accepted_of_judged")
    put("gate.overall.rule_accepted_of_candidates", "gate", "overall.rule.accepted_of_candidates")
    put("gate.overall.readback_vs_rule", "gate", "overall.readback_vs_rule")
    put("gate.overall.jev_vs_decisions", "gate", "overall.jev_vs_decisions")
    put("gate.overall.decisions_accepted", "gate", "overall.decisions.accepted")
    put("gate.overall.decisions_asked", "gate", "overall.decisions.asked")
    for c in CURRICULA:
        put(f"gate.{c}.rule_accepted_of_candidates", "gate", f"per_curriculum.{c}.rule.accepted_of_candidates")
    put("dataset.train_rows", "dataset", "checks.train_rows")
    put("dataset.train_rows_from_v2", "dataset", "checks.train_rows_from_v2")
    put("dataset.train_rows_from_round2", "dataset", "checks.train_rows_from_round2")
    put("dataset.round2_added_to_rejected", "dataset", "round2.added_to_rejected")
    put("dataset.round2_added_to_train_by_curriculum", "dataset", "round2.added_to_train_by_curriculum")
    put("dataset.round2_added_to_train_readback_inconsistent", "dataset", "round2.added_to_train_readback_inconsistent")
    put("dataset.round2_added_to_train_starts_with_style_label", "dataset", "round2.added_to_train_starts_with_style_label")
    put("dataset.train_sha256", "dataset", "files.train.sha256")

    # audit (LLM auditors; per status, never pooled)
    for st in ("accepted", "rejected"):
        for m in ("notes_in_sample", "notes_scored", "wrong_label", "ambiguity_only", "clean", "clean_strict", "route_not_ok", "wrong_label_or_route_not_ok"):
            put(f"audit.{st}.{m}", "audit", f"by_status.{st}.{m}")
    put("audit.sampling", "audit", "sampling")
    put("audit.verdicts_total", "audit", "verdicts.total")
    put("audit.verdicts_discarded", "audit", "verdicts.discarded")
    DOCS["audit.*"] = "auditors were language-model readers (Claude Haiku) who saw the claimed labels; accepted and rejected were sampled at different rates, so do not pool"

    # tokens and USD per service
    put("cost.typesafe.requests", "ts", "requests")
    put("cost.typesafe.tokens", "ts", "tokens")
    put("cost.typesafe.usd", "ts", "cost_usd")
    put("cost.openai_decisions.requests", "oa", "requests")
    put("cost.openai_decisions.tokens", "oa", "tokens")
    oa = load("oa")
    if oa:
        OUT["cost.openai_decisions.usd_list_rate"] = oa["input_tokens"] * 0.10 / 1e6
        SRC["cost.openai_decisions.usd_list_rate"] = SOURCES["oa"] + "#input_tokens x USD 0.10 per million (Decisions guide, opened 2026-11-14; output not charged; list rate, not a bill)"
    put("cost.nemotron.requests", "teacher_ledger", "teacher_requests")
    null("cost.nemotron.usd", "Verda billing for the Nemotron endpoint was not read; no price was opened")
    null("cost.haiku_audit.tokens_and_usd", "the auditor's token usage was not recorded in a file")

    # student comparison (pre-registered; written by scribe/v3/compare_students.py)
    comp = load("student")
    if comp is None:
        for ts in ("test_nemotron", "test_haiku", "test_pooled"):
            null(f"student.{ts}.v3_vs_v2_exact_match_mcnemar_p", f"source file {SOURCES['student']} does not exist")
    else:
        put("student.preregistration_sha256", "student", "preregistration.sha256")
        put("student.multiplicity", "student", "multiplicity")
        put("student.decoding", "student", "decoding")
        put("student.reference.run", "student", "reference.run")
        for ts in ("test_nemotron", "test_haiku", "pooled"):
            put(f"student.reference.{ts}.exact_match", "student", f"reference.summary.{ts}.note_exact_match")
        put("student.reference.test_haiku.no_event.exact_match", "student", "reference.summary.test_haiku.by_kind.no_event")
        SOURCES["result:reference"] = STUDENT_RESULT.format("v2-selected")
        for k, path in (("validation_exact_match", "val.metrics.note_exact_match.value"), ("train_steps", "train.global_step"),
                        ("train_examples", "data.train_tokens.examples")):
            put(f"student.reference.{k}", "result:reference", path)
        runs = [("comparisons", i, c) for i, c in enumerate(comp.get("comparisons", []))]
        runs += [("posthoc", i, c) for i, c in enumerate(comp.get("posthoc", []))]
        for part, i, c in runs:
            r, base = c["run"], f"{part}.{i}"
            put(f"student.{r}.what", "student", f"{base}.what")
            for ts in ("test_nemotron", "test_haiku", "pooled"):
                put(f"student.{r}.{ts}.exact_match", "student", f"{base}.summary.{ts}.note_exact_match")
                put(f"student.{r}.{ts}.vs_reference.exact_mcnemar_p", "student", f"{base}.paired_vs_reference.{ts}.exact_mcnemar_p")
                put(f"student.{r}.{ts}.vs_reference.difference_in_exact_match", "student", f"{base}.paired_vs_reference.{ts}.difference_in_exact_match")
            if part == "comparisons":
                put(f"student.{r}.pooled.vs_reference.holm_adjusted_p", "student", f"{base}.paired_vs_reference.pooled.holm_adjusted_p")
            put(f"student.{r}.test_haiku.no_event.exact_match", "student", f"{base}.summary.test_haiku.by_kind.no_event")
            SOURCES[f"result:{r}"] = STUDENT_RESULT.format(r)
            for k, path in (("validation_exact_match", "val.metrics.note_exact_match.value"), ("train_steps", "train.global_step"),
                            ("train_examples", "data.train_tokens.examples")):
                put(f"student.{r}.{k}", f"result:{r}", path)
            if str(c.get("what", "")).startswith("primary"):
                for ts, key in (("test_nemotron", "test_nemotron"), ("test_haiku", "test_haiku"), ("test_pooled", "pooled")):
                    put(f"student.{ts}.v3_vs_v2_exact_match_mcnemar_p", "student", f"{base}.paired_vs_reference.{key}.exact_mcnemar_p")
        null("student.S-4b-lora-r16.validation_exact_match",
             "the 4B run ran out of GPU memory twice and a third attempt was stopped by the coordinator to protect the "
             "pre-registered runs (data/scribe/v3/student/S-4b-lora-r16/*.log); there is no 4B number")
        DOCS["student.*"] = ("every run used the same 324 optimisation steps (train_steps), so a run with more training rows "
                             "(train_examples) made fewer passes over each note; compare data arms with that in mind. "
                             "v3_vs_v2_* keys are the pre-registered primary against the frozen version-2 reference")

    # cascade at inference (written by scribe/v3/cascade.py)
    if load("cascade") is None:
        null("cascade.verdict", f"source file {SOURCES['cascade']} does not exist")
    else:
        put("cascade.chosen_student", "cascade", "student.chosen")
        put("cascade.student_choice_reason", "cascade", "student.why")
        put("cascade.threshold_rule", "cascade", "design.threshold_rule")
        put("cascade.empirical_not_guaranteed", "cascade", "design.empirical_not_guaranteed")
        put("cascade.verdict", "cascade", "verdict.lines")
        for sig in ("student", "jev", "student+jev"):
            for t in ("5pct", "10pct"):
                put(f"cascade.{sig}.{t}.validation_threshold", "cascade", f"validation_in_sample.{sig}.{t}.threshold")
                for g in ("test_nemotron", "test_haiku", "test_pooled"):
                    put(f"cascade.{sig}.{t}.{g}.coverage", "cascade", f"test.all_notes.{sig}.{t}.{g}.coverage")
                    put(f"cascade.{sig}.{t}.{g}.error_among_accepted", "cascade", f"test.all_notes.{sig}.{t}.{g}.error_among_accepted")
                if sig != "student":
                    vs = f"test.all_notes.{sig}.{t}.test_pooled.vs_student"
                    put(f"cascade.{sig}.{t}.test_pooled.coverage_difference_vs_student", "cascade", f"{vs}.coverage_difference")
                    put(f"cascade.{sig}.{t}.test_pooled.coverage_difference_vs_student95", "cascade", f"{vs}.coverage_difference95")
                    put(f"cascade.{sig}.{t}.test_pooled.error_difference_vs_student95", "cascade", f"{vs}.error_difference95")
                    pb = f"pipeline_bootstrap.by_signal.{sig}.{t}"
                    put(f"cascade.{sig}.{t}.pipeline.coverage_difference_vs_student95", "cascade", f"{pb}.coverage_difference_vs_student95")
                    put(f"cascade.{sig}.{t}.pipeline.error_difference_vs_student95", "cascade", f"{pb}.error_difference_vs_student95")
            put(f"cascade.{sig}.aurc.test_pooled", "cascade", f"test.all_notes.{sig}.aurc.test_pooled")
            if sig != "student":
                put(f"cascade.{sig}.aurc_difference_vs_student.test_pooled", "cascade", f"test.all_notes.{sig}.aurc_difference_vs_student.test_pooled.difference")
                put(f"cascade.{sig}.aurc_difference_vs_student95.test_pooled", "cascade", f"test.all_notes.{sig}.aurc_difference_vs_student.test_pooled.paired_bootstrap95")
        put("cascade.aurc_best_possible.test_pooled", "cascade", "test.all_notes._reference.test_pooled.aurc_best_possible_order")
        put("cascade.aurc_random_order.test_pooled", "cascade", "test.all_notes._reference.test_pooled.aurc_random_order")
        put("cascade.decisions_subset.per_split", "cascade", "design.decisions_subset.per_split")
        for sig in ("student", "decisions", "student+jev", "student+jev+decisions"):
            for t in ("5pct", "10pct"):
                put(f"cascade.decisions_subset.{sig}.{t}.coverage", "cascade", f"test.decisions_subset.{sig}.{t}.test_pooled.coverage")
                put(f"cascade.decisions_subset.{sig}.{t}.error_among_accepted", "cascade", f"test.decisions_subset.{sig}.{t}.test_pooled.error_among_accepted")
            put(f"cascade.decisions_subset.{sig}.aurc", "cascade", f"test.decisions_subset.{sig}.aurc.test_pooled")
        for j in ("jev", "decisions"):
            put(f"cascade.cost.{j}.notes_answered", "cascade", f"judges.{j}.answered")
            put(f"cascade.cost.{j}.errors", "cascade", f"judges.{j}.errors")
            for k in ("tokens_per_note", "usd_per_1000_notes", "latency_s_p50", "latency_s_p95"):
                put(f"cascade.cost.{j}.{k}", "cascade", f"judges.{j}.cost.{k}")
        put("cascade.openai_tokens_this_step", "cascade", "ledgers.this_step.openai_tokens_ledger_difference")
        put("cascade.typesafe_usd_this_step", "cascade", "ledgers.this_step.typesafe_usd_ledger_difference")
        DOCS["cascade.*"] = ("thresholds chosen on validation notes only and applied to test; empirical, not guarantees. *95 keys "
                             "are paired bootstrap 95% intervals; 'pipeline' intervals also re-choose the thresholds on resampled "
                             "validation notes. Decisions keys are on a hash-chosen subset only. Synthetic notes; not for clinical use")

    OUT["_sources"] = SRC
    OUT["_not_done"] = NOT_DONE
    OUT["_docs"] = DOCS
    OUT["_format"] = "flat keys; shares are <key>.n, <key>.d, <key>.share (+ .wilson95); null values are explained in _not_done; sources in _sources"
    save_json(V3 / "summary-v1.json", OUT)
    log("summarise", inputs=list(SOURCES.values()), outputs=["data/scribe/v3/summary-v1.json"], metrics=dict(keys=len(OUT), not_done=len(NOT_DONE)), cost_usd=0, status="ok")
    print(f"{len(OUT)} keys, {len(NOT_DONE)} null with reason")


if __name__ == "__main__":
    main()
