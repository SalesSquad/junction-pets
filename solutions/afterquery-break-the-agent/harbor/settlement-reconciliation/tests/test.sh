#!/bin/bash
set -uo pipefail

# Harbor launches this script in a SEPARATE verifier container after the agent
# is stopped. The only agent-owned inputs are frozen JSON artifacts.
mkdir -p /logs/verifier
if ! python3 /tests/evaluate.py --source /app/data/orders.json --artifact /app/output/decisions.json --reward-dir /logs/verifier; then
  printf '0.000000\n' > /logs/verifier/reward.txt
  printf '{"error":"verifier_crash","reward":0}\n' > /logs/verifier/details.json
  exit 1
fi
