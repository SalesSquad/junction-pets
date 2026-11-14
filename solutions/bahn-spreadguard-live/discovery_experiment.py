#!/usr/bin/env python3
"""Isolated, unranked-only Bahn quote/driver price-discovery experiment.

NOT the reviewed default policy. Run only on an official unranked practice seed;
do not use for a board or final before five-world service qualification.
"""
from __future__ import annotations

import atexit
from collections import Counter
from typing import Any

from spread import starter

from dispatch import SpreadGuardDesk, round_up_div


COUNTS: Counter[str] = Counter()


@atexit.register
def report_aggregate() -> None:
    print("DISCOVERY_DECISIONS=" + repr(dict(sorted(COUNTS.items()))), flush=True)


class DiscoveryDesk(SpreadGuardDesk):
    """Price-discovery hypothesis: conservative routes, lower driver ramp."""

    def quote(self, request: dict[str, Any]) -> None:
        self.requests[request["id"]] = request
        COUNTS["requests"] += 1
        if self.now >= request["respondBy"] or not request["options"]:
            COUNTS["expired"] += 1
            return
        origin = request["legs"][0]["pickup"]["placeId"]
        backlog = self._local_backlog(origin)
        nearby = self._driver_count(origin)
        eligible: list[tuple[int, dict[str, Any], int]] = []
        for option in request["options"]:
            slack = self._slack(request, option)
            if slack < 480 + self._booking_delay_buffer():
                COUNTS["time_veto"] += 1
                continue
            if self.roster and nearby < 2:
                COUNTS["driver_veto"] += 1
                continue
            if backlog >= 5 and slack < 900:
                COUNTS["backlog_veto"] += 1
                continue
            # Competitors typically price around 1.26-1.54x list at level 8.
            # No hidden reserve/cost is assumed; all prices are exact cents.
            price = round_up_div(option["listPriceCents"] * 132, 100)
            if price * 100 < request["referenceFeeCents"] * 135:
                COUNTS["fee_veto"] += 1
                continue
            projected = price - round_up_div(request["referenceFeeCents"] * 120, 100)
            eligible.append((projected + min(300, slack // 10), option, price))
        if eligible:
            _, option, price = max(eligible, key=lambda e: (e[0], e[1]["deadline"]))
            COUNTS["competitive"] += 1
            prices = {option["kind"]: price}
        else:
            COUNTS["fallback"] += 1
            option = request["options"][0]
            prices = {option["kind"]: min((2**31 - 1), option["listPriceCents"] * 20)}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def fees_for(self, order: dict[str, Any], cars: int) -> list[dict[str, int]]:
        if self.level < 7:
            return super().fees_for(order, cars)
        total = len(order["legs"])
        ref = round_up_div(self.requests[order["id"]]["referenceFeeCents"] * cars, total)
        urgent = order["id"] in self.urgent
        factors = [155, 170, 190, 220] if urgent else [100, 110, 120, 135, 150]
        times = [0, 15, 30, 60] if urgent else [0, 30, 90, 180, 300]
        cap = self._remaining_fee_budget(order, cars)
        steps = []
        for gap, factor in zip(times, factors):
            fee = round_up_div(ref * factor, 100)
            if cap is not None:
                fee = min(fee, cap)
            # Avoid a plateau of duplicate fee steps after reaching a cap.
            if steps and fee <= steps[-1]["feeCents"]:
                continue
            steps.append({"at": self.now + gap, "feeCents": fee})
        return steps


if __name__ == "__main__":
    starter.Desk = DiscoveryDesk
    starter.main()
