# Pathway scribe, version 2: a measured comparison

All notes are SYNTHETIC. Research artefact, not for clinical use. Gemma 3 is used under the Gemma Terms of Use.

Version 1 trained one recipe and reported one number. Version 2 runs a staged comparison under a time
budget and reports what each choice was worth on validation notes, then reads the test notes once.
The ablation ran once, on 2026-11-14 on an A100 80 GB (Verda, `az-equity-a100-20261114`) with a
35-minute budget: `RESULTS.md` is rendered by `report.py` from `data/scribe/v2/ablation-v1.json`, and the
run log is `data/scribe/v2/gpu-runs/v2-ablation.jsonl`. Only 3 configurations were trained, all on 270M
(the LoRA control, the full fine-tune and the version-1 recipe); the 1B and 4B rungs and every Stage B and C
arm were dropped for time. Later runs with this code (1B, data arms) are in `data/scribe/v3/student/`, and
`TRAINING.md` at the project root puts all of it together. Post-hoc checks of the finished run (review of
2026-11-14) are in `posthoc_checks.py` and `data/scribe/v2/posthoc-checks-v1.json`.

## Run

```bash
# CPU, no model, no network (100 tests, about 2 seconds):
scribe/.venv/bin/python -m unittest discover -s scribe/v2/tests

# What would run, and which data and formats are available right now:
scribe/.venv/bin/python scribe/v2/run_ablation.py --plan --time-budget-min 60

# Fresh Ubuntu CUDA box (one GPU with bfloat16): installs pinned libraries, runs the tests,
# downloads the three pinned models, then runs the ablation for 60 minutes.
bash scribe/v2/run_gpu.sh 60
```

Copy to the box, keeping the paths: `scribe/` (without `.venv` and `artifacts`), `data/scribe/v2/dataset/`,
`data/scribe/dataset-v1/`, `data/scribe/haiku-test.jsonl`, and an empty `runs/`.

Outputs: `data/scribe/v2/ablation-v1.json`, `scribe/v2/RESULTS.md` (rendered from that JSON by
`report.py`), one directory per run under `scribe/v2/artifacts/` (adapter, `loss-curve.json`,
`result.json`, per-note validation records, `train.log`), and a run log in `runs/v2-ablation.jsonl`.

## Files

| file | what it does | needs a GPU |
| --- | --- | --- |
| `config.py` | one `RunConfig` per run; generates the stage grids | no |
| `data_iface.py` | the only module that touches `data_tools.py` and the data files | no |
| `formats.py` | absolute and expression output formats, tolerant JSON parsing | no |
| `constrained.py` | schema-constrained decoding engine behind `prefix_allowed_tokens_fn` | no |
| `risk.py` | Learn-then-Test threshold for auto-accepting notes, plus its simulation | no |
| `report.py` | `RESULTS.md` from the ablation JSON | no |
| `modeling.py` | model loading, adapters (LoRA, rsLoRA, DoRA, PiSSA, EVA, LoRA+), saving | yes |
| `train.py` | one run: train, loss curve, validation by generation, `result.json` | yes |
| `evaluate.py` | greedy decoding, scoring, breakdowns by writer and kind; scoring is pure Python | decoding only |
| `run_ablation.py` | stages A, B, C, final run, frozen selection, test evaluation, risk control | yes |
| `run_gpu.sh` | set-up and launch on a fresh box | yes |
| `posthoc_checks.py` | post-hoc checks of the finished ablation from saved records; `--resummarise` re-runs the test summariser | no |
| `training_figures.py` | derived figures quoted in `TRAINING.md` (`data/scribe/v2/training-figures-v1.json`) | no |

## Design

