#!/usr/bin/env python3
"""Reproducible *synthetic* sensitivity study for Bahn 97 RescueDesk.

It runs the actual SDK-compatible RescueDesk fee/offer decisions under three
arms but uses explicitly invented driver-response hazards. No sponsor worlds,
real-world effect estimates, API tokens or hidden challenge data are used.
"""
from __future__ import annotations

import copy
import json
import os
import random
from contextlib import contextmanager

from rescue_experiment import RescueDesk
from test_dispatch import FakeWorld, request, won_order


SEED = 97141114
N = 1500
ARMS = ("discovery", "fees", "full")
SCENARIOS = {
    "balanced": {"hazard": 0.080, "elasticity": 1.1, "offer": 0.14},
    "scarce": {"hazard": 0.045, "elasticity": 1.1, "offer": 0.07},
    "high_fee_elasticity": {"hazard": 0.055, "elasticity": 2.4, "offer": 0.12},
    "zero_fee_elasticity": {"hazard": 0.055, "elasticity": 0.0, "offer": 0.12},
    "severe_shortage": {"hazard": 0.025, "elasticity": 0.8, "offer": 0.02},
}


@contextmanager
def mode(name: str):
    before = os.environ.get("SPREAD_RESCUE_MODE")
    os.environ["SPREAD_RESCUE_MODE"] = name
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("SPREAD_RESCUE_MODE", None)
        else:
            os.environ["SPREAD_RESCUE_MODE"] = before


def make_case(rng: random.Random, n: int) -> tuple[dict, dict, int, list[float], list[float]]:
    req = request()
    req["id"] = f"SYNTH-{n}"
    req["referenceFeeCents"] = rng.randint(11000, 26000)
    order = won_order(req)
    order["id"] = req["id"]
    order["priceCents"] = round(req["referenceFeeCents"] * rng.uniform(2.5, 3.5))
    horizon = rng.choices((180, 360, 720, 1200, 2200), (1, 2, 3, 3, 1))[0]
    now = rng.randint(0, 6) * 1440 + rng.randint(7 * 60, 20 * 60)
    order["lastPickupAt"] = now + horizon
    order["deadline"] = now + horizon + 400
    # Paired random variates per case and step: differences reflect strategy
    # choices rather than different simulated weeks.
    draws = [rng.random() for _ in range(horizon // 15 + 2)]
    offers = [rng.random(), rng.random()]
    return req, order, now, draws, offers


def policy_actions(req: dict, order: dict, now: int, arm: str) -> tuple[list[dict], list[dict]]:
    with mode(arm):
        world = FakeWorld()
        desk = RescueDesk(world, 8, now)
        desk.requests[order["id"]] = req
        desk.orders[order["id"]] = copy.deepcopy(order)
        fees = desk.fees_for(order, 1)
        # Use the real contract hook and candidate filtering without an actual
        # world.act. The synthetic gig is accepted and mapped locally.
        desk.carry({"type": "post", "stops": [
            {"orderId": order["id"], "leg": 0, "kind": "pickup"},
            {"orderId": order["id"], "leg": 0, "kind": "delivery"}],
            "audience": {"experienced": False, "manualLicence": False},
            "schedule": fees}, f"GIG-{order['id']}")
        if arm == "full":
            desk._maybe_offer(f"GIG-{order['id']}")
        offers = [a for a in desk.outbox if a["type"] == "offer"]
    return fees, offers


def simulate(case: tuple, arm: str, scenario: dict) -> tuple[bool, int]:
    req, order, now, draws, offer_draws = case
    fees, offers = policy_actions(req, order, now, arm)
    ref = req["referenceFeeCents"]
    # Targeted invitations are answered no later than 10 simulated minutes.
    for action, u in zip(offers, offer_draws):
        p = min(0.70, scenario["offer"] * (action["feeCents"] / ref) ** scenario["elasticity"])
        if u < p:
            return True, action["feeCents"]
    for index, u in enumerate(draws):
        minute = index * 15
        if minute >= order["lastPickupAt"] - now:
            break
        fee = fees[0]["feeCents"]
        for step in fees:
            if step["at"] <= now + minute:
                fee = step["feeCents"]
        p = min(0.80, scenario["hazard"] * (fee / ref) ** scenario["elasticity"])
        if u < p:
            return True, fee
    # A late/undelivered vehicle contributes a synthetic penalty; its true
    # sponsor accounting is different and cannot be inferred here.
    return False, 0


def run() -> list[dict]:
    rng = random.Random(SEED)
    cases = [make_case(rng, n) for n in range(N)]
    output = []
    for scenario_name, assumptions in SCENARIOS.items():
        row = {"scenario": scenario_name, "assumptions": assumptions, "arms": {}}
        for arm in ARMS:
            on_time = 0
            earnings = 0
            for case in cases:
                success, cost = simulate(case, arm, assumptions)
                on_time += int(success)
                # Same won orders and quote prices in all arms. The invented
                # late penalty is deliberately explicit (€150 per miss).
                earnings += case[1]["priceCents"] - cost - (0 if success else 15000)
            row["arms"][arm] = {
                "on_time_pct": round(100 * on_time / N, 2),
                "on_time": on_time,
                "synthetic_margin_eur": round(earnings / 100, 2),
            }
        output.append(row)
    return output


if __name__ == "__main__":
    print(json.dumps({"kind": "SYNTHETIC_SENSITIVITY_NOT_SPONSOR_EVIDENCE",
                      "seed": SEED, "orders_per_scenario": N,
                      "conditional_on_won": True, "assumed_late_penalty_cents": 15000,
                      "results": run()}, indent=2))
