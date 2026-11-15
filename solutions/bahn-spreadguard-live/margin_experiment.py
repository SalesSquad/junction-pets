#!/usr/bin/env python3
"""Opt-in margin overlay on the frozen 139% / +240 min admission candidate.

Three independent, environment-switchable changes (unranked practice only):

* SPREAD_MARGIN_RAMP=1   fee raises pause from 21:00 to 07:00 and start on the
                         pickup day; with lots of slack the raise gaps double.
                         The last raise still lands before ``lastPickupAt`` - 3 h.
* SPREAD_MARGIN_TRUST_BPS=N  add N basis points of price per counted on-time
                         order to the dealer (level 8 trust is +1 % per order).
* SPREAD_MARGIN_REGION=1 raise the price in a region (pickup place and places
                         within 80 km) after a streak of wins, back off on loss.
                         Targets the unannounced competitor outage.

Defaults are the frozen ``vol360`` candidate: 139% of list + 0.8% per counted
on-time order to the dealer, slack floor 360 min (was 480), next-day buffer
SPREAD_ADMISSION_EXTRA_SLACK=120 (AdmissionDesk default; the old candidate used
240), backlog veto on, region pricing off, night-aware fee ramp on. Every other
admission veto of the 139% / +240 min candidate is kept.

    python margin_experiment.py --level 8 --seed <seed>    # unranked practice
    python margin_experiment.py --final                    # only with owner approval
"""
from __future__ import annotations

import atexit
import math
import os
from collections import Counter, deque
from typing import Any

from spread import starter

from admission_experiment import AdmissionDesk
from dispatch import DAY, round_up_div

MARGIN_COUNTS: Counter[str] = Counter()
ACTIVE_FROM = 7 * 60
ACTIVE_TO = 21 * 60
OUTAGE_KM = 80.0


@atexit.register
def report_margin_aggregate() -> None:
    print("MARGIN_DECISIONS=" + repr(dict(sorted(MARGIN_COUNTS.items()))), flush=True)


def km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def advance_active(start: int, minutes: int) -> int:
    """`minutes` of driver-active time after `start`, skipping 21:00-07:00."""
    t = start
    left = minutes
    while left > 0:
        day = t // DAY
        tod = t % DAY
        if tod < ACTIVE_FROM:
            t = day * DAY + ACTIVE_FROM
            continue
        if tod >= ACTIVE_TO:
            t = (day + 1) * DAY + ACTIVE_FROM
            continue
        room = ACTIVE_TO - tod
        step = min(room, left)
        t += step
        left -= step
    return t


