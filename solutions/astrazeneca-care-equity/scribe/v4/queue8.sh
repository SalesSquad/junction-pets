#!/bin/zsh
# Step 8 MLX queue: one MLX job at a time (scribe/v4/binfer.py, batched); stress first (primary), then the 700 test
# notes. Outputs resume by id, so a crash is repaired without generating a scored note twice.
set -u
cd "${0:A:h}/../.." || exit 1
MLX=scribe/artifacts/mlx-venv/bin/python
OUT=data/scribe/v4/eval/outputs
DS=data/scribe/v2/dataset
for arm in A-270m-abs B-270m-expr-aug C-1b-expr-aug; do
  echo "$(date -u +%FT%TZ) start $arm"
  HF_HUB_OFFLINE=1 $MLX scribe/v4/binfer.py --arm $arm \
    --io data/scribe/stress/stress-v1.parquet:$OUT/$arm/stress.jsonl \
    --io $DS/test_haiku.parquet:$OUT/$arm/test.jsonl \
    --io $DS/test_nemotron.parquet:$OUT/$arm/test.jsonl || echo "$(date -u +%FT%TZ) FAILED $arm"
done
echo "$(date -u +%FT%TZ) QUEUE_END"
