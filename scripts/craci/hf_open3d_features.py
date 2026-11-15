#!/usr/bin/env python3
"""Package or restore hash-verified bounded features for CRACI jobs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

LINES = ("v2d", "g1", "robo")
LIMIT = 19 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transfer(source, target, pack):
    report = json.loads((source / "preparation.json").read_text(encoding="utf-8"))
    target.mkdir(parents=True, exist_ok=False)
    for line in LINES:
        expected = report["lines"][line]
        if expected["bytes"] > LIMIT:
            raise ValueError("feature input exceeds bound")
        entry = line + ".npz"
        if pack:
            raw = (source / entry).read_bytes()
        else:
            with zipfile.ZipFile(source / (line + ".zip")) as archive:
                if archive.namelist() != [entry] or archive.getinfo(entry).file_size > LIMIT:
                    raise ValueError("unexpected feature archive")
                raw = archive.read(entry)
        if len(raw) != expected["bytes"] or sha(raw) != expected["sha256"]:
            raise ValueError("feature size or digest mismatch")
        if pack:
            with zipfile.ZipFile(target / (line + ".zip"), "x", zipfile.ZIP_STORED) as archive:
                archive.writestr(entry, raw)
        else:
            (target / entry).write_bytes(raw)
    (target / "preparation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pack", "unpack"))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    transfer(args.source, args.target, args.mode == "pack")
