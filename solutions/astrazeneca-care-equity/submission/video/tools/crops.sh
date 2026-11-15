#!/bin/bash
# Re-crop the product screenshots used by the video from submission/shots/ (1440 px captures).
# Run from submission/video: bash tools/crops.sh   (needs ffmpeg). Crops are w:h:x:y in 1440-px page pixels.
set -euo pipefail
SHOTS=../shots
OUT=assets/shots
mkdir -p "$OUT"
crop() { ffmpeg -loglevel error -y -i "$SHOTS/$1" -vf "crop=$2" -frames:v 1 "$OUT/$3"; echo "$3 <- $1 ($2)"; }
# 15 Nov polish: the start page is 937 px tall now (shorter survival tile); pad back to 963 so the frame keeps its size.
crop 01-hero-1440.png            1440:937:0:0,pad=1440:963:0:0:color=0xfafaf6 hero.png
crop 02-gap-map-1440.png         1300:1000:100:330   gapmap.png
crop 03-who-how-where-1440.png   1300:1000:80:60     whohow.png
crop 08-safetynet-1440.png       1180:1040:80:20     safetynet.png
crop 09-flare-gate-1440.png      980:480:70:10       flaregate.png
# 15 Nov polish: the plan now comes before the method block, so the draft starts at y 450 instead of 1060.
crop 11-planner-nemotron-1440.png 1100:900:80:450    planner.png
# 15 Nov polish: the raw model output is now folded away, so the capture is 1399 px tall; pad to keep 1320x1400.
crop 14b-gemma-demo-demo-04-1440.png 1320:1359:90:40,pad=1320:1400:0:0:color=0xfafaf6 gemma04.png
