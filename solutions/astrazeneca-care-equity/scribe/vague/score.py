"""Score the vague-time gate (scribe/vague/rule.py) on STORED outputs only. No model inference, no network.

POST HOC: designed after the stress results were seen. SYNTHETIC notes only. A person confirms every extracted event;
the gate only moves notes from 'pre-filled for one-click confirmation' to 'needs editing'.

Reads the stored Gemma 3 1B (C-1b-expr-aug) outputs and the stored Nemotron v3 reader cache through
scribe/v4/eval8.py (same parsing and date code as data/scribe/v4/eval/results-v1.json), puts the gate in front of
  1. Gemma 1B alone (every parsed answer pre-filled; the 1B reader has no flag of its own), and
  2. the chosen two-reader cascade (C, agreement: pre-filled only when Gemma 1B and Nemotron agree exactly),
and reports both with and without the gate, with Wilson 95% intervals. As a comparison it also runs the needs-person
detector of the frozen resolver arm A' (scribe/v3/resolve.py, frozen 2026-11-14T21:37:24Z, before the stress set).

    scribe/.venv/bin/python scribe/vague/score.py        writes data/scribe/vague/results-v1.json
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scribe" / "v4"))

import rule as R  # noqa: E402
import eval8 as E  # noqa: E402  (stored outputs, parsing, Wilson rate, vague_outcomes)

OUT = ROOT / "data/scribe/vague"
FREEZE = OUT / "freeze-v1.json"
RESULTS = OUT / "results-v1.json"
RUNLOG = ROOT / "runs/deliv-vague.jsonl"
STORED = ROOT / "data/scribe/v4/eval/results-v1.json"
POST_HOC = "post hoc: designed after the stress results were seen"
GEMMA = "C"  # Gemma 3 1B expression format, augmented (C-1b-expr-aug)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def log(step, command, outputs=None, metrics=None, status="ok"):
    line = dict(ts=now(), step=step, command=command, outputs=outputs or {}, metrics=metrics or {}, cost_usd=0, status=status)
    with RUNLOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def rate(k, n):
    return E.rate(k, n)


def gold(row):
    return E.gold_of(row)


# ---- detectors ----------------------------------------------------------------------------------------------------


def detect(rows):
    """{id: spans} for the post hoc rule and for the frozen A' needs-person detector."""
    rule = {r["id"]: R.find_vague(r["note_text"]) for r in rows}
    frozen = {r["id"]: E.RV.needs_person_spans(r["note_text"], "A'") for r in rows}
    return rule, frozen


def overlaps_phrase(note_text, spans, phrase):
    """True when a detected span overlaps an occurrence of the gold vague phrase in the note."""
    low = R.normalise(note_text)
    p = R.normalise(phrase)
    i = low.find(p)
    while i >= 0:
        if any(s["start"] < i + len(p) and i < s["end"] for s in spans):
            return True
        i = low.find(p, i + 1)
    return False


def flag_summary(rows, spans_by_id, vague_known):
    """Notes flagged; on the stress set also vague notes caught, missed and false flags."""
    flagged = [r for r in rows if spans_by_id[r["id"]]]
    res = {"notes": len(rows), "flagged": rate(len(flagged), len(rows)),
           "by_category": dict(collections.Counter(s.get("category", "frozen_A_prime") for r in flagged for s in spans_by_id[r["id"]]))}
    if vague_known:
        vague = [r for r in rows if r["has_vague"]]
        other = [r for r in rows if not r["has_vague"]]
        caught = [r for r in vague if spans_by_id[r["id"]]]
        facts = [(r, v) for r in vague for v in json.loads(r["vague_json"])]
        on_phrase = [(r, v) for r, v in facts if overlaps_phrase(r["note_text"], spans_by_id[r["id"]], v["phrase"])]
        false = [r for r in other if spans_by_id[r["id"]]]
        res.update({
            "vague_notes_caught": rate(len(caught), len(vague)),
            "vague_facts_whose_own_phrase_was_detected": rate(len(on_phrase), len(facts)),
            "vague_notes_missed": [{"id": r["id"][:16], "vague_phrases": [v["phrase"] for v in json.loads(r["vague_json"])]}
                                   for r in vague if not spans_by_id[r["id"]]],
            "false_flags_on_notes_without_a_vague_fact": rate(len(false), len(other)),
            "false_flag_notes": [{"id": r["id"][:16], "kind": r["kind"], "phrases": [s["phrase"] for s in spans_by_id[r["id"]]],
                                  "categories": sorted({s.get("category", "frozen_A_prime") for s in spans_by_id[r["id"]]})} for r in false],
        })
    else:
        res["vague_facts_by_construction"] = 0
        res["every_flag_is_a_false_flag_by_construction"] = True
        res["flagged_notes"] = [{"id": r["id"][:16], "phrases": [s["phrase"] for s in spans_by_id[r["id"]]],
                                 "categories": sorted({s.get("category", "frozen_A_prime") for s in spans_by_id[r["id"]]})}
                                for r in flagged]
    return res


