#!/usr/bin/env python3
"""Opt-in Uber-inspired *market-control* experiment for Bahn Spread.

Uber uses batch matching and supply-aware prices, but the public Spread SDK
does not expose individual driver selection. We therefore maintain virtual
capacity reservations across simultaneous quotes, price the opportunity cost
of scarce driver capacity and front-load gig offers when booking stalls.

This is NOT a calibrated win/late model and has not passed official practice.
Do not use with --board or --final; the five-world DiscoveryDesk is the control.
"""
from __future__ import annotations

from collections import Counter, deque
from typing import Any

from spread import starter

from dispatch import round_up_div
from discovery_experiment import DiscoveryDesk


class UberMarketDesk(DiscoveryDesk):
    """Bounded primal-dual marketplace controller; no hidden SDK access."""

    def __init__(self, world: Any, level: int, now: int):
        super().__init__(world, level, now)
        self.pending_quotes: dict[str, tuple[str, int]] = {}
        self.demand_history: deque[tuple[int, str]] = deque(maxlen=512)
        self.scored_completions = 0
        self.late_completions = 0
        self.marked_outcomes: set[str] = set()
        self.cancelled_won: set[str] = set()
        self.market_counters: Counter[str] = Counter()

    def _expire_quotes(self) -> None:
        for request_id, (_, expires) in list(self.pending_quotes.items()):
            if expires < self.now:
                self.pending_quotes.pop(request_id, None)

    def _free_supply(self, origin: str) -> int:
        return self._driver_count(origin) if self.roster else 0

    def _virtual_free_supply(self, origin: str) -> int:
        """Maximum-cardinality *virtual* driver/job matching on real road times.

        One driver cannot satisfy two neighborhoods' simultaneous needs. We
        reserve the nearest feasible drivers for existing unbooked orders and
        one capacity token per *pair* of pending competitive price quotes.
        This is a planning approximation, never a real SDK driver assignment.
        """
        if not self.roster:
            return 0
        self._expire_quotes()
        busy = set(self.active_drivers.values())
        free_drivers = sorted((d for d in self.roster if d["id"] not in busy),
                              key=lambda d: d["id"])
        positions: dict[str, str] = {}
        for driver in free_drivers:
            driver_id = driver["id"]
            observed = self.driver_place_observed_at.get(driver_id, -10000)
            positions[driver_id] = (
                self.driver_places[driver_id]
                if driver_id in self.driver_places
                and 0 <= self.now - observed <= 180
                else driver["homePlaceId"]
            )
        jobs: list[tuple[int, str, str]] = []
        for order_id, order in self.orders.items():
            if order.get("status") != "waiting":
                continue
            # A split trade-in may need two different drivers in two places.
            # Use the official SDK leg->gig mapping, counting each open gig
            # exactly once, while excluding gigs already booked to a driver.
            groups: dict[str, int] = {}
            for leg, delivered_at in enumerate(order.get("deliveredAt", [])):
                if delivered_at is not None:
                    continue
                gig_id = self.leg_gigs.get(order_id, {}).get(leg)
                if gig_id in self.active_drivers:
                    continue
                groups.setdefault(gig_id or "unposted", leg)
            for group, leg in groups.items():
                pickup = order["legs"][leg]["pickup"]["placeId"]
                jobs.append((int(order["deadline"]), f"{order_id}:{group}", pickup))
        by_place: dict[str, list[tuple[int, str]]] = {}
        for request_id, (place, expiry) in self.pending_quotes.items():
            by_place.setdefault(place, []).append((expiry, request_id))
        for place, pending in by_place.items():
            for index, (expiry, request_id) in enumerate(sorted(pending)):
                if index % 2 == 1:  # bounded 0.5 token per pending quote
                    jobs.append((expiry, "pending:" + request_id, place))
        jobs.sort()
        # With as many outstanding jobs as free drivers, the city has no
        # uncommitted supply anywhere; a full graph search adds no value.
        # This also bounds matching work in overloaded official worlds.
        if len(jobs) >= len(free_drivers) and jobs:
            return 0
        candidates: list[list[str]] = []
        for _, _, place in jobs:
            reachable = sorted((self.roads.get((positions[d["id"]], place), 10000),
                                d["id"]) for d in free_drivers)
            candidates.append([driver_id for minutes, driver_id in reachable
                               if minutes <= 150])
        assigned: dict[str, int] = {}

        def augment(job_index: int, seen: set[str]) -> bool:
            for driver_id in candidates[job_index]:
                if driver_id in seen:
                    continue
                seen.add(driver_id)
                if driver_id not in assigned or augment(assigned[driver_id], seen):
                    assigned[driver_id] = job_index
                    return True
            return False

        for job_index in range(len(jobs)):
            augment(job_index, set())
        return sum(driver_id not in assigned
                   and self.roads.get((place, origin), 10000) <= 150
                   for driver_id, place in positions.items())

    def _pressure(self, origin: str, free: int) -> float:
        """Outstanding virtual bids reserve half a driver until resolved.

        The half-weight is an intentionally conservative *heuristic*, not a
        purported probability of winning a competitor's actual auction.
        """
        self._expire_quotes()
        pending = sum(1 for place, _ in self.pending_quotes.values()
                      if self.roads.get((place, origin), 10_000) <= 120)
        return (self._local_backlog(origin) + 0.5 * pending) / max(1, free)

    def _recent_demand(self, origin: str) -> float:
        """Graph-aware demand proxy on the actual directed road graph."""
        return sum(
            max(0.0, 1.0 - self.roads.get((place, origin), 10_000) / 240.0)
            for seen_at, place in self.demand_history
            if 0 <= self.now - seen_at <= 240
        )

    def _censored_booking_buffer(self, origin: str) -> int:
        """Use accepted booking delays AND right-censored open gig wait ages.

        The official SDK provides no complete driver-acceptance hazard model;
        this is a bounded wait-age proxy, *not* a fitted survival probability.
        Ignore completed and already booked gigs to avoid stale-post bias.
        """
        booked_p90 = 0
        if len(self.booking_delays) >= 6:
            booked = sorted(self.booking_delays)
            booked_p90 = booked[(9 * (len(booked) - 1)) // 10]
        open_waits: list[int] = []
        for gig_id, post in self.posts.items():
            if gig_id in self.active_drivers:
                continue
            schedule = post.get("schedule", [])
            stops = post.get("stops", [])
            if not schedule or not stops:
                continue
            pickup = next((stop for stop in stops if stop.get("kind") == "pickup"),
                          stops[0])
            order = self.orders.get(pickup.get("orderId"))
            if not order or order.get("status") not in ("waiting", "booked", "moving"):
                continue
            leg_index = int(pickup.get("leg", 0))
            if leg_index >= len(order.get("deliveredAt", [])):
                continue
            if order["deliveredAt"][leg_index] is not None:
                continue
            if order["legs"][leg_index]["pickup"]["placeId"] != origin:
                continue
            age = self.now - int(schedule[0]["at"])
            if age >= 0:
                open_waits.append(min(age, 240))
        tail_age = max(booked_p90, max(open_waits, default=0))
        return min(150, max(0, tail_age - 75))

    def _service_debt_buffer(self) -> int:
        """Increase conservatism if completed deliveries fall below 95%.

        Early tiny samples do not activate the feedback loop. There is no
        guarantee that future seeds follow the same outcome distribution.
        """
        overdue = {order_id for order_id, order in self.orders.items()
                   if order_id not in self.marked_outcomes
                   and order_id not in self.cancelled_won
                   and self.now > int(order.get("deadline", self.now))
                   and any(at is None for at in order.get("deliveredAt", []))}
        cancellations = self.cancelled_won - self.marked_outcomes
        n = self.scored_completions + len(overdue) + len(cancellations)
        if n < 30:
            return 0
        smoothed_miss_rate = (
            self.late_completions + len(overdue) + len(cancellations) + 1
        ) / (n + 2)
        return min(150, round(max(0, smoothed_miss_rate - 0.05) * 1200))

    def _market_quote(self, request: dict[str, Any]) -> dict[str, int]:
        origin = request["legs"][0]["pickup"]["placeId"]
        free = self._free_supply(origin)
        # The old experimental policy implicitly treated a roster error as
        # unlimited supply. Missing observations are a *capacity unknown*.
        if free < 2:
            self.market_counters["supply_veto"] += 1
            return self._fallback_quote(request)
        backlog = self._local_backlog(origin)
        pressure = self._pressure(origin, free)
        virtual_free = self._virtual_free_supply(origin)
        demand = self._recent_demand(origin)
        wait_buffer = self._censored_booking_buffer(origin)
        debt_buffer = self._service_debt_buffer()
        # Shadow capacity price ties the *customer offer* to driver scarcity.
        scarcity = max(0.0, pressure - 0.35) + 0.30 * max(0, 2 - virtual_free)
        dynamic_pct = min(10, round(5 * scarcity + 0.8 * demand / max(1, free)))
        quote_pct = 132 + dynamic_pct
        # The 95% on-time aspiration is implemented as an explicit conservative
        # slack gate; no falsely calibrated event probability is claimed.
        minimum_slack = 480 + self._booking_delay_buffer() + wait_buffer \
            + debt_buffer + min(180, round(110 * scarcity))
        reference = int(request["referenceFeeCents"])
        choices: list[tuple[int, dict[str, Any], int]] = []
        for option in request["options"]:
            slack = self._slack(request, option)
            if virtual_free == 0 and slack < 1200:
                self.market_counters["capacity_veto"] += 1
                continue
            if slack < minimum_slack:
                self.market_counters["risk_veto"] += 1
                continue
            if backlog >= 5 and slack < 900 + wait_buffer:
                self.market_counters["backlog_veto"] += 1
                continue
            price = round_up_div(option["listPriceCents"] * quote_pct, 100)
            if price * 100 < reference * 135:
                self.market_counters["margin_veto"] += 1
                continue
            # The new market controller insists that revenue can actually
            # fund a scarcity-adjusted *driver acceptance ladder*, not merely
            # the 100%-reference first bid. This specifically addresses the
            # control's 1.35x floor / 85%-cap driver starvation blindspot.
            required_fee_pct = 110 + min(25, round(12 * scarcity)
                                         + wait_buffer // 30)
            if price * 85 < reference * required_fee_pct:
                self.market_counters["cash_veto"] += 1
                continue
            shadow = round(reference * min(0.22, 0.075 * scarcity
                                           + 0.025 * demand / max(1, free)))
            expected_driver_cost = round_up_div(reference * 120, 100)
            margin = price - expected_driver_cost - shadow
            if margin <= 0:
                self.market_counters["shadow_veto"] += 1
                continue
            # Bounded tail-cost proxy: penalize brittle options, without
            # claiming this is an observed/default probability of lateness.
            tail_cost = round_up_div(reference * max(0, 1000 - slack), 2500)
            net_utility = margin - tail_cost
            if net_utility <= 0:
                self.market_counters["tail_veto"] += 1
                continue
            choices.append((net_utility, option, price))
        if not choices:
            return self._fallback_quote(request)
        _, option, price = max(choices, key=lambda c: (c[0], c[1]["deadline"]))
        self.pending_quotes[request["id"]] = (origin, int(request["respondBy"]) + 20)
        self.market_counters["competitive"] += 1
        return {option["kind"]: price}

    def _fallback_quote(self, request: dict[str, Any]) -> dict[str, int]:
        self.market_counters["fallback"] += 1
        option = request["options"][0]
        return {option["kind"]: min(2**31 - 1, option["listPriceCents"] * 20)}

    def quote(self, request: dict[str, Any]) -> None:
        self.requests[request["id"]] = request
        if self.now >= request["respondBy"] or not request["options"]:
            self.market_counters["expired"] += 1
            return
        origin = request["legs"][0]["pickup"]["placeId"]
        # On SDK reconnect `openRequests` are replayed through quote(). Do not
        # charge a capacity token to a request *against itself* when re-quoted.
        self.pending_quotes.pop(request["id"], None)
        prices = self._market_quote(request)
        self.outbox.append({"type": "quote", "requestId": request["id"],
                            "prices": prices})
        self.demand_history.append((self.now, origin))

    def fees_for(self, order: dict[str, Any], cars: int) -> list[dict[str, int]]:
        if self.level < 7:
            return super().fees_for(order, cars)
        origin = order["legs"][0]["pickup"]["placeId"]
        free = self._free_supply(origin)
        shortage = self._pressure(origin, max(1, free))
        stalled = self._censored_booking_buffer(origin)
        virtual_shortage = max(0, 2 - self._virtual_free_supply(origin))
        uplift = min(20, round(10 * max(0, shortage - 0.3))
                     + stalled // 30 + virtual_shortage * 4)
        urgency = order["id"] in self.urgent
        factors = ([155, 170, 190, 220] if urgency else [100, 110, 120, 135, 150])
        times = ([0, 15, 30, 60] if urgency else [0, 30, 90, 180, 300])
        reference = round_up_div(self.requests[order["id"]]["referenceFeeCents"]
                                 * cars, len(order["legs"]))
        cap = self._remaining_fee_budget(order, cars)
        if cap is not None and cap < reference:
            self.market_counters["underfunded_gig"] += 1
        schedule: list[dict[str, int]] = []
        for gap, factor in zip(times, factors):
            bid = round_up_div(reference * (factor + (0 if urgency else uplift)), 100)
            if cap is not None:
                bid = min(bid, cap)
            if schedule and bid <= schedule[-1]["feeCents"]:
                continue
            schedule.append({"at": self.now + gap, "feeCents": bid})
        return schedule

    def _mark_complete(self, order: dict[str, Any]) -> None:
        identifier = order["id"]
        new = identifier not in self.marked_outcomes and all(
            at is not None for at in order.get("deliveredAt", []))
        super()._mark_complete(order)
        if new and identifier in self.completed:
            self.marked_outcomes.add(identifier)
            self.scored_completions += 1
            self.late_completions += int(max(order["deliveredAt"]) > order["deadline"])

    def handle(self, event: dict[str, Any]) -> None:
        if event.get("seq") in self.seen:
            return
        if event["kind"] in ("order_won", "order_lost"):
            request_id = event.get("requestId") or event.get("order", {}).get("requestId")
            if request_id is None and event["kind"] == "order_won":
                request_id = event["order"]["id"]
            if request_id is not None:
                self.pending_quotes.pop(request_id, None)
        if event["kind"] == "order_cancelled" and event.get("orderId"):
            self.cancelled_won.add(event["orderId"])
        super().handle(event)

    def rejoin(self, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        self.pending_quotes.clear()  # Can't reconstruct accepted quote from raw request.
        self.demand_history.clear()
        self.marked_outcomes.clear()
        self.scored_completions = 0
        self.late_completions = 0
        self.cancelled_won = {event["orderId"] for event in history
                              if event.get("kind") == "order_cancelled"
                              and event.get("orderId")}
        replay_open_ids = {req["id"] for req in snapshot.get("openRequests", [])}
        historic_requests: dict[str, dict[str, Any]] = {}
        settled: set[str] = set()
        for event in history:
            if event.get("kind") == "price_request":
                req = event.get("request", {})
                if req.get("legs"):
                    origin = req["legs"][0]["pickup"]["placeId"]
                    # The sponsor starter re-quotes open requests below; do
                    # not count their demand twice across a reconnect.
                    if req["id"] not in replay_open_ids:
                        self.demand_history.append((int(event["at"]), origin))
                    historic_requests[req["id"]] = req
            if event.get("kind") == "order_lost" and event.get("requestId"):
                settled.add(event["requestId"])
            elif event.get("kind") == "order_won":
                order = event.get("order", {})
                settled.add(event.get("requestId") or order.get("requestId")
                            or order.get("id", ""))
        now = int(snapshot.get("now", self.now))
        # Reconstruct *conservative* virtual reservations on reconnect. Event
        # logs do not prove whether each unresolved request was competitively
        # quoted; conservatively reserving it is safer than over-committing.
        for request_id, req in historic_requests.items():
            expiry = int(req["respondBy"]) + 20
            if request_id not in settled and expiry >= now:
                origin = req["legs"][0]["pickup"]["placeId"]
                self.pending_quotes[request_id] = (origin, expiry)
        super().rejoin(snapshot, history)


if __name__ == "__main__":
    starter.Desk = UberMarketDesk
    starter.main()
