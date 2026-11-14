#!/usr/bin/env python3
"""Generate an owned, non-personal HEVC test card. Requires ffmpeg + DejaVu Sans."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
font = os.environ.get("CHIBI_TEST_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
subprocess.run([
    "ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", "color=c=white:s=640x480:r=24:d=12",
    "-vf", f"drawtext=fontfile='{font}':text='CHIBI TEST VIDEO':fontcolor=black:fontsize=32:x=40:y=70,"
           f"drawtext=fontfile='{font}':text='CHARGER A':fontcolor=black:fontsize=54:x=40:y=190,"
           f"drawtext=fontfile='{font}':text='65 W - USB C':fontcolor=black:fontsize=40:x=40:y=290",
    "-c:v", "libx265", "-preset", "fast", "-x265-params", "pools=1:frame-threads=1:log-level=error",
    "-tag:v", "hvc1", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
    str(root / "Resources" / "charger-label.mp4")
], check=True)