# ---- pre-fill policies --------------------------------------------------------------------------------------------


def policy(rows, prefill, answer):
    """prefill: {id: bool}; answer: {id: pred}. Same fields as results-v1.json cascade entries."""
    acc = [r for r in rows if prefill[r["id"]]]
    wrong = [r for r in acc if answer[r["id"]] != gold(r)]
    out = {"notes": len(rows), "prefilled_for_one_click_confirmation": rate(len(acc), len(rows)),
           "prefilled_and_correct": rate(len(acc) - len(wrong), len(rows)),
           "error_among_prefilled": rate(len(wrong), len(acc)),
           "needs_editing": rate(len(rows) - len(acc), len(rows)),
           "per_100_notes_prefilled_correctly": round(100 * (len(acc) - len(wrong)) / len(rows), 1) if rows else None}
    if rows and "has_vague" in rows[0]:
        vague = [r for r in rows if r["has_vague"]]
        out["vague_notes_prefilled"] = rate(sum(prefill[r["id"]] for r in vague), len(vague))
        out["wrong_prefilled_ids"] = [r["id"][:16] + (" (vague)" if r["has_vague"] else "") for r in wrong]
    else:
        out["wrong_prefilled_ids"] = [r["id"][:16] for r in wrong]
    return out


def vague_view(rows, preds_c, prefill, gate):
    """Per vague fact, the stored eval8.vague_outcomes() categories, with 'sent to a person' = the note is not pre-filled."""
    per = {r["id"]: dict(preds_c[r["id"]], flag=(not prefill[r["id"]]) or gate[r["id"]], flag_phrases=[]) for r in rows}
    return E.vague_outcomes(rows, per, "nemotron")  # 'nemotron' = note-level flag semantics in eval8


def evaluate_split(split, rows, preds, gates):
    c, n = preds[GEMMA], preds["nemotron"]
    answer = {r["id"]: c[r["id"]]["pred"] for r in rows}
    parsed = {r["id"]: c[r["id"]]["pred"] is not None for r in rows}
    agree = {r["id"]: parsed[r["id"]] and c[r["id"]]["pred"] == n[r["id"]]["pred"] for r in rows}
    res = {"gemma_1b_alone": {}, "cascade_C_agreement": {}}
    res["gemma_1b_alone"]["without_gate"] = policy(rows, parsed, answer)
    res["cascade_C_agreement"]["without_gate"] = policy(rows, agree, answer)
    for gname, gate in gates.items():
        res["gemma_1b_alone"][f"with_gate_{gname}"] = policy(rows, {k: v and not gate[k] for k, v in parsed.items()}, answer)
        res["cascade_C_agreement"][f"with_gate_{gname}"] = policy(rows, {k: v and not gate[k] for k, v in agree.items()}, answer)
    if split == "stress":
        none = {r["id"]: False for r in rows}
        res["vague_facts"] = {
            "gemma_1b_alone_without_gate": vague_view(rows, c, parsed, none),
            "cascade_without_gate": vague_view(rows, c, agree, none),
        }
        for gname, gate in gates.items():
            res["vague_facts"][f"gemma_1b_alone_with_gate_{gname}"] = vague_view(rows, c, parsed, gate)
            res["vague_facts"][f"cascade_with_gate_{gname}"] = vague_view(rows, c, agree, gate)
    return res


