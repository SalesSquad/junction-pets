"""Render scribe/v2/RESULTS.md from the ablation JSON. Standard library only.

Every figure in the report is read from the JSON; nothing is computed from assumptions. A part that
did not run is printed as "not run", never as a number.

    python scribe/v2/report.py data/scribe/v2/ablation-v1.json > scribe/v2/RESULTS.md
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

NOT_RUN = "not run"


def pct(value, digits=1):
    return NOT_RUN if value is None else f"{100 * value:.{digits}f}%"


def rate(block, digits=1):
    """A proportion with its Wilson 95% interval: '83.2% (79.6-86.3), n=500'."""
    if not block or block.get("value") is None:
        return NOT_RUN
    lo, hi = block.get("ci95") or (None, None)
    interval = f" ({100 * lo:.{digits}f}-{100 * hi:.{digits}f})" if lo is not None and hi is not None else ""
    return f"{100 * block['value']:.{digits}f}%{interval}"


def num(value, digits=1, unit=""):
    return NOT_RUN if value is None else f"{value:,.{digits}f}{unit}"


def _cause(block):
    cause = block.get("unparsable_by_cause")
    if not cause or not cause.get("unparsable"):
        return ""
    return f" ({cause['cut_at_cap']} / {cause['malformed']})"


def _writer_mix(out):
    """Haiku-written share of the calibration (validation) notes and of the pooled test notes."""
    data = out.get("data") or {}
    def share(group):
        rows = {k: (v or {}).get("rows") or 0 for k, v in (data.get(group) or {}).items()}
        total = sum(rows.values())
        haiku = sum(v for k, v in rows.items() if k.endswith("haiku"))
        return haiku, total
    vh, vt = share("val")
    th, tt = share("test")
    if not vt or not tt:
        return ""
    return (f"The pooled test check mixes {th} Haiku-written of {tt} notes ({pct(th / tt)}); the calibration notes had "
            f"{vh} of {vt} ({pct(vh / vt)}). A different writer mix is a different population.")


def table(header, rows):
    if not rows:
        return "_" + NOT_RUN + "_\n"
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _run_row(name, run):
    val, train = run.get("val") or {}, run.get("train") or {}
    memory = train.get("peak_gpu_memory_bytes")
    by_split = val.get("by_split") or {}

    def split_rate(split):
        block = (by_split.get(split) or {}).get("note_exact_match") or {}
        return NOT_RUN if block.get("value") is None else f"{pct(block['value'])} of {block.get('n')}"

    return [
        name,
        run.get("description") or "",
        run.get("status") or "",
        rate(val.get("note_exact_match")),
        split_rate("val_nemotron"),
        split_rate("val_haiku"),
        num(val.get("event_f1"), 3),
        rate(val.get("invalid_output")),
        num(train.get("train_seconds"), 0, " s"),
        num(train.get("seconds_per_step"), 2),
        num(memory / 2**30 if memory else None, 1, " GiB"),
    ]


RUN_HEADER = [
    "run",
    "configuration",
    "status",
    "val exact match, all notes (95% CI)",
    "Nemotron-written",
    "Haiku-written",
    "val event F1",
    "val unparsable",
    "training time",
    "s/step",
    "peak GPU memory",
]


def stage_reading(out, key):
    """What a stage's selection actually rested on, derived from the stored stage record rather than from
    the rationale string written at freeze time (review findings 0 and 1)."""
    stage = (out.get("stages") or {}).get(key) or {}
    selection = stage.get("selection") or {}
    runs = out.get("runs") or {}
    if key == "A":
        ladder = stage.get("ladder") or []
        finished = [n for n in ladder if (runs.get(n) or {}).get("status") == "ok"]
        if len(finished) == 1:
            missing = [n for n in ladder if n not in finished]
            return (f"only one ladder run finished ({finished[0]}); no size was compared"
                    + (f" ({', '.join(missing)} did not run)" if missing else ""))
        return selection.get("rationale", "")
    if "arms_completed" in stage and not stage["arms_completed"]:
        return "no arm ran (all dropped for time or unavailable); the control stays by default and nothing was compared"
    return selection.get("rationale", "")


def finalist_reading(selection):
    tests = selection.get("comparisons") or []
    if not tests:
        return selection.get("rationale", "")
    t = tests[0]
    verdict = "adopted" if selection.get("adopted") else "kept the incumbent"
    return (f"{t['a']} vs {t['b']}: {t['a_exact']:.3f} vs {t['b_exact']:.3f}, {t['a_only_correct']} vs {t['b_only_correct']} "
            f"discordant notes, exact McNemar p = {t['exact_p']:.3f}; the incumbent is kept unless the finalist is better "
            f"with p < 0.05 ({verdict}). This difference is within noise."
            if t["exact_p"] >= 0.05 else
            f"{t['a']} vs {t['b']}: {t['a_exact']:.3f} vs {t['b_exact']:.3f}, {t['a_only_correct']} vs {t['b_only_correct']} "
            f"discordant notes, exact McNemar p = {t['exact_p']:.4f} ({verdict}).")


def budget_reading(out):
    """Which planned items the budget ruled out, from the stored planning and drop records (finding 2)."""
    dropped = out.get("dropped") or []
    planning = {p["item"]: p for p in out.get("planning") or []}
    lines = []
    ladder = [d["item"] for d in dropped if d["stage"] == "A"]
    arms = [d["item"] for d in dropped if d["stage"] in ("B", "C_format", "C_data")]
    if ladder or arms:
        lines.append(
            f"The time budget ruled out {len(ladder)} size-ladder run(s) ({', '.join(ladder) or 'none'}) and "
            f"{len(arms)} Stage B/C arm(s) ({', '.join(arms) or 'none'}).")
    reserves = sorted({planning[a]["reserve_basis"] for a in arms if a in planning and planning[a].get("reserve_basis")})
    for basis in reserves:
        lines.append(f"Time held back for the final phase when those arms were dropped: {basis}.")
    sacrificed = [d["item"] for d in dropped if d["stage"] == "final"]
    if reserves and sacrificed:
        lines.append(f"Final-phase items later dropped anyway: {', '.join(sacrificed)}. Reserving time for items that are "
                     "sacrificed first is what dropped the arms (scribe/v2/run_ablation.py now reserves only the "
                     "never-sacrificed part).")
    return lines


def load_posthoc(ablation_path):
    """data/scribe/v2/posthoc-checks-v1.json, used only when it was computed from this exact ablation file."""
    path = pathlib.Path(ablation_path).with_name("posthoc-checks-v1.json")
    if not path.exists():
        return None
    posthoc = json.loads(path.read_text())
    if posthoc.get("ablation_sha256") != hashlib.sha256(pathlib.Path(ablation_path).read_bytes()).hexdigest():
        return None
    return posthoc


def _stage(out, key, title, lines):
    stage = (out.get("stages") or {}).get(key)
    lines.append(f"### {title}\n")
    if not stage:
        lines.append(f"_{NOT_RUN}_\n")
        return
    runs = out.get("runs") or {}
    names = stage.get("arms", [])
    control = stage.get("control")
    rows = [_run_row(n, runs[n]) for n in ([control] if control and control not in names else []) + names if n in runs]
    lines.append(table(RUN_HEADER, rows))
    missing = [n for n in names if n not in runs]
    if missing:
        lines.append("Not run: " + ", ".join(missing) + ".\n")
    selection = stage.get("selection") or {}
    if selection:
        lines.append(f"Selected: **{selection.get('winner')}**. {stage_reading(out, key)}\n")
        tests = selection.get("comparisons") or []
        if tests:
            lines.append(
                table(
                    ["comparison", "only first correct", "only second correct", "exact McNemar p"],
                    [[f"{t['a']} vs {t['b']}", t["a_only_correct"], t["b_only_correct"], f"{t['exact_p']:.4f}"] for t in tests],
                )
            )


def render(out, posthoc=None):
    lines = []
    smoke = out.get("smoke")
    lines.append("# SAMA pathway scribe, version 2: ablation results\n")
    lines.append(
        "Generated by `scribe/v2/report.py` from `data/scribe/v2/ablation-v1.json`. "
        "All notes are SYNTHETIC. Research artefact, not for clinical use.\n"
    )
    if smoke:
        lines.append(
            "**WIRING TEST ONLY.** This file was produced with tiny randomly initialised models on CPU. "
            "The numbers say nothing about Gemma.\n"
        )
    status = out.get("status", "unknown")
    budget = out.get("budget") or {}
    lines.append(
        f"Status: **{status}**"
        + (f" ({out['error']})" if out.get("error") else "")
        + f". Started {out.get('started_utc', '?')}, finished {out.get('finished_utc', NOT_RUN)}, host {out.get('host', '?')}. "
        f"Time budget {num(budget.get('minutes'), 0)} min, used {num((budget.get('elapsed_seconds') or 0) / 60, 1)} min"
        + (" (over budget)" if budget.get("over_budget") else "")
        + ".\n"
    )
    versions = out.get("versions") or {}
    if versions:
        lines.append("Libraries: " + ", ".join(f"{k} {v}" for k, v in versions.items() if v) + ".\n")
    bases = out.get("bases")
    if not bases:
        try:
            import config  # scribe/v2/config.py: the pins the run used

            bases = {k: {"repo": v["repo"], "revision": v["revision"]} for k, v in config.BASES.items()}
            source = "from scribe/v2/config.py; this JSON does not record them"
        except ImportError:
            bases, source = {}, ""
    else:
        source = "as recorded in this JSON"
    if bases:
        lines.append(
            "Base models (" + source + "): " + "; ".join(f"{k} = `{v['repo']}` at `{v['revision']}`" for k, v in bases.items())
            + ". Ungated Unsloth mirrors of Gemma 3, used under the Gemma Terms of Use (https://ai.google.dev/gemma/terms) "
            "and the Gemma Prohibited Use Policy (https://ai.google.dev/gemma/prohibited_use_policy).\n"
        )

    # ---- selection ----
    lines.append("## Selected configuration\n")
    selection = out.get("selection")
    if not selection:
        lines.append(f"_{NOT_RUN}: the selection was not frozen, so the test notes were not read._\n")
    else:
        lines.append(f"**{selection.get('description')}** (run `{selection.get('run')}`), frozen {selection.get('frozen_utc')}.\n")
        lines.append(f"Validation exact match: {rate(selection.get('validation_exact_match'))}.\n")
        check = selection.get("decoding_check") or {}
        lines.append(f"Decoding: **{'schema-constrained' if selection.get('decoding') == 'auto' else 'unconstrained greedy, tolerant parsing'}**. {check.get('rationale', '')}\n")
        paired = check.get("paired_test") or {}
        if paired:
            lines.append(f"Paired validation notes: {paired.get('a_only_correct')} right only when constrained, "
                         f"{paired.get('b_only_correct')} right only when unconstrained (exact McNemar p = {paired.get('exact_p', float('nan')):.3f}).\n")
        audit = (posthoc or {}).get("decoding_check_audit")
        if audit:
            caps = sorted(set((audit["constrained_arm"].get("max_new_tokens_by_split") or {}).values()))
            lines.append(
                f"Not a like-for-like check (post-hoc audit, `data/scribe/v2/posthoc-checks-v1.json`): the unconstrained arm is "
                f"{audit['unconstrained_arm']['decoder']} with at most {audit['unconstrained_arm']['max_new_tokens']} new tokens, the "
                f"constrained arm {audit['constrained_arm']['decoder']} with {', '.join(str(c) for c in caps)}. "
                f"{audit['raw_differ']} of {audit['n']} raw answers differ, {audit['raw_differ_although_unconstrained_answer_was_valid_strict_json']} "
                f"of them although the unconstrained answer was already valid JSON, so those differences do not come from the constraint. "
                f"Only {audit['max_notes_the_constraint_could_change']} unconstrained answers were unparsable, so the check could have "
                f"found a gain of at most {audit['max_notes_the_constraint_could_change']} notes.\n")
        lines.append("What the selection rested on (derived from the stored stage records):\n")
        for key, title in (("A", "Stage A"), ("B", "Stage B"), ("C_format", "Stage C, output format"), ("C_data", "Stage C, training data")):
            if key in (out.get("stages") or {}):
                lines.append(f"- {title}: {stage_reading(out, key)}")
        for fin in (out.get("stages") or {}).get("finalists") or []:
            lines.append(f"- Finalist: {finalist_reading(fin)}")
        lines.append("")
        stored = selection.get("rationale") or []
        derived = [stage_reading(out, k) for k in ("A", "B", "C_format", "C_data") if k in (out.get("stages") or {})]
        if any(r not in derived and not any(r.endswith(d) for d in derived) for r in stored[: len(derived)]):
            lines.append("The rationale strings stored at freeze time (`selection.rationale`) read: "
                         + "; ".join(f"\"{r}\"" for r in stored)
                         + ". Where they differ from the list above, the list above is correct: they were written by code that "
                         "called a single finished rung \"the highest\" and a stage in which no arm ran a negative test "
                         "(review findings 0 and 1, fixed in run_ablation.py).\n")
        for line in budget_reading(out):
            lines.append(line)
        lines.append("")
        for note in selection.get("serving_notes") or []:
            lines.append(f"- Serving: {note}")
        lines.append("")
    final = out.get("final") or {}
    if final.get("reused"):
        lines.append(f"Final run: `{final.get('run')}` (reused; {final.get('note')}).\n")

    # ---- test ----
    lines.append("## Test results (first read in this session, after the selection was frozen)\n")
    test = out.get("test")
    if not test:
        lines.append(f"_{NOT_RUN}_\n")
    else:
        overlap = (posthoc or {}).get("v1_overlap")
        if overlap:
            sel = overlap["systems"].get("selected") or {}
            a, b = sel.get("scored_by_v1") or {}, sel.get("never_scored_before") or {}
            lines.append(
                f"test_nemotron is not a fresh test set for the project: {a.get('n')} of its {sel.get('test_nemotron_n')} notes were "
                f"scored by the version-1 model and analysed note by note before this ablation was designed "
                f"(`{overlap['source']}`). Selected configuration on those {a.get('n')}: {a.get('k')} exactly right; on the "
                f"{b.get('n')} never scored before: {b.get('k')} exactly right, "
                f"{rate({'value': b['k'] / b['n'], 'ci95': b.get('wilson95')}) if b.get('n') else NOT_RUN}.\n")
        rows = []
        for label, system in test["systems"].items():
            for split, block in system["splits"].items():
                rows.append(
                    [
                        label,
                        split,
                        block.get("n"),
                        rate(block.get("note_exact_match")),
                        num(block.get("event_f1"), 3),
                        rate(block.get("route_accuracy")),
                        rate(block.get("invalid_output")) + _cause(block),
                        (block.get("constraint") or {}).get("backend", ""),
                    ]
                )
        lines.append(
            table(
                ["system", "test set", "n", "note exact match (95% CI)", "event F1", "route accuracy", "unparsable (cut at the token cap / malformed)", "constraint engine"],
                rows,
            )
        )
        lines.append("Event F1 is a harmonic mean, not a binomial proportion, so it has no Wilson interval. "
                     "An answer cut at the token cap ran out of new tokens before it closed; that share measures the cap "
                     "as much as the model.\n")
        lines.append("### Paired comparisons (exact two-sided McNemar on note-level exact match)\n")
        lines.append(
            table(
                ["first", "second", "test set", "only first correct", "only second correct", "p", "Holm-adjusted p"],
                [
                    [t["a"], t["b"], t["split"], t["a_only_correct"], t["b_only_correct"], f"{t['exact_p']:.4f}", f"{t.get('holm_adjusted_p', float('nan')):.4f}"]
                    for t in test.get("mcnemar") or []
                ],
            )
        )
        selected = test["systems"].get("selected")
        if selected:
            for label, key in (("writer", "by_writer"), ("kind of note", "by_kind")):
                rows = []
                for split, block in selected["splits"].items():
                    for value, group in (block.get(key) or {}).items():
                        rows.append([split, value, group.get("n"), rate(group.get("note_exact_match")), num(group.get("event_f1"), 3), rate(group.get("invalid_output"))])
                lines.append(f"### Selected configuration by {label}\n")
                lines.append(table(["test set", label, "n", "note exact match (95% CI)", "event F1", "unparsable"], rows))

    # ---- risk control ----
    lines.append("## Risk control for auto-accepting notes\n")
    control = out.get("risk_control")
    if not control:
        lines.append(f"_{NOT_RUN}_\n")
    else:
        lines.append(
            f"Rule: auto-accept a note when its confidence ({control.get('confidence')}) reaches a threshold chosen on "
            f"{control.get('calibration_n')} calibration notes, so that the error among accepted notes is at most alpha "
            f"with probability at least {1 - control.get('delta', 0):.2f} (Learn-then-Test, exact binomial tail). "
            f"Error = {control.get('error_definition')}. Calibration error rate: {pct(control.get('calibration_error_rate'))}.\n"
        )
        rows = []
        for entry in control.get("results") or []:
            fit = entry["calibration"]
            found = fit.get("threshold") is not None
            base = [
                entry["alpha"],
                entry["method"],
                f"{fit['threshold']:.5f}" if found else "none",
                pct(fit.get("coverage")) if found else "0.0%",
                f"{fit.get('errors_accepted')}/{fit.get('n_accepted')}" if found else "-",
            ]
            checks = entry.get("checks") or {}
            if not checks:
                rows.append(base + ["-", "-", "-", "-", "-", fit.get("reason", "")])
            for name, stats in checks.items():
                within = stats.get("risk_at_most_alpha")
                bound = stats.get("risk_upper_bound")
                rows.append(
                    base
                    + [
                        name,
                        pct(stats.get("coverage")),
                        f"{stats.get('errors_accepted')}/{stats.get('accepted')}" + (f" = {pct(stats.get('risk'))}" if stats.get("risk") is not None else ""),
                        "-" if within is None else ("yes" if within else "**no**"),
                        "-" if bound is None else pct(bound),
                        fit.get("reason", ""),
                    ]
                )
        lines.append(
            table(
                ["alpha", "method", "threshold (mean log-prob)", "calibration coverage", "calibration errors/accepted", "checked on", "coverage", "errors/accepted", "within alpha on this split", "95% upper bound", "certified on calibration"],
                rows,
            )
        )
        failing = sorted({(e["alpha"], name) for e in control.get("results") or [] for name, st in (e.get("checks") or {}).items()
                          if st.get("risk_at_most_alpha") is False and st.get("accepted")})
        for alpha, name in failing:
            lines.append(f"On {name}, the notes accepted at alpha = {alpha} had an observed error above alpha. The guarantee is for "
                         "notes exchangeable with the calibration notes as a whole, not for each writer.\n")
        mix = _writer_mix(out)
        if mix:
            lines.append(mix + "\n")
        lines.append(f"Caveat: {control.get('caveat', '')}\n")

    # ---- stages ----
    lines.append("## Stages (all choices on validation notes)\n")
    _stage(out, "A", "Stage A: size ladder", lines)
    _stage(out, "B", "Stage B: adapter method and initialisation", lines)
    _stage(out, "C_format", "Stage C: output format", lines)
    _stage(out, "C_data", "Stage C: training data", lines)
    for selection in (out.get("stages") or {}).get("finalists") or []:
        lines.append(f"Finalist check: {finalist_reading(selection)}\n")
    other = [n for n in (out.get("runs") or {}) if n.startswith(("final-", "v1-"))]
    if other:
        lines.append("### Final-phase runs\n")
        lines.append(table(RUN_HEADER, [_run_row(n, out["runs"][n]) for n in other]))

    # ---- dropped ----
    lines.append("## Dropped for time or unavailable\n")
    dropped = out.get("dropped") or []
    if dropped:
        lines.append(table(["stage", "item", "reason"], [[d["stage"], d["item"], d["reason"]] for d in dropped]))
    else:
        lines.append("Nothing was dropped.\n")

    # ---- data and protocol ----
    lines.append("## Data\n")
    rows = []
    for group, splits in (out.get("data") or {}).items():
        for name, info in (splits or {}).items():
            rows.append([name, info.get("rows"), info.get("source") or "unavailable"])
    lines.append(table(["split", "notes", "source"], rows))
    protocol = out.get("protocol") or {}
    if protocol:
        lines.append("## Protocol\n")
        for key in ("steps", "effective_batch", "seed", "selection_metric", "size_rule", "arm_rule", "decoding_rule", "budget_claim_order", "final_phase_sacrifice_order", "reserve_rule"):
            if key in protocol:
                lines.append(f"- {key.replace('_', ' ')}: {protocol[key]}")
        lines.append("")
    notes = out.get("notes") or []
    lines.append("## Notes and limits\n")
    for note in notes:
        lines.append(f"- {note}")
    lines += [
        "- One seed per run. With a few hundred validation notes a difference of a few points is within noise; "
        "this is why a change replaces the control only on a paired test.",
        "- Labels come from a synthetic generator checked by models, not by clinicians; all figures are relative to those labels.",
        "- Risk-control thresholds hold for notes exchangeable with the calibration notes. Real clinical notes are not.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.write(render(json.load(open(sys.argv[1])), load_posthoc(sys.argv[1])))
