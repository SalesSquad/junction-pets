#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
gpu_failure() {
    rc=$?
    python3 -c 'import sys;sys.path.insert(0,"scribe");from common import log;log("gpu_failure",command="run_gpu.sh",metrics={"exit_code":int(sys.argv[1])},status="error")' "$rc"
    exit "$rc"
}
trap gpu_failure ERR
export HF_HOME="${HF_HOME:-$PWD/scribe/.hf-cache}"
python3 -c 'import sys;sys.path.insert(0,"scribe");from common import log;log("gpu_setup_start",command="python3 -m venv; pip install dependencies")'
python3 -m venv scribe/.gpu-venv
PY=scribe/.gpu-venv/bin/python
"$PY" -m pip install torch transformers peft accelerate pyarrow sentencepiece protobuf
"$PY" -c 'import sys;sys.path.insert(0,"scribe");from common import log;log("gpu_setup",command="pip install torch transformers peft accelerate pyarrow sentencepiece protobuf")'
"$PY" scribe/train_lora.py "$@"
"$PY" scribe/evaluate.py
