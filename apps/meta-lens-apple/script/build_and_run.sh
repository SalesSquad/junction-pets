#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="ChibiLensDesktop"
TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_BUNDLE="$TASK_ROOT/dist/$APP_NAME.app"
TASK_BINARY="$TASK_BUNDLE/Contents/MacOS/$APP_NAME"

task_bundle_pids() {
  # Exact executable path comparison; no regex and no killing other processes.
  ps -axo pid=,comm= | awk -v expected="$TASK_BINARY" '$2 == expected { print $1 }'
}

case "$MODE" in
  run|--debug|debug|--logs|logs|--telemetry|telemetry|--verify|verify) ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac

cd "$TASK_ROOT"
swift build --product "$APP_NAME"
TASK_BUILT_BINARY="$(swift build --show-bin-path)/$APP_NAME"
mkdir -p "$TASK_BUNDLE/Contents/MacOS"
cp "$TASK_BUILT_BINARY" "$TASK_BINARY"
cp "$TASK_ROOT/script/Info.plist" "$TASK_BUNDLE/Contents/Info.plist"
chmod +x "$TASK_BINARY"

case "$MODE" in
  run)
    /usr/bin/open -n "$TASK_BUNDLE"
    ;;
  --debug|debug)
    lldb -- "$TASK_BINARY"
    ;;
  --logs|logs)
    /usr/bin/open -n "$TASK_BUNDLE"
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    /usr/bin/open -n "$TASK_BUNDLE"
    /usr/bin/log stream --info --style compact --predicate 'subsystem == "cloud.taika.chibilens.replay"'
    ;;
  --verify|verify)
    TASK_BEFORE="$(task_bundle_pids)"
    /usr/bin/open -n "$TASK_BUNDLE"
    sleep 1
    TASK_AFTER="$(task_bundle_pids)"
    for TASK_CANDIDATE in $TASK_AFTER; do
      TASK_WAS_RUNNING=false
      for TASK_PRIOR in $TASK_BEFORE; do
        if [[ "$TASK_PRIOR" == "$TASK_CANDIDATE" ]]; then
          TASK_WAS_RUNNING=true
          break
        fi
      done
      if [[ "$TASK_WAS_RUNNING" == false ]]; then
        exit 0
      fi
    done
    echo "New task-owned ChibiLensDesktop process not confirmed" >&2
    exit 1
    ;;
esac
