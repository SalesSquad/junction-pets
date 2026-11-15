"""Write scribe/RESULTS.md (and print the key numbers as JSON).

Where the figures come from:
  metrics            data/scribe/eval-v1.json (scribe/mlx_fallback.py merge) and data/scribe/post-eval-v1.json
                     (scribe/post_eval.py), both computed from the stored predictions;
  run circumstances  runs/train.jsonl, read here, and the meta block of eval-v1.json. That block was assembled by
                     scribe/artifacts/build_meta.py, which computes the training figures from the run's files but
                     types in the framework versions, host hardware, base-model snapshot and outage times. Every
                     one of those that runs/train.jsonl also records is compared with the log below, and the
                     script stops on a difference. The host hardware is not in any log;
  GPU box            runs/genomics.jsonl (the other job on that box) for the GPU model and the outage;
  provenance         data/scribe/provenance-v1.json (scribe/provenance.py);
  v1 CUDA path       data/scribe/cuda-path-check-v1.json (scribe/check_cuda_path.py).
Sentences and table layout are written here; the figures in them are read from those files.

  scribe/.venv/bin/python scribe/results_md.py                              # scribe/RESULTS.md only
  scribe/.venv/bin/python scribe/results_md.py --update-data-collection     # also the status block of DATA_COLLECTION.md

SYNTHETIC data only; research artefact, not a medical device.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
E = json.loads((ROOT / "data/scribe/eval-v1.json").read_text())
M = E["meta"]
_post = ROOT / "data/scribe/post-eval-v1.json"
P = json.loads(_post.read_text()) if _post.exists() else None
_prov = ROOT / "data/scribe/provenance-v1.json"
PROV = json.loads(_prov.read_text()) if _prov.exists() else None
_cuda = ROOT / "data/scribe/cuda-path-check-v1.json"
CUDA = json.loads(_cuda.read_text()) if _cuda.exists() else None
STATS = json.loads((ROOT / "data/scribe/dataset-stats.json").read_text())


def _log(path):
    return [json.loads(x) for x in (ROOT / path).read_text().splitlines() if x.strip()]


RUN = _log("runs/train.jsonl")
GEN = _log("runs/genomics.jsonl") if (ROOT / "runs/genomics.jsonl").exists() else []


def step(name, log=RUN):
    s = next((d for d in log if d.get("step") == name), None)
    if s is None:
        raise SystemExit(f"runs/train.jsonl has no step {name}")
    return s


S_GPU, S_DOWN, S_KEY = step("gpu_setup"), step("gpu_unreachable"), step("gpu_host_key_changed")
S_FB, S_ABORT, S_TRAIN = step("local_fallback_setup"), step("local_train_aborted"), step("local_train")
S_HAIKU, S_HCHECK = step("haiku_write_notes"), step("haiku_code_check")
GPU_MODEL = next((d["metrics"].get("gpu") for d in GEN if d.get("step") == "gpu_preflight" and d.get("host") == S_GPU["host"]), None)
OTHER_JOB_OUTAGE = any(d.get("step") == "gpu_unreachable" for d in GEN)
DOWN_FROM = re.search(r"(\d\d:\d\d)-\d\d:\d\d UTC", S_DOWN["command"])[1]
KEY_AT = re.search(r"at (\d\d:\d\d) UTC", S_KEY["command"])[1]
ABORT_BATCH = re.search(r"batch (\d+)", S_ABORT["command"])[1]


def check_meta_against_log():
    """Every run circumstance that the meta block types in and runs/train.jsonl also records must agree."""
    g, t, h = M["gpu"], M["training"], M["haiku"]
    gm = S_GPU["metrics"]
    pairs = [
        ("planned model", g["planned_model"], S_GPU["inputs"]["base_model"]),
        ("GPU set-up versions", all(f"{k} {gm[k]}" in g["setup"] for k in ("torch", "transformers", "peft")), True),
        ("GPU cache size", g["setup"].endswith(gm["hf_cache_size"].rstrip("G") + " GB"), True),
        ("last contact", g["last_contact_utc"], S_DOWN["metrics"]["last_successful_contact_utc"]),
        ("unreachable from", g["unreachable_from_utc"], DOWN_FROM),
        ("host key changed at", g["host_key_changed_utc"], KEY_AT),
        ("known host key", g["known_key"], S_KEY["metrics"]["known_ed25519"]),
        ("new host key", g["new_key"], S_KEY["metrics"]["new_ed25519"]),
        ("base snapshot", M["base_model_snapshot"], S_FB["inputs"]["snapshot"]),
        ("base model", E["base_model"], S_FB["inputs"]["base_model"]),
        ("framework", M["framework"].startswith(f"MLX {S_FB['metrics']['mlx']}, mlx-lm {S_FB['metrics']['mlx_lm']}"), True),
        ("wall-clock budget", t["wall_clock_cap_minutes"], S_TRAIN["inputs"]["wall_clock_budget_minutes"]),
        ("iterations", t["iterations_reached"], S_TRAIN["metrics"]["iterations"]),
        ("train start", t["train_start_utc"].replace("+00:00", "Z"), S_TRAIN["metrics"]["train_start_utc"]),
        ("train end", t["train_end_utc"].replace("+00:00", "Z"), S_TRAIN["metrics"]["process_exit_observed_utc"]),
        ("validation notes per pass", t["val_notes_per_pass"], S_TRAIN["metrics"]["val_notes"]),
        ("Haiku successful calls", h["calls_ok"], S_HAIKU["metrics"]["calls_ok"]),
        ("Haiku failed calls", h["calls_failed"], S_HAIKU["metrics"]["calls_failed_max_tokens"]),
        ("Haiku cost of successful calls", h["cost_usd_successful"], S_HAIKU["metrics"]["cost_usd_successful"]),
        ("Haiku cost of failed calls", h["cost_usd_failed"], S_HAIKU["metrics"]["cost_usd_failed"]),
        ("Haiku notes accepted", h["accepted"], S_HCHECK["metrics"]["accepted"]),
        ("Haiku notes rejected", h["rejected"], S_HCHECK["metrics"]["rejected"]),
    ]
    bad = [(name, a, b) for name, a, b in pairs if a != b]
    if bad:
        raise SystemExit(f"eval-v1.json meta disagrees with runs/train.jsonl: {bad}")
    return len(pairs)


CHECKED = check_meta_against_log()
_la = ROOT / "data/scribe/label-audit-v1.json"
LA = json.loads(_la.read_text()) if _la.exists() else None
LABEL_AUDIT = (
    f"A separate reading of {LA['n']} sampled accepted notes in full by a second model ({LA['auditor']}) judged {LA['label_wrong']} labels wrong "
    f"({100 * LA['wilson95'][0]:.1f}% to {100 * LA['wilson95'][1]:.1f}%; `data/scribe/label-audit-v1.json`; limits: {LA['limits']}). "
    "The two model-based audits disagree widely and neither is a human audit."
    if LA else "")
KEY = {}


def pct(w):
    if w["value"] is None:
        return "n/a (n=0)"
    return f"{100 * w['value']:.1f}% ({100 * w['ci95'][0]:.1f}–{100 * w['ci95'][1]:.1f}; n={w['n']})"


def f3(x):
    return f"{x:.3f}"


def pv(p):
    return f"{p:.3g}"


def fails(lo, hi, who):
    return sum(p[who] is None for p in E["predictions"][lo:hi])


def block(name, part, lo, hi, tag):
    b, a = part["base"], part["adapter"]
    rows = [
        ("Event-level F1 (type and date exact)", f3(b["f1"]), f3(a["f1"])),
        ("Event precision (Wilson 95%)", pct(b["precision"]), pct(a["precision"])),
        ("Event recall (Wilson 95%)", pct(b["recall"]), pct(a["recall"])),
        ("Event type-only F1", f3(b["type_only_f1"]), f3(a["type_only_f1"])),
        ("Note-level exact match (Wilson 95%)", pct(b["note_exact_match"]), pct(a["note_exact_match"])),
        ("Route accuracy (Wilson 95%)", pct(b["route_accuracy"]), pct(a["route_accuracy"])),
        ("Distractor date extracted as an event (Wilson 95%)", pct(b["distractor_extraction"]), pct(a["distractor_extraction"])),
        ("Output not valid canonical JSON (counted as failure)", f"{fails(lo, hi, 'base')} of {hi - lo}", f"{fails(lo, hi, 'adapter')} of {hi - lo}"),
    ]
    out = [f"| {name} | base | base + adapter |", "| --- | --- | --- |"]
    out += [f"| {r[0]} | {r[1]} | {r[2]} |" for r in rows]
    mc = part["mcnemar"]
    rc = part["risk_coverage"]
    out += [
        "",
        f"McNemar exact two-sided test on note-level exact match: base-only correct {mc['base_only_correct']}, "
        f"adapter-only correct {mc['adapter_only_correct']}, p = {pv(mc['exact_p'])}.",
        "",
        "Risk-coverage, in sample (notes ranked by mean log-probability of the generated JSON tokens; largest share of the "
        "top-ranked notes whose error rate on these same notes is at or below the limit). The cut-off is chosen and scored on "
        "the same notes, so these shares are optimistic. They do not say how many notes could skip review; "
        "see \"Confidence threshold fixed on validation notes\" below:",
        "",
        "| error limit | base | base + adapter |",
        "| --- | --- | --- |",
        f"| at most 1% | {100 * rc['base']['largest_empirical_coverage']['0.01']:.1f}% | {100 * rc['adapter']['largest_empirical_coverage']['0.01']:.1f}% |",
        f"| at most 5% | {100 * rc['base']['largest_empirical_coverage']['0.05']:.1f}% | {100 * rc['adapter']['largest_empirical_coverage']['0.05']:.1f}% |",
    ]
    KEY.update(
        {
            f"{tag}_n": str(hi - lo),
            f"{tag}_event_f1_base": f3(b["f1"]),
            f"{tag}_event_f1_adapter": f3(a["f1"]),
            f"{tag}_note_exact_base": pct(b["note_exact_match"]),
            f"{tag}_note_exact_adapter": pct(a["note_exact_match"]),
            f"{tag}_route_accuracy_base": pct(b["route_accuracy"]),
            f"{tag}_route_accuracy_adapter": pct(a["route_accuracy"]),
            f"{tag}_mcnemar_p": pv(mc["exact_p"]),
            f"{tag}_mcnemar_base_only_adapter_only": f"{mc['base_only_correct']} / {mc['adapter_only_correct']}",
            f"{tag}_coverage_at_1pct_error_adapter": f"{100 * rc['adapter']['largest_empirical_coverage']['0.01']:.1f}%",
            f"{tag}_coverage_at_5pct_error_adapter": f"{100 * rc['adapter']['largest_empirical_coverage']['0.05']:.1f}%",
            f"{tag}_invalid_json_base": f"{fails(lo, hi, 'base')} of {hi - lo}",
            f"{tag}_invalid_json_adapter": f"{fails(lo, hi, 'adapter')} of {hi - lo}",
        }
    )
    return out


def forms(part):
    out = [
        "| date form | notes | base F1 | adapter F1 | base exact match | adapter exact match |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for f, v in part["by_date_form"].items():
        out.append(
            f"| {f} | {v['base']['note_exact_match']['n']} | {f3(v['base']['f1'])} | {f3(v['adapter']['f1'])} | "
            f"{pct(v['base']['note_exact_match'])} | {pct(v['adapter']['note_exact_match'])} |"
        )
        KEY[f"test_form_{f}_adapter_f1"] = f3(v["adapter"]["f1"])
    return out


n = E["counts"]["test"]
x = E["counts"]["extra_test"]
T, H = E["test"], E.get("extra_test")
t, d, h, g = M["training"], M["dataset"], M["haiku"], M["gpu"]
ta, tb = T["adapter"]["note_exact_match"], T["base"]["note_exact_match"]
mc = T["mcnemar"]
better = ta["value"] > tb["value"] and mc["exact_p"] < 0.05
verdict = (
    f"On this test the adapter beats the base model: note-level exact match {pct(ta)} against {pct(tb)}, "
    f"McNemar p = {pv(mc['exact_p'])}."
    if better
    else f"The adapter does NOT beat the base model on this test: note-level exact match {pct(ta)} against {pct(tb)}, "
    f"McNemar p = {pv(mc['exact_p'])}."
)
KEY["verdict"] = "adapter beats base" if better else "adapter does not beat base"
hist = T["adapter"]["date_error_histogram"]
zero = hist.get("0", 0)
total = sum(hist.values())

def haiku_reject_line(h):
    """Why the Haiku notes were rejected: counted from the rejected notes if present, else the run log's words."""
    path = ROOT / "scribe/artifacts/haiku-writer/rejected.jsonl"
    if path.exists():
        import collections

        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        why = collections.Counter(
            (tuple(sorted(w.lower() for w in r["code_check"].get("extra", []))), tuple(r["code_check"].get("missing", []))) for r in rows)
        if len(why) == 1:
            (extra, missing), k = next(iter(why.items()))
            if extra and not missing:
                words = ", ".join(f"\"{w}\"" + (" (today)" if w == "tänään" else "") for w in extra)
                return (f"All {k} rejected Haiku notes failed the code check for one reason: {words} counted as an undeclared date expression "
                        "(`scribe/artifacts/haiku-writer/rejected.jsonl`).")
        return f"Rejected Haiku notes by code-check reason (extra, missing): {dict(why)}."
    return f"{h['rejected']} Haiku notes were rejected; run log: \"{S_HCHECK['metrics']['reject_reason']}\"."


