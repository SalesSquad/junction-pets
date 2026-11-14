#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CUBLAS_WORKSPACE_CONFIG=:4096:8
if [ ! -x ml/.venv/bin/python ]; then
  python3 -m venv ml/.venv || { python3 -m pip install --user virtualenv; python3 -m virtualenv ml/.venv; }
fi
ml/.venv/bin/python -m pip --version >/dev/null 2>&1 || ml/.venv/bin/python -m ensurepip
ml/.venv/bin/python -m pip install -r ml/requirements.txt
# Separate artifacts preserve the original five-seed run.
ml/.venv/bin/python ml/fetch_panel.py --out ml/data/panel.json
ml/.venv/bin/python ml/fetch_panel.py --extra-indicators 150 --out ml/data/panel-extended.json
ml/.venv/bin/python ml/sweep.py --device cuda --seeds 3 --tag gpu-sweep "$@"
ml/.venv/bin/python ml/export_forecasts.py --device cuda --tag gpu-sweep "$@" --sweep
