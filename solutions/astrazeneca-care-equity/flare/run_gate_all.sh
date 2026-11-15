#!/usr/bin/env bash
# Reproduce the comparability gate from the solution folder (SYNTHETIC data, about 3-4 minutes, one simulator
# thread to keep memory small). Needs flare/.venv from flare/run_all.sh. No model is run.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=flare/.venv/bin/python
"$PY" flare/gate_prep.py
"$PY" flare/run_gate.py --threads 1 > data/flare/run-gate-p12.log 2>&1
"$PY" flare/build_gate.py
"$PY" -m unittest discover -s flare/tests
node --test flare/flare.test.mjs
