# scribe/mlx2: Gemma retrained to copy dates, code computes them (NVIDIA_OPTIONS.md step 3)

SYNTHETIC notes only. Research artefact, not a medical device. Every extracted event is a proposal: pre-filled for
one-click confirmation or flagged as needing editing, and a person confirms every event.

Local MLX (Apple silicon) LoRA training of Gemma 3 on the v2 dataset (`data/scribe/v2/dataset/train.parquet`, 2,354
rows). Only one MLX process runs at a time. Step 3 reads train and val only; step 8 scores test and the stress set once.

| Arm | Base | Output format | Training data |
| --- | --- | --- | --- |
| `A-270m-abs` (control) | `mlx-community/gemma-3-270m-it-bf16` | absolute dates (version-1 prompt), then the step 1 resolver (`scribe/v3/resolve.py`, arm A' and A) | train as is |
| `B-270m-expr-aug` | same | expression (`scribe/v2/data_tools.py`), code resolves every date | train with phrasing augmentation |
| `C-1b-expr-aug` (only if B >= 0.80 on validation) | `mlx-community/gemma-3-1b-it-bf16` | expression | as B |

Recipe (matched to `data/scribe/v3/student/RUNS.md` where mlx-lm allows): LoRA r16, alpha 32 (MLX scale 2.0), dropout 0,
all seven projections of all layers, AdamW without weight decay, lr 2e-4, 5% warm-up then cosine to 0, 324 optimiser
steps at an effective batch of 16 (5,184 examples) via mlx-lm `--grad-accumulation-steps`, prompt masked, seed
20261114. mlx-lm has no gradient-norm clipping (CUDA used 1.0).

## Commands (from the solution folder)

```sh
PY=scribe/.venv/bin/python; MLX=scribe/artifacts/mlx-venv/bin/python
$PY scribe/mlx2/export.py                    # round trip on every train/val row, augmentation, chat JSONL
(cd scribe/mlx2 && $PY timing.py)            # 20 val notes per base size
(cd scribe/mlx2 && $MLX train.py --arm A-270m-abs)
(cd scribe/mlx2 && HF_HUB_OFFLINE=1 $MLX infer.py --base 270m --format absolute \
    --adapter ../v4/artifacts/A-270m-abs/adapter --split val --output ../../data/scribe/v4/mlx/outputs/A-270m-abs/val.jsonl)
(cd scribe/mlx2 && $PY score.py)             # -> data/scribe/v4/mlx/validation-v1.json + outputs/<arm>/val-records.jsonl
(cd scribe/mlx2 && $PY export_adapter.py --arm A-270m-abs)   # MLX adapter -> PEFT layout + adapters-v1.json
$PY -m unittest discover -s scribe/mlx2/tests
```

## Loading a trained arm (step 8 and the CPU demo)

`data/scribe/v4/mlx/adapters-v1.json` lists per arm: format, prompt function, resolution function, MLX base and
adapter, PEFT base and adapter, and sha256 hashes. Adapters live in the git-ignored `scribe/v4/artifacts/<arm>/`.

- MLX: `infer.py --base <270m|1b> --format <absolute|expression> --adapter scribe/v4/artifacts/<arm>/adapter --input
  <rows.parquet|jsonl> --output <file>` (rows need `id`, `note_date`, `note_text`). It stores the raw text and
  `confidence` (mean log-probability of the generated tokens). Resolve as `score.py` `parse()` does: expression arms
  with `data_tools.resolve_expression`, absolute arms with `canonicalise` then `resolve.repair(..., "A'")`.
- PEFT (PyTorch, CPU or CUDA): `PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(<peft_base>),
  "scribe/v4/artifacts/<arm>/peft")`, the base tokenizer's chat template with `add_generation_prompt=True`, greedy.
  `peft_parity.py` checks this path against the MLX outputs on validation notes.

## Augmentation (train only)

`export.py` rewrites every relative-date phrase in a seeded third of the train notes that have one ("35 päivää
sitten" -> "kolme päivää sitten", "eilen", "päivä sitten", "viikko sitten", "kuusi viikkoa sitten"), keeping the order
of the rewritten dates, and recomputes the expression target and the label by code. Number words 7-12 and
"toissapäivänä" are held out for the stress set (`data/scribe/v4/mlx/heldout-phrasings.json`). A rewritten note keeps
its other dates, so its timeline can be implausible (a referral "eilen" before an assessment months ago); the target
is still exactly what the note says.
