# How we train the Gemma pathway scribe

All notes in this project are SYNTHETIC. Language models wrote every note from sampled answer keys, and
other language models checked them. No real patient text is used. Nothing here is validated clinically,
nothing is for clinical use, and nothing below shows that the scribe would help a patient. A judge or
auditor model only tells us whether two models agree; it does not establish what is true.

Every number is copied from a JSON file in this repository, or from a run log line, and the source is
given in brackets. Figures that no earlier script wrote (paired validation tests between the post-ablation
students, serving parity, epochs, GPU seconds, cost totals) were computed by
`scribe/v2/training_figures.py` into `data/scribe/v2/training-figures-v1.json` [called *figures* below].
Short names: *ablation* = `data/scribe/v2/ablation-v1.json`, *compare* =
`data/scribe/v3/student/compare-v1.json`, *research* = `runs/wf2-research-and-build-reports.json`,
*summary* = `data/scribe/v3/summary-v1.json`.

## 1. The learning problem

The input is one Finnish visit note plus the date it was written. The output is one canonical JSON
object: the patient's entry route (one of 5 values) and a list of completed cancer-pathway events, each
with a type (one of 9), a date `YYYY-MM-DD` and a precision (`DAY` or `MONTH`). Relative dates
("three weeks ago") must be resolved against the note date. The prompt is fixed in `scribe/prompts.py`.
We fine-tune Gemma 3, an instruction-tuned causal language model, by supervised learning. The objective
is the mean token cross-entropy of the answer given the prompt, `L(θ) = -Σ_t log p_θ(y_t | x, y_<t)`,
summed only over the answer tokens and the closing `<end_of_turn>` token; every prompt token has label
-100 and adds nothing to the loss. Only the low-rank adapter matrices are trained (one arm trains all
weights). The primary metric is note-level exact match: the whole canonical JSON must equal the label.
Event F1, route accuracy and the share of unparsable outputs are secondary.

## 2. Data

### Two writers and their gates

| writer | notes written | code check failed | judge (TypeSafe Jev) rejected, of notes past the code check | kept | source |
| --- | --- | --- | --- | --- | --- |
| Nemotron 3.5 Super VL, round 1 | 4,476 generated | 9.8% (9.0-10.7), n = 4,476 | 38.6% (37.1-40.1), n = 4,037 | 2,466 (train 1,716, val 250, test 500) | `data/scribe/dataset-stats.json` |
| Claude Haiku 5.5, version 2 | 1,198 | 0 of 1,198 (0.0-0.3%) | 300 of 1,198, 25.0% (22.7-27.6) | 898 (train 638, val 60, test 200) | `data/scribe/v2/dataset-stats.json` |
| Nemotron, round 2 (5 curricula) | 1,600 | 11 of 1,600 failed after one repair (1,589 passed) | Jev rule with the v2 questions: 83 of 1,589 rejected (accepted 1,506, 94.8%) | 1,506 added to train only | *summary* `teacher.overall`, `gate.overall` |

By kind of Haiku note, Jev rejected 239 of 898 standard notes (26.6%), 61 of 150 careful notes (40.7%) and
0 of 150 no-event notes (0.0-2.5%) [`data/scribe/v2/dataset-stats.json`]. Because the gate rejected no
no-event note, its one question was asked of 60 accepted notes that do contain events; all 60 were judged
to contain an event [`data/scribe/v2/no-event-gate-control.json`]. In round 2 a blind second call of the
teacher read 1,465 of the 1,589 checked notes back exactly as specified (0.922), but only 170 of 238
no-event notes [*summary* `teacher.overall`, `teacher.no_event`]. Splits are made per whole episode, so no
note of one episode sits in two splits [`data/scribe/dataset-stats.json`
`whole_episode_split_reassignments`]. The validation and test files of version 3 are the version-2 files
byte for byte (same sha256, checked for this document) [`scribe/TEACHING.md` section 5, from
`data/scribe/v3/dataset/dataset-stats.json`].

Important for reading the results: `test_haiku` was filtered by the same Jev gate as the Haiku training
notes, so it is not an unfiltered sample of that writer [`data/scribe/v2/dataset/CARD.md`]. It also comes
from the same 12 Haiku writer sessions as the Haiku training notes: notes were held out by a hash of their
id, not by session (`scribe/v2/data_tools.py` `assign_haiku`; review finding 8). Once Haiku notes are in
the training set, `test_haiku` is a held-out sample of a *seen* writer and of seen sessions, not of an
unseen one. And `test_nemotron` is not fresh for the project as a whole: 200 of its 500 notes were scored
by the version-1 model and analysed note by note before version 2 was designed. On those 200 the
selected configuration got 90 right, on the other 300 it got 120 right, 40.0% (34.6-45.6)
[`data/scribe/v2/posthoc-checks-v1.json` `v1_overlap`].

