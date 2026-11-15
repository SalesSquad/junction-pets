#!/usr/bin/env bash
# Start vLLM on 127.0.0.1 through serve/entrypoint.sh with the selected adapter as a LoRA module.
# usage: start_server.sh <adapter dir> <base repo> <base revision> [gpu memory share] [text-only 1|0]
set -euo pipefail
cd /root/scribe-v2
umask 077
python3 -c 'import secrets; print(secrets.token_hex(24))' > serve-smoke/.key   # never printed
export SCRIBE_API_KEY="$(cat serve-smoke/.key)"
export SCRIBE_ADAPTER_DIR="$1" SCRIBE_BASE_MODEL="$2" SCRIBE_BASE_REVISION="$3"
export SCRIBE_GPU_MEMORY_UTILIZATION="${4:-0.10}" SCRIBE_TEXT_ONLY="${5:-1}"
export SCRIBE_HOST=127.0.0.1 SCRIBE_PORT=8000
export HF_HOME=/root/scribe-v2/scribe/.hf-cache HF_HUB_OFFLINE=1
export SCRIBE_VLLM_BIN=/root/scribe-v2/serve-smoke/.vllm-venv/bin/vllm
export PATH=/root/scribe-v2/serve-smoke/.vllm-venv/bin:$PATH
date -u +%FT%TZ > serve-smoke/vllm.started
nohup bash serve/entrypoint.sh > serve-smoke/vllm.log 2>&1 < /dev/null &
echo $! > serve-smoke/vllm.pid
echo "started pid $(cat serve-smoke/vllm.pid)"