# ---- README (every number is read from the results dict) -----------------------------------------------------------


def pc(x):
    if x["n"] == 0:
        return f"{x['k']}/0"
    return f"{x['k']}/{x['n']} ({100 * x['value']:.1f}%, 95% CI {100 * x['ci95'][0]:.1f}-{100 * x['ci95'][1]:.1f})"


def render_readme(doc):
    s = doc["sets"]
    st, te, va = s["stress"], s["test"], s["val"]
    stored = json.loads(STORED.read_text())["sets"]["stress"]["systems"]
    L = ["# Vague-time gate (post hoc)", "",
         "**POST HOC: designed after the stress results were seen.** SYNTHETIC notes only. Research artefact, not a medical "
         "device. A person confirms every extracted event; the gate only moves a note from 'pre-filled for one-click "
         "confirmation' to 'needs editing'. Every number below is read from `data/scribe/vague/results-v1.json` "
         "(written by `scribe/vague/score.py` from stored outputs; no model was run).", "",
         "## What it is", "",
         f"`scribe/vague/rule.py` ({doc['rule']['version']}, sha256 `{doc['rule']['sha256'][:16]}...`, frozen "
         f"{doc['rule']['frozen_at_utc']} in `data/scribe/vague/freeze-v1.json` before it read any note) lists vague or approximate "
         "Finnish time expressions explicitly: vague quantities ('pari viikkoa'), approximations ('noin kaksi viikkoa', 'reilu "
         "viikko'), ranges ('2-3 viikkoa'), weeks/months/years without a day ('viime viikolla', 'viime kuussa'), parts of a "
         "period ('maaliskuun alussa'), seasons, holidays, 'around' words and 'the date is not known'. Standard library; "
         "tests: `python3 -m unittest discover -s scribe/vague/tests`.", "",
         "Comparison detector: the needs-person list of the frozen resolver arm A' (`scribe/v3/lexicon.py`, frozen "
         f"{doc['comparison_detector']['frozen_at_utc']}, before the stress set). Caveat: the stress set's vague family "
         "(`scribe/stress/phrases.py`: 'pari viikkoa sitten', 'muutama päivä sitten', 'kuukausi sitten', 'pari kuukautta "
         "sitten', 'viime kuussa') was written by the same project with the same notion of vague, so this detector is not "
         "independent of it.", "",
         "## Flags", "",
         "| set | post hoc rule | frozen A' detector | either |", "| --- | --- | --- | --- |",
         f"| validation, notes flagged (all false by construction) | {pc(va['detector_rule_v1']['flagged'])} | {pc(va['detector_frozen_A_prime']['flagged'])} | {pc(va['detector_union']['flagged'])} |",
         f"| test, notes flagged (all false by construction) | {pc(te['detector_rule_v1']['flagged'])} | {pc(te['detector_frozen_A_prime']['flagged'])} | {pc(te['detector_union']['flagged'])} |",
         f"| stress, vague notes caught | {pc(st['detector_rule_v1']['vague_notes_caught'])} | {pc(st['detector_frozen_A_prime']['vague_notes_caught'])} | {pc(st['detector_union']['vague_notes_caught'])} |",
         f"| stress, false flags (notes without a vague fact) | {pc(st['detector_rule_v1']['false_flags_on_notes_without_a_vague_fact'])} | {pc(st['detector_frozen_A_prime']['false_flags_on_notes_without_a_vague_fact'])} | {pc(st['detector_union']['false_flags_on_notes_without_a_vague_fact'])} |",
         "",
         "Validation and test notes hold no vague fact by construction (`data/scribe/v2/WRITER_INSTRUCTIONS.md` section 3.3 "
         "forbids any other time reference and a code check rejects notes that hold one). The rule's flags there: "
         + "; ".join(f"{x['phrases']} ({k})" for k, d in (("validation", va), ("test", te)) for x in d["detector_rule_v1"]["flagged_notes"])
         + ". On stress it flags " + "; ".join(str(x["phrases"]) for x in st["detector_rule_v1"]["false_flag_notes"])
         + " in notes without a vague fact. All four sit in sentences about how the patient feels, not on a pathway date "
         "('viime aikoina' and 'viime päivinä' are vague time words; 'muistelee', 'recalls', is a hedge the rule lists "
         "because recalled dates are often approximate). Each costs one pre-filled note, never an error.", "",
         "The rule misses every stress note whose vague phrase is 'kuukausi sitten' ("
         + str(len([m for m in st["detector_rule_v1"]["vague_notes_missed"] if m["vague_phrases"] == ["kuukausi sitten"]]))
         + " notes): the rule treats 'a month ago' as an exact calendar shift, the stress set as a 25-35 day window. "
         "This is a difference of definition. Changing the rule now would fit it to the stress set, so v1 stays as frozen.", "",
         "## Effect on the readers (stored outputs)", "",
         "| policy | set | pre-filled for one-click confirmation | error among pre-filled |", "| --- | --- | --- | --- |"]
    for pol, name in (("cascade_C_agreement", "two-reader cascade (Gemma 3 1B + Nemotron agree)"), ("gemma_1b_alone", "Gemma 3 1B alone")):
        for split, label in (("test", "test 700"), ("stress", "stress 308")):
            for g, gl in (("without_gate", "no gate"), ("with_gate_rule_v1", "+ post hoc rule"),
                          ("with_gate_frozen_A_prime", "+ frozen A' detector"), ("with_gate_union", "+ either")):
                v = s[split][pol][g]
                L.append(f"| {name}, {gl} | {label} | {pc(v['prefilled_for_one_click_confirmation'])} | {pc(v['error_among_prefilled'])} |")
    vf = st["vague_facts"]
    L += ["", "Vague facts on the stress set (29 facts in 29 notes) that reach a person:", "",
          f"- Gemma 3 1B alone: no gate {pc(vf['gemma_1b_alone_without_gate']['sent_to_person'])} "
          f"(stored: {stored['C']['vague_outcome']['invented_precise_date']['k']} precise days and "
          f"{stored['C']['vague_outcome']['month_without_flag']['k']} months invented without a flag); + post hoc rule "
          f"{pc(vf['gemma_1b_alone_with_gate_rule_v1']['sent_to_person'])}; + frozen A' detector "
          f"{pc(vf['gemma_1b_alone_with_gate_frozen_A_prime']['sent_to_person'])}; + either {pc(vf['gemma_1b_alone_with_gate_union']['sent_to_person'])}.",
          f"- Two-reader cascade: no gate {pc(vf['cascade_without_gate']['sent_to_person'])} (the two readers already disagree "
          f"on most vague notes); + post hoc rule {pc(vf['cascade_with_gate_rule_v1']['sent_to_person'])}; + frozen A' detector "
          f"{pc(vf['cascade_with_gate_frozen_A_prime']['sent_to_person'])}.",
          f"- Stored Nemotron v3 alone, for reference: flags {stored['nemotron']['vague_outcome']['sent_to_person']['k']}/29 vague facts "
          f"for a person and leaves the vague event out in {stored['nemotron']['vague_outcome']['dropped']['k']}/29.", "",
          "## Reading", "",
          "- On the two-reader cascade the gate changes little: it removes the one vague note the readers agreed on, which was "
          "wrong. The test set loses " + str(te["cascade_C_agreement"]["without_gate"]["prefilled_for_one_click_confirmation"]["k"]
                                            - te["cascade_C_agreement"]["with_gate_rule_v1"]["prefilled_for_one_click_confirmation"]["k"])
          + " pre-filled note to the post hoc rule.",
          "- On Gemma 3 1B alone (the offline, on-device path) the gate matters: without it every vague fact is dated without a flag.",
          "- The stress vague family has five phrase types. Most of the rule's lexicon (seasons, holidays, approximations, "
          "ranges) is tested only by unit tests on constructed strings.",
          f"- Our no-gate numbers reproduce the stored results-v1.json cascade and exact-match counts: {doc['reproduces_stored']['all_ok']}.", ""]
    return "\n".join(L)


