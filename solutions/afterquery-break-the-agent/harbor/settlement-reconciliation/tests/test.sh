#!/bin/bash
set -uo pipefail

# Harbor mounts the verifier here only after agent execution. Even a broken
# solver yields a real 0–1 score; a broken verifier remains an error in details.
mkdir -p /logs/verifier
if ! python3 /tests/evaluate.py --solver /app/reconcile.py --reward-dir /logs/verifier; then
  printf '0.000000\n' > /logs/verifier/reward.txt
  printf '{"error":"verifier_crash","reward":0}\n' > /logs/verifier/details.json
  exit 1
fi
