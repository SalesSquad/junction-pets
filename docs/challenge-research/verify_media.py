#!/usr/bin/env python3
"""Verify recovered study artifacts, optionally against local original recordings."""
from pathlib import Path
import argparse, hashlib, json, subprocess
def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--originals", type=Path, help="Optional owner-local directory containing original MOVs")
    parser.add_argument("--decode", action="store_true", help="Fully decode every rendition with installed FFmpeg")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((Path(__file__).parent / "media-manifest.json").read_text())
    seen = set()
    for entry in manifest["entries"]:
        assert entry["recording"] not in seen, "duplicate recording"
        seen.add(entry["recording"])
        for field in ("rendition", "transcript"):
            evidence = entry[field]
            path = (root / evidence["path"]).resolve()
            assert root in path.parents, "artifact escapes repository"
            assert digest(path) == evidence["sha256"], str(path)
        rendition = root / entry["rendition"]["path"]
        assert rendition.stat().st_size == entry["rendition"]["bytes"]
        if args.originals:
            source = args.originals / entry["source"]["filename"]
            assert digest(source) == entry["source"]["sha256"], str(source)
        if args.decode:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-err_detect", "explode", "-i", str(rendition), "-f", "null", "-"], check=True)
            probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(rendition)]))
            assert any(s["codec_type"] == "audio" for s in probe["streams"])
            assert abs(float(probe["format"]["duration"]) - entry["source"]["duration_seconds"]) < .25
    assert len(seen) == 19, "expected recovered19-recording set"
    print(f"Verified {len(seen)} rendition/transcript pairs" + (" with full decode" if args.decode else ""))
if __name__ == "__main__":
    main()
