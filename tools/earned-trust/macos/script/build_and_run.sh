#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="EarnedTrust"
BUNDLE_ID="cloud.taika.earnedtrust"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BUNDLE="$ROOT_DIR/dist/$APP_NAME.app"

case "$MODE" in run|--debug|--logs|--telemetry|--verify|--build-only) ;; *)
  echo "usage: $0 [--debug|--logs|--telemetry|--verify|--build-only]" >&2; exit 2 ;;
esac
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "EarnedTrust requires macOS 14+ and the installed Swift toolchain." >&2; exit 2
fi

cd "$ROOT_DIR"
if [[ "$MODE" != "--build-only" ]]; then pkill -x "$APP_NAME" >/dev/null 2>&1 || true; fi
swift build --product EarnedTrust
BUILD_DIR="$(swift build --show-bin-path)"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
cp "$BUILD_DIR/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

# Bundle.module searches Bundle.main.resourceURL for its SwiftPM resource bundle.
for resource in "$BUILD_DIR"/*.bundle; do
  [[ -d "$resource" ]] || continue
  /usr/bin/ditto "$resource" "$APP_BUNDLE/Contents/Resources/$(basename "$resource")"
done

cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>Earned Trust</string>
  <key>CFBundleDisplayName</key><string>Earned Trust</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

if [[ "$MODE" == "--build-only" ]]; then printf '%s\n' "$APP_BUNDLE"; exit 0; fi
case "$MODE" in
  --debug) lldb -- "$APP_BUNDLE/Contents/MacOS/$APP_NAME" ;;
  --logs)
    /usr/bin/open -n "$APP_BUNDLE"
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry)
    /usr/bin/open -n "$APP_BUNDLE"
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify)
    /usr/bin/open -n "$APP_BUNDLE"
    sleep 2
    pgrep -x "$APP_NAME" >/dev/null
    printf 'Launched %s; process exists. Visual inspection is separate.\n' "$APP_NAME"
    ;;
  run) /usr/bin/open -n "$APP_BUNDLE" ;;
esac
