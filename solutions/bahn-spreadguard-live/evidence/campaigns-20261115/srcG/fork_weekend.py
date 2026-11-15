#!/usr/bin/env python3
"""Same-future fork experiment: one parent world, one child per policy arm.

    python fork_weekend.py parent <seed> <fork_minute> <arm,arm,...>

The parent plays the frozen vol360 policy up to <fork_minute>, is forked once per
arm (same minute, same future draws) and deleted. Each child runs in its own
process: it rebuilds the desk from the shared history (rejoin) and plays the arm's
policy to the end, printing one RESULT line. Unranked practice only; never --board
or --final.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from run_pair import POLICIES

HERE = os.path.dirname(os.path.abspath(__file__))


def apply_env(policy: str) -> None:
    cfg = dict(POLICIES[policy])
    if cfg.pop("cls", "margin") != "margin":
        raise SystemExit("fork arms must be MarginDesk policies")
    os.environ["SPREAD_ADMISSION_PRICE_PCT"] = "139"
    os.environ["SPREAD_ADMISSION_EXTRA_SLACK"] = cfg.pop("SPREAD_ADMISSION_EXTRA_SLACK", "240")
    cfg.setdefault("SPREAD_MARGIN_FLOOR", "480")
    cfg.setdefault("SPREAD_MARGIN_REGION", "1")
    os.environ.update(cfg)


def play(world, desk, stop: int) -> None:
    from spread import starter
    while desk.now < stop:
        midnight = (desk.now // starter.DAY + 1) * starter.DAY
        actions, desk.outbox = desk.outbox, []
        step = world.advance(until=starter.WAKE_ON, max=min(stop, midnight), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            desk.handle(event)


def parent(seed: str, fork_minute: int, arms: list[str]) -> None:
    apply_env("vol360")
    from spread import starter
    from spread.client import Client
    from margin_experiment import MarginDesk
    client = Client()
    world = client.create(level=8, seed=seed, board=False)
    try:
        snap = world.snapshot()
        desk = MarginDesk(world, 8, snap["now"])
        play(world, desk, fork_minute)
        # Send what the desk decided at the fork minute so every child starts alike.
        if desk.outbox:
            world.act(desk.outbox)
            desk.outbox = []
        children = [(arm, world.fork().id) for arm in arms]
    finally:
        world.delete()
    procs = []
    for arm, wid in children:
        procs.append(subprocess.Popen(
            [sys.executable, os.path.join(HERE, "fork_weekend.py"), "child", wid, arm, seed, str(fork_minute)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=HERE))
    for (arm, wid), proc in zip(children, procs):
        out, _ = proc.communicate()
        lines = [l for l in out.splitlines() if l.startswith("RESULT ")]
        if lines:
            print(lines[-1], flush=True)
        else:
            print(f"CHILD_FAILED {arm} {wid} " + " | ".join(out.splitlines()[-3:]), flush=True)


def child(wid: str, arm: str, seed: str, fork_minute: int) -> None:
    apply_env(arm)
    from spread.client import Client
    from margin_experiment import MarginDesk
    client = Client()
    world = client.world(wid)
    t0 = time.time()
    try:
        history = world.events()
        snap = world.snapshot()
        world._last_seq = history[-1]["seq"] if history else -1
        desk = MarginDesk(world, 8, snap["now"])
        desk.rejoin(snap, history)
        play(world, desk, snap["endsAt"])
        score = world.score()
    except BaseException:
        try:
            world.delete()
        except Exception:  # noqa: BLE001
            pass
        raise
    print("RESULT " + json.dumps({"seed": f"{seed}@{fork_minute}", "policy": arm, "world": wid,
                                  "fork_minute": fork_minute, "elapsed": round(time.time() - t0, 1),
                                  **score}), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "parent":
        parent(sys.argv[2], int(sys.argv[3]), sys.argv[4].split(","))
    else:
        child(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
