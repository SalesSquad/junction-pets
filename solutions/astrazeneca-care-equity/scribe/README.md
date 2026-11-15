# SAMA pathway scribe

Reads one Finnish visit note plus its note date and proposes the patient's entry route and dated cancer-pathway events (spec: DATA_COLLECTION.md section 4). All notes are SYNTHETIC, nothing is for clinical use, and a person confirms every proposed event.

**Start here.** Final numbers: [v4/RESULTS.md](v4/RESULTS.md). Reproduce them offline in seconds, with no key, network, model or GPU: `bash scribe/v4/reproduce.sh` (prints REPRODUCED or DIFFERS and leaves `data/` untouched; see [v4/README.md](v4/README.md)). What is live code and what is kept as history: [ARCHIVE.md](ARCHIVE.md). How the models were trained: [../TRAINING.md](../TRAINING.md).

## Current pipeline (as of 15 November 2026)

Legend: **[keys]** needs an API key or hosted endpoint; **[GPU]** needs a GPU or Apple-silicon training run; **[offline]** reproducible from stored files (`v4/reproduce.sh` covers steps 8 and 9).

1. **Sample answer keys** (entry route, events, dates; no text yet) [offline]. `sample.py`; round 2 `teacher2/specs.py`; stress set `stress/specs.py`, `stress/phrases.py`.
2. **Teacher writes the notes** [keys]. Nemotron 3.5 Super VL: round 1 `generate.py` (+ `finalise.py`), round 2 `teacher2/protocol.py`; stress notes `stress/pipeline.py`, code gate `stress/check.py`. Haiku-written notes go through `v2/data_tools.py`. Prompts: `prompts.py`.
3. **Jev judges check note against key** [keys]. TypeSafe System One (and Decisions) in `judges/core.py`, run by `judges/run.py`; planted-error benchmark `judges/benchmark.py`; round-2 gate `v3/gate.py`. Code checks: `verify.py`.
4. **Dataset and splits** [offline from stored notes]. `v2/data_tools.py` (dataset v2, whole-episode splits, the one the MLX arms use); `v3/build_dataset.py` (v2 plus round-2 notes, used by the CUDA v3 students); card/stats `v3/card.py`.
5. **LoRA training** [GPU]. CUDA v2/v3: `v2/train.py`, `v2/config.py`, `v2/run_gpu.sh`, `v2/run_ablation.py`. MLX v4 (the three adapters evaluated at the end, A-270m-abs, B-270m-expr-aug, C-1b-expr-aug): `mlx2/export.py`, `mlx2/train.py`, `mlx2/run_arm.sh`, `mlx2/export_adapter.py`. Output formats: `v2/formats.py`.
6. **Inference with the adapters** [GPU / Apple silicon]. MLX greedy generation: `mlx2/infer.py`, batched `v4/binfer.py`, `v4/infer8.py`, `v4/queue8.sh`; check against PEFT `mlx2/peft_parity.py`, `v4/parity8.py`. Stored outputs are in `data/scribe/v4/`.
7. **Frozen resolver** [offline]. Code, not the model, turns "kolme viikkoa sitten" into a date: `v3/resolve.py` and `v3/lexicon.py` (sha256-pinned, never edit); vague-time flag `vague/rule.py`.
8. **Nemotron second reader** [keys]. `nemotron/reader.py` (prompt v3, selected on validation), `nemotron/common.py`, `v4/nemo8.py` (stress-set reads); its stored answers are in `data/scribe/v4/eval/nemotron/`.
9. **Cascade and preregistered evaluation** [offline]. A note is pre-filled only when two readers agree: `v3/cascade.py` (threshold rule, leak guard), `nemotron/cascade_agreement.py`, `v4/eval8.py` (`verify` then `score`), `v4/render8.py` (RESULTS.md), `v4/local_pairs.py` (local-only reader pairs, post hoc), `metrics.py`.
10. **Serving** [GPU for vLLM, keys for the Nemotron reader]. `../serve/client.py` (schema check, code-computed dates, risk score), `../serve/convert_mlx_adapter.py`, `../serve/guard.py`, `../serve/demo/`; deployment notes `../serve/README.md`. Not deployed.

Tests: `python3 -m unittest discover -s scribe/v4/tests` (and the same for `scribe/v3/tests`, `scribe/v2/tests`, `scribe/mlx2/tests`, `scribe/nemotron/tests`).

## History

Everything below describes version 1 (14 November 2026). It is kept as the record of what was tried first; the files are listed in [ARCHIVE.md](ARCHIVE.md). Version-1 results are in [RESULTS.md](RESULTS.md).

- **Version-1 GPU training never ran.** The A100 box got unpinned libraries (Transformers 5.23.0), then stopped answering and returned with a changed SSH host key. `train_lora.py` passes `warmup_ratio`, which that Transformers no longer accepts (`check_cuda_path.py`, `data/scribe/cuda-path-check-v1.json`). `run_gpu.sh`, `train_lora.py` and `evaluate.py` are kept as written and must not be used; `v2/run_gpu.sh` replaced them with pinned versions.
- **What was trained instead:** a 1B MLX fallback (`mlx_fallback.py`, base `mlx-community/gemma-3-1b-it-bf16`), scored on held-out Nemotron-written and Haiku-written notes. Added after review: `post_eval.py` (validation-fixed confidence cut-off), `provenance.py` (model and service versions), `results_md.py`, `manifest_eval.py`.
- **Version-1 generation** (`generate.py`, `finalise.py`, `build_dataset.py`, `topup.py`): hard cap 4,500 requests, a conservative $1 internal stop, one process writing the usage ledger at a time, never reset the ledger. Dataset defects: `data/scribe/dataset-v1/ERRATA.md`.
- **Evaluation caveats that still apply.** Risk thresholds chosen and scored on the same notes are optimistic. Wilson intervals are for binomial proportions; McNemar is exact two-sided. Jev re-judging estimates model disagreement, not proven label noise. No clinical validity or safety is established; no clinician has reviewed anything.
- **Terms.** Gemma models and derived adapters are under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms) and [Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy), which restricts automated healthcare decisions, so every extraction stays a proposal. Identifiers: `data/scribe/provenance-v1.json`.
