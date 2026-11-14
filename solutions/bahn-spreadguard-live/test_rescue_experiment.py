"""No-key official-SDK contracts for the opt-in Bahn rescue experiment.

These fixtures do NOT establish a 97% service rate or a sponsor-world score.
"""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

from rescue_experiment import RescueDesk, OFFER_DAY_LIMIT
from test_dispatch import FakeWorld, request, won_order


class UniqueWorld(FakeWorld):
    def __init__(self):
        super().__init__()
        self.next_id = 0
        self.sent = []

    def act(self, actions):
        results = []
        for action in actions:
            self.sent.append(action)
            self.next_id += 1
            results.append({"ok": True, "id": f"g{self.next_id}"})
        return results


class RescueSDKContract(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"SPREAD_RESCUE_MODE": "full"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.world = UniqueWorld()
        self.desk = RescueDesk(self.world, 8, 480)
        self.req = request()

    def _win(self, urgent_pickup=False):
        req = copy.deepcopy(self.req)
        self.desk.requests[req["id"]] = req
        order = won_order(req)
        if urgent_pickup:
            order["lastPickupAt"] = self.desk.now + 250
        self.desk.handle({"kind": "order_won", "seq": 1, "at": self.desk.now,
                          "order": order})
        return order

    def test_discovery_control_keeps_original_policy(self):
        with patch.dict(os.environ, {"SPREAD_RESCUE_MODE": "discovery"}):
            control = RescueDesk(self.world, 8, 480)
            control.requests["R1"] = self.req
            order = won_order(self.req)
            self.assertEqual(control.fees_for(order, 1)[0]["feeCents"], 12000)
            control.handle({"kind": "order_won", "seq": 1, "at": 480,
                            "order": order})
            self.assertEqual(len([x for x in control.outbox if x["type"] == "offer"]), 0)
            self.assertEqual(len([x for x in control.outbox if x["type"] == "post"]), 1)

    def test_neutral_fees_keep_discovery_baseline(self):
        self.desk.requests["R1"] = self.req
        normal = self.desk.fees_for(won_order(self.req), 1)
        self.assertEqual([x["feeCents"] for x in normal],
                         [12000, 13200, 14400, 16200, 18000])

    def test_urgent_fee_is_targeted_monotone_and_bounded(self):
        self.desk.requests["R1"] = self.req
        order = won_order(self.req)
        order["lastPickupAt"] = 700
        fees = self.desk.fees_for(order, 1)
        self.assertEqual(fees[0]["feeCents"], 12000)  # cheap 10-minute offer window
        self.assertEqual(fees[1]["feeCents"], 17400)
        self.assertLessEqual(fees[-1]["feeCents"], order["priceCents"] * 85 // 100)
        self.assertEqual([x["feeCents"] for x in fees],
                         sorted(x["feeCents"] for x in fees))
        self.assertTrue(all(isinstance(x["feeCents"], int) and x["feeCents"] > 0
                            for x in fees))
        self.assertLessEqual(len(fees), 48)

    def test_target_offer_resolves_new_post_id_immediately(self):
        order = self._win(urgent_pickup=True)
        posts = [x for x in self.world.sent if x["type"] == "post"]
        offers = [x for x in self.desk.outbox if x["type"] == "offer"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(len(offers), 2)
        self.assertIn(offers[0]["gigId"], self.desk.posts)
        self.assertLessEqual(offers[0]["feeCents"], order["priceCents"] * 85 // 100)
        self.assertEqual(offers[0]["feeCents"], 13200)
        self.assertEqual(offers[1]["feeCents"], 13800)

    def test_manual_premium_audience_and_candidate_filter(self):
        self.desk.roster[0]["rating"] = 4.3
        self.desk.roster[1]["completedGigs"] = 10
        self.desk.roster[2]["licence"] = "automatic_only"
        self.req["legs"][0]["car"]["premium"] = True
        self._win(urgent_pickup=True)
        offers = [x for x in self.desk.outbox if x["type"] == "offer"]
        self.assertEqual([o["driverId"] for o in offers], ["D3"])

    def test_night_suppresses_offers(self):
        self.desk.now = 1380  # 23:00 world time, unopened until 07:00.
        self._win(urgent_pickup=True)
        self.assertEqual(len([x for x in self.desk.outbox if x["type"] == "offer"]), 0)

    def test_day_offer_budget_and_dedup(self):
        self.desk.roster = self.desk.roster[:1]
        for i in range(OFFER_DAY_LIMIT + 2):
            # The next offer is only considered after the previous 10-minute
            # invitation expired. A driver must not receive two concurrently.
            self.desk.now = 480 + 11 * i
            req = copy.deepcopy(self.req)
            req["id"] = f"R{i}"
            order = won_order(req)
            order["id"] = req["id"]
            order["lastPickupAt"] = self.desk.now + 250
            self.desk.requests[order["id"]] = req
            self.desk.orders[order["id"]] = order
            gid = f"manual-gig-{i}"
            self.desk.carry({"type": "post", "stops": [
                {"orderId": order["id"], "leg": 0, "kind": "pickup"},
                {"orderId": order["id"], "leg": 0, "kind": "delivery"}],
                "audience": {"experienced": False, "manualLicence": False},
                "schedule": [{"at": self.desk.now, "feeCents": 12000}]}, gid)
            self.desk._maybe_offer(gid)
            self.desk._maybe_offer(gid)
        offers = [x for x in self.desk.outbox if x["type"] == "offer"]
        self.assertEqual(len(offers), OFFER_DAY_LIMIT)
        self.assertEqual(self.desk.offer_day_counts[("D0", 0)], OFFER_DAY_LIMIT)

    def test_offer_blocked_when_fee_budget_exhausted(self):
        order = self._win(urgent_pickup=True)
        gid = next(iter(self.desk.posts))
        self.desk.outbox.clear()
        self.desk.pending_offers.clear()
        self.desk.offer_attempts.clear()
        order["priceCents"] = 4000  # even posted fee exceeds 85% cash cap
        self.desk._maybe_offer(gid)
        self.assertFalse([x for x in self.desk.outbox if x["type"] == "offer"])

    def test_drop_reprices_existing_live_gig_once(self):
        self._win(urgent_pickup=True)
        gid = next(iter(self.desk.posts))
        self.desk.outbox.clear()
        self.desk.handle({"kind": "gig_booked", "seq": 2, "at": 495,
                          "gigId": gid, "driverId": "D0", "feeCents": 17400})
        self.desk.handle({"kind": "gig_dropped", "seq": 3, "at": 505,
                          "gigId": gid, "driverId": "D0"})
        reprices = [x for x in self.desk.outbox if x["type"] == "reprice"]
        self.assertEqual(len(reprices), 1)
        self.assertEqual(reprices[0]["gigId"], gid)
        self.assertLessEqual(reprices[0]["schedule"][-1]["feeCents"],
                             self.desk.orders["R1"]["priceCents"] * 85 // 100)
        self.desk.handle({"kind": "gig_dropped", "seq": 3, "at": 505,
                          "gigId": gid, "driverId": "D0"})
        self.assertEqual(len([x for x in self.desk.outbox if x["type"] == "reprice"]), 1)

    def test_failed_visit_reuses_sdk_retry_and_privacy_constraints(self):
        self._win()
        self.desk.send()  # neutral-risk posts use normal starter batching
        gid = next(iter(self.desk.posts))
        self.desk.outbox.clear()
        self.desk.handle({"kind": "gig_booked", "seq": 2, "at": 520,
                          "gigId": gid, "driverId": "D0", "feeCents": 12000})
        self.desk.now = 555  # the official runner advances desk.now first
        self.desk.handle({"kind": "visit_failed", "seq": 3, "at": 555,
                          "gigId": gid, "orderId": "R1", "leg": 0,
                          "reason": "not_ready"})
        posts = [x for x in self.world.sent if x["type"] == "post"]
        self.assertEqual(len(posts), 2)
        self.assertGreaterEqual(posts[-1]["stops"][0]["window"]["from"], 675)
        self.assertEqual(self.desk.failures["R1"], 1)

    def test_declined_offer_tries_another_candidate(self):
        self._win(urgent_pickup=True)
        first_offers = [x for x in self.desk.outbox if x["type"] == "offer"]
        self.assertEqual(len(first_offers), 2)
        self.desk.outbox.clear()
        first = first_offers[0]
        self.desk.handle({"kind": "offer_answered", "seq": 2, "at": 490,
                          "gigId": first["gigId"], "driverId": first["driverId"],
                          "answer": "declined"})
        next_offers = [x for x in self.desk.outbox if x["type"] == "offer"]
        self.assertEqual(len(next_offers), 1)
        self.assertNotEqual(next_offers[0]["driverId"], first["driverId"])

    def test_rejoin_fails_closed_on_offer_quota_for_current_day(self):
        order = won_order(self.req)
        self.desk.rejoin({"openRequests": [], "orders": [order], "gigs": [],
                          "now": 480, "driverPositions": []}, [
                              {"kind": "price_request", "seq": 0,
                               "at": 480, "request": self.req}])
        self.assertEqual(self.desk._offer_closed_day, 0)
        self.desk.orders["R1"] = order
        self.desk.carry({"type": "post", "stops": [
            {"orderId": "R1", "leg": 0, "kind": "pickup"},
            {"orderId": "R1", "leg": 0, "kind": "delivery"}],
            "audience": {"experienced": False, "manualLicence": False},
            "schedule": [{"at": 480, "feeCents": 12000}]}, "g1")
        self.desk._maybe_offer("g1")
        self.assertFalse([x for x in self.desk.outbox if x["type"] == "offer"])

    def test_rush_curve_available_as_ablation(self):
        with patch.dict(os.environ, {"SPREAD_RESCUE_CURVE": "rush"}):
            desk = RescueDesk(self.world, 8, 480)
            desk.requests["R1"] = self.req
            order = won_order(self.req)
            order["lastPickupAt"] = 700
            self.assertEqual(desk.fees_for(order, 1)[0]["feeCents"], 17400)

    def test_sponsor_refused_offer_keeps_daily_quota(self):
        self._win(urgent_pickup=True)
        first = next(x for x in self.desk.outbox if x["type"] == "offer")
        driver = first["driverId"]
        quota_before = self.desk.offer_day_counts[(driver, 0)]
        self.desk.outbox.clear()
        self.desk.read_results([first], [{"ok": False, "reason": "not_available"}])
        self.assertEqual(self.desk.offer_day_counts[(driver, 0)], quota_before)
        self.assertIn((first["gigId"], driver), self.desk.offer_attempts)

    def test_no_show_blacklists_driver_and_preserves_no_urgent_budget(self):
        self._win(urgent_pickup=True)
        gid = next(iter(self.desk.posts))
        self.desk.outbox.clear()
        self.desk.handle({"kind": "gig_booked", "seq": 2, "at": 500,
                          "gigId": gid, "driverId": "D0", "feeCents": 12000})
        self.desk.now = 510
        self.desk.handle({"kind": "no_show", "seq": 3, "at": 510,
                          "gigId": gid, "driverId": "D0"})
        self.assertNotIn("R1", self.desk.urgent)
        self.assertIn("D0", self.desk.bad_driver_by_order["R1"])
        self.assertTrue([a for a in self.desk.outbox if a["type"] == "reprice"])
        self.assertTrue(all(a["driverId"] != "D0" for a in self.desk.outbox
                            if a["type"] == "offer"))


if __name__ == "__main__":
    unittest.main()