# ---- main ---------------------------------------------------------------------------------------------------------


def reproduce_check(stored, split, ours):
    """Our no-gate numbers must equal the stored results-v1.json ones (same outputs, same code)."""
    cfg = next(x for x in stored["cascade"]["configurations"] if x["gemma"] == GEMMA and x["signal"] == "agreement")
    want = cfg["validation" if split == "val" else split]
    got = ours["cascade_C_agreement"]["without_gate"]
    if split == "val":
        ok = want["accepted"] == got["prefilled_for_one_click_confirmation"]["k"] and want["wrong"] == got["error_among_prefilled"]["k"]
        want_s = {"accepted": want["accepted"], "wrong": want["wrong"]}
    else:
        ok = (want["prefilled_for_one_click_confirmation"]["k"] == got["prefilled_for_one_click_confirmation"]["k"]
              and want["error_among_prefilled"]["k"] == got["error_among_prefilled"]["k"])
        want_s = {"prefilled": want["prefilled_for_one_click_confirmation"]["k"], "wrong": want["error_among_prefilled"]["k"]}
    exact = stored["sets"][split]["systems"][GEMMA]["exact_match"]["k"] if split != "val" else None
    got_exact = ours["gemma_1b_alone"]["without_gate"]["prefilled_and_correct"]["k"]
    ok_exact = exact is None or exact == got_exact
    return {"stored": want_s, "recomputed": {"prefilled": got["prefilled_for_one_click_confirmation"]["k"],
                                             "wrong": got["error_among_prefilled"]["k"]},
            "gemma_1b_exact_stored": exact, "gemma_1b_exact_recomputed": got_exact, "ok": ok and ok_exact}