### Independent label audits

The labels are exact for the sampled answer key. The open question is whether the note states exactly
that key. That was checked by other models, never by a person:

| audit | what was read | result | source |
| --- | --- | --- | --- |
| stricter second Jev pass, round 1 | 60 accepted notes | disagreed on 43 of 60 (71.7%, 59.2-81.5); a model-based proxy, biased by stricter thresholds | `data/scribe/audit-summary.json` |
| Claude Sonnet, full read, round 1 | 60 accepted notes | 2 of 60 labels wrong (3.3%, 0.9-11.4), both an ambiguous event type | `data/scribe/label-audit-v1.json` |
| Claude Haiku, labels visible, round 2 | 160 accepted, 80 rejected | accepted: wrong label 2 of 160 (1.25%, 0.34-4.44), wrong label or route not supported 6 of 160 (3.75%, 1.73-7.94); rejected: 2 of 80 and 8 of 80 | *summary* `audit` |
| version-2 Haiku notes | none | neither audit was run on them | `data/scribe/v2/dataset/CARD.md` |

The two round-2 groups were sampled at different rates, so only the by-group rates are meaningful, and
their intervals overlap: this sample does not show that the gate removes wrong labels [*summary*
`audit.sampling`; `scribe/TEACHING.md` section 5]. On a benchmark with planted errors (report half, 80
corrupted and 80 clean pairs) the Jev rule caught 60 of 80 corruptions and rejected 1 of 80 clean pairs
with its first question set, and 66 of 80 and 0 of 80 with the second, which was designed after the first
set's results had been seen [*summary* `judges.report160`, `judges.policy.chosen_on`]. Details:
`scribe/TEACHING.md`.

## 3. What current documentation says about Gemma 3 LoRA fine-tuning

Only facts the research step marked as verified at the source on 2026-11-14 [*research*
`research:lora-practice.facts`]. None of these sources ranks adapter methods for a ~1.7k-example
extraction task; that was not established by any source opened.

