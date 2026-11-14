#!/usr/bin/env bash
# usage: run_smoke.sh <tag> <guided mode> <concurrency> [extra smoke_test.py arguments]
cd /root/scribe-v2
tag="$1"; guided="$2"; conc="$3"; shift 3
export SCRIBE_API_KEY="$(cat serve-smoke/.key)"
python3 serve/smoke_test.py --base-url http://127.0.0.1:8000 --notes serve-smoke/heldout-v2-100.jsonl \
  --model pathway-scribe --format absolute --guided "$guided" --concurrency "$conc" --no-log \
  --out "serve-smoke/smoke-$tag.json" --results-out "serve-smoke/smoke-$tag-results.jsonl" "$@" > "serve-smoke/smoke-$tag.stdout" 2> "serve-smoke/smoke-$tag.stderr"
echo "exit=$? tag=$tag $(date -u +%FT%TZ)"