def main():
    freeze = json.loads(FREEZE.read_text())
    rule_sha = sha(HERE / "rule.py")
    if rule_sha != freeze["files"]["scribe/vague/rule.py"]:
        raise SystemExit("rule.py changed after its freeze; refusing to score")
    if sha(E.STRESS) != E.STRESS_SHA256:
        raise SystemExit("stress set hash mismatch")
    stored = json.loads(STORED.read_text())
    doc = {
        "schema": "scribe-vague-gate-results-v1", "synthetic": True, "post_hoc": POST_HOC, "created_utc": now(),
        "label": "POST HOC: designed after the stress results were seen. SYNTHETIC notes only. Not a preregistered result.",
        "person_confirms": "Every extracted event is a proposal: pre-filled for one-click confirmation or flagged as needing editing. "
                           "A person confirms every event. The gate only moves notes to 'needs editing'.",
        "rule": {"version": R.RULE_VERSION, "file": "scribe/vague/rule.py", "sha256": rule_sha, "frozen_at_utc": freeze["frozen_at_utc"],
                 "freeze_file": "data/scribe/vague/freeze-v1.json", "matches_freeze": True,
                 "how_written": "explicit Finnish lexicon written from general Finnish before any note of validation, test or stress was read; "
                                "the two example phrases of the task brief were known; not revised after the validation count"},
        "comparison_detector": {"name": "frozen_A_prime", "what": "needs_person_spans() of the frozen resolver arm A' (scribe/v3/resolve.py, "
                                "lexicon fi-relative-lexicon-v1)", "frozen_at_utc": "2026-11-14T21:37:24Z",
                                "note": "frozen before the stress set existed; using it as a gate in front of Gemma 1B or the cascade is post hoc"},
        "inputs": {"stored_results": {"file": str(STORED.relative_to(ROOT)), "sha256": sha(STORED)},
                   "stress_set": {"file": str(E.STRESS.relative_to(ROOT)), "sha256": E.STRESS_SHA256},
                   "gemma_1b_outputs": {p: sha(ROOT / p) for p in ("data/scribe/v4/eval/parity/C-1b-expr-aug/val-batch.jsonl",
                                                                  "data/scribe/v4/eval/outputs/C-1b-expr-aug/test.jsonl",
                                                                  "data/scribe/v4/eval/outputs/C-1b-expr-aug/stress.jsonl")},
                   "nemotron_cache": {k: str(v.relative_to(ROOT)) for k, v in E.NEMO_CACHE.items()},
                   "parsing": "scribe/v4/eval8.py predictions() (batched MLX outputs on all three sets, as the stored cascade)"},
        "policies": {"gemma_1b_alone": "every parsed Gemma 3 1B answer pre-filled (the 1B reader has no flag of its own)",
                     "cascade_C_agreement": "the chosen two-reader cascade: pre-filled only when the code-resolved Gemma 3 1B answer and the "
                                            "Nemotron v3 answer agree exactly",
                     "with_gate_X": "the same, but a note flagged by detector X goes to 'needs editing'",
                     "union": "a note flagged by the post hoc rule OR the frozen A' detector (combination chosen post hoc)"},
        "readme": "scribe/vague/README.md (rendered from this file by scribe/vague/score.py)",
        "sets": {}, "reproduces_stored": {},
    }
    for split in ("val", "test", "stress"):
        rows = E.load_rows(split)
        preds, _missing = E.predictions(split, rows, "batch")
        rule_spans, frozen_spans = detect(rows)
        vague_known = split == "stress"
        entry = {"post_hoc": POST_HOC, "synthetic": True, "notes": len(rows),
                 "detector_rule_v1": flag_summary(rows, rule_spans, vague_known),
                 "detector_frozen_A_prime": flag_summary(rows, frozen_spans, vague_known)}
        union_spans = {k: rule_spans[k] + frozen_spans[k] for k in rule_spans}
        entry["detector_union"] = flag_summary(rows, union_spans, vague_known)
        gates = {"rule_v1": {k: bool(v) for k, v in rule_spans.items()},
                 "frozen_A_prime": {k: bool(v) for k, v in frozen_spans.items()},
                 "union": {k: bool(v) for k, v in union_spans.items()}}
        entry.update(evaluate_split(split, rows, preds, gates))
        if split == "val":
            entry["construction_check"] = ("data/scribe/v2/WRITER_INSTRUCTIONS.md section 3.3 forbids any date or time reference other than the "
                                           "given date strings, and a code check rejects notes in which anything else looks like a date; so no "
                                           "validation or test note holds a vague fact by construction, and every flag there is a false flag")
        doc["sets"][split] = entry
        doc["reproduces_stored"][split] = reproduce_check(stored, split, entry)
    doc["reproduces_stored"]["all_ok"] = all(v["ok"] for v in doc["reproduces_stored"].values() if isinstance(v, dict))
    E.save_json(RESULTS, doc)
    (HERE / "README.md").write_text(render_readme(doc), encoding="utf-8")
    s = doc["sets"]
    metrics = {
        "val_flagged": s["val"]["detector_rule_v1"]["flagged"]["k"], "test_flagged": s["test"]["detector_rule_v1"]["flagged"]["k"],
        "stress_vague_caught": s["stress"]["detector_rule_v1"]["vague_notes_caught"],
        "stress_false_flags": s["stress"]["detector_rule_v1"]["false_flags_on_notes_without_a_vague_fact"]["k"],
        "cascade_test": {k: (v["prefilled_for_one_click_confirmation"]["k"], v["error_among_prefilled"]["k"])
                         for k, v in s["test"]["cascade_C_agreement"].items()},
        "cascade_stress": {k: (v["prefilled_for_one_click_confirmation"]["k"], v["error_among_prefilled"]["k"])
                           for k, v in s["stress"]["cascade_C_agreement"].items()},
        "reproduces_stored": doc["reproduces_stored"]["all_ok"]}
    log("score", "scribe/.venv/bin/python scribe/vague/score.py", outputs={"json": str(RESULTS.relative_to(ROOT))}, metrics=metrics)
    print(json.dumps(metrics, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
