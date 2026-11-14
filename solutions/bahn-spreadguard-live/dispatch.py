#!/usr/bin/env python3
"""SpreadGuard: low-latency Bahn Express strategy on the official Spread SDK.

Requires the unmodified `spread-0.1.0` Python package. The official starter owns
HTTP, rate limiting, practice time-stepping, final streaming, reconnect and
server-snapshot recovery. This file changes only its deterministic decisions.

The heuristics have NOT been calibrated on official practice worlds. Use `--seed`
for practice and `--board` only once qualification has been established.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

from spread import starter


MINUTE = 1
HOUR = 60
DAY = 1440
UNKNOWN_ROAD_MINUTES = 420


def road_index(map_data: dict[str, Any]) -> dict[tuple[str, str], int]:
    """Exact directed map from the public official `/v1/map` contract."""
    return {(edge["from"], edge["to"]): int(edge["minutes"])
            for edge in map_data.get("roads", [])
            if isinstance(edge.get("minutes"), int) and edge["minutes"] >= 0}


def round_up_div(a: int, b: int) -> int:
    return (a + b - 1) // b


class SpreadGuardDesk(starter.Desk):
    """Official starter event/API semantics; improve pricing and driver funding."""

    def __init__(self, world: Any, level: int, now: int):
        super().__init__(world, level, now)
        self.roads: dict[tuple[str, str], int] = {}
        self.roster: list[dict[str, Any]] = []
        self.trust: Counter[str] = Counter()
        self.won_by_dealer: Counter[str] = Counter()
        self.lost_by_dealer: Counter[str] = Counter()
        self.completed: set[str] = set()
        self.seen: set[int] = set()
        try:
            self.roads = road_index(world.client.map())
        except (starter.SpreadError, KeyError, TypeError, OSError):
            # No fake route claim: unknown lanes use a large conservative buffer.
            pass
        try:
            self.roster = list(world.roster())
        except (starter.SpreadError, KeyError, TypeError, OSError):
            pass

    def _route_minutes(self, request: dict[str, Any]) -> int:
        previous: str | None = None
        total = 0
        for leg in request["legs"]:
            a = leg["pickup"]["placeId"]
            b = leg["delivery"]["placeId"]
            if previous and previous != a:
                total += self.roads.get((previous, a), UNKNOWN_ROAD_MINUTES)
            total += self.roads.get((a, b), UNKNOWN_ROAD_MINUTES)
            previous = b
        return total

    def _driver_count(self, pickup_place_id: str) -> int:
        """Homes, not promises of availability. Only softens the risk score."""
        return sum(self.roads.get((d["homePlaceId"], pickup_place_id), 10000) <= 150
                   for d in self.roster)

    def _ready(self, request: dict[str, Any]) -> int:
        return max(self.now + HOUR, *(leg["pickup"]["window"]["from"]
                                      for leg in request["legs"]))

    @staticmethod
    def _open_at(place: dict[str, Any], earliest: int, latest: int,
                 note: dict[str, Any] | None, stop: str,
                 trade_in_customer_pickup: bool = False) -> int | None:
        """First stop inside its real published hours and note-adjusted slot.

        Dealer acceptance is delayed until its next opening; a Sunday arrival
        is not an on-time Sunday delivery. The second pickup of a connected
        trade-in may follow the new car's delivery after the original slot.
        """
        window = starter.window_from_note(note, place["window"], stop)
        start = max(earliest, window["from"])
        end = min(latest, window["to"])
        if trade_in_customer_pickup:
            end = latest
        if start > end:
            return None
        hours = place.get("hours")
        if place.get("privateAddress") or hours is None:
            return start

        for day in range(start // DAY, end // DAY + 1):
            weekday = day % 7
            if weekday <= 4:
                if weekday not in hours.get("weekdays", []):
                    continue
                opens, closes = hours["opens"], hours["closes"]
            elif weekday == 5 and hours.get("saturday") is not None:
                opens = hours["saturday"]["opens"]
                closes = hours["saturday"]["closes"]
            else:
                continue  # Sunday or a closed Saturday
            candidate = max(start, day * DAY + opens)
            if candidate <= min(end, day * DAY + closes):
                return candidate
        return None

    def _slack(self, request: dict[str, Any], option: dict[str, Any]) -> int:
        """Conservative sequential route and site-hours buffer, not a guarantee."""
        cursor = self.now + HOUR
        previous: str | None = None
        note = request.get("note")
        for index, leg in enumerate(request["legs"]):
            pickup = leg["pickup"]
            destination = leg["delivery"]
            connected_trade_in = (index > 0 and previous == pickup["placeId"]
                                  and pickup.get("privateAddress", False))
            earliest_pickup = cursor
            if previous is not None and previous != pickup["placeId"]:
                earliest_pickup += round_up_div(
                    self.roads.get((previous, pickup["placeId"]), UNKNOWN_ROAD_MINUTES) * 125, 100
                )
            pickup_at = self._open_at(
                pickup, earliest_pickup, option["deadline"], note, "pickup",
                trade_in_customer_pickup=connected_trade_in,
            )
            if pickup_at is None:
                return -10000
            road = self.roads.get((pickup["placeId"], destination["placeId"]),
                                  UNKNOWN_ROAD_MINUTES)
            charge = (55 if leg["car"]["electric"]
                      and leg["car"]["chargePercent"] is not None
                      and leg["car"]["chargePercent"] < 30 else 0)
            arrival = pickup_at + round_up_div(road * 125, 100) + 70 + charge + 150
            deadline = option["deadline"]
            if destination.get("privateAddress"):
                deadline = min(deadline, destination["window"]["to"] + 30)
            delivered_at = self._open_at(destination, arrival, deadline, note, "delivery")
            if delivered_at is None:
                return -10000
            cursor = delivered_at
            previous = destination["placeId"]
        return option["deadline"] - cursor

    def _price_factor_bps(self, dealer: str, backlog: int) -> int:
        if self.level <= 3:
            return 10000
        if self.level <= 6:
            return 11300
        if self.level == 7:
            return 12500
        # First safe deliveries build trust, then we capture a fraction of the
        # provable +1% dealer acceptance premium, capped at 25 deliveries.
        trust_bps = min(2000, 78 * self.trust[dealer])
        wins = self.won_by_dealer[dealer]
        losses = self.lost_by_dealer[dealer]
        learned_bps = 180 if wins > losses + 2 else -180 if losses > wins + 3 else 0
        backlog_bps = min(1100, 175 * max(0, backlog - 2))
        return max(11500, min(15600, 12800 + trust_bps + learned_bps + backlog_bps))

    def _local_backlog(self, pickup_place_id: str) -> int:
        return sum(1 for order in self.orders.values()
                   if order.get("status") in ("waiting", "booked", "moving")
                   and order["legs"]
                   and order["legs"][0]["pickup"]["placeId"] == pickup_place_id)

    def quote(self, request: dict[str, Any]) -> None:
        self.requests[request["id"]] = request
        if self.now >= request["respondBy"] or not request["options"]:
            return
        dealer = request["dealerId"]
        origin = request["legs"][0]["pickup"]["placeId"]
        backlog = self._local_backlog(origin)
        fee = request["referenceFeeCents"]
        factor = self._price_factor_bps(dealer, backlog)
        # Select only options with time to hire and recover a driver. A quote to
        # the long option steers execution into the most resilient deadline.
        eligible: list[tuple[float, dict[str, Any], int]] = []
        for option in request["options"]:
            slack = self._slack(request, option)
            if slack < (120 if self.level < 7 else 210):
                continue
            if self.level >= 7 and self.roster and self._driver_count(origin) < 2:
                if slack < 600:
                    continue
            if self.level >= 7 and backlog >= 8 and slack < 700:
                continue
            # Exact integer cents; the official API rejects fractional money.
            price = round_up_div(option["listPriceCents"] * factor, 10000)
            # Reserve approximately a fee ramp plus cash for cancellations.
            if self.level >= 7 and price * 100 < fee * 185:
                continue
            # Strictly positive projected gross margin after a rescue reserve.
            gain = price - round_up_div(fee * (170 if self.level >= 7 else 125), 100)
            if gain <= 0:
                continue
            # Preserve dealer option preference; de-risk tight windows.
            value = gain - max(0, 600 - slack) * max(1, price // 2000)
            eligible.append((value, option, price))
        if eligible:
            _, best, price = max(eligible, key=lambda x: (x[0], x[1]["deadline"]))
            prices = {best["kind"]: price}
        elif self.level > 3:
            # Avoid unquoted-request goodwill loss without intentionally taking
            # a risky order. At levels <=3 all quotes win, hence no decline.
            first = request["options"][0]
            prices = {first["kind"]: min((2**31 - 1), first["listPriceCents"] * 20)}
        else:
            return
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def fees_for(self, order: dict[str, Any], cars: int) -> list[dict[str, int]]:
        total = len(order["legs"])
        fee = round_up_div(self.requests[order["id"]]["referenceFeeCents"] * cars, total)
        if self.level == 1:
            return [{"at": self.now, "feeCents": fee}]
        if self.level < 7:
            return starter.steep(self.now, fee, self.level) if order["id"] in self.urgent \
                else starter.rising(self.now, fee, self.level)
        # Level 8 shortage: pay enough immediately that drivers needn't learn
        # to wait for periodic raises, then escalate quickly only when unbooked.
        # Never reduce fees; latest steps stay within API 48-step limit.
        factor = [205, 225, 240, 260] if order["id"] in self.urgent else [155, 165, 185, 210, 230]
        gaps = [0, 15, 30, 60] if order["id"] in self.urgent else [0, 30, 90, 180, 300]
        return [{"at": self.now + at, "feeCents": round_up_div(fee * rate, 100)}
                for at, rate in zip(gaps, factor)]

    def post(self, order: dict[str, Any], legs: list[int], retry: starter.Retry = starter.Retry()) -> None:
        note = self.requests[order["id"]].get("note")
        text = (note or {}).get("text", "").lower()
        # Positive evidence from dealer notes; hidden facts are never invented.
        manual = bool(re.search(r"manual|manuaal|manuell|käsivaiht", text))
        plates = bool(re.search(r"no plates|kilvet puuttu|ei kilpi|utan skylt|skyltar sakn", text))
        if manual or plates:
            retry = starter.Retry(retry.pickup_from,
                                  manual_licence=retry.manual_licence or manual,
                                  plates=retry.plates or plates)
        super().post(order, legs, retry)

    def _mark_complete(self, order: dict[str, Any]) -> None:
        if order["id"] in self.completed or any(t is None for t in order["deliveredAt"]):
            return
        self.completed.add(order["id"])
        dealer = order["dealerId"]
        if max(order["deliveredAt"]) <= order["deadline"]:
            self.trust[dealer] = min(25, self.trust[dealer] + 1)
        else:
            self.trust[dealer] //= 2

    def handle(self, event: dict[str, Any]) -> None:
        if event["seq"] in self.seen:
            return
        self.seen.add(event["seq"])
        kind = event["kind"]
        if kind == "order_lost":
            req = self.requests.get(event["requestId"])
            if req:
                self.lost_by_dealer[req["dealerId"]] += 1
        elif kind == "order_won":
            self.won_by_dealer[event["order"]["dealerId"]] += 1
        super().handle(event)
        if kind == "delivered":
            order = self.orders.get(event["orderId"])
            if order:
                self._mark_complete(order)

    def rejoin(self, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        # Reconstruct adaptive pricing/trust from *server* evidence, then let
        # official Desk repair open orders/gigs. No local database is required.
        requests = {e["request"]["id"]: e["request"] for e in history
                    if e["kind"] == "price_request"}
        known_orders: dict[str, dict[str, Any]] = {}
        for event in history:
            kind = event["kind"]
            if kind == "order_won":
                order = event["order"]
                known_orders[order["id"]] = {**order, "deliveredAt": list(order["deliveredAt"])}
                self.won_by_dealer[order["dealerId"]] += 1
            elif kind == "order_changed":
                order = event["order"]
                known_orders[order["id"]] = {**order, "deliveredAt": list(order["deliveredAt"])}
            elif kind == "order_lost":
                request = requests.get(event["requestId"])
                if request:
                    self.lost_by_dealer[request["dealerId"]] += 1
            elif kind == "delivered":
                order = known_orders.get(event["orderId"])
                if order and event["leg"] < len(order["deliveredAt"]):
                    order["deliveredAt"][event["leg"]] = event["at"]
                    self._mark_complete(order)
        self.seen = {e["seq"] for e in history}
        super().rejoin(snapshot, history)


def main() -> None:
    # The complete official CLI, API client, batched advance actions, final
    # stream, resilient reconnect and 20/s action rate limiter remain intact.
    starter.Desk = SpreadGuardDesk
    starter.main()


if __name__ == "__main__":
    main()
