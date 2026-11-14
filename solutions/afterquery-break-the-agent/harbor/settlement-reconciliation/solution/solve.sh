#!/bin/sh
set -eu

# The Oracle proves a complete program can solve new cases. It does not bake
# precomputed fixture answers into /app or copy verifier tests into the agent.
cp /solution/reconcile.py /app/reconcile.py
python3 /app/reconcile.py --input /app/data/orders.json --output /app/output/report.json
