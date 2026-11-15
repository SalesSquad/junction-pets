#!/bin/sh
# Run a command with the Exa API key (and, if present, the Nemotron inference key) read from the macOS
# Keychain for this process only. The keys are never printed, logged or written to disk.
set -eu
KEY="$(security find-generic-password -s salesquad.junction2026.exa -w 2>/dev/null || true)"
if [ -z "$KEY" ]; then
  echo "No Keychain item 'salesquad.junction2026.exa'. Save the key first:" >&2
  echo "  security add-generic-password -s salesquad.junction2026.exa -a \"\$USER\" -w" >&2
  exit 1
fi
# Optional third judge (Nemotron on Verda): exported only when its Keychain item exists.
NEMO="$(security find-generic-password -s salesquad.junction2026.verda-dc -w 2>/dev/null || true)"
if [ -n "$NEMO" ] && [ -z "${VERDA_INFERENCE_KEY:-}" ]; then
  export VERDA_INFERENCE_KEY="$NEMO"
fi
# Optional on-device judge (gemma/serve_mlx_decide.py): used when it answers on its default port.
if [ -z "${LOCAL_JUDGE_URL:-}" ] && curl -s -m 1 http://127.0.0.1:8790/health >/dev/null 2>&1; then
  export LOCAL_JUDGE_URL="http://127.0.0.1:8790"
fi
# Optional on-device semantic catalog (bench/catalog/serve_catalog.py), likewise.
if [ -z "${CATALOG_URL:-}" ] && curl -s -m 1 http://127.0.0.1:8791/health >/dev/null 2>&1; then
  export CATALOG_URL="http://127.0.0.1:8791"
fi
EXA_API_KEY="$KEY" exec "$@"