- **Stage A, size.** Default LoRA (rank 16, alpha 32, all seven language-model projections, no dropout),
  absolute format, Nemotron notes, 324 optimisation steps at an effective batch of 16 on 270M, 1B and 4B.
  The 270M full fine-tune (Google's documented use of that model) runs alongside as a finalist.
- **Stage B, method and initialisation** on the chosen size, one change at a time: rsLoRA at twice the
  scale, rsLoRA at four times the rank and the same scale, LoRA+ (ratio 16, base rate halved),
  PiSSA (`pissa_niter_4`, alpha = r), optionally EVA (`--with-eva`), DoRA last.
- **Stage C, format then data** on the chosen method: expression output against absolute dates, then
  Nemotron+Haiku training notes against Nemotron only, at the same number of steps.
- **Final.** The selected configuration is the final run (an identical finished run is reused; use
  `--final-steps` or `--retrain-final` to train it again). Constrained decoding is checked on validation.
  The version-1 recipe is trained. Then the selection is frozen and the base model zero-shot, the
  version-1 recipe and the selected configuration are evaluated once on `test_nemotron` and `test_haiku`,
  with exact McNemar tests (Holm-adjusted p-values alongside) and the risk-control check.
- **Selection rules** are fixed in `run_ablation.py` before any run. Size: highest validation exact
  match, but the smaller model if it is within 3 points and not significantly worse (paired exact McNemar
  p >= 0.05). Arm: replaces its control only if better with p < 0.05 on the paired validation notes
  (unadjusted for the number of arms). Decoding: constrained only if strictly higher on validation.
- **Test isolation.** `train.py` never loads a test split. `evaluate.py` refuses a test split unless it is
  given the frozen selection file, which `run_ablation.py` writes only after every choice is made and
  deletes at the start of a session. Selection code sees a validation-only view of each run; a unit test
  feeds it results whose test fields raise when read.
- **Time budget.** Items claim the budget in order: A sizes small to large, A extras, B arms as listed,
  C format, C data. An item runs only if its estimate fits in what is left after reserving the part of the
  final phase that is never sacrificed (the test of the selected configuration, plus its final run if it
  must be retrained); otherwise it is dropped and listed in the output. Until the review of 2026-11-14 the
  reserve also covered the decoding check, the version-1 recipe and the zero-shot base, which dropped
  every Stage B and C arm of the A100 run by a few seconds each (finding 2). Estimates come from runs measured in the same
  session, scaled by parameter count for a size not yet measured. The smallest size always runs first and
  is never cut short. In the final phase the constrained-decoding check goes first, then the version-1
  recipe, then the zero-shot base; the selected configuration is always tested.
- **Risk control.** `risk.py` picks the confidence threshold on the validation notes of the selected
  system so that the error among auto-accepted notes is at most alpha (0.01 and 0.05) with probability at
  least 0.95, then reports coverage and realised error on the test sets. Confidence is the mean token
  log-probability under the unconstrained model distribution. Certifying alpha = 0.01 needs at least 299
  accepted notes without a single error, so 250 validation notes cannot do it; the code says so instead
  of returning a threshold.

## Gemma-specific settings and where they come from

From the research step of 2026-11-14 (sources opened that day; tiny random models on CPU only):
pinned ungated mirrors `unsloth/gemma-3-{270m,1b,4b}-it`; `dtype=bfloat16` and `attn_implementation="sdpa"`
(float16 overflows); the chat template already contains `<bos>`, so text is tokenised with
`add_special_tokens=False`; the loss covers the answer and its `<end_of_turn>`; target modules are a
regular expression limited to the language model (a suffix list also adapts the SigLIP vision tower of
4B); no `modules_to_save`; integer warm-up steps (`warmup_ratio` is gone in Transformers 5); libraries
pinned to torch 2.15.0, transformers 5.23.0, peft 0.21.3, accelerate 1.15.0.

Added while writing this code:

- **Answer-only output head.** The stock forward pass computes logits over the 262k-token vocabulary for
  every position; at batch 16 and about 520 tokens that is roughly 2.2 billion numbers per step, of which
  about 85% are discarded by the label mask. `modeling.answer_only_loss` applies the head to the
  supervised positions only. It gives the same loss as the stock path (identical on tiny text and
  multimodal Gemma 3 models), every run compares the two on two examples before training and falls back
  to the stock path if they disagree, and `--full-logits` forces the stock path.
- **Full fine-tune in float32** master weights with bfloat16 autocast. This is a decision, not something
  taken from Google's guide.
- **Out-of-memory retry.** A run that runs out of memory is started again with half the batch and twice
  the accumulation (same effective batch); the retry is recorded.

## Constrained decoding

Plain Transformers has one constraint hook, `prefix_allowed_tokens_fn`. `constrained.py` feeds it from a
small engine of its own: the JSON schema is compiled to a character automaton and a token is allowed when
its characters keep the automaton alive. It emits exactly the compact, key-ordered JSON the adapter is
trained on. `lm-format-enforcer` is used instead when it is installed and the engine cannot compile a
schema; if neither works the output is parsed tolerantly. Each evaluation records which of the three was
used. Calendar validity (31 February) is still checked after decoding.

## What is taken from `data_tools.py`

`data_iface.py` is the only module that imports `scribe/v2/data_tools.py` (written by another step). It
looks for these names, first existing one wins; the file as it stands on 2026-11-14 provides the first
name of every row:

| purpose | names tried |
| --- | --- |
| rows of a split (`train_nemotron`, `train_haiku`, `val_*`, `test_*`) | `load_split(name)`, `load_rows(name)`, `read_split(name)` |
| chat messages asking for the expression format | `expression_messages(row)`, `messages_expression(row)` |
| the exact target text (or a dict, dumped compactly) | `expression_target(row)`, `to_expression(row)`, `target_expression(row)` |
| expression object + note date to the absolute form | `resolve_expression(obj, note_date)`, `resolve(...)`, `to_absolute(...)` |
| optional JSON schema for constrained decoding | `EXPRESSION_SCHEMA`, `expression_schema()` |

If the split loader fails (the dataset is not built), files are looked up as `<name>.parquet|jsonl` or
`train|val|test.parquet|jsonl` (filtered on the row's writer) under `data/scribe/v2/dataset-v2/`,
`data/scribe/v2/` or `data/scribe/dataset-v2/`, then the version-1 files and `data/scribe/haiku-test.jsonl`.
Rows need `id`, `note_text`, `note_date` and either `target_json` or `ground_truth`; `writer` and `kind`
drive the breakdowns. Before any GPU time is spent on the expression format, the first 200 training rows
must survive the round trip target text -> parse -> resolve and come back as their own labels. A stage
whose data or format is missing or fails that check is dropped with the reason in the output.

## Checked on this machine (CPU only, 2026-11-14)

- **Unit tests:** 100 pass (90 before the review fixes of 2026-11-14) with `scribe/.venv` (Python 3.12, no torch): grid generation, stage selection
  on made-up results including results whose test fields raise when read, time-budget dropping with a fake
  clock, the risk-control guarantee simulation, report generation, the decoding engine, scoring, label
  masking, and five checks against the real `data_tools.py`.
- **Constrained decoding with the real Gemma 3 tokenizer** (262,145 tokens): 300 of 300 random walks
  through the absolute schema and 200 of 200 through the expression schema decode to compact, schema-valid
  JSON; all 2,466 version-1 labels are in the absolute schema's language; the tokenizer's own segmentation
  of 500 absolute and 300 expression labels is allowed at every step and ends on the stop token.
- **Expression format of the real `data_tools.py`:** 3,000 sampler rows and all 1,200 slice specifications
  give targets inside the schema's language that resolve back to their labels.
- **Token lengths of the built version-2 dataset, real tokenizer:** no example exceeds 768 tokens in either
  format (longest: 686 absolute, 761 expression, both in `train_nemotron`); the longest answer is 118 tokens
  absolute and 139 expression. The Nemotron training split is 887,017 tokens per epoch in the absolute
  format, the same figure the research step measured.
- **Wiring with tiny randomly initialised Gemma 3 models** (transformers 5.23.0, peft 0.21.3, torch 2.15.0,
  real tokenizer, text-only and multimodal classes): every arm type (LoRA, rsLoRA at two settings, LoRA+,
  PiSSA, EVA, DoRA, full fine-tune, the 4B stand-in, the version-1 recipe with gradient checkpointing)
  trains, saves, reloads in a new process and decodes. Reloaded models reproduce the trained model's token
  log-probabilities to within 3e-8 (the PiSSA adapter after conversion to a plain rank-32 LoRA included)
  and differ from the base model. No adapter lands in the vision tower. The answer-only loss equals the
  stock loss. `run_ablation.py` ran end to end several times, the last time on the built version-2 dataset
  with both Stage C arms, with final-run reuse and with `--resume`. These runs say nothing about Gemma.
- **Risk control, 5,000 simulated calibration draws per setting:** the chosen threshold had true risk above
  alpha in at most 66 of 5,000 draws (1.3%) with 500 calibration notes and 54 of 5,000 (1.1%) with 250,
  against the 5% that the guarantee allows, across three synthetic scenarios including one with
  confidently wrong notes.

## Not checked, and what could go wrong

- When this section was written nothing had run on a GPU. Since then the A100 run measured 270M (and,
  after the ablation, 1B) throughput and memory (`RESULTS.md`, `TRAINING.md`); 4B ran out of memory twice on
  a shared card and has no number. `run_gpu.sh` ran there once.
- The 270M mirror's chat template carries Unsloth's own fixes and was not opened here; the wiring tests
  used the 1B tokenizer for every size. If a template does not put `<end_of_turn>` directly after the answer,
  `train.py` stops that run with a "chat template drift" error and the ladder continues with the next size.
- Time estimates are extrapolated by parameter count until a size has been measured, and the multipliers
  for DoRA, gradient checkpointing and small batches are planning values. A run that overshoots is cut by
  its time cap and then does not count; the output says so.
- EVA repeats passes over the training data until its components converge; how long that takes on real
  notes is unknown. It is off unless `--with-eva` is given.
- `lm-format-enforcer` is not installed here, so that path is untested. The engine in `constrained.py` is
  what will run.
- The validation notes choose the configuration and also calibrate the risk threshold. That is what was
  asked for, and it makes the calibration notes not quite a fresh sample; the test check is the honest
  read-out. With 310 validation notes alpha = 0.01 needs at least 299 accepted notes with no error at all.
- The fixed-sequence threshold search starts where enough notes are accepted, which depends on the
  calibration confidences (not on labels). The guarantee is exact when confidence orders notes by error;
  the Bonferroni variant reported next to it needs no such assumption. Report one of them, chosen in
  advance (the code marks fixed_sequence as primary).
- One seed per arm and no correction for the number of arms: a difference of a few points on 310
  validation notes is noise, which is why an arm must win a paired test to replace its control.
- Gemma 4 was not considered; the scope was Gemma 3.
