#!/usr/bin/env bash
cd /root/scribe-v2
pid=$(cat serve-smoke/vllm.pid 2>/dev/null) || exit 0
kill -TERM "$pid" 2>/dev/null
for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
kill -0 "$pid" 2>/dev/null && { kill -KILL "$pid"; sleep 2; }
pkill -KILL -f 'serve-smoke/.vllm-venv/bin' 2>/dev/null
rm -f serve-smoke/.key
sleep 2
echo "stopped $(date -u +%FT%TZ)"; nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader; nvidia-smi --query-gpu=memory.used --format=csv,noheader
