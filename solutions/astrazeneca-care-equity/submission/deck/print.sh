#!/bin/sh
# Build deck.html from the JSON files and print it to SAMA-deck.pdf with headless Chrome (one Chrome at a time).
set -e
cd "$(dirname "$0")"
node build.mjs
PROFILE="${TMPDIR:-/tmp}/sama-deck-chrome"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-first-run \
  --user-data-dir="$PROFILE" --no-pdf-header-footer --run-all-compositor-stages-before-draw \
  --virtual-time-budget=4000 --print-to-pdf="$PWD/SAMA-deck.pdf" "file://$PWD/deck.html" 2>/dev/null
rm -rf "${PROFILE:?}"
ls -la SAMA-deck.pdf
