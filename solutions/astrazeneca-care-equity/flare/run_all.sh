#!/usr/bin/env bash
# Reproduce Lane C step 9 from the solution folder: three FLARE simulator runs (23 county sites,
# SYNTHETIC data) and their equivalence diffs against the central table. About 4 minutes on a Mac.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=flare/.venv/bin/python
if [ ! -x "$PY" ]; then
  uv venv flare/.venv --python 3.12
  uv pip install --python "$PY" "nvflare==2.9.1" "pandas>=1.5.1" pyarrow scipy
fi
for run in "none 12" "none 4" "age_band 12"; do
  set -- $run
  "$PY" flare/run_fedstats.py --strata "$1" --precision "$2" --threads 4 > "data/flare/run-$1-p$2.log" 2>&1
  "$PY" flare/compare.py --strata "$1" --precision "$2" > "data/flare/compare-$1-p$2.txt" || echo "compare $1 p$2: equivalence check failed (expected for p4)"
done
