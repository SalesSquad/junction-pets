#!/usr/bin/env python3
"""Fake `rsync` for ops/tests: copies between local paths and the fake remote homes.

user@H:path maps to $FAKE_VERDA_DIR/remote/H/path (paths relative to the remote home only).
Supports what the tool uses: -az, -e CMD, --exclude PATTERN, trailing-slash semantics.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

D = Path(os.environ["FAKE_VERDA_DIR"])


def resolve(spec):
    head, sep, path = spec.partition(":")
    if sep and "@" in head and "/" not in head:
        host = head.rpartition("@")[2]
        state = json.loads((D / "state.json").read_text()) if (D / "state.json").exists() else {"vms": {}}
        if not any(v["ip"] == host and v["status"] == "running" and not v["deleted"] for v in state["vms"].values()):
            sys.stderr.write(f"ssh: connect to host {host} port 22: Operation timed out\nrsync error: unexplained error (code 255)\n")
            sys.exit(255)
        if path.startswith("/"):
            sys.stderr.write("fake rsync: absolute remote paths are not supported in tests\n")
            sys.exit(64)
        return D / "remote" / host / path
    return Path(spec)


def main():
    args = sys.argv[1:]
    with open(D / "rsync_calls.jsonl", "a") as f:
        f.write(json.dumps({"argv": args, "t": time.time()}) + "\n")
    excludes, pos, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a in ("-e", "--rsh"):
            i += 2
        elif a == "--exclude":
            excludes.append(args[i + 1])
            i += 2
        elif a.startswith("--exclude="):
            excludes.append(a.split("=", 1)[1])
            i += 1
        elif a.startswith("-"):
            i += 1
        else:
            pos.append(a)
            i += 1
    *srcs, dst = pos
    rc = 0
    for src in srcs:
        s, d = resolve(src), resolve(dst)
        if not s.exists():
            sys.stderr.write(f'rsync: link_stat "{src}" failed: No such file or directory (2)\n')
            rc = 23
            continue
        if s.is_dir():
            target = d if src.endswith("/") else d / s.name
            shutil.copytree(s, target, ignore=shutil.ignore_patterns(*excludes), dirs_exist_ok=True)
        else:
            if dst.endswith("/") or d.is_dir():
                d.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d / s.name)
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
    sys.exit(rc)


main()
