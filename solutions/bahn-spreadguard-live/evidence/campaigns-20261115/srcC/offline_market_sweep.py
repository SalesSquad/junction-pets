#!/usr/bin/env python3
"""Deterministic no-key *structural* stress comparison, not practice scoring.

Identical synthetic requests are passed to both opt-in pricing policies in
balanced, congested, and supply-unknown scenarios. We only count quote shape,
conservatism and fee feasibility. We do NOT invent booking/winning/late labels
or claim these statistics predict official sponsor-world profit.
"""
from __future__ import annotations

import copy
import random
from collections import defaultdict

from discovery_experiment import DiscoveryDesk
from test_dispatch import FakeWorld, request, won_order
from uber_market_experiment import UberMarketDesk


def prepare(desk, driver_count: int, backlog: int, wait_age: int):
    desk.roster = desk.roster[:driver_count]
    for index in range(backlog):
        req = request()
        order = won_order(req)
        order["id"] = f"queue-{index}"
        order["status"] = "waiting"
        desk.orders[order["id"]] = order
        if wait_age:
            desk.posts[f"post-{index}"] = {
                "stops": [{"kind": "pickup", "orderId": order["id"], "leg": 0}],
                "schedule": [{"at": desk.now - wait_age, "feeCents": 12000}],
            }


def sweep(samples: int = 600) -> None:
    rng = random.Random(20261114)
    scenarios = (
        ("balanced", 8, 0, 0),
        ("queue", 4, 2, 90),
        ("shortage", 2, 5, 180),
        ("unknown_supply", 0, 0, 0),
    )
    for label, drivers, backlog, wait_age in scenarios:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for index in range(samples):
            req = request()
            req["id"] = f"synthetic-{label}-{index}"
            base_price = rng.randint(18000, 68000)
            req["referenceFeeCents"] = rng.randint(8000, 47000)
            for option, multiple in zip(req["options"], (1.2, 1.0, 0.8)):
                option["listPriceCents"] = round(base_price * multiple)
            for policy_name, policy in (("discovery", DiscoveryDesk),
                                        ("uber_market", UberMarketDesk)):
                desk = policy(FakeWorld(), 8, 480)
                prepare(desk, drivers, backlog, wait_age)
                desk.quote(copy.deepcopy(req))
                quote = desk.outbox.pop()["prices"]
                kind, cents = next(iter(quote.items()))
                option = next(o for o in req["options"] if o["kind"] == kind)
                stats = counts[policy_name]
                stats["requests"] += 1
                if cents >= 10 * option["listPriceCents"]:
                    stats["declined"] += 1
                    continue
                stats["competitive"] += 1
                stats["sum_quote_cents"] += cents
                stats["sum_slack_minutes"] += desk._slack(req, option)
                assert cents * 100 >= req["referenceFeeCents"] * 135
                assert cents * 85 >= req["referenceFeeCents"] * 100
        for name in ("discovery", "uber_market"):
            s = counts[name]
            competitive = s["competitive"]
            print(f"scenario={label} strategy={name} requests={s['requests']} "
                  f"competitive={competitive} decline={s['declined']} "
                  f"quote_rate={competitive/s['requests']:.3f} "
                  f"mean_quote_eur={(s['sum_quote_cents']/competitive/100) if competitive else 0:.2f} "
                  f"mean_slack_min={(s['sum_slack_minutes']/competitive) if competitive else 0:.1f}")
    print("LIMITATION=synthetic_quote_fee_structural_sweep_no_dealer_or_driver_outcomes")


if __name__ == "__main__":
    sweep()
