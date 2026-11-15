#!/usr/bin/env python3
"""Restart smoke for MarginDesk on an unranked practice world (never --board/--final).

Plays a level-8 practice world to Wednesday 12:00, discards the desk, rebuilds a new
one from the server snapshot and full event history (as `play_final` does after a
crash or server restart), then plays to the end. Prints the final score as JSON.
Usage: rejoin_smoke.py <seed>
"""
from __future__ import annotations

import json
import sys

from spread import starter
from spread.client import Client

import margin_experiment  # noqa: F401  (configures defaults via the environment)
from margin_experiment import MarginDesk

DAY = 1440


def step(world, desk, until: int) -> None:
    while desk.now < until:
        midnight = (desk.now // DAY + 1) * DAY
        actions, desk.outbox = desk.outbox, []
        result = world.advance(until=starter.WAKE_ON, max=min(until, midnight), actions=actions)
        desk.read_results(actions, result["results"])
        desk.now = result["now"]
        for event in result["events"]:
            desk.handle(event)


def main() -> None:
    seed = sys.argv[1]
    client = Client()
    world = client.create(level=8, seed=seed, board=False)
    try:
        snapshot = world.snapshot()
        desk = MarginDesk(world, 8, snapshot["now"])
        step(world, desk, 2 * DAY + 12 * 60)
        before = (len(desk.win_times), len(desk.close_times), sum(desk.trust.values()))
        # Simulated crash: a fresh desk rebuilds its books from the server.
        history = world.events()
        snapshot = world.snapshot()
        desk = MarginDesk(world, 8, snapshot["now"])
        desk.rejoin(snapshot, history)
        after = (len(desk.win_times), len(desk.close_times), sum(desk.trust.values()))
        desk.send()
        step(world, desk, snapshot["endsAt"])
    except BaseException:
        try:
            world.delete()
        except Exception:  # noqa: BLE001
            pass
        raise
    score = world.score()
    print("REJOIN " + json.dumps({"seed": seed, "world": world.id, "before": before,
                                  "after": after, **score}), flush=True)


if __name__ == "__main__":
    main()
