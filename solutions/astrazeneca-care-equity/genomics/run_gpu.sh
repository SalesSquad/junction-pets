#!/usr/bin/env bash
# Runs on the GPU box in /root/genomics: install, probe, choose the window, score.
# usage: nohup bash run_gpu.sh <time budget for scoring in seconds> [coverage|window] > logs/run_gpu.log 2>&1 < /dev/null &
# Inputs expected in data/: GRCh37.p13_chr17.fna.gz and variants.csv (columns chrom,pos,ref,alt).
# Research use only; not for clinical decisions.
set -euo pipefail
ROOT=/root/genomics
BUDGET=${1:-2100}
PREFER=${2:-coverage}     # coverage: every variant, window as large as the budget allows; window: largest window, as many variants as the budget allows
cd "$ROOT"
mkdir -p logs out data
echo "=== $(date -u +%FT%TZ) setup"
bash remote_setup.sh > logs/setup.log 2>&1
. venv/bin/activate
export HF_HOME="$ROOT/hf" CUDA_VISIBLE_DEVICES=0 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
echo "=== $(date -u +%FT%TZ) gpu before"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader
echo "=== $(date -u +%FT%TZ) probe"
python score_evo2.py probe --fasta data/GRCh37.p13_chr17.fna.gz --variants data/variants.csv \
  --metrics out/probe.json --windows 1024,2048,4096,8192 > logs/probe.log 2>&1 || echo "probe exited with $?"
grep -E '^\{' logs/probe.log || tail -5 logs/probe.log
echo "=== $(date -u +%FT%TZ) choose"
WINDOW=$(python score_evo2.py choose --probe out/probe.json --variants data/variants.csv --out out/choice.json --budget-seconds "$BUDGET" --prefer "$PREFER")
echo "window $WINDOW"
[ "$WINDOW" -gt 0 ] || { echo "no window fits the memory limit"; exit 3; }
echo "=== $(date -u +%FT%TZ) score"
python score_evo2.py score --fasta data/GRCh37.p13_chr17.fna.gz --variants data/variants.csv --window "$WINDOW" \
  --out out/evo2-scores.csv --metrics out/evo2-run.json --checkpoint out/checkpoint.jsonl \
  --max-seconds "$BUDGET" > logs/score.log 2>&1
echo "=== $(date -u +%FT%TZ) done"
tail -c 400 logs/score.log