def cuda_lines():
    """What the version-1 CUDA training would have done on the GPU box (data/scribe/cuda-path-check-v1.json)."""
    if not CUDA:
        return ["- The version-1 CUDA scripts were not checked against the libraries of the GPU box (run `scribe/check_cuda_path.py`)."]
    if CUDA["would_construct"]:
        return [f"- `{CUDA['script']}` constructs its training arguments under transformers {CUDA['transformers_here']} (checked by `scribe/check_cuda_path.py`)."]
    return [
        f"- **The version-1 GPU training could not have run there either.** `{CUDA['script']}` passes "
        + ", ".join(f"`{k}`" for k in CUDA["keywords_rejected"])
        + f" to `TrainingArguments`, which transformers {CUDA['transformers_here']} rejects; that is the version the box had installed"
        f" ({'same version' if CUDA['same_version_as_gpu_box'] else 'NOT the same version: ' + str(CUDA['transformers_on_gpu_box'])}). `scribe/run_gpu.sh` installs "
        + ", ".join(CUDA["run_gpu_sh_unpinned_packages"]) + " without a version pin, so a fresh run would get the same failure. "
        f"Checked on {CUDA['checked_utc'][:10]} by `scribe/check_cuda_path.py` (`data/scribe/cuda-path-check-v1.json`). "
        f"The training attempt itself was never made: {'no' if not CUDA['training_attempt_on_gpu_box_logged'] else 'a'} training step on the box is logged.",
        f"- **Superseded.** The GPU path is now {CUDA['superseded_by']}. The version-1 CUDA path (`scribe/run_gpu.sh`, `scribe/train_lora.py`, "
        "`scribe/evaluate.py`) is kept as it was and has never run on a GPU.",
    ]


