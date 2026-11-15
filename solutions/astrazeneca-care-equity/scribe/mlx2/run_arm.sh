#!/bin/zsh
# One arm through the single MLX queue: train, validation inference, PEFT export. SYNTHETIC notes only.
#   scribe/mlx2/run_arm.sh <arm> <270m|1b> <absolute|expression> [batch]
set -u
cd "${0:A:h}" || exit 1
ARM=$1; BASE=$2; FMT=$3; BATCH=${4:-}
MLX=../artifacts/mlx-venv/bin/python; PY=../.venv/bin/python
OUT=../../data/scribe/v4/mlx/outputs/$ARM
echo "start $(date -u +%FT%TZ) $ARM"
if pgrep -f "mlx_lm.lora|infer.py --base" >/dev/null; then echo "another step-3 MLX job is running; refusing"; exit 3; fi
$MLX train.py --arm "$ARM" ${BATCH:+--batch=$BATCH} || { echo "train failed $(date -u +%FT%TZ)"; exit 1; }
HF_HUB_OFFLINE=1 $MLX infer.py --base "$BASE" --format "$FMT" --adapter ../v4/artifacts/$ARM/adapter --split val \
  --output $OUT/val.jsonl || { echo "infer failed $(date -u +%FT%TZ)"; exit 2; }
$PY export_adapter.py --arm "$ARM" || echo "export failed"
echo "done $(date -u +%FT%TZ) $ARM"
