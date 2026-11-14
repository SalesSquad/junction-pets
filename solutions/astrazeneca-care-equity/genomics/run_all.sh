#!/usr/bin/env bash
# Drives the whole benchmark from the local machine.
#   GPU_HOST=root@<address> SSH_KEY=~/.ssh/<key> bash genomics/run_all.sh start [budget_seconds] [coverage|window]
#   GPU_HOST=... SSH_KEY=... bash genomics/run_all.sh status
#   GPU_HOST=... SSH_KEY=... bash genomics/run_all.sh collect     # copies the scores back and runs the analysis
# Research use only; not for clinical decisions.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GPU_HOST:?set GPU_HOST, for example root@203.0.113.7}" "${SSH_KEY:?set SSH_KEY to the private key file}"
SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o BatchMode=yes "$GPU_HOST")
SCP=(scp -q -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o BatchMode=yes)
case "${1:-status}" in
  start)
    BUDGET=${2:-2100}
    PREFER=${3:-coverage}
    [ -f data/genomics/raw/variants-keys.csv ] || python3 genomics/fetch_data.py > /dev/null
    "${SSH[@]}" 'mkdir -p /root/genomics/data /root/genomics/out /root/genomics/logs; nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader'
    "${SCP[@]}" genomics/remote_setup.sh genomics/run_gpu.sh genomics/score_evo2.py genomics/windows.py "$GPU_HOST:/root/genomics/"
    "${SCP[@]}" data/genomics/raw/GRCh37.p13_chr17.fna.gz "$GPU_HOST:/root/genomics/data/"
    "${SCP[@]}" data/genomics/raw/variants-keys.csv "$GPU_HOST:/root/genomics/data/variants.csv"
    "${SSH[@]}" "cd /root/genomics && (nohup bash run_gpu.sh $BUDGET $PREFER > logs/run_gpu.log 2>&1 < /dev/null &); sleep 1; echo started with a scoring budget of $BUDGET s, prefer $PREFER"
    ;;
  status)
    "${SSH[@]}" 'cd /root/genomics && date -u +%FT%TZ && tail -n 12 logs/run_gpu.log; grep -E "^===" logs/setup.log | tail -n 2; tail -n 1 logs/score.log 2>/dev/null | cut -c1-300; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader'
    ;;
  collect)
    "${SCP[@]}" "$GPU_HOST:/root/genomics/out/evo2-scores.csv" data/genomics/evo2-scores.csv
    "${SCP[@]}" "$GPU_HOST:/root/genomics/out/evo2-run.json" data/genomics/evo2-run.json
    "${SCP[@]}" "$GPU_HOST:/root/genomics/out/probe.json" data/genomics/evo2-probe.json
    "${SCP[@]}" "$GPU_HOST:/root/genomics/out/choice.json" data/genomics/evo2-window-choice.json
    python3 genomics/analyse.py
    ;;
  *) echo "usage: run_all.sh start [budget_seconds] | status | collect"; exit 2 ;;
esac