def provenance_lines():
    if not PROV:
        return []
    b, v, te, pl = PROV["base_model"], PROV["verifier"], PROV["teacher"], PROV.get("planned_model", {})
    return [
        f"  Snapshot `{b['snapshot']}`, converted from `{b['upstream_repository']}` (licence tag `{b['licence_tag']}`);",
        f"  weights `{b['weights_file']}`, {b['weights_bytes']:,} bytes, sha256 `{b['weights_sha256']}`.",
        f"  Terms: <{PROV['terms']['gemma_terms_of_use']}> and <{PROV['terms']['gemma_prohibited_use_policy']}>. The adapter is a derivative and subject to them.",
        "",
        "## Model and service versions",
        "",
        "| role | what the logs record |",
        "| --- | --- |",
        f"| Base model of the fallback | `{b['repository']}`, snapshot `{b['snapshot']}`, sha256 of the weights `{b['weights_sha256'][:16]}…` |",
        f"| Framework of the fallback | MLX {PROV['framework']['mlx']}, mlx-lm {PROV['framework']['mlx_lm']} |",
        *([f"| Planned model (not trained) | `{pl['repository']}`, snapshot `{pl['snapshot']}`; on the box: "
           + ", ".join(f"{k} {val}" for k, val in pl["libraries_installed_on_gpu_box"].items()) + " |"] if pl else []),
        f"| Teacher (writes the notes) | `{te['model_id']}`, {sum(c['calls'] for c in te['calls'].values()):,} calls; {te['version']} |",
        f"| Verifier (accepts or rejects) | alias `{v['model_alias_requested']}`, {v['calls']:,} calls; {v['resolved_version']}. Same day, other jobs: "
        + "; ".join(f"`{x['model']}` in `{x['file']}` at {x['at_utc']}" for x in v["same_day_versions_recorded_elsewhere"]) + " |",
        f"| Independent writer | {PROV['independent_writer']['model']} ({PROV['independent_writer']['model_source']}) |",
        "",
        "Sources: `data/scribe/provenance-v1.json`, written by `scribe/provenance.py` from `runs/scribe.jsonl`, `runs/train.jsonl`, the cached snapshot and the files named there.",
    ]


