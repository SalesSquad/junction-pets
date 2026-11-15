# SAMA pathway scribe

Synthetic Finnish cancer-pathway extraction research. The specification is DATA_COLLECTION.md section 4. No patient/clinician names or real clinical notes are used. Everything here is SYNTHETIC and nothing is for clinical use.

**What was actually run (14 November 2026).** Results are in [RESULTS.md](RESULTS.md); every step is in `runs/train.jsonl`.

- **Version-1 GPU training: never trained.** The A100 box was set up with unpinned libraries (it got Transformers 5.23.0, `runs/train.jsonl`), then stopped answering and came back with a changed SSH host key; no training step ran there. The version-1 script could not have trained there anyway: `scribe/train_lora.py` passes `warmup_ratio`, which the Transformers version installed on the box no longer accepts (`scribe/check_cuda_path.py` checks the script's arguments against that same version; result in `data/scribe/cuda-path-check-v1.json`).
- **What was trained instead:** a 1B MLX fallback on this MacBook Pro (`scribe/mlx_fallback.py`, base `mlx-community/gemma-3-1b-it-bf16`, which was downloaded here into the git-ignored `scribe/artifacts/hf-cache`). It was evaluated on held-out Nemotron-written notes and on Haiku-written notes.
- **Superseded:** the GPU path is now `scribe/v2/`, which pins torch, Transformers, PEFT and Accelerate and uses integer warm-up steps. The version-1 CUDA files (`run_gpu.sh`, `train_lora.py`, `evaluate.py`) are kept as they are for the record and should not be used.
- Checks added after review: `scribe/post_eval.py` (`data/scribe/post-eval-v1.json`: confidence cut-off fixed on validation notes, the adapter on all test notes, ground truth against the pathway order with the eventlog validator). Defects of the frozen dataset: `data/scribe/dataset-v1/ERRATA.md` and the card. Versions of every model and service: `scribe/provenance.py` (`data/scribe/provenance-v1.json`).

**Terms.** Gemma models and anything derived from them, including the adapter, are subject to the Gemma Terms of Use (<https://ai.google.dev/gemma/terms>) and the Gemma Prohibited Use Policy (<https://ai.google.dev/gemma/prohibited_use_policy>). The policy restricts automated decisions in healthcare, so every extraction stays a proposal that a person confirms. Model, teacher and verifier identifiers are recorded in `data/scribe/provenance-v1.json`.

## Local generation (Python 3.12)

```bash
UV_CACHE_DIR=/tmp/sama-uv uv venv --python 3.12 scribe/.venv
UV_CACHE_DIR=/tmp/sama-uv uv pip install --python scribe/.venv/bin/python httpx pyarrow
set -a; . ~/.config/verda-inference/env; . ~/.config/typesafe/env; set +a
scribe/.venv/bin/python scribe/generate.py --preflight
scribe/.venv/bin/python scribe/generate.py --start 0 --count 20
# Select remaining count from measured throughput/acceptance. Hard cap 4500 requests including retries.
scribe/.venv/bin/python scribe/finalise.py
scribe/.venv/bin/python scribe/build_dataset.py --audit
scribe/.venv/bin/python -m unittest discover -s scribe/tests
```

Only one generation/audit process may write the usage ledger at once. Cache files are keyed by sample index; reuse keeps completed teacher calls and probabilities. Keep cache and usage.json together. Never reset the ledger to circumvent a cap. Failed verifier attempts reserve 100k tokens each conservatively; successful calls settle against actual reported tokens. A conservative $1 internal stop is far below the authorized $10. Actual cost uses the owner's $0.042/million-token price. Teacher price is unknown and logged as null. No credentials are stored.

`models.json` records GET /models discovery. Teacher `chat_template_kwargs.enable_thinking=false` follows [NVIDIA's model documentation](https://docs.nvidia.com/nim/large-language-models/2.1.5/get-started/advanced/get-started-nemotron-3.5-super-vl.html). The verifier HTTP shape and usage follow [TypeSafe System One](https://docs.typesafe.ai/api/system-one). Initial failed prompts are retained in cache; later generation caches record their prompt; early pilots retain planned facts and observed output. Code checks include word count in addition to exact date spans. All semantic probabilities are recorded, including second-pass audit results in `data/scribe/audit/`.

## Version-1 CUDA path (superseded, do not run)

`scribe/run_gpu.sh` installs torch, Transformers, PEFT and Accelerate without version pins and then runs `scribe/train_lora.py` and `scribe/evaluate.py`. With the Transformers version such an install brought on 14 November 2026 the training stops when it builds its `TrainingArguments` (`warmup_ratio`; see `data/scribe/cuda-path-check-v1.json`). These files have never run on a GPU and are kept as they were. Use `scribe/v2/run_gpu.sh` (see `scribe/v2/README.md`). An earlier version of this file said this machine never downloads Gemma; the MLX fallback did download the 1B model here.

The scoring code is shared: `scribe/metrics.py` is used by the MLX fallback and by version 2. `scribe/evaluate.py` also reads external-writer notes (`--extra-test`); external JSONL needs `note_text`, `note_date`, and `target_json` (or `entry_route` and `events`); optionally `date_forms`, `distractors`, `id`. Unknown distractor denominators remain unavailable, not zero-percent success. Risk thresholds chosen and scored on the same notes are optimistic; `scribe/post_eval.py` fixes the threshold on the validation notes and reports the test error with an exact upper bound. Neither is a clinical error bound. Wilson intervals apply to binomial proportions; F1 is a harmonic mean rather than a binomial proportion. McNemar is exact two-sided. Date errors pair same-type dates in sorted order and exclude unmatched events. An extracted distractor means any predicted pathway event on the distractor's date. Date-form breakdowns include notes containing that form, so groups overlap.

Jev re-judging estimates *model disagreement*, not independently proven label noise: correlated errors may escape both passes. No clinical validity, clinical safety or live care integration is established: the evaluation measures agreement with a synthetic teacher-and-verifier pipeline, and no clinician has reviewed it.

## Local MLX fallback and the checks added after review

```bash
export HF_HOME=$PWD/scribe/artifacts/hf-cache HF_HUB_OFFLINE=1
PY=scribe/artifacts/mlx-venv/bin/python; E=scribe/artifacts/mlx-eval
# adapter on the validation notes and on the 300 test notes outside the first seeded 200
$PY scribe/mlx_fallback.py infer --model mlx-community/gemma-3-1b-it-bf16 --adapter scribe/artifacts/adapter-v1 --split val --output $E/adapter-val.jsonl
$PY scribe/mlx_fallback.py infer --model mlx-community/gemma-3-1b-it-bf16 --adapter scribe/artifacts/adapter-v1 --test-subset 200 --complement --output $E/adapter-test-rest.jsonl
# after a change to scribe/metrics.py: rebuild the evaluation file from the stored predictions
scribe/.venv/bin/python scribe/mlx_fallback.py merge --extra-test data/scribe/haiku-test.jsonl --test-subset 200 --base $E/base.jsonl --adapter $E/adapter-0.jsonl,$E/adapter-1.jsonl --meta scribe/artifacts/eval-meta.json --output data/scribe/eval-v1.json
$PY scribe/check_cuda_path.py                    # data/scribe/cuda-path-check-v1.json (needs the box's Transformers version, not torch)
scribe/.venv/bin/python scribe/provenance.py     # data/scribe/provenance-v1.json
scribe/.venv/bin/python scribe/post_eval.py      # data/scribe/post-eval-v1.json and dataset-v1/ERRATA.md
scribe/.venv/bin/python scribe/build_dataset.py --card-only   # dataset-v1/CARD.md; the split files are not rewritten
scribe/.venv/bin/python scribe/results_md.py     # scribe/RESULTS.md (add --update-data-collection to rewrite the status block of DATA_COLLECTION.md)
scribe/.venv/bin/python scribe/manifest_eval.py  # data/scribe/manifest-eval-v1.json and the descriptive fields of manifest.json
```

`data/scribe/manifest.json` describes the dataset build; its hash map was written at the end of the build, before any training, and is kept as written because version 2 checks the version-1 inputs against it. Its other fields say what ran afterwards. `data/scribe/manifest-eval-v1.json` lists the files of the training and evaluation stage with their hashes.
