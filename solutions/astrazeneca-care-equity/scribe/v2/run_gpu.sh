#!/usr/bin/env bash
# Version-2 scribe ablation on a fresh Ubuntu CUDA box (one GPU with bfloat16 support).
#
#   bash scribe/v2/run_gpu.sh [time budget in minutes, default 60] [extra run_ablation.py arguments]
#   SIZES=270m,1b bash scribe/v2/run_gpu.sh 30          # restrict the size ladder
#
# Copy to the box first, keeping the paths: scribe/ (without .venv and artifacts), data/scribe/dataset-v1/,
# data/scribe/haiku-test.jsonl, data/scribe/v2/ and an empty runs/ directory.
# Set-up, unit tests and model download happen before the time budget starts; the budget covers the
# ablation itself. Nothing here creates, resizes or stops any cloud resource.
set -euo pipefail
cd "$(dirname "$0")/../.."

BUDGET="${1:-60}"
[ "$#" -gt 0 ] && shift
SIZES="${SIZES:-270m,1b,4b}"
export HF_HOME="${HF_HOME:-$PWD/scribe/.hf-cache}"
export TOKENIZERS_PARALLELISM=false
export PYTHONDONTWRITEBYTECODE=1
VENV=scribe/.gpu-venv-v2
PY="$VENV/bin/python"
# pyarrow is pinned to the version the A100 run used (ablation-v1.json versions). The versions of
# sentencepiece, protobuf and huggingface_hub (a dependency) that ran were not recorded, so they cannot be
# pinned to them; the full `pip freeze` of every later set-up is written next to the run log instead.
PINS='torch==2.15.0 transformers==5.23.0 peft==0.21.3 accelerate==1.15.0 pyarrow==26.0.1 sentencepiece protobuf'

runlog() { # step, command, status
    if [ -x "$PY" ]; then
        "$PY" -c 'import sys; sys.path.insert(0, "scribe/v2"); from core import log; log(sys.argv[1], command=sys.argv[2], status=sys.argv[3])' "$@" && return 0
    fi
    # No venv yet (or it cannot import): one plain JSON line, so a failed set-up still leaves a record.
    mkdir -p runs
    printf '{"ts": "%s", "step": "%s", "command": "%s", "status": "%s", "note": "written by run_gpu.sh without the venv"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" >> runs/v2-ablation.jsonl
}
# Set before the installs (review finding 24): a failing venv or pip step is logged too.
trap 'runlog v2_gpu_failure "run_gpu.sh $BUDGET" error' ERR

if [ ! -x "$PY" ]; then
    python3 -m venv "$VENV" # on a bare image: apt-get install -y python3-venv
fi
# pip is not upgraded: the venv keeps the pip bundled with this Python, so the installer does not change
# between runs (an unpinned `--upgrade pip` did, review finding 24).
# Pinned: an unpinned install now brings Transformers 5, where warmup_ratio no longer exists,
# and PEFT below 0.18 does not work with Transformers 5.
# shellcheck disable=SC2086
"$PY" -m pip install --quiet $PINS
mkdir -p runs
"$PY" -m pip freeze > runs/v2-pip-freeze.txt
runlog v2_gpu_setup "pip install $PINS (full list: runs/v2-pip-freeze.txt)" ok

nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
"$PY" -c 'import torch; assert torch.cuda.is_available() and torch.cuda.is_bf16_supported(), "a CUDA GPU with bfloat16 support is required"'

"$PY" -m unittest discover -s scribe/v2/tests
runlog v2_gpu_unit_tests "python -m unittest discover -s scribe/v2/tests" ok

# Download the pinned, ungated mirrors (licence: Gemma Terms of Use) before the clock starts.
"$PY" - "$SIZES" <<'EOF'
import sys

sys.path.insert(0, "scribe/v2")
from huggingface_hub import snapshot_download

from config import BASES
from core import log

for key in sys.argv[1].split(","):
    base = BASES[key]
    path = snapshot_download(base["repo"], revision=base["revision"])
    log("v2_gpu_download", command=f"snapshot_download {base['repo']}@{base['revision']}", outputs=[path])
    print("downloaded", base["repo"], "->", path)
EOF

"$PY" scribe/v2/run_ablation.py --plan --time-budget-min "$BUDGET" --sizes "$SIZES" "$@"
"$PY" scribe/v2/run_ablation.py --time-budget-min "$BUDGET" --sizes "$SIZES" "$@"
echo "Results: data/scribe/v2/ablation-v1.json and scribe/v2/RESULTS.md; run directories under scribe/v2/artifacts/"
