#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Deterministic CUDA matrix products need this (PyTorch reproducibility note).
export CUBLAS_WORKSPACE_CONFIG=":4096:8"
# Tesla V100 (compute capability 7.0) needs an older wheel: pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1
if [ ! -x ml/.venv/bin/python ]; then
  python3 -m venv ml/.venv || { python3 -m pip install --user virtualenv; python3 -m virtualenv ml/.venv; }
fi
ml/.venv/bin/python -m pip --version >/dev/null 2>&1 || ml/.venv/bin/python -m ensurepip
ml/.venv/bin/python -m pip install -r ml/requirements.txt
args=(--device cuda --seeds 5 "$@")
ml/.venv/bin/python ml/fetch_panel.py
ml/.venv/bin/python ml/train_forecaster.py "${args[@]}"
ml/.venv/bin/python ml/evaluate.py "${args[@]}"
ml/.venv/bin/python ml/export_forecasts.py "${args[@]}"
