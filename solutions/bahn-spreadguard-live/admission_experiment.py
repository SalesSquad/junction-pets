#!/usr/bin/env python3
"""Opt-in official Spread 0.1.0 market-admission counterfactual.

This is an experiment, not a ranked or final policy. It preserves the proven
Discovery fee schedule and changes only the *quoted price* and incremental
pre-booking time buffer. Evaluate with matched official unranked seed worlds.
"""
from __future__ import annotations

import atexit
import os
from collections import Counter
from typing import Any

from spread import starter

from discovery_experiment import DiscoveryDesk
from dispatch import round_up_div


ADMISSION_COUNTS: Counter[str] = Counter()


@atexit.register
def report_admission_aggregate() -> None:
    print("ADMISSION_DECISIONS=" + repr(dict(sorted(ADMISSION_COUNTS.items()))), flush=True)


class AdmissionDesk(DiscoveryDesk):
    """Small, falsifiable supply/demand quote overlay.

    Environment-controlled factors permit separate pure-price, pure-slack
    and combined ablations without touching the baseline Discovery script.
    A rejected quote uses the sponsor-supported high-price decline; it does
    not miss quote submission and damage dealer trust.
    """

    def __init__(self, world: Any, level: int, now: int):
        super().__init__(world, level, now)
        self.quote_pct = int(os.getenv("SPREAD_ADMISSION_PRICE_PCT", "132"))
        self.extra_slack = int(os.getenv("SPREAD_ADMISSION_EXTRA_SLACK", "120"))
        self.surge_per_backlog = int(os.getenv("SPREAD_ADMISSION_SURGE_PER_BACKLOG", "0"))
        if not (100 <= self.quote_pct <= 160):
            raise ValueError("SPREAD_ADMISSION_PRICE_PCT outside 100..160")
        if not (0 <= self.extra_slack <= 720):
            raise ValueError("SPREAD_ADMISSION_EXTRA_SLACK outside 0..720")
        if not (0 <= self.surge_per_backlog <= 5):
            raise ValueError("SPREAD_ADMISSION_SURGE_PER_BACKLOG outside 0..5")

    def quote(self, request: dict[str, Any]) -> None:
        if self.level < 7:
            super().quote(request)
            return
        self.requests[request["id"]] = request
        ADMISSION_COUNTS["requests"] += 1
        if self.now >= request["respondBy"] or not request["options"]:
            ADMISSION_COUNTS["expired"] += 1
            return
        origin = request["legs"][0]["pickup"]["placeId"]
        backlog = self._local_backlog(origin)
        nearby = self._driver_count(origin)
        eligible: list[tuple[int, dict[str, Any], int]] = []
        for option in request["options"]:
            slack = self._slack(request, option)
            # First preserve every normal Discovery admission condition.
            floor = 480 + self._booking_delay_buffer()
            if slack < floor:
                ADMISSION_COUNTS["baseline_time_veto"] += 1
                continue
            if self.roster and nearby < 2:
                ADMISSION_COUNTS["driver_veto"] += 1
                continue
            if backlog >= 5 and slack < 900:
                ADMISSION_COUNTS["backlog_veto"] += 1
                continue
            # Fable's falsifiable hypothesis: add risk buffer ONLY for
            # next-day pickups, which accounted for the observed late cases.
            if option["kind"] == "next_day" and slack < floor + self.extra_slack:
                ADMISSION_COUNTS["next_day_slack_veto"] += 1
                continue
            surge_pct = min(12, max(0, backlog - 2) * self.surge_per_backlog)
            factor = min(160, self.quote_pct + surge_pct)
            price = round_up_div(option["listPriceCents"] * factor, 100)
            if price * 100 < request["referenceFeeCents"] * 135:
                ADMISSION_COUNTS["fee_veto"] += 1
                continue
            projected = price - round_up_div(request["referenceFeeCents"] * 120, 100)
            eligible.append((projected + min(300, slack // 10), option, price))
        if eligible:
            _, option, price = max(eligible, key=lambda e: (e[0], e[1]["deadline"]))
            prices = {option["kind"]: price}
            ADMISSION_COUNTS["competitive"] += 1
            if self.quote_pct > 132 or self.surge_per_backlog:
                ADMISSION_COUNTS["price_adjusted"] += 1
        else:
            # Sponsor-safe losing quote preserves dealer goodwill.
            option = request["options"][0]
            prices = {option["kind"]: min(2**31 - 1, option["listPriceCents"] * 20)}
            ADMISSION_COUNTS["declined"] += 1
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


if __name__ == "__main__":
    starter.Desk = AdmissionDesk
    starter.main()
