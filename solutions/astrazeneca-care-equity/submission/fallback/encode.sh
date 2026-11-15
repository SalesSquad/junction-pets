#!/bin/sh
# Encode the frames written by record.mjs into submission/fallback/SAMA-demo-fallback.mp4 (silent, 1440x810, 30 fps CFR).
# Each frame in list.txt is repeated round(duration x 30) times through symlinks, so step times stay exact.
# Usage: FRAMES_DIR=/path/to/frames sh submission/fallback/encode.sh
set -e
cd "$(dirname "$0")"
: "${FRAMES_DIR:?set FRAMES_DIR}"
SEQ="$FRAMES_DIR/seq"
mkdir -p "$SEQ"
find "$SEQ" -name 's*.jpg' -type l -delete
awk -v dir="$FRAMES_DIR" '
  /^file / { f = $2; gsub(/\x27/, "", f); next }
  /^duration / { acc += $2 * 30; n = int(acc + 0.5) - done; for (i = 0; i < n; i++) { printf "%s/%s %s/seq/s%06d.jpg\n", dir, f, dir, done + i } done += n }
' "$FRAMES_DIR/list.txt" | while read -r src dst; do ln -s "$src" "$dst"; done
ffmpeg -loglevel error -y -framerate 30 -i "$SEQ/s%06d.jpg" -vf "format=yuv420p" \
  -c:v libx264 -preset medium -crf 20 -movflags +faststart SAMA-demo-fallback.mp4
ls -la SAMA-demo-fallback.mp4
