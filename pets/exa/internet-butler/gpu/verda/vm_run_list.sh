#!/bin/bash
# Listwise clause judge (gpu/train_list.py) on a fresh Verda GPU VM, then prune-then-listwise scoring on B0's top-m
# sets. The defaults are round 4 (LK3, bench/situations/listwise/PROTOCOL.md amendment 6): Gemma 3 4B-it with
# (a) Finnish augmentation, English train situations translated by Claude Haiku 5.5 (train.fi_aug.jsonl), (b) option-
# subset augmentation (p 0.5, size 2..5, keeps a gold option), (c) Nemotron distillation (beta 0.5) on non-Finnish
# rows only; 2 epochs capped at 45 minutes; 4 orders at test time. Test accuracy is sealed. No credentials on the VM;
# synthetic data only.
#
# In /root/job before the start: train.jsonl valid.jsonl test.jsonl, the TEACHER and EXTRA_TRAIN files, train_list.py
# (gpu/train_list.py), prune/{valid,test}_m{m}.jsonl (bench/situations/listwise/prune_sets.py), inputs.sha256 (sha256
# of every uploaded input) and this script. Start it detached; it appends to run.log and touches DONE at the end
# (gpu/verda/guard.sh waits for DONE, pulls run.log and runs/, and shuts the VM down).
#
# Environment (unset = the round-4 value; set to an empty string = off):
#   OUT=runs/list4b_kd3  EPOCHS=2  TRAIN_MIN=45 (time budget in minutes)  PERMS=4
#   TEACHER=train.nemo.jsonl  BETA=0.5  KD_SKIP_LANG=Finnish
#   EXTRA_TRAIN=train.fi_aug.jsonl  SUBSET_PROB=0.5  SUBSET_MAX=5  PRUNE_M="3 4 5"
# Settings of rounds 3b + 3c (LK2 and its pruned scoring, amendments 3 and 4):
#   OUT=runs/list4b_kd2 TRAIN_MIN=32 EXTRA_TRAIN= SUBSET_PROB=
set -euo pipefail
cd /root/job
exec > >(tee -a run.log) 2>&1
OUT=${OUT-runs/list4b_kd3}; EPOCHS=${EPOCHS-2}; TRAIN_MIN=${TRAIN_MIN-45}; PERMS=${PERMS-4}
TEACHER=${TEACHER-train.nemo.jsonl}; BETA=${BETA-0.5}; KD_SKIP_LANG=${KD_SKIP_LANG-Finnish}
EXTRA_TRAIN=${EXTRA_TRAIN-train.fi_aug.jsonl}; SUBSET_PROB=${SUBSET_PROB-0.5}; SUBSET_MAX=${SUBSET_MAX-5}
PRUNE_M=${PRUNE_M-3 4 5}
echo "start $(date -u +%FT%TZ) out=$OUT epochs=$EPOCHS train_min=$TRAIN_MIN perms=$PERMS teacher=$TEACHER beta=$BETA" \
  "kd_skip_lang=$KD_SKIP_LANG extra_train=$EXTRA_TRAIN subset=$SUBSET_PROB/$SUBSET_MAX prune_m=$PRUNE_M"
sha256sum -c inputs.sha256
nvidia-smi conf-compute -srs 1 2>/dev/null || true  # CC GPUs only
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH=$HOME/.local/bin:$PATH
[ -x .venv/bin/python ] || uv venv -q .venv --python 3.12
CU=$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9]*\)\..*/\1/p' | head -1)
IDX=https://download.pytorch.org/whl/cu128; [ "${CU:-12}" -ge 13 ] && IDX=https://download.pytorch.org/whl/cu130
uv pip install -q --python .venv/bin/python torch --index-url $IDX
uv pip install -q --python .venv/bin/python "transformers>=4.57" peft accelerate safetensors
.venv/bin/python -c "import torch,transformers,peft;print('torch',torch.__version__,torch.cuda.get_device_name(0),'tf',transformers.__version__,'peft',peft.__version__)"
export HF_HOME=/root/job/hf
.venv/bin/python -c "from huggingface_hub import snapshot_download as s; print(s('unsloth/gemma-3-4b-it', revision='bf46152c47f5dd20b896357cb51abc4c03b8ee8c'))" > model.path
M=$(cat model.path); echo "model $M $(date -u +%FT%TZ)"
args=(--train train.jsonl --valid valid.jsonl --test test.jsonl --model "$M" --out "$OUT" --epochs "$EPOCHS"
      --perms "$PERMS" --grad-ckpt --probe-every 50 --probe-n 200)
if [ -n "$EXTRA_TRAIN" ]; then args+=(--extra-train "$EXTRA_TRAIN"); fi
if [ -n "$TEACHER" ]; then args+=(--teacher "$TEACHER" --beta "$BETA"); fi
if [ -n "$KD_SKIP_LANG" ]; then args+=(--kd-skip-lang "$KD_SKIP_LANG"); fi
if [ -n "$SUBSET_PROB" ]; then args+=(--subset-prob "$SUBSET_PROB" --subset-max "$SUBSET_MAX"); fi
if [ -n "$TRAIN_MIN" ]; then args+=(--time-budget-min "$TRAIN_MIN"); fi
.venv/bin/python train_list.py "${args[@]}"
echo "trained $(date -u +%FT%TZ)"
for m in $PRUNE_M; do
  .venv/bin/python train_list.py --valid prune/valid_m$m.jsonl --test prune/test_m$m.jsonl --model "$M" \
    --eval-only --adapter "$OUT/adapter" --out "runs/prune_$(basename "$OUT")_m$m" --perms "$PERMS" 2>&1 | grep -E '"final"|Error' | cut -c1-200
done
echo "done $(date -u +%FT%TZ)"
touch DONE
