# Live code and history

Worked out on 15 November 2026 from `v4/RESULTS.md`, `../TRAINING.md` and the imports of `v4/*.py`, `v3/cascade.py`, `nemotron/*.py` and `serve/client.py`. Nothing was moved or refactored. All notes are SYNTHETIC.

## Live (the final evaluation, the cascade or serve/ import or run it)

- `v4/eval8.py`, `v4/render8.py`, `v4/local_pairs.py`: final scoring, RESULTS.md, post hoc local reader pairs (`v4/reproduce.sh` runs them).
- `v4/binfer.py`, `v4/infer8.py`, `v4/nemo8.py`, `v4/parity8.py`, `v4/queue8.sh`: produced the stored step 8 outputs; need MLX or a Nemotron key.
- `v3/resolve.py`, `v3/lexicon.py`: the frozen relative-date resolver, sha256-pinned, read by `eval8.py`, `v3/cascade.py` and `serve/client.py`.
- `v3/cascade.py`, `v3/common.py`: cascade threshold rule and leak guard; helpers used by `nemotron/` and `v4/nemo8.py`.
- `mlx2/` (`m2common.py`, `export.py`, `train.py`, `infer.py`, `score.py`, `export_adapter.py`, `peft_parity.py`, `run_arm.sh`): MLX training and inference of the three evaluated adapters.
- `nemotron/` (`reader.py`, `common.py`, `cascade_agreement.py`, `reader_report.py`, `preflight.py`): Nemotron second reader.
- `vague/` (`rule.py`, `score.py`): vague-time flag used in the cascade (post hoc).
- `v2/data_tools.py`, `v2/formats.py`, `v2/data_iface.py`, `v2/core.py`: dataset v2 and splits, expression format and its code-side date computation, used by `eval8.py` and `mlx2/`.
- `sample.py`, `prompts.py`, `metrics.py`, `verify.py`: answer-key sampler, fixed prompt and parser, scoring statistics, code checks; imported by almost everything above.
- `teacher2/`, `stress/`, `judges/core.py`, `judges/run.py`: round-2 teacher, stress-set generation, Jev/Decisions judging (keys needed to rerun; outputs are stored).
- `../serve/` (`client.py`, `convert_mlx_adapter.py`, `guard.py`, `demo/`): serving; loads `v3/resolve.py` by path.

## Superseded (kept as the record of an experiment, not for new use)

- `generate.py`, `finalise.py`, `build_dataset.py`, `topup.py`: version-1 data generation (round-2 code copies its request style and retry rule but does not import it). Kept: it produced dataset v1 and its ERRATA.
- `train_lora.py`, `evaluate.py`, `run_gpu.sh`, `check_cuda_path.py`: version-1 CUDA path that never ran (`warmup_ratio` rejected by Transformers 5). Kept: the evidence for why v2 pins versions. Do not run.
- `mlx_fallback.py`, `post_eval.py`, `provenance.py`, `results_md.py`, `manifest_eval.py`: version-1 MLX fallback and its checks. Kept: they produced `scribe/RESULTS.md` and `data/scribe/eval-v1.json`.
- `v2/train.py`, `v2/run_ablation.py`, `v2/evaluate.py`, `v2/modeling.py`, `v2/constrained.py`, `v2/config.py`, `v2/risk.py`, `v2/report.py`, `v2/posthoc_checks.py`, `v2/training_figures.py`, `v2/run_gpu.sh`: CUDA v2 ablation (3 runs, A100). Kept: the CUDA recipe the MLX arms were matched to and the source of `TRAINING.md` figures.
- `v3/gate.py`, `v3/build_dataset.py`, `v3/audit_inputs.py`, `v3/score_audit.py`, `v3/summarise.py`, `v3/card.py`, `v3/compare_students.py`: teaching round 2 (dataset v3, CUDA students). Kept: record of that round; the v4 MLX arms train on dataset v2.
- `v3/artifacts/`, `v4/artifacts/B-270m-expr-aug-killed-1`: adapters and a killed run. Kept as record.

## Date resolution exists in several places

Found by grep (`def resolve*`, `relative`):

- `v3/resolve.py` + `v3/lexicon.py`: **the frozen resolver (hash-pinned in `data/scribe/v4/resolver/freeze.json`; do not edit).**
- `v2/data_tools.py` (`resolve_date`, `resolve_expression`) and `v2/formats.py` (`to_absolute`): expression format to absolute dates, used in training and scoring.
- `serve/client.py` (`resolve_expression`, `resolve_object`, `apply_relative_dates`): a separate copy of the expression resolver for serving; it loads `v3/resolve.py` by file path.
- `runs/diagnose/resolve_relative.py`: the original diagnostic rule `v3/resolve.py` was ported from; still imported by `nemotron/cascade_agreement.py`.
- `v3/cascade.py` (`resolve_note`), `stress/check.py` (`resolve_check`), `stress/phrases.py` (the stress generator's own date arithmetic), `mlx2/export.py` (round-trip check).

A later refactor should make one module own date logic, and have serving, training, scoring and the cascade import from it. Because the frozen files are hash-pinned, that module must either be `v3/resolve.py` itself or wrap it without changing its bytes. Not done now.
