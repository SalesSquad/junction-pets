#!/usr/bin/env python3
"""Fake `ssh` for ops/tests: runs the remote command locally with bash.

The "remote" home directory of host H is $FAKE_VERDA_DIR/remote/H. A connection succeeds only
when the fake verda state has a machine with that ip whose last reported status is 'running'.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

D = Path(os.environ["FAKE_VERDA_DIR"])
WITH_VALUE = {"-i", "-o", "-p", "-l", "-F", "-E", "-e", "-J"}


def main():
    argv = sys.argv[1:]
    i, target, rest = 0, None, []
    while i < len(argv):
        a = argv[i]
        if a in WITH_VALUE:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            target, rest = a, argv[i + 1:]
            break
    host = (target or "").rpartition("@")[2]
    cmd = " ".join(rest)
    scenario = json.loads((D / "scenario.json").read_text())
    counter = D / "ssh_count"
    n = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(n + 1))
    with open(D / "ssh_calls.jsonl", "a") as f:
        f.write(json.dumps({"host": host, "cmd": cmd, "argv": argv, "t": time.time()}) + "\n")
    if n < scenario.get("ssh_fail_first", 0):
        sys.stderr.write(f"ssh: connect to host {host} port 22: Connection refused\n")
        sys.exit(255)
    state = json.loads((D / "state.json").read_text()) if (D / "state.json").exists() else {"vms": {}}
    up = any(v["ip"] == host and v["status"] == "running" and not v["deleted"] for v in state["vms"].values())
    if not up:
        sys.stderr.write(f"ssh: connect to host {host} port 22: Operation timed out\n")
        sys.exit(255)
    home = D / "remote" / host
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HOME=str(home))
    sys.exit(subprocess.run(["bash", "-c", cmd], env=env, cwd=home).returncode)


main()
