#!/usr/bin/env python3
"""Opt-in Bahn 97 rescue experiment using the official Spread 0.1.0 Desk.

The five-world Discovery benchmark remains untouched. This controller keeps
its quote policy, adds bounded deadline-sensitive fees, and uses the official
``offer`` invitation API (not driver assignment). It is NOT 97%-qualified.
Run an unranked practice comparison only if sponsor-world slots are available.
"""
from __future__ import annotations

import atexit
import os
from collections import Counter, defaultdict
from typing import Any

from spread import starter

from discovery_experiment import DiscoveryDesk
from dispatch import DAY, DRIVER_POSITION_TTL_MINUTES, UNKNOWN_ROAD_MINUTES, round_up_div


RESCUE_COUNTS: Counter[str] = Counter()
OFFER_DAY_LIMIT = 2  # One below the sponsor hard cap of 3, including uncertainty.
OFFER_GIG_LIMIT = 2  # Sponsor allows 3 simultaneous; keep headroom for races.
OFFER_TTL_MINUTES = 10
OFFER_OPEN_MINUTE = 7 * 60
OFFER_CLOSE_MINUTE = 22 * 60 + 45  # Last invitation can finish before 23:00.
MAX_SWEEP_OFFERS = 4


@atexit.register
def report_rescue_aggregate() -> None:
    # Only aggregate decision counts, never partner request/customer payloads.
    print("RESCUE_DECISIONS=" + repr(dict(sorted(RESCUE_COUNTS.items()))), flush=True)