class MarginDesk(AdmissionDesk):
    def __init__(self, world: Any, level: int, now: int):
        super().__init__(world, level, now)
        self.ramp_on = os.getenv("SPREAD_MARGIN_RAMP", "1") == "1"
        self.trust_bps = int(os.getenv("SPREAD_MARGIN_TRUST_BPS", "80"))
        self.trust_cap_bps = int(os.getenv("SPREAD_MARGIN_TRUST_CAP_BPS", "1600"))
        self.region_on = os.getenv("SPREAD_MARGIN_REGION", "0") == "1"
        self.region_step = int(os.getenv("SPREAD_MARGIN_REGION_STEP_BPS", "400"))
        self.region_cap = int(os.getenv("SPREAD_MARGIN_REGION_CAP_BPS", "3000"))
        self.region_loss = int(os.getenv("SPREAD_MARGIN_REGION_LOSS_BPS", "800"))
        self.price_cap_bps = int(os.getenv("SPREAD_MARGIN_PRICE_CAP_BPS", "18500"))
        self.slack_floor = int(os.getenv("SPREAD_MARGIN_FLOOR", "360"))
        self.backlog_veto = os.getenv("SPREAD_MARGIN_BACKLOG", "1") == "1"
        self.base_bps = int(os.getenv("SPREAD_MARGIN_BASE_BPS", "13900"))
        self.fee_pct = int(os.getenv("SPREAD_MARGIN_FEE_PCT", "100"))
        self.weekend_ramp = os.getenv("SPREAD_MARGIN_RAMP_WEEKEND", "0") == "1"
        # Quote every eligible option and let the dealer choose (default: best one only).
        self.multi = os.getenv("SPREAD_MARGIN_MULTI", "0") == "1"
        # Adaptive admission: loosen the time gates while recent orders find
        # drivers easily, tighten them as deadline warnings pile up.
        self.adapt = os.getenv("SPREAD_MARGIN_ADAPT", "0") == "1"
        self.adapt_lo = float(os.getenv("SPREAD_MARGIN_ADAPT_LO", "0.04"))
        self.adapt_hi = float(os.getenv("SPREAD_MARGIN_ADAPT_HI", "0.08"))
        self.win_times: deque[int] = deque()
        self.close_times: deque[int] = deque()
        self.closed_orders: set[str] = set()
        if not 60 <= self.fee_pct <= 120:
            raise ValueError("SPREAD_MARGIN_FEE_PCT outside 60..120")
        if not (0 <= self.trust_bps <= 120 and 0 <= self.region_cap <= 5000
                and 13900 <= self.price_cap_bps <= 20000):
            raise ValueError("margin overlay parameter outside its safe range")
        self.neighbours: dict[str, set[str]] = {}
        try:
            places = {p["id"]: p for p in world.client.map().get("places", [])}
            for pid, place in places.items():
                self.neighbours[pid] = {q for q, other in places.items()
                                        if km(place, other) <= OUTAGE_KM}
        except (starter.SpreadError, KeyError, TypeError, OSError):
            self.region_on = False
        self.region_bump: Counter[str] = Counter()
        self.region_streak: Counter[str] = Counter()
        self.region_day = now // DAY
        self.quoted_origin: dict[str, str] = {}

    # ------------------------------------------------------------- pricing
    def _region_bps(self, origin: str) -> int:
        if not self.region_on:
            return 0
        if self.now // DAY != self.region_day:
            self.region_day = self.now // DAY
            self.region_bump.clear()
            self.region_streak.clear()
        return self.region_bump[origin]

    def _learn_region(self, origin: str, won: bool) -> None:
        if not self.region_on:
            return
        self._region_bps(origin)  # day reset
        for place in self.neighbours.get(origin, {origin}):
            if won:
                self.region_streak[place] += 1
                if self.region_streak[place] >= 3:
                    self.region_bump[place] = min(self.region_cap,
                                                  self.region_bump[place] + self.region_step)
            else:
                self.region_streak[place] = 0
                self.region_bump[place] = max(0, self.region_bump[place] - self.region_loss)

    def quote(self, request: dict[str, Any]) -> None:
        if self.level < 8:
            super().quote(request)
            return
        self.requests[request["id"]] = request
        MARGIN_COUNTS["requests"] += 1
        if self.now >= request["respondBy"] or not request["options"]:
            MARGIN_COUNTS["expired"] += 1
            return
        origin = request["legs"][0]["pickup"]["placeId"]
        backlog = self._local_backlog(origin)
        nearby = self._driver_count(origin)
        trust = min(self.trust_cap_bps, self.trust_bps * self.trust[request["dealerId"]])
        region = self._region_bps(origin)
        factor_bps = min(self.price_cap_bps, self.base_bps + trust + region)
        if trust:
            MARGIN_COUNTS["trust_priced"] += 1
        if region:
            MARGIN_COUNTS["region_priced"] += 1
        slack_floor, extra_slack, backlog_veto = self._gates()
        eligible: list[tuple[int, dict[str, Any], int]] = []
        for option in request["options"]:
            slack = self._slack(request, option)
            floor = slack_floor + self._booking_delay_buffer()
            if slack < floor:
                continue
            if self.roster and nearby < 2:
                continue
            if backlog_veto and backlog >= 5 and slack < 900:
                continue
            if option["kind"] == "next_day" and slack < floor + extra_slack:
                continue
            price = round_up_div(option["listPriceCents"] * factor_bps, 10000)
            if price * 100 < request["referenceFeeCents"] * 135:
                continue
            projected = price - round_up_div(request["referenceFeeCents"] * 120, 100)
            eligible.append((projected + min(300, slack // 10), option, price))
        if eligible:
            _, option, price = max(eligible, key=lambda e: (e[0], e[1]["deadline"]))
            prices = {option["kind"]: price}
            if self.multi and len(eligible) > 1:
                prices = {opt["kind"]: p for _, opt, p in eligible}
                MARGIN_COUNTS["multi_option"] += 1
            self.quoted_origin[request["id"]] = origin
            MARGIN_COUNTS["competitive"] += 1
        else:
            option = request["options"][0]
            prices = {option["kind"]: min(2**31 - 1, option["listPriceCents"] * 20)}
            MARGIN_COUNTS["declined"] += 1
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def _gates(self) -> tuple[int, int, bool]:
        if not self.adapt:
            return self.slack_floor, self.extra_slack, self.backlog_veto
        horizon = self.now - DAY
        while self.win_times and self.win_times[0] < horizon:
            self.win_times.popleft()
        while self.close_times and self.close_times[0] < horizon:
            self.close_times.popleft()
        won = len(self.win_times)
        if won < 15:
            MARGIN_COUNTS["gate_warmup"] += 1
            return 360, 120, True
        rate = len(self.close_times) / won
        if rate <= self.adapt_lo:
            MARGIN_COUNTS["gate_loose"] += 1
            return 240, 0, False
        if rate <= self.adapt_hi:
            MARGIN_COUNTS["gate_mid"] += 1
            return 360, 120, True
        MARGIN_COUNTS["gate_tight"] += 1
        return 480, 240, True

    # ---------------------------------------------------------------- fees
    def fees_for(self, order: dict[str, Any], cars: int) -> list[dict[str, int]]:
        steps = super().fees_for(order, cars)
        if self.level >= 7 and order["id"] not in self.urgent and self.fee_pct != 100:
            scaled = []
            for step in steps:
                fee = max(1, step["feeCents"] * self.fee_pct // 100)
                if scaled and fee <= scaled[-1]["feeCents"]:
                    continue
                scaled.append({"at": step["at"], "feeCents": fee})
            steps = scaled or steps
        if (not self.ramp_on or self.level < 7 or order["id"] in self.urgent
                or len(steps) <= 1):
            return steps
        legs = [leg for i, leg in enumerate(order["legs"])
                if order["deliveredAt"][i] is None] or order["legs"]
        ready = min(leg["pickup"]["window"]["from"] for leg in legs)
        anchor = self.now
        if ready // DAY > self.now // DAY:
            anchor = max(self.now, (ready // DAY) * DAY + ACTIVE_FROM)
            MARGIN_COUNTS["ramp_future_day"] += 1
        limit = order.get("lastPickupAt")
        limit = limit - 180 if isinstance(limit, int) else None
        scale = 2 if limit is not None and limit - self.now > 20 * 60 else 1
        if self.weekend_ramp and order["deadline"] // DAY - self.now // DAY > 1:
            scale = 1  # a weekend or more lies ahead: keep the base raise speed
            MARGIN_COUNTS["ramp_weekend"] += 1
        out = [steps[0]]
        n = len(steps)
        for i, step in enumerate(steps[1:], 1):
            t = advance_active(anchor, (step["at"] - self.now) * scale)
            if limit is not None:
                t = min(t, limit - (n - 1 - i) * 20)
            t = max(t, out[-1]["at"] + 1, self.now + i)
            out.append({"at": t, "feeCents": step["feeCents"]})
        if out[-1]["at"] != steps[-1]["at"]:
            MARGIN_COUNTS["ramp_shifted"] += 1
        return out

    # -------------------------------------------------------------- events
    def handle(self, event: dict[str, Any]) -> None:
        kind = event.get("kind")
        if event.get("seq") not in self.seen:
            if kind == "order_won":
                self.win_times.append(event["at"])
            elif kind == "deadline_close" and event["orderId"] not in self.closed_orders:
                self.closed_orders.add(event["orderId"])
                self.close_times.append(event["at"])
        if kind in ("order_won", "order_lost") and event.get("seq") not in self.seen:
            rid = event["order"]["id"] if kind == "order_won" else event["requestId"]
            origin = self.quoted_origin.pop(rid, None)
            if origin is not None:
                self._learn_region(origin, kind == "order_won")
        super().handle(event)

    def rejoin(self, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        # After a restart, rebuild the admission controller from server history.
        for event in history:
            if event["kind"] == "order_won":
                self.win_times.append(event["at"])
            elif event["kind"] == "deadline_close" and event["orderId"] not in self.closed_orders:
                self.closed_orders.add(event["orderId"])
                self.close_times.append(event["at"])
        super().rejoin(snapshot, history)


if __name__ == "__main__":
    starter.Desk = MarginDesk
    starter.main()
