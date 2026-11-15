#!/bin/zsh
# Paired unranked practice campaign (never --board, never --final).
# Usage: run_campaign.sh <out.jsonl> <parallel 1-4> <seed-prefix> <n-seeds> <policy...>
# Needs the official SDK venv in SPREAD_PY (default: the pinned race venv) and the
# team key in the macOS Keychain service com.salessquad.junction.spread.
set -u
OUT=${1:A}; PAR=$2; PREFIX=$3; N=$4; shift 4
LOGS=${OUT:h}/logs
mkdir -p "$LOGS"
cd "${0:A:h}"
export SPREAD_URL=${SPREAD_URL:-https://spread.bahnexpress.com}
export SPREAD_KEY="$(security find-generic-password -s com.salessquad.junction.spread -w)"
PY=${SPREAD_PY:-/tmp/spread-race-20261114-venv/bin/python}
jobs=()
for i in $(seq -w 1 $N); do for p in "$@"; do jobs+=("${PREFIX}-$i $p"); done; done
printf '%s\n' "${jobs[@]}" | xargs -P "$PAR" -L 1 sh -c '"$0" run_pair.py "$1" "$2" > "'"$LOGS"'/$1-$2.log" 2>&1; grep "^RESULT " "'"$LOGS"'/$1-$2.log" | sed "s/^RESULT //" >> "'"$OUT"'"; echo done $1 $2' "$PY"
echo CAMPAIGN_DONE