class RescueDesk(DiscoveryDesk):
    """Sponsor-safe targeted invitations and bounded failed-booking rescue.

    Modes: discovery (unchanged control), fees (driver fee schedule only),
    full (fees + targeted offers and drop repricing). Default is *full* because
    selecting this separate script is the opt-in; dispatch.py is unchanged.
    """

    def __init__(self, world: Any, level: int, now: int):
        super().__init__(world, level, now)
        self.rescue_mode = os.getenv("SPREAD_RESCUE_MODE", "full")
        if self.rescue_mode not in ("discovery", "fees", "full"):
            raise ValueError("SPREAD_RESCUE_MODE must be discovery, fees or full")
        self.rescue_curve = os.getenv("SPREAD_RESCUE_CURVE", "offer_first")
        if self.rescue_curve not in ("offer_first", "rush"):
            raise ValueError("SPREAD_RESCUE_CURVE must be offer_first or rush")
        self.failures: Counter[str] = Counter()
        self.failure_reasons: dict[str, str] = {}
        self.drops: Counter[str] = Counter()
        self.offer_attempts: set[tuple[str, str]] = set()  # (gig, driver)
        self.offer_day_counts: Counter[tuple[str, int]] = Counter()
        self.pending_offers: dict[str, dict[str, int]] = defaultdict(dict)
        self.bad_driver_by_order: dict[str, set[str]] = defaultdict(set)
        self._rejoining = False
        self._offer_closed_day: int | None = None

    def _pickup_budget(self, order: dict[str, Any]) -> int:
        """Time until the sponsor's actual last feasible pickup, in minutes."""
        cutoff = order.get("lastPickupAt")
        if isinstance(cutoff, int):
            return cutoff - self.now
        return order["deadline"] - self.now - 420  # older fixture fallback

    def _risk_band(self, order: dict[str, Any]) -> int:
        if self.rescue_mode == "discovery" or self.level < 7:
            return 0
        minutes = self._pickup_budget(order)
        # Once the pickup cutoff has passed, an early bidding war cannot save
        # on-time service. Keep the SDK's official deadline warning policy.
        if minutes <= 0:
            return 0
        band = 2 if minutes <= 360 else 1 if minutes <= 900 else 0
        if len(self.booking_delays) >= 6:
            recent = sorted(self.booking_delays)
            p75 = recent[(3 * (len(recent) - 1)) // 4]
            if minutes <= p75 + 150:
                band = max(band, 2)
        if self.failures[order["id"]] or self.drops[order["id"]]:
            band = max(band, 1)
        # Licence/plates failures are handled by the SDK's retry audience and
        # stop flags; overpaying cannot repair a missing credential or plate.
        # No speculative charge for a car the dealer has not yet prepared.
        if self.failure_reasons.get(order["id"]) in ("not_ready", "closed"):
            band = min(band, 1)
        return band

    def fees_for(self, order: dict[str, Any], cars: int) -> list[dict[str, int]]:
        if self.rescue_mode == "discovery" or self.level < 7:
            return super().fees_for(order, cars)
        band = self._risk_band(order)
        if band == 0 and order["id"] not in self.urgent:
            return super().fees_for(order, cars)

        ref = round_up_div(self.requests[order["id"]]["referenceFeeCents"] * cars,
                           len(order["legs"]))
        if order["id"] in self.urgent:
            factors, delays = (155, 175, 195, 220), (0, 10, 30, 60)
        elif self.rescue_curve == "rush" or (self.drops[order["id"]]
                                               and self.failure_reasons.get(order["id"]) not in ("not_ready", "closed")):
            # Recover a reopened, unexpectedly abandoned pickup promptly.
            factors, delays = ((145, 165, 185, 205, 220), (0, 10, 25, 60, 120)) if band >= 2 else (
                (120, 135, 150, 170, 185), (0, 15, 45, 90, 180))
        elif band >= 2:
            # Offer-first auction: buy a 10-minute cheap targeted response
            # before exposing every app driver to the expensive public ramp.
            factors, delays = (100, 145, 165, 190, 210), (0, 15, 30, 60, 120)
        else:
            factors, delays = (100, 115, 135, 155, 170), (0, 20, 45, 90, 180)

        cap = self._remaining_fee_budget(order, cars)
        steps: list[dict[str, int]] = []
        for pct, offset in zip(factors, delays):
            cents = round_up_div(ref * pct, 100)
            if cap is not None:
                cents = min(cents, cap)
            if steps and cents <= steps[-1]["feeCents"]:
                continue
            steps.append({"at": self.now + offset, "feeCents": max(1, cents)})
        return steps

    @staticmethod
    def _fee_now(schedule: list[dict[str, int]], now: int) -> int:
        amount = schedule[0]["feeCents"] if schedule else 0
        for step in schedule:
            if step["at"] <= now:
                amount = step["feeCents"]
        return amount

    def _gig_context(self, gig_id: str) -> tuple[dict[str, Any], dict[str, Any], int] | None:
        post = self.posts.get(gig_id)
        if not post or not post.get("stops") or gig_id in self.booked:
            return None
        order_id = post["stops"][0]["orderId"]
        order = self.orders.get(order_id)
        if not order or order.get("status") in ("cancelled", "delivered"):
            return None
        pickups = [s for s in post["stops"] if s["kind"] == "pickup"]
        if not pickups:
            return None
        if not all(self.leg_gigs.get(order_id, {}).get(s["leg"]) == gig_id
                   and order["deliveredAt"][s["leg"]] is None for s in pickups):
            return None
        return order, post, len(pickups)

    def _reprice_reopened(self, gig_id: str) -> None:
        context = self._gig_context(gig_id)
        if context is None or self._pickup_budget(context[0]) <= 0:
            return
        order, post, cars = context
        if any(a.get("type") in ("reprice", "withdraw") and a.get("gigId") == gig_id
               for a in self.outbox):
            return
        schedule = self.fees_for(order, cars)
        if not schedule:
            return
        previous = post.get("schedule", [])
        floor = self._fee_now(previous, self.now)
        cap = self._remaining_fee_budget(order, cars)
        if cap is not None and floor > cap:
            RESCUE_COUNTS["reprice_budget_block"] += 1
            return
        # The new offer must never lower what an open gig already pays now.
        for step in schedule:
            step["feeCents"] = max(floor, step["feeCents"])
        if previous and schedule[-1]["feeCents"] <= floor:
            return
        self.outbox.append({"type": "reprice", "gigId": gig_id,
                            "schedule": schedule})
        RESCUE_COUNTS["drop_reprice"] += 1

    def _candidate_drivers(self, gig_id: str) -> list[dict[str, Any]]:
        context = self._gig_context(gig_id)
        if context is None:
            return []
        order, post, _ = context
        pickup = next(s for s in post["stops"] if s["kind"] == "pickup")
        delivery = next(s for s in reversed(post["stops"]) if s["kind"] == "delivery")
        origin = order["legs"][pickup["leg"]]["pickup"]["placeId"]
        destination = order["legs"][delivery["leg"]]["delivery"]["placeId"]
        active = set(self.active_drivers.values())
        disqualified = self.bad_driver_by_order.get(order["id"], set())
        audience = post["audience"]
        candidates: list[tuple[tuple[float, int, str], dict[str, Any]]] = []
        for driver in self.roster:
            driver_id = driver["id"]
            if driver_id in active or driver_id in disqualified:
                continue
            if audience.get("manualLicence") and driver.get("licence") != "manual":
                continue
            if (audience.get("experienced") and
                    (driver.get("rating", 0) < 4.8 or driver.get("completedGigs", 0) < 50)):
                continue
            observed = self.driver_place_observed_at.get(driver_id, -10000)
            current = (self.driver_places.get(driver_id, driver["homePlaceId"])
                       if 0 <= self.now - observed <= DRIVER_POSITION_TTL_MINUTES
                       else driver["homePlaceId"])
            deadhead = self.roads.get((current, origin), UNKNOWN_ROAD_MINUTES)
            if deadhead > 240:
                continue
            homebound = self.roads.get((destination, driver["homePlaceId"]),
                                       UNKNOWN_ROAD_MINUTES)
            # Explicit directed-route opportunity cost; not a true acceptance
            # probability. A reliable, shorter-reposition driver ranks higher.
            reliability_penalty = driver.get("drops", 0) * 12 / max(
                1, driver.get("completedGigs", 0))
            score = (deadhead + min(420, homebound) * 0.25
                     + 90 * reliability_penalty
                     - 20 * float(driver.get("rating", 0)))
            candidates.append(((score, deadhead, driver_id), driver))
        return [d for _, d in sorted(candidates, key=lambda e: e[0])]

    def _expire_local_offers(self) -> None:
        for gig_id in list(self.pending_offers):
            self.pending_offers[gig_id] = {
                driver: expires for driver, expires in self.pending_offers[gig_id].items()
                if expires > self.now
            }
            if not self.pending_offers[gig_id]:
                del self.pending_offers[gig_id]

    def _maybe_offer(self, gig_id: str, preferred_driver: str | None = None) -> None:
        if (self.rescue_mode != "full" or self._rejoining
                or self._offer_closed_day == self.now // DAY or self.level < 7):
            return
        local_clock = self.now % DAY
        if not OFFER_OPEN_MINUTE <= local_clock < OFFER_CLOSE_MINUTE:
            return
        self._expire_local_offers()
        context = self._gig_context(gig_id)
        if context is None:
            return
        order, post, cars = context
        band = self._risk_band(order)
        if band == 0:
            return  # Preserve driver invitation quota for at-risk pickups.
        if self._pickup_budget(order) <= 0:
            return
        current = len(self.pending_offers.get(gig_id, {}))
        limit = OFFER_GIG_LIMIT if band >= 2 else 1
        if current >= limit:
            return
        cap = self._remaining_fee_budget(order, cars)
        pending_reprice = next((a for a in self.outbox if a.get("type") == "reprice"
                                and a.get("gigId") == gig_id), None)
        base = self._fee_now((pending_reprice or post).get("schedule", []), self.now)
        ref = round_up_div(self.requests[order["id"]]["referenceFeeCents"] * cars,
                           len(order["legs"]))
        ranked = self._candidate_drivers(gig_id)
        if preferred_driver is not None:
            ranked.sort(key=lambda d: d["id"] != preferred_driver)
        for driver in ranked:
            if current >= limit:
                break
            driver_id = driver["id"]
            key = (gig_id, driver_id)
            if key in self.offer_attempts:
                continue
            if any(driver_id in pending for pending in self.pending_offers.values()):
                continue
            if self.offer_day_counts[(driver_id, self.now // DAY)] >= OFFER_DAY_LIMIT:
                continue
            if any(a["type"] == "offer" and a["gigId"] == gig_id and a["driverId"] == driver_id
                   for a in self.outbox):
                continue
            # First invitation is economical; the second, only for imminent
            # pickups, buys a modest acceptance premium. Viewed gigs get the
            # currently public fee because interest is already demonstrated.
            percent = (100 if preferred_driver is not None else
                       110 if band >= 2 and current == 0 else
                       115 if band >= 2 else 100)
            requested = max(base, round_up_div(ref * percent, 100))
            amount = min(requested, cap) if cap is not None else requested
            if amount < max(1, base):
                RESCUE_COUNTS["offer_budget_block"] += 1
                return
            # Reserve quota at intent, including a refused/uncertain action.
            self.offer_day_counts[(driver_id, self.now // DAY)] += 1
            self.offer_attempts.add(key)
            self.pending_offers[gig_id][driver_id] = self.now + OFFER_TTL_MINUTES
            self.outbox.append({"type": "offer", "gigId": gig_id,
                                "driverId": driver_id, "feeCents": amount})
            RESCUE_COUNTS["targeted_offer"] += 1
            current += 1

    def _sweep_offers(self) -> None:
        """Use existing sponsor event wakes; never invent a simulator tick.

        WAKE_ON also includes offer answers/drop events for the opt-in main()
        runner. The deterministic sweep is bounded to 4 invitations per wake.
        """
        if self.rescue_mode != "full" or self._rejoining:
            return
        before = len([a for a in self.outbox if a.get("type") == "offer"])
        waiting = sorted((order for order in self.orders.values()
                          if order.get("status") in ("waiting", "booked")
                          and 0 < self._pickup_budget(order) <= 900),
                         key=lambda o: (self._pickup_budget(o), o["id"]))
        for order in waiting:
            for gig_id in self.gigs_of(order["id"]):
                self._maybe_offer(gig_id)
                count = len([a for a in self.outbox if a.get("type") == "offer"])
                if count - before >= MAX_SWEEP_OFFERS:
                    return

    def _clear_offer(self, gig_id: str, driver_id: str | None = None) -> None:
        if driver_id is None:
            self.pending_offers.pop(gig_id, None)
            self.outbox = [a for a in self.outbox
                           if not (a.get("type") == "offer" and a.get("gigId") == gig_id)]
        else:
            self.pending_offers.get(gig_id, {}).pop(driver_id, None)
            if not self.pending_offers.get(gig_id):
                self.pending_offers.pop(gig_id, None)

    def read_results(self, actions: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
        super().read_results(actions, results)
        for action, result in zip(actions, results):
            if action["type"] == "post" and result.get("ok") is True:
                self._maybe_offer(result["id"])
            elif action["type"] == "reprice" and result.get("ok") is True:
                gig = self.posts.get(action["gigId"])
                if gig:
                    gig["schedule"] = action["schedule"]
            elif action["type"] == "offer" and result.get("ok") is False:
                self._clear_offer(action["gigId"], action["driverId"])
                RESCUE_COUNTS["offer_refused"] += 1
                self._maybe_offer(action["gigId"])

    def handle(self, event: dict[str, Any]) -> None:
        if event["seq"] in self.seen:
            return
        kind = event["kind"]
        if kind == "visit_failed":
            self.failures[event["orderId"]] += 1
            self.failure_reasons[event["orderId"]] = event["reason"]
        elif kind in ("gig_dropped", "no_show"):
            post = self.posts.get(event["gigId"])
            if post:
                order_id = post["stops"][0]["orderId"]
                self.drops[order_id] += 1
                if event.get("driverId"):
                    self.bad_driver_by_order[order_id].add(event["driverId"])
        super().handle(event)
        if self.rescue_mode != "full":
            return
        if kind in ("order_won", "order_changed", "visit_failed", "gig_expired"):
            order_id = (event["order"]["id"] if kind in ("order_won", "order_changed")
                        else event.get("orderId"))
            if kind == "gig_expired":
                old = self.posts.get(event["gigId"])
                order_id = old["stops"][0]["orderId"] if old else None
            if order_id and (order := self.orders.get(order_id)) and self._risk_band(order) >= 1:
                # Force the SDK to resolve post -> gigId before this event ends.
                # Its native send()/read_results() handles action validation.
                self.send_post_of(order_id)
        elif kind in ("gig_dropped", "no_show"):
            # An offer may survive a transient booking. Keep its in-flight
            # quota until answer/expiry, even if we discard unsent invitations.
            self._reprice_reopened(event["gigId"])
            self._maybe_offer(event["gigId"])
        elif kind == "gig_viewed":
            self._maybe_offer(event["gigId"], preferred_driver=event["driverId"])
        elif kind == "offer_answered":
            self._clear_offer(event["gigId"], event["driverId"])
            if event["answer"] != "accepted":
                self._maybe_offer(event["gigId"])
        elif kind == "gig_booked":
            self.outbox = [a for a in self.outbox if not (
                a.get("type") == "offer" and a.get("gigId") == event["gigId"])]
        elif kind == "order_cancelled":
            for item in event.get("gigs", []):
                self._clear_offer(item["gigId"])
        self._sweep_offers()

    def rejoin(self, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        # The sponsor snapshot contains no in-flight offer/quota ledger. Never
        # reconstruct an imaginary empty quota and issue duplicate invitations.
        self._rejoining = True
        self._offer_closed_day = snapshot["now"] // DAY
        gig_orders = {gig["id"]: gig["stops"][0]["orderId"]
                      for gig in snapshot["gigs"] if gig.get("stops")}
        for event in history:
            if event["kind"] == "visit_failed":
                self.failures[event["orderId"]] += 1
                self.failure_reasons[event["orderId"]] = event["reason"]
            elif event["kind"] in ("gig_dropped", "no_show"):
                order_id = gig_orders.get(event["gigId"])
                if order_id:
                    self.drops[order_id] += 1
                    if event.get("driverId"):
                        self.bad_driver_by_order[order_id].add(event["driverId"])
        try:
            super().rejoin(snapshot, history)
        finally:
            self._rejoining = False


if __name__ == "__main__":
    starter.Desk = RescueDesk
    # A viewed gig, offer answer or dropped booking is actionable NOW; waiting
    # until the next unrelated price request wastes the 10-minute offer window.
    starter.WAKE_ON = list(dict.fromkeys([*starter.WAKE_ON, "gig_viewed",
                                       "offer_answered", "gig_dropped", "no_show"]))
    starter.main()