L = [
    "# Pathway scribe: training and evaluation results (v1)",
    "",
    "SYNTHETIC ONLY. Every note here was written by a language model about simulated people. Research artefact,",
    "not a medical device, not for clinical use.",
    "",
    "Generated by `scribe/results_md.py`. Metrics come from `data/scribe/eval-v1.json` and `data/scribe/post-eval-v1.json`,",
    "computed from the stored predictions. Run circumstances come from `runs/train.jsonl` and from the meta block of",
    "`eval-v1.json`; that block was assembled by `scribe/artifacts/build_meta.py`, which types in the framework versions,",
    f"host hardware, base-model snapshot and outage times. {CHECKED} values of that block that the run log also records were compared",
    "with the log when this file was written and agree. The host hardware is in no run log; it was checked against the machine",
    "(`sysctl`, step check_host_hardware in `runs/scribe-v1-fix.jsonl`). Versions and terms come from `data/scribe/provenance-v1.json`.",
    "",
    "## What was run, and what was not",
    "",
    f"- **The planned run did not happen.** The plan was a LoRA adapter on `{g['planned_model']}` on a Verda GPU box"
    + (f" ({GPU_MODEL}, `runs/genomics.jsonl`)." if GPU_MODEL else "."),
    f"  The box was set up ({g['setup']}), then stopped answering at {g['unreachable_from_utc']} UTC (last contact {g['last_contact_utc']} UTC).",
    f"  At {g['host_key_changed_utc']} UTC the address answered again with a different SSH host key",
    f"  (known `{g['known_key']}`, new `{g['new_key']}`). The changed key was not accepted and nothing was run there.",
    "  " + ("The same outage is recorded by the other job on that box (`runs/genomics.jsonl`). " if OTHER_JOB_OUTAGE else "")
    + f"Run log: \"{S_KEY['metrics']['action']}\". **No Gemma 3 4B number exists.**",
    *cuda_lines(),
    f"- **What ran instead:** a reduced fallback on the MacBook Pro ({M['host_hardware']}) with MLX:",
    f"  `{E['base_model']}` (an MLX conversion of Gemma 3 1B instruction-tuned, ungated; Gemma terms apply), not the",
    "  `unsloth/gemma-3-1b-it` mirror named in the plan, and not on CUDA.",
    *provenance_lines(),
    "",
    "Reductions against the plan:",
    "",
    f"- **Reduced training:** {t['iterations_used']} training notes, each seen once ({t['share_of_epoch']} of one pass over the {d['train']} available),",
    f"  a count fixed in advance to fit a wall-clock budget of {t['wall_clock_cap_minutes']:g} minutes. It took {t['wall_clock_seconds']} s from process start to exit,",
    "  model loading and validation passes included, while the base-model evaluation shared the machine.",
    f"- **Reduced test:** a seeded random {n} of the {d['test']} test notes (seed {M['test_subset_seed']}), plus {x} notes written by Claude Haiku.",
    "  Intervals are wide accordingly. (The adapter was later run on all test notes; see below.)",
    f"- A first local attempt with batch size {ABORT_BATCH} was stopped; run log: \"{S_ABORT['metrics']['reason']}\" "
    f"({S_ABORT['metrics']['iterations_completed']} iterations completed).",
    "",
    "## Data",
    "",
    "| item | count |",
    "| --- | --- |",
    f"| Training notes available (Nemotron-written, code check and Jev accepted) | {d['train']} |",
    f"| Validation notes available / used per validation pass | {d['val']} / {t['val_notes_per_pass']} |",
    f"| Test notes available / evaluated | {d['test']} / {n} |",
    f"| Rejected by the verifier (not used) | {d['rejected']} |",
    f"| Independent-writer tuples sampled (seed {h['seed']}, no id shared with the dataset or cache) | {h['sampled']} |",
    f"| Haiku notes written / accepted by the same code check / evaluated | {h['written']} / {h['accepted']} / {x} |",
    "",
    haiku_reject_line(h),
    "The Haiku notes passed the code check only; they were not sent through Jev.",
    f"Haiku cost reported by the tool: ${h['cost_usd_successful']} for the {h['calls_ok']} successful calls, plus ${h['cost_usd_failed']} for {h['calls_failed']} calls",
    f"that ended at the token limit without output (that part read from the helper's own ledger; total ${h['cost_usd_total']}).",
    f"Run log on the call sizes: planned \"{S_HAIKU['inputs']['plan']}\"; actual \"{S_HAIKU['inputs']['actual']}\".",
    "",
    "Label quality warning carried over from the dataset card: a stricter second Jev pass disagreed with",
    f"{d['audit_disagreements']} of {d['audit_sampled']} accepted notes. Training and test labels come from the same teacher and the same filter, so",
    "the test measures agreement with that pipeline, not clinical truth.",
    LABEL_AUDIT,
    "",
    "## Training",
    "",
    "| setting | value |",
    "| --- | --- |",
    f"| Base model | `{E['base_model']}` |",
    f"| Framework | {M['framework']} |",
    f"| LoRA | rank {t['lora_rank']}, scale {t['lora_scale']}, dropout {t['lora_dropout']}, all {t['lora_layers']} layers, attention and MLP projections |",
    f"| Trainable parameters | {t['trainable_parameters']} |",
    f"| Batch / gradient accumulation / learning rate | {t['batch_size']} / {t['grad_accumulation']} / {t['learning_rate']} constant, AdamW |",
    "| Loss | assistant turn only (prompt masked), stop token included |",
    f"| Iterations planned / completed / in the evaluated checkpoint | {t['iterations_planned']} / {t['iterations_reached']} / {t['iterations_used']} |",
    f"| Wall-clock budget / actual | {t['wall_clock_cap_minutes']:g} min / {t['wall_clock_seconds']} s ({'budget reached, run cut' if S_TRAIN['metrics'].get('cap_hit') else 'budget not reached'}) |",
    f"| Training loss, first report (iteration {t['first_train_iter']}) / last report (iteration {t['last_train_iter']}) | {t['first_train_loss']} / {t['last_train_loss']} |",
    f"| Validation loss by iteration ({t['val_notes_per_pass']} notes) | {t['val_losses']} |",
    f"| Adapter file | `{t['adapter_file']}`, {t['adapter_bytes']} bytes, sha256 `{t['adapter_sha256']}` |",
    "",
    "Loss curve, training log and configuration: `data/scribe/train-artifacts/` (copies; the weights stay git-ignored under `scribe/artifacts/`).",
    "",
    f"## Held-out test notes (n = {n}, Nemotron-written)",
    "",
    f"Same prompt for both models (`scribe/prompts.py`), {E['decoding']} decoding, at most {E['max_new_tokens']} new tokens. An output that is not",
    "valid JSON in the exact required shape counts as a failed note with no events.",
    "",
]
L += block("metric", T, 0, n, "test")
L += ["", f"**Verdict.** {verdict}", ""]
L += [
    f"Date error on events whose type was found (adapter): {zero} of {total} dates exact.",
    "",
    "### By date form",
    "",
    "A note is counted under every date form it contains, so the groups overlap.",
    "",
]
L += forms(T)


