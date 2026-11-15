#!/usr/bin/env bash
# Wait up to $1 seconds for GET /health = 200. Prints the seconds waited, or the log tail on failure.
cd /root/scribe-v2
for i in $(seq 1 "${1:-40}"); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8000/health || true)
  if [ "$code" = "200" ]; then echo "HEALTHY after_polls=$i started=$(cat serve-smoke/vllm.started) now=$(date -u +%FT%TZ)"; exit 0; fi
  if ! kill -0 "$(cat serve-smoke/vllm.pid)" 2>/dev/null; then echo "SERVER EXITED"; tail -40 serve-smoke/vllm.log; exit 3; fi
  sleep 1
done
echo "NOT YET now=$(date -u +%FT%TZ)"; tail -5 serve-smoke/vllm.log | cut -c1-300; exit 1
