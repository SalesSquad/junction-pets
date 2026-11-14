#!/usr/bin/env bash
set -euo pipefail

TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_ROOT"
swift run --jobs 1 chibi-lens-replay --contracts | node scripts/check-contracts.mjs
