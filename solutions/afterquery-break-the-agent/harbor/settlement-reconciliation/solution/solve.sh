#!/bin/sh
set -eu

# The Oracle runs during the AGENT phase, BEFORE the verifier is mounted.
# The verifier only sees the final inert JSON artifact, never this program.
cp /solution/reconcile.py /app/reconcile.py
python3 /app/reconcile.py --input /app/data/orders.json --output /app/output/decisions.json