def relative(part, tag):
    out = [
        "| notes | n | adapter event F1 | adapter note-level exact match | base note-level exact match |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, label in [("with_relative_date", "contain a relative date (N days or weeks ago)"), ("absolute_dates_only", "absolute dates only")]:
        v = part[name]
        out.append(
            f"| {label} | {v['adapter']['note_exact_match']['n']} | {f3(v['adapter']['f1'])} | {pct(v['adapter']['note_exact_match'])} | {pct(v['base']['note_exact_match'])} |"
        )
        KEY[f"{tag}_{name}_adapter_note_exact"] = pct(v["adapter"]["note_exact_match"])
        KEY[f"{tag}_{name}_adapter_event_f1"] = f3(v["adapter"]["f1"])
    return out


RD = E["by_relative_date"]
_rel, _abs = RD["test"]["with_relative_date"]["adapter"]["note_exact_match"], RD["test"]["absolute_dates_only"]["adapter"]["note_exact_match"]
L += [
    "",
    "### Relative against absolute dates",
    "",
    (f"The adapter does not resolve relative dates: none of the {_rel['n']} test notes that contain one is fully right, while "
     if _rel["value"] == 0 else f"On test notes that contain a relative date the adapter is fully right in {pct(_rel)}, while ")
    + f"notes with only absolute dates are fully right in {pct(_abs)}.",
    f"Event types are still found (type-only F1 {f3(T['adapter']['type_only_f1'])}); where a date is wrong it is off, in both directions,",
    f"by between {min(abs(int(k)) for k in hist if int(k))} and {max(abs(int(k)) for k in hist)} days. A note with a relative date therefore still needs a date calculator in code or a person.",
    "",
]
L += relative(RD["test"], "test")
if H:
    L += [
        "",
        f"## Notes written by a different model (Claude Haiku, n = {x})",
        "",
        "These test whether the adapter learned the task or the teacher's writing style. Same prompt and decoding.",
        "",
    ]
    L += block("metric", H, n, n + x, "haiku")
    L += ["", "Relative against absolute dates:", ""]
    L += relative(RD["extra_test"], "haiku")
def validator_sentence(O):
    """What eventlog/validate.py reports on the ground truth (post-eval-v1.json, pathway_order_check)."""
    v = (O.get("eventlog_validator") or {}).get("by_split")
    if not v:
        return "The eventlog validator was not run on these episodes."
    acc = [k for k in ("train", "val", "test") if k in v]
    flagged = sum(v[k]["episodes_flagged"] for k in acc)
    same = all(v[k]["same_episodes_as_pair_check"] for k in v)
    strict = [k for k in acc if not v[k]["strict_mode_valid"]]
    return (f"Run on the ground truth, `eventlog/validate.py` flags {flagged} accepted episodes{' (the same ones)' if same else ' (not exactly the same ones)'}"
            + (f" and {v['haiku']['episodes_flagged']} Haiku notes" if "haiku" in v else "")
            + f"; its strict mode for simulator output rejects {'every split' if len(strict) == len(acc) else ', '.join(strict) or 'no split'}.")


def crossing_sentence(V):
    """Whether any id, target or note text occurs in more than one split (post-eval-v1.json, split_overlap)."""
    c = V.get("crossing_splits")
    if not c:
        return "Ids, targets and note texts across splits were not checked."
    if not any(c.values()):
        return "No id, target (route and events) or note text occurs in more than one split."
    return "Occurring in more than one split: " + ", ".join(f"{k} {v}" for k, v in c.items()) + "."


def limit_lines():
    out = []
    if P:
        S, O = P["selective"], P["pathway_order_check"]
        held = [lim for lim, v in S["limits"].items()
                if v["test_all"].get("error_upper_bound_95_one_sided") is not None and v["test_all"]["error_upper_bound_95_one_sided"] <= float(lim)]
        acc = O["accepted_episodes_with_reversed_pair"], O["accepted_episodes"]
        out += [
            "- The in-sample risk-coverage shares are optimistic by construction. With the cut-off fixed on validation notes "
            + ("no target is shown to hold" if not held else "only " + ", ".join(f"at most {100 * float(x):g}%" for x in held) + " is shown to hold")
            + " on the test notes (see that section). Every extraction needs human confirmation until a threshold",
            "  has been validated on real, human-labelled notes.",
            f"- About one episode in {round(acc[1] / acc[0])} of the ground truth ({acc[0]} of {acc[1]}) breaks the pathway order that `DATA_COLLECTION.md` now documents (see above).",
        ]
    else:
        out += ["- The risk-coverage shares are in sample and optimistic; no out-of-sample threshold was computed (run `scribe/post_eval.py`)."]
    out += [
        "- Gemma's prohibited-use policy restricts automated decisions in healthcare. Letting extractions into a record without a",
        "  person confirming them would fall under it; this is one more reason the design keeps `verified_by_human`.",
    ]
    if PROV:
        v = PROV["verifier"]
        out += [f"- The verifier was called through the floating alias `{v['model_alias_requested']}`; the version it resolved to during the dataset build was",
                "  not captured (`data/scribe/provenance-v1.json`)."]
    return out


def post_sections():
    """Checks added after review, from data/scribe/post-eval-v1.json."""
    if not P:
        return ["", "## Checks added after review", "", "`data/scribe/post-eval-v1.json` is missing; run `scribe/post_eval.py`.", ""]
    S, A, O, V, D = P["selective"], P["adapter_all_test"], P["pathway_order_check"], P["split_overlap"], P["dedup_report"]
    ub = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"

    def cell(c):
        if not c.get("admitted"):
            return "none admitted"
        return (f"{c['admitted']} of {c['n']} admitted, {c['errors_among_admitted']} wrong "
                f"({100 * c['error_rate_among_admitted']:.1f}%; at most {ub(c['error_upper_bound_95_one_sided'])})")

    out = ["", "## Confidence threshold fixed on validation notes", "",
           "The risk-coverage figures above pick their cut-off on the notes they are scored on. Here the cut-off is fixed on the",
           f"{S['validation_notes']} validation notes ({S['validation_note']}), then applied unchanged to the test notes and the Haiku-written notes.",
           f"Score: {S['score']}. \"At most\" is the exact one-sided 95% upper bound on the error rate among admitted notes.", "",
           f"| target error | validation (where the cut-off is set) | all {A['n']} test notes | Haiku-written notes |",
           "| --- | --- | --- | --- |"]
    for lim, v in S["limits"].items():
        out.append(f"| at most {100 * float(lim):g}% | {cell(v['validation'])} | {cell(v['test_all'])} | {cell(v['haiku'])} |")
    one, five = S["limits"]["0.01"], S["limits"]["0.05"]
    need = S["notes_needed_without_error_for_claim"]
    # A target is shown to hold on the test notes only if the exact upper bound is at or below it.
    held = {lim: (v["test_all"].get("error_upper_bound_95_one_sided") is not None and v["test_all"]["error_upper_bound_95_one_sided"] <= float(lim))
            for lim, v in S["limits"].items()}
    t5 = five["test_all"]
    out += ["",
            ("Reading: neither target is shown to hold out of sample. " if not any(held.values()) else
             "Reading: shown to hold out of sample at 95% confidence: " + ", ".join(f"at most {100 * float(k):g}%" for k, h in held.items() if h) + ". ")
            + f"At the 1% cut-off the test notes give {one['test_all']['errors_among_admitted']} wrong among {one['test_all']['admitted']} admitted, "
            f"which is compatible with an error rate up to {ub(one['test_all']['error_upper_bound_95_one_sided'])}. At the 5% cut-off the observed error is "
            f"{100 * t5['error_rate_among_admitted']:.1f}%, {'above' if t5['error_rate_among_admitted'] > 0.05 else 'at or below'} the target "
            f"(upper bound {ub(t5['error_upper_bound_95_one_sided'])}). "
            f"A claim of at most 1% error at 95% confidence needs at least {need['0.01']} admitted notes without a single error (at most 5%: {need['0.05']}). "
            + ("**No extraction can skip human confirmation on this evidence.**" if not any(held.values()) else
               "Even so, synthetic notes do not establish an error rate on real notes; every extraction stays a proposal a person confirms."),
            f"Of the {one['test_all']['notes_with_relative_date']} test notes with a relative date, {one['test_all']['admitted_with_relative_date']} are admitted at the 1% cut-off and "
            f"{t5['admitted_with_relative_date']} at the 5% cut-off (of {t5['admitted']} admitted): the score mostly separates notes with and without relative dates.",
            "",
            "In-sample cut-offs for comparison (chosen on the notes they are scored on, as in the first evaluation), and what happens when they are moved to the other set:", "",
            f"| target error | chosen and scored on the {n} test notes | chosen and scored on the Haiku notes | Haiku cut-off applied to the {n} test notes | test cut-off applied to the Haiku notes |",
            "| --- | --- | --- | --- | --- |"]
    for lim, v in S["limits"].items():
        c = v["in_sample_for_comparison"]
        out.append(f"| at most {100 * float(lim):g}% | {cell(c['test_first_200'])} | {cell(c['haiku'])} | {cell(c['haiku_threshold_applied_to_test_first_200'])} | {cell(c['test_threshold_applied_to_haiku'])} |")

    a = A["adapter"]
    out += ["", f"## The adapter on all {A['n']} test notes", "",
            f"{A['note'][0].upper() + A['note'][1:]}.", "",
            "| notes | n | event F1 | note-level exact match | route accuracy | invalid JSON |", "| --- | --- | --- | --- | --- | --- |",
            f"| all test notes | {A['n']} | {f3(a['f1'])} | {pct(a['note_exact_match'])} | {pct(a['route_accuracy'])} | {A['invalid_json']} |",
            f"| the {n} of the first evaluation | {A['first_200']['note_exact_match']['n']} | {f3(A['first_200']['f1'])} | {pct(A['first_200']['note_exact_match'])} | {pct(A['first_200']['route_accuracy'])} | |",
            f"| the other {A['other_300']['note_exact_match']['n']} | {A['other_300']['note_exact_match']['n']} | {f3(A['other_300']['f1'])} | {pct(A['other_300']['note_exact_match'])} | {pct(A['other_300']['route_accuracy'])} | |",
            f"| contain a relative date | {A['with_relative_date']['note_exact_match']['n']} | {f3(A['with_relative_date']['f1'])} | {pct(A['with_relative_date']['note_exact_match'])} | {pct(A['with_relative_date']['route_accuracy'])} | |",
            f"| absolute dates only | {A['absolute_dates_only']['note_exact_match']['n']} | {f3(A['absolute_dates_only']['f1'])} | {pct(A['absolute_dates_only']['note_exact_match'])} | {pct(A['absolute_dates_only']['route_accuracy'])} | |",
            "", f"Validation notes (n = {S['validation_notes']}): note-level exact match {pct(S['validation_exact_match'])}."]

    e, ne = O["episodes_with_reversed_pair"], O["episodes"]
    w = O["without_those_episodes"]
    acc = O["accepted_episodes_with_reversed_pair"], O["accepted_episodes"]
    out += ["", "## Ground truth against the documented pathway order", "",
            f"`DATA_COLLECTION.md` section 1 fixes one order (`eventlog/schema.py`). {O['sampler_order_differs'][0].upper() + O['sampler_order_differs'][1:]}. "
            f"Counted against the documented order, {acc[0]} of {acc[1]} accepted episodes ({100 * acc[0] / acc[1]:.1f}%, about one in {round(acc[1] / acc[0])}) contain a reversed pair "
            f"({e['train']} of {ne['train']} training, {e['val']} of {ne['val']} validation, {e['test']} of {ne['test']} test), and {e['haiku']} of the {ne['haiku']} Haiku notes. "
            "By pair: " + "; ".join(f"{k}: {v}" for k, v in sorted(O["reversed_pairs_by_type"].items())) + ". "
            + validator_sentence(O) + " "
            f"{O['consequence'][0].upper() + O['consequence'][1:]}.", "",
            "Scores without those episodes: "
            f"adapter note-level exact match on all test notes {pct(w['test_all_adapter_exact_match'])}; on the {n} of the first evaluation {pct(w['test_first_200_adapter_exact_match'])} "
            f"(base {pct(w['test_first_200_base_exact_match'])}); on the Haiku notes {pct(w['haiku_adapter_exact_match'])}. "
            "The sampler was not changed and the data were not regenerated: a second dataset version built in parallel depends on the sampler as it is.",
            "", "## Identical event lists across splits", "",
            f"{V['cause'][0].upper() + V['cause'][1:]}. {V['test_notes_sharing_an_event_list_with_a_training_note']} of the {A['n']} test notes have exactly the event list of a training note "
            f"({V['of_which_in_first_200']} of them among the {n} first evaluated; {V['of_which_single_event']} are single-event notes; the adapter got {V['adapter_correct_among_them']} of them right). "
            f"Without them the adapter's exact match on the test notes is {pct(V['test_all_adapter_exact_match_without_them'])}. "
            f"Validation notes sharing an event list with a training note: {V['val_notes_sharing_an_event_list_with_a_training_note']}. " + crossing_sentence(V),
            "", "## De-duplication of cached rows", ""]
    if "ids_occurring_more_than_once" in D:
        out += [f"{D['rule_used_for_dataset_v1'][0].upper() + D['rule_used_for_dataset_v1'][1:]}. Of {D['cache_rows_with_a_verdict']} cached rows, {D['ids_occurring_more_than_once']} ids occur more than once: "
                f"in {D['first_row_rejected_and_a_later_row_accepted']} the first row was rejected and a later one accepted, in {D['first_row_accepted_and_another_accepted_row_dropped']} a second accepted note was dropped. "
                f"{D['consequence'][0].upper() + D['consequence'][1:]}."]
    else:
        out += [D["status"]]
    KEY.update({
        "validation_exact_match_adapter": pct(S["validation_exact_match"]),
        "test_all_500_exact_match_adapter": pct(a["note_exact_match"]),
        "selective_1pct_test_all": cell(one["test_all"]),
        "selective_5pct_test_all": cell(five["test_all"]),
        "selective_1pct_haiku": cell(one["haiku"]),
        "episodes_with_reversed_pair": f"{O['accepted_episodes_with_reversed_pair']} of {O['accepted_episodes']}",
    })
    return out


L += post_sections()


def lenient(part, tag):
    b, a, mc = part["base"], part["adapter"], part["mcnemar"]
    KEY[f"{tag}_lenient_event_f1_base"] = f3(b["f1"])
    KEY[f"{tag}_lenient_event_f1_adapter"] = f3(a["f1"])
    KEY[f"{tag}_lenient_note_match_base"] = pct(b["note_match_ignoring_precision"])
    KEY[f"{tag}_lenient_note_match_adapter"] = pct(a["note_match_ignoring_precision"])
    KEY[f"{tag}_lenient_mcnemar_p"] = pv(mc["exact_p"])
    return [
        "| metric (lenient reading) | base | base + adapter |",
        "| --- | --- | --- |",
        f"| Event-level F1 (type and date) | {f3(b['f1'])} | {f3(a['f1'])} |",
        f"| Event precision (Wilson 95%) | {pct(b['precision'])} | {pct(a['precision'])} |",
        f"| Event recall (Wilson 95%) | {pct(b['recall'])} | {pct(a['recall'])} |",
        f"| Note match, precision field ignored (Wilson 95%) | {pct(b['note_match_ignoring_precision'])} | {pct(a['note_match_ignoring_precision'])} |",
        f"| Route accuracy (Wilson 95%) | {pct(b['route_accuracy'])} | {pct(a['route_accuracy'])} |",
        f"| Outputs with no readable JSON object | {b['unreadable']} | {a['unreadable']} |",
        "",
        f"McNemar exact two-sided: base-only correct {mc['base_only_correct']}, adapter-only correct {mc['adapter_only_correct']}, p = {pv(mc['exact_p'])}.",
    ]


if "lenient" in E:
    L += [
        "",
        "## Supplementary: the same outputs read leniently",
        "",
        "The strict score above fails a note for any deviation from the required JSON shape. To see what the base model",
        "understands apart from the format, the same outputs are re-read while tolerating code fences, a missing",
        "`precision` field, extra keys and a repeated `events` key. This reading is not the headline metric.",
        "",
        f"### Test notes (n = {n})",
        "",
    ]
    L += lenient(E["lenient"]["test"], "test")
    if "extra_test" in E["lenient"]:
        L += ["", f"### Haiku-written notes (n = {x})", ""]
        L += lenient(E["lenient"]["extra_test"], "haiku")

L += [
    "",
    "## Limits",
    "",
    "- Not the planned model, hardware or training length. Nothing here says how Gemma 3 4B would do.",
    "- The base model almost never produces the required JSON shape, so the strict comparison is mostly a format comparison.",
    "  The lenient reading shows the base model is also weak on content (it mostly names one event and the wrong date).",
    "  What the short fine-tune taught is the output format, the event types, the route and copying absolute dates;",
    "  it did not teach date arithmetic.",
    *limit_lines(),
    "- Simulated notes are short, one style family, with dates given in "
    + f"{len(STATS['date_forms'])} fixed forms ({', '.join(STATS['date_forms'])}). Real clinical text is harder.",
    "- Labels are unaudited by humans (see the warning above).",
    "",
    "## Files",
    "",
    "- `data/scribe/eval-v1.json`: all metrics, curves and every prediction (`scribe/mlx_fallback.py merge`).",
    "- `data/scribe/haiku-test.jsonl`: the accepted Haiku-written notes with their ground truth.",
    f"- `data/scribe/post-eval-v1.json`: validation-fixed thresholds, the adapter on all {P['adapter_all_test']['n'] if P else 'the'} test notes, order and overlap checks (`scribe/post_eval.py`).",
    "- `data/scribe/provenance-v1.json`: base-model snapshot and weight hash, terms, teacher and verifier identifiers and versions (`scribe/provenance.py`).",
    "- `data/scribe/cuda-path-check-v1.json`: whether the version-1 CUDA script would construct its training arguments (`scribe/check_cuda_path.py`).",
    "- `data/scribe/train-artifacts/`: training log, loss curve, LoRA configuration, Haiku call ledger, evaluation meta block.",
    "- `scribe/artifacts/adapter-v1/`: the adapter weights (git-ignored).",
    "- `runs/train.jsonl`: one line per executed step of the run, including the failures; `runs/scribe-v1-fix.jsonl`: the checks after review.",
    "- `scribe/mlx_fallback.py`: the local training-data, inference and scoring code used here.",
    "",
    "## The version-1 CUDA path is superseded",
    "",
    "`scribe/run_gpu.sh`, `scribe/train_lora.py` and `scribe/evaluate.py` were repaired after the first attempt (stop token supervised,",
    "batched decoding, wall-clock cap) but have never run on a GPU"
    + (f", and `scribe/train_lora.py` would stop at `TrainingArguments` under transformers {CUDA['transformers_here']} "
       f"(rejected: {', '.join(CUDA['keywords_rejected'])})" if CUDA and not CUDA["would_construct"] else "")
    + ". Do not use them for the planned run. `scribe/v2/` is the GPU path: `scribe/v2/run_gpu.sh` pins the library versions",
    "and its training uses integer warm-up steps; see `scribe/v2/README.md`.",
    "",
]
(ROOT / "scribe/RESULTS.md").write_text("\n".join(L))


def document_status():
    """Status paragraph for DATA_COLLECTION.md section 4, between SCRIBE:STATUS markers. Every figure is
    read from the evaluation files. Returns the block; writing it into DATA_COLLECTION.md is opt-in."""
    a, b = T["adapter"], T["base"]
    rd = RD["test"]
    au = d
    out = [f"**Status, 14 November 2026 (SYNTHETIC; details in `scribe/RESULTS.md`).** The planned run, a LoRA adapter on `{g['planned_model']}` on a CUDA box, did not happen: "
           f"the box became unreachable before training. A reduced fallback ran instead on a laptop: `{E['base_model']}`, {t['iterations_used']} training notes seen once, "
           f"{t['wall_clock_seconds']} s. On {n} held-out notes the adapter reaches note-level exact match {pct(a['note_exact_match'])} against {pct(b['note_exact_match'])} for the base model, "
           f"which almost never produces the required format, and route accuracy {pct(a['route_accuracy'])}. "
           f"It does not resolve relative dates: {pct(rd['with_relative_date']['adapter']['note_exact_match'])} exact on notes that contain one, "
           f"{pct(rd['absolute_dates_only']['adapter']['note_exact_match'])} on notes with absolute dates only."]
    if P:
        S, O = P["selective"], P["pathway_order_check"]
        one, five = S["limits"]["0.01"]["test_all"], S["limits"]["0.05"]["test_all"]
        out += [f"On all {P['adapter_all_test']['n']} test notes the exact match is {pct(P['adapter_all_test']['adapter']['note_exact_match'])}. "
                f"With a confidence cut-off fixed on the {S['validation_notes']} validation notes, the cut-off aimed at 1% error admits {one['admitted']} test notes with {one['errors_among_admitted']} wrong "
                f"(compatible with an error rate up to {100 * one['error_upper_bound_95_one_sided']:.1f}%), and the one aimed at 5% admits {five['admitted']} with {five['errors_among_admitted']} wrong "
                f"({100 * five['error_rate_among_admitted']:.1f}%). No extraction can skip human confirmation on this evidence.",
                f"Two warnings about the labels. A stricter second pass of the verifier disagreed with {au['audit_disagreements']} of {au['audit_sampled']} accepted notes"
                + (f", while a second model reading {LA['n']} sampled notes in full judged {LA['label_wrong']} labels wrong" if LA else "")
                + "; neither is a human audit, so the test measures agreement with the teacher-and-verifier pipeline, not truth. "
                f"And {O['accepted_episodes_with_reversed_pair']} of {O['accepted_episodes']} accepted episodes break the pathway order of section 1, because the sampler still uses an older order "
                "(`data/scribe/dataset-v1/ERRATA.md`). The measured extraction error was not fed back into the design study of section 3."]
    return "\n".join(out)


def data_collection_status(write):
    """Compare (and with write=True replace) the SCRIBE:STATUS block of DATA_COLLECTION.md. That file belongs to
    the whole project, so it is only written when --update-data-collection is given."""
    path = ROOT / "DATA_COLLECTION.md"
    if not path.exists():
        return "DATA_COLLECTION.md missing"
    block = f"<!-- SCRIBE:STATUS:BEGIN -->\n{document_status()}\n<!-- SCRIBE:STATUS:END -->"
    doc = path.read_text()
    pattern = re.compile(r"<!-- SCRIBE:STATUS:BEGIN -->.*?<!-- SCRIBE:STATUS:END -->", re.S)
    found = pattern.search(doc)
    if not found:
        return "no SCRIBE:STATUS markers"
    if found.group(0) == block:
        return "current"
    if write:
        path.write_text(pattern.sub(lambda _: block, doc))
        return "updated"
    return "stale: run with --update-data-collection"


KEY["data_collection_status_block"] = data_collection_status("--update-data-collection" in sys.argv[1:])
KEY.update(
    {
        "train_notes_available": str(d["train"]),
        "train_iterations_used": str(t["iterations_used"]),
        "adapter_sha256": t["adapter_sha256"],
        "adapter_bytes": str(t["adapter_bytes"]),
        "haiku_notes_accepted": f"{h['accepted']} of {h['written']}",
        "haiku_cost_usd_total": str(h["cost_usd_total"]),
    }
)
json.dump(KEY, sys.stdout, ensure_ascii=False, indent=1)