- **Sizes.** 270M and 1B are text-only (`Gemma3ForCausalLM`); 4B, 12B and 27B are text plus image
  (`Gemma3ForConditionalGeneration`) ([Unsloth Gemma 3 guide](https://unsloth.ai/docs/models/tutorials/gemma-3-how-to-run-and-fine-tune.md)).
  Google designed the 270M model for task-specific fine-tuning, naming entity extraction and
  unstructured-to-structured text as uses ([Google blog](https://developers.googleblog.com/en/introducing-gemma-3-270m/)).
- **Google's 270M guide is a full fine-tune**: learning rate 5e-5, 5 epochs, batch 4, max length 512,
  constant schedule ([guide](https://ai.google.dev/gemma/docs/core/huggingface_text_full_finetune)).
- **Google's Gemma 3 QLoRA guide** (last Gemma 3 revision): r 16, alpha 16, dropout 0.05,
  `target_modules='all-linear'`, `modules_to_save=['lm_head','embed_tokens']`, lr 2e-4 constant, 3 epochs,
  max sequence length 512 ([cookbook a2d15e8730](https://raw.githubusercontent.com/google-gemma/cookbook/a2d15e8730/docs/core/huggingface_text_finetune_qlora.ipynb)).
  The current guide targets Gemma 4 ([guide](https://ai.google.dev/gemma/docs/core/huggingface_text_finetune_qlora)).
- **Unsloth** targets all seven projections (`q,k,v,o,gate,up,down`), r 16 or 32, alpha r or 2r,
  dropout 0, lr 2e-4, 1-3 epochs, effective batch 16 ([LoRA hyperparameter guide](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide.md)).
- **Precision.** In float16 Gemma 3 activations overflow to infinity; use bfloat16 ([Unsloth](https://unsloth.ai/docs/models/tutorials/gemma-3-how-to-run-and-fine-tune.md)).
- **Template.** There is no system role; system text goes into the first user turn
  ([prompt structure](https://ai.google.dev/gemma/docs/core/prompt-structure)). The template already emits
  `<bos>`, so tokenise with `add_special_tokens=False` or get two
  ([TRL SFT trainer](https://raw.githubusercontent.com/huggingface/trl/v1.18.0/trl/trainer/sft_trainer.py)).
- **Loss on the completion only**, and that includes the closing `<end_of_turn>` (same TRL source).
- **Eager attention is no longer needed**: the warning was removed by
  [transformers PR #40744](https://github.com/huggingface/transformers/pull/40744) (absent from 4.57.1 and 5.23.0).
- **Serving constraint.** vLLM rejects DoRA, adapter bias, `modules_to_save` other than classifier heads
  and PiSSA/OLoRA initialisations unless converted; it accepts plain LoRA and rsLoRA
  ([vLLM peft_helper.py](https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/lora/peft_helper.py)).
  Google's `modules_to_save=['embed_tokens', ...]` would also add 167,772,160 trainable parameters on 270M.
- **Methods.** In the PEFT maintainers' one-seed benchmark (Llama-3.2-3B, MetaMathQA) rank-64 rsLoRA
  scored 0.5133, rank-32 LoRA 0.4784 and DoRA 0.4693, and DoRA trained 1.26 times as long
  ([PEFT method comparison](https://raw.githubusercontent.com/huggingface/peft/v0.21.3/method_comparison/MetaMathQA/results/lora--llama-3.2-3B-rank64-rslora.json)).
- **Versions** on 2026-11-14: peft 0.21.3, transformers 5.23.0, trl 1.18.0; PEFT below 0.18.0 does not
  work with Transformers 5 ([PyPI](https://pypi.org/pypi/peft/json)).

### Three pitfalls in our version-1 code

1. **Transformers 5 removed `warmup_ratio`.** `scribe/train_lora.py` passes it, so `TrainingArguments`
   raises `TypeError` on transformers 5.23.0, the version on the GPU box; `scribe/run_gpu.sh` installed
   the libraries unpinned [`data/scribe/cuda-path-check-v1.json` `would_construct: false`]. Version 2 pins
   torch 2.15.0, transformers 5.23.0, peft 0.21.3, accelerate 1.15.0 (`scribe/v2/run_gpu.sh`) and passes
   an integer `warmup_steps` (`scribe/v2/train.py`).
2. **The stop token was never trained.** The version-1 label mask contains `<end_of_turn>` in 0 of 1,716
   training rows, so the adapter never learns to stop [*research* fact "The v1 label mask never supervises
   the stop token"]. Version 2 supervises it and refuses to run if the last supervised token is not
   `<end_of_turn>` (`scribe/v2/train.py` `encode`); all version-2 runs have `supervise_stop_token: true`
   [*ablation* `runs.*.config`].
3. **A suffix list of target modules also adapts the vision tower** of the 4B and larger models: on a tiny
   multimodal Gemma 3 the seven-suffix list put 6 of 20 adapters into the SigLIP encoder, where text input
   gives them no gradient [*research*]. Version 2 targets a regular expression over the language-model
   layers only (`scribe/v2/config.py`); every version-2 run reports `adapters_in_vision_tower: 0`
   [*ablation* `runs.*.adapter`]. This check is vacuous for the sizes we trained (270M and 1B are
   text-only); 4B never trained.

## 4. Ablation design, and why selection never touches test data

One protocol for every run [*ablation* `protocol`, `selection.config`]: 324 optimisation steps at an
effective batch of 16 (5,184 examples drawn, 3.02 epochs of the 1,716 Nemotron notes [*figures*
`epochs`]), AdamW without weight decay, cosine schedule with 5% warm-up, gradient clip 1.0, bf16, seed
20261114, maximum length 1,024 with refusal rather than truncation, loss on the answer and
`<end_of_turn>`, greedy decoding with tolerant parsing. The control is LoRA r 16, alpha 32 (scale 2.0),
dropout 0, on all seven attention and MLP projections of the language model.

Stages, all chosen on the 310 validation notes (250 Nemotron-written, 60 Haiku-written):

- **A, size ladder**: 270M, 1B, 4B with the control LoRA, plus a 270M full fine-tune at lr 5e-5 (Google's
  270M recipe) as an extra finalist. Rule: highest validation exact match; a smaller size wins if within
  3 points and McNemar p >= 0.05.
- **B, method**: rsLoRA at twice the scale, rsLoRA at four times the rank, LoRA+, PiSSA, DoRA; one change
  at a time against the control.
- **C, output format and data**: a date-expression output format; adding the Haiku training notes.
- **Arm rule**: a change replaces the control only if it is better on the paired validation notes with
  exact McNemar p < 0.05. **Decoding rule**: constrained decoding only if strictly higher on validation.

A planner gave each arm a time estimate and kept a reserve for the final phase; whatever did not fit the
35-minute budget was dropped and recorded [*ablation* `planning`, `dropped`].

Test data is read only after the selection is frozen. The selection was frozen at 18:49:54 UTC
[*ablation* `selection.frozen_utc`]; the two test evaluations are logged at 18:54:10 and 18:58:25 UTC
[`data/scribe/v2/gpu-runs/v2-ablation.jsonl`]. Each system was evaluated on test once. The later
comparisons were fixed in a pre-registration at 19:08:08 UTC, before any of those runs had a test result
[`data/scribe/v3/student/preregistration.json`]. One caveat: the 1B run had written its validation
result to the GPU box 5 seconds earlier, so the 1B test rule was strictly fixed after that result existed
[`data/scribe/v3/student/RUNS.md`, `gpu-logs/queue.log`]. The risk-control threshold (section 7) is the
one place where validation notes were reused after selection.

## 5. Results

### Stage A: size ladder (validation, 310 notes)

| run | configuration | val exact match (95% CI) | Nemotron-written (250) | Haiku-written (60) | training time | peak GPU memory | source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-270m-lora-r16 | LoRA r16, lr 2e-4 | 36.1% (31.0-41.6) | 41.2% | 15.0% | 96 s | 15.5 GiB | *ablation* |
| A-270m-full-finetune | all weights, lr 5e-5 | 37.7% (32.5-43.3) | 43.6% | 13.3% | 199 s | 22.1 GiB | *ablation* |
| S-1b-lora-r16, run after the ablation | LoRA r16, lr 2e-4 | 40.3% (35.0-45.9) | 44.8% | 21.7% | 254 s | 39.8 GiB | `S-1b-lora-r16/result.json` |
| A-4b-lora-r16 | LoRA r16 | **no number** | | | | | |

- The full fine-tune against LoRA: 10 notes only the full fine-tune got right, 5 only LoRA, exact McNemar
  p = 0.302. **Within noise**; LoRA stayed because the finalist rule keeps the incumbent unless the
  challenger is better with p < 0.05 [*ablation* `stages.finalists`]. The rationale string stored at freeze
  time says LoRA "has the highest validation exact match", but it was the only ladder run that finished, and
  the full fine-tune (37.7%) and the version-1 recipe (37.1%) both scored higher; `scribe/v2/RESULTS.md` now
  derives the reading from the stage records instead (review finding 0).
- 1B against the 270M reference: 17 notes against 4, p = 0.0072 (unadjusted). With a Holm correction
  over all ten post-hoc validation pairs it is p = 0.065 [*figures* `validation_pairs`].
- **4B has no number.** Inside the ablation it was dropped by the planner (next table). Afterwards it ran
  out of GPU memory twice, once beside the 1B run and once beside three 270M runs, and a third attempt
  (batch 4, accumulation 4, gradient checkpointing) was stopped by the coordinator so that it would not
  take memory from the pre-registered runs [`data/scribe/v3/student/RUNS.md`; `gpu-logs/s4b.log`,
  `s4b2.log`, `queue3.log`].

### What was dropped for time

| item | reason recorded by the planner [*ablation* `dropped`] |
| --- | --- |
| A-1b-lora-r16 | estimated 792 s (extrapolated from 270M by parameter count) did not fit: a final-phase reserve of 5,448 s left -3,570 s |
| A-4b-lora-r16 | estimated 3,407 s; final-phase reserve 23,429 s |
| B-rslora-scale-x2, B-rslora-rank-x4, B-loraplus, B-pissa | estimated 282 s each (measured), 278 s left after a 1,311 s reserve |
| B-dora | estimated 341 s, 278 s left |
| C-format-expression, C-data-nemotron+haiku | estimated 282 s each, 278 s left |
| zero-shot base on test | did not fit the remaining budget |

Three things this table hides. The reserve that dropped every Stage B and C arm (1,311 s) included time for
the zero-shot base (345 s) and the version-1 recipe (707 s), items that the protocol sacrifices first; without
the zero-shot share the first arm would have fitted, and the zero-shot base was then dropped anyway
[*ablation* `planning`; review finding 2; `scribe/v2/run_ablation.py` now reserves only the never-sacrificed
part]. The 1B reserve alone (5,448 s) was larger than the whole 35-minute budget, so the 1B arm could not
run under that rule. And the 1B estimate was too high: run afterwards, the 1B
arm needed 254 s of training and 444 s in all [*figures* `gpu.planner_estimate_vs_measured_1b`]. Stage B
never ran, so **we have no evidence on rsLoRA, LoRA+, PiSSA or DoRA for this task.** The data arm of
Stage C ran after the ablation as `C-270m-all-v2data` (below).

Constrained decoding gave the same validation exact match as unconstrained decoding (0.361 both; 0
discordant notes), so the frozen setting is unconstrained greedy [*ablation* `selection.decoding_check`].
That check was weak: the two arms were decoded by different code with different token caps (134 and 320),
34 of 310 raw answers differ although 32 of those were already valid JSON without the constraint, and only
2 unconstrained answers were unparsable, so the constraint could have changed at most 2 notes
[`data/scribe/v2/posthoc-checks-v1.json` `decoding_check_audit`].

### Final test results of the ablation (read once, after the freeze)

The selected configuration is `A-270m-lora-r16`. The comparison system is the repaired version-1 recipe
run on 270M (dropout 0.05, batch 2 x accumulation 8, gradient checkpointing, stop token supervised)
[*ablation* `runs.v1-recipe-270m.config`, `scribe/v2/config.py` `v1_recipe`].

| system | test set (writer) | n | note exact match (95% CI) | event F1 | route accuracy | unparsable |
| --- | --- | --- | --- | --- | --- | --- |
| selected | test_nemotron | 500 | 42.0% (37.8-46.4) | 0.675 | 99.2% | 0.2% |
| selected | test_haiku | 200 | 13.0% (9.0-18.4) | 0.413 | 76.5% | 5.5% |
| v1 recipe | test_nemotron | 500 | 42.0% (37.8-46.4) | 0.676 | 99.4% | 0.4% |
| v1 recipe | test_haiku | 200 | 15.0% (10.7-20.6) | 0.434 | 84.0% | 5.0% |

| pair | test set | only selected correct | only v1 recipe correct | exact McNemar p | Holm-adjusted p |
| --- | --- | --- | --- | --- | --- |
| selected vs v1 recipe | test_nemotron | 4 | 4 | 1.000 | 1.000 |
| selected vs v1 recipe | test_haiku | 3 | 7 | 0.344 | 1.000 |
| selected vs v1 recipe | pooled | 7 | 11 | 0.481 | 1.000 |

[*ablation* `test.systems`, `test.mcnemar`; also `scribe/v2/RESULTS.md`.] **All three differences are
within noise.** Of the selected adapter's 11 unparsable Haiku-written answers, 9 were cut at the 134-token
generation cap and 2 were malformed, so that 5.5% measures the cap as much as the model
[*ablation* `test.systems.selected.splits.test_haiku.unparsable_by_cause`]. On Haiku-written notes the selected adapter got 1 of 20 careful notes and 0 of 33 notes
with no event right [*ablation*; *compare* `reference.summary.test_haiku.by_kind`].

### After the ablation: pre-registered data comparisons and the 1B run

Every run keeps the control configuration, seed and 324 steps. A larger training set is therefore seen
for fewer epochs: **the data arms differ in epochs as well as in data**, and these results cannot separate
the two [*figures* `epochs`]. Paired tests are against the reference on the same 700 test notes; the
Holm adjustment covers the three pre-registered comparisons on the pooled endpoint [*compare*
`multiplicity`].

| run | training data | train notes | epochs | val exact match (310) | test_nemotron (500) | test_haiku (200) | pooled (700) | pooled: only new / only reference correct | p | Holm p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A-270m-lora-r16 (reference) | Nemotron round 1 | 1,716 | 3.02 | 36.1% (31.0-41.6) | 42.0% (37.8-46.4) | 13.0% (9.0-18.4) | 33.7% (30.3-37.3) | | | |
| V3-270m-nemotron (primary) | + 1,506 round-2 notes | 3,222 | 1.61 | 40.0% (34.7-45.5) | 41.8% (37.6-46.2) | 29.0% (23.2-35.6) | 38.1% (34.6-41.8) | 54 / 23 | 0.00054 | 0.00054 |
| V3-270m-all | + round 2 + 638 Haiku notes | 3,860 | 1.34 | 40.3% (35.0-45.9) | 39.4% (35.2-43.7) | 40.0% (33.5-46.9) | 39.6% (36.0-43.2) | 63 / 22 | 9.8e-6 | 2.0e-5 |
| C-270m-all-v2data | + 638 Haiku notes | 2,354 | 2.20 | 43.2% (37.8-48.8) | 42.0% (37.8-46.4) | 47.5% (40.7-54.4) | 43.6% (39.9-47.3) | 75 / 6 | 2.9e-16 | 8.7e-16 |
| S-1b-lora-r16 (post hoc, not in the Holm family) | Nemotron round 1, Gemma 3 1B | 1,716 | 3.02 | 40.3% (35.0-45.9) | 43.2% (38.9-47.6) | 27.0% (21.3-33.5) | 38.6% (35.0-42.2) | 46 / 12 | 8.2e-6 | not adjusted |

[Test columns and paired tests: *compare*; validation column and epochs: *figures*.] The same
comparisons per writer, unadjusted [*compare* `paired_vs_reference`]:

| run | Nemotron-written: only new / only ref, p | Haiku-written: only new / only ref, p | no-event Haiku notes right (of 33) |
| --- | --- | --- | --- |
| reference | | | 0 |
| V3-270m-nemotron | 8 / 9, p = 1.0 | 46 / 14, p = 4.2e-5 | 21 |
| V3-270m-all | 4 / 17, p = 0.0072 | 59 / 5, p = 9.0e-13 | 15 |
| C-270m-all-v2data | 6 / 6, p = 1.0 | 69 / 0, p = 3.4e-21 | 21 |
| S-1b-lora-r16 | 12 / 6, p = 0.238 | 34 / 6, p = 8.4e-6 | 0 |

What is real and what is noise:

- **All three pre-registered arms beat the reference on the pooled endpoint**, and stay significant after
  Holm adjustment. In every case the gain comes from the Haiku-written notes.
- **On Nemotron-written notes, nothing improved.** V3-270m-nemotron (41.8%), C-270m-all-v2data (42.0%) and
  the 1B run (43.2%) are within noise of the reference's 42.0%. V3-270m-all is the one real change there,
  and it is a drop: 39.4% against 42.0%, 4 notes against 17, p = 0.0072 (unadjusted).
- **The round-2 curricula help a writer they never saw.** V3-270m-nemotron has no Haiku training notes and
  still went from 13.0% to 29.0% on Haiku-written notes, and from 0 to 21 of 33 no-event notes. That is
  the cleanest evidence of better robustness across writers that we have.
- **The Haiku-written gains of the two arms with Haiku training notes are partly in-distribution.** Their
  `test_haiku` notes come from the writer and the gate they trained on (section 2).
- **Among the four new runs, validation does not separate most of them.** C-270m-all-v2data is highest on
  validation (43.2%), but against S-1b (17 / 8, p = 0.108) and V3-270m-all (16 / 7, p = 0.093) the
  difference is within noise. Against V3-270m-nemotron it is 15 / 5, p = 0.041 unadjusted, 0.248 after a
  Holm correction over all ten pairs [*figures* `validation_pairs`].
- **1B is the only size step we have**, and only on Nemotron-only data. Its test evaluation was triggered
  by the pre-registered validation rule; it is not part of the Holm family. A 1B run with the mixed-writer
  data was not done.

## 6. The recipe we recommend, and how sure we are

**Recommendation.** Gemma 3 270M instruction-tuned (`unsloth/gemma-3-270m-it`, revision
`23cf460f6bb16954176b3ddcc8d4f250501458a9`), LoRA rank 16, alpha 32, dropout 0, on the seven attention
and MLP projections of the language model; AdamW, lr 2e-4, cosine with 5% warm-up, 324 steps at
effective batch 16, bf16; loss on the answer plus `<end_of_turn>`; trained on the gated notes of both
writers (Nemotron round 1 and Haiku); greedy decoding, with schema-constrained outputs when served, and
every extraction sent to a person for confirmation. This is the `C-270m-all-v2data` configuration
[`data/scribe/v3/student/C-270m-all-v2data/result.json` `config`].

**Why.** It has the highest validation exact match of every run we have (43.2%), the choice rule that the
ablation used. The test results agree (43.6% pooled; no loss on Nemotron-written notes, 13.0% to 47.5% on
Haiku-written notes). It is the smallest model and trains in 176 s on one A100 [*figures* `gpu`].

**How sure.** Moderately sure that mixing writers in training helps on notes from those writers: the
effect is large on validation and test and survives Holm adjustment. Not sure that it beats the
round-2 or 1B alternatives: on validation those differences are within noise, and we picked the winner
among three arms whose test results we had already seen, so 43.6% is an optimistic estimate of this
recipe; a fresh test set is needed for an unbiased one. Not sure about anything the runs did not vary:
there is one seed per run, no adapter method beyond plain LoRA was tested, no size above 1B, and data
size is confounded with epochs. Adding the round-2 curricula as well (V3-270m-all) lost accuracy on
Nemotron-written notes; we cannot tell whether that is the fewer epochs (1.34), the 87 round-2 notes that
start with a literal style label [*summary* `dataset.round2_added_to_train_starts_with_style_label`], or
something else. Two concrete next runs: the recommended recipe at 1B, and the round-2 data at a fixed
number of epochs instead of a fixed number of steps.

## 7. Risk control: when may a note skip review?

Rule tested: accept a note automatically when its confidence (mean token log-probability of the
generated answer) reaches a threshold chosen with Learn-then-Test, so that the error rate among accepted
notes is at most alpha with probability at least 0.95 (fixed-sequence testing with the exact binomial
tail; delta 0.05). An error is any difference from the label, or an unparsable answer. Calibration used
the 310 validation notes, whose error rate was 63.9% [*ablation* `risk_control`]. Why LTT and not plain
conformal risk control: CRC bounds the expected joint rate of "accepted and wrong", not the error rate
among accepted notes; LTT section 3.2 covers the selective case
([LTT](https://arxiv.org/pdf/2110.01052), [CRC](https://arxiv.org/pdf/2208.02814)) [*research*
`research:decoding-risk`].

| alpha | threshold (mean log-prob) | calibration: accepted, errors | test_nemotron: accepted, errors | test_haiku: accepted, errors | pooled: accepted, errors |
| --- | --- | --- | --- | --- | --- |
| 0.05 | -0.00502 | 101 of 310 (32.6%), 1 error | 191 of 500 (38.2%), 1 error (0.5%; upper bound 2.5%) | 13 of 200 (6.5%), 2 errors (15.4%; upper bound 41.0%) | 204 of 700 (29.1%), 3 errors (1.5%; upper bound 3.8%) |
| 0.01 | none certified: at least 554 accepted error-free notes would be needed, the calibration set has 308 parsable ones (Bonferroni); no threshold passed (fixed sequence) | | | | |

[*ablation* `risk_control.results`.] Caveats, in order of weight:

- **The calibration notes were also the selection notes**, so they are not a fresh sample, and the
  guarantee is weaker than stated [*ablation* `risk_control.caveat`].
- **The guarantee is marginal over notes like the calibration mix** (250 Nemotron-written, 60
  Haiku-written). It says nothing per writer. On Haiku-written test notes the accepted notes were 2 wrong
  of 13, above the 5% target.
- Errors are measured against model-written labels on synthetic notes. Real clinical notes are not
  exchangeable with them, so no threshold here licenses skipping review of a real note.

The cascade (student answer plus a judge check before a person) was not measured:
`data/scribe/v3/cascade/cascade-v1.json` does not exist. See `scribe/TEACHING.md` section 7 and
`runs/cascade-v3.jsonl`.

## 8. Serving

**vLLM smoke test (executed, on the A100).** vLLM 0.29.0 with xgrammar 0.2.9 [`runs/v2-gpu.jsonl`
`vllm_venv_install`] served the selected 270M adapter as `pathway-scribe` beside the base model. 100
held-out notes (50 from `test_nemotron`, 50 from `test_haiku`), concurrency 8, 384 maximum new tokens
[`serve/smoke/smoke-guided.json`, `smoke-plain.json`]:

| decoding | valid JSON | exact match (95% CI) | route accuracy | event F1 | latency p50 / p95 | notes per second |
| --- | --- | --- | --- | --- | --- | --- |
| structured outputs (JSON schema) | 100 of 100 | 22% (15.0-31.1) | 91% | 0.583 | 1.28 s / 1.80 s | 5.74 |
| plain | 98 of 100 | 22% (15.0-31.1) | 89% | 0.582 | 1.40 s / 1.99 s | 5.21 |

Latency is client-side wall time per request, first request excluded. Provenance of the run (base
revision, adapter, start script, server log) is in `serve/smoke/README.md`.

Against the in-process Transformers evaluation of the same adapter on the same 100 notes
[*figures* `serving_parity`, from `serve/smoke/tools/compare_offline.py`]:

- **Verdicts agree on every note**: 22 right in both, 78 wrong in both, with and without structured
  outputs. Offline exact match on this subset is 19 of 50 Nemotron-written and 3 of 50 Haiku-written
  notes; served, the same.
- **The answers themselves are identical on only 68 of 100 notes (structured outputs) and 70 of 100
  (plain).** Every differing answer is wrong both ways.
- The offline run cut answers at 134 new tokens, the server at 384. Offline, 6 of the 100 answers
  were unparsable (1 Nemotron-written, 5 Haiku-written); served, 0 with structured outputs and 2
  without.

So the 22% reflects the model rather than the serving stack, but serving is not answer-for-answer
identical. The 22% must not be read against the 42.0% and 13.0% test figures: half of these notes are
Haiku-written. Every note went to human review: the client has no calibrated threshold.

**Serverless deployment (planned, NOT executed).** `serve/deploy.md` gives the commands for a Verda
serverless container: the pinned vLLM image, the adapter baked in, scale to zero (`--min-replicas 0`,
`--max-replicas 1`, concurrency 8), on an L40S at 2.22 USD per GPU-hour on demand. No image was pushed,
no deployment created and nothing was spent. Open points include the compute name, registry
credentials, cold-start time and the cost of a paused deployment (`serve/deploy.md` section 10).

## 9. Cost and compute actually used

| item | amount | source |
| --- | --- | --- |
| GPU for training, evaluation and serving tests | one A100 80 GB (`1A100.22V`, on demand, listed 2.386 USD/h), created 16:56:35 UTC, deleted 19:27 UTC: 2.51 h, **5.98 USD at the list price** (not the invoice; shared with the Evo 2 genomics run) | *figures* `machine_cost` |
| training time of the 7 runs with a result | 2,122 s of training, 3,071 s including loading, evaluation loss and validation generation | *figures* `gpu` |
| ablation | 2,077 s of a 35-minute budget | *ablation* `budget` |
| TypeSafe Jev (round-1 gate, version-2 gate, round-2 judges and gate) | 0.2876 + 0.0593 + 0.1715 = **0.5184 USD** | *figures* `api_spend` |
| OpenAI Decisions (judge benchmark) | 1,038,484 tokens in 690 requests; 0.104 USD at the list rate for input tokens | *figures* `api_spend` |
| Claude Haiku as writer | 0.071 USD for 60 early test notes; 0.050 USD reported for the version-2 pilot (5 calls reported no cost) | *figures* `api_spend` |

Unknown, because no file records it: the Nemotron teacher on Verda (4,500 requests in round 1, 4,042 in
round 2, no price read); Haiku writing of the 1,198 version-2 notes beyond the pilot; the Haiku audit of
round 2; the first GPU machine (`az-equity-gpu-20261114`); the GPU time of the test evaluations and of the
three 4B attempts. A total cost of the project therefore cannot be given.

## 10. What failed

- **The first GPU machine was lost.** `az-equity-gpu-20261114` stopped answering at 16:31 UTC (last
  contact 16:29:42) and came back about 17:01 with a different SSH host key, which was not accepted; the
  version-1 4B training never ran [`runs/train.jsonl`, `runs/genomics.jsonl`, `scribe/RESULTS.md`]. The
  coordinator attributes the loss to another job draining the shared cloud balance; no file in this
  repository records the cause.
- **Transformers 5 broke the version-1 script** (`warmup_ratio`, section 3). It would have failed at
  `TrainingArguments` even if the machine had stayed up [`data/scribe/cuda-path-check-v1.json`].
  With the machine lost, version 1 instead ran as a reduced MLX fallback on a laptop (Gemma 3 1B, 41.0% exact match on 200
  test notes; a different protocol, not comparable with the tables above) [`scribe/RESULTS.md`].
- **4B ran out of memory** twice on a shared GPU; the third attempt was stopped (section 5).
- **A GPU sat idle for about an hour.** Between the end of the Evo 2 scoring at 17:27:31 UTC and the
  version-2 set-up at 18:23:27 UTC, 55.9 minutes, no run log records any work on the A100 [*figures*
  `gpu.gap_between_recorded_gpu_jobs`]. The coordinator attributes this to a monitoring bug; the
  repository records only the gap.
- **The planner dropped 1B and all of Stage B and C** (section 5): a 1B final-phase reserve larger than the
  whole budget, a 1B estimate of 792 s against 254 s of training measured later, and a reserve for items
  that are sacrificed first; each Stage B arm was estimated at 282 s with 278 s left. Fixed in
  `scribe/v2/run_ablation.py` after the review; not rerun, because the GPU machine is gone.
- **The batch tool for short-lived GPU machines had a cleanup hole.** The version-2 review found that
  `ops/verda_job.py` skipped deleting its machine when the terminal or a pipe it printed to went away,
  and trusted an HTTP 503 as proof that no machine was created. Both are fixed and covered by tests that
  fail on the old code (`ops/README.md`). The tool was never used against Verda, so no machine was lost
  this way.
- Smaller failures, each repaired and rerun once: both round-2 runs stopped at the length guard (one note
  of 1,050 tokens against a guard of 1,024; raised to 1,536); the first V3-270m-nemotron run ran out of
  memory while a 4B attempt was loading; the first test evaluation of C-270m-all-v2data started in the
  wrong working directory [`data/scribe/v3/student/RUNS.md`]. The zero-shot base model was never scored on
  test.

## 11. Limits

- Synthetic notes, model-written labels, model-only audits. Exact match measures agreement with the
  teacher-and-judge pipeline, not truth, and says nothing about real clinical notes.
- One seed per run. With 310 validation notes the 95% interval is about 5 points either side, so gains of
  a few points cannot be resolved.
- The held-out sets are small and come from two writers only; `test_haiku` is gated, shares writer
  sessions with the Haiku training notes and is, for arms trained on Haiku notes, in-distribution; 200 of
  the 500 `test_nemotron` notes had been analysed in version 1. The round-2 curricula (terse, long,
  careful, no-event) have no held-out set of their own [`scribe/TEACHING.md` section 6].
- Fixed steps confound data size with epochs. Stage B never ran. Nothing above 1B was measured.
- The risk-control threshold was calibrated on the selection notes, and on the minority writer the
  accepted notes had 2 errors in 13, above the target (13 notes alone cannot prove a violation, and cannot
  rule one out either).
- Gemma 3 is under the Gemma Terms of Use. Adapters are Model Derivatives, and the Prohibited Use Policy
  names automated decisions in healthcare ([terms](https://ai.google.dev/gemma/terms),
  [policy](https://ai.google.dev/gemma/prohibited_use_policy)). Every extraction stays a proposal until a
  person confirms it.
