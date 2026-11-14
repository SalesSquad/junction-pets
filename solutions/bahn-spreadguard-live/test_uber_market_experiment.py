"""Contract-level, no-key checks for the opt-in market experiment.

Uses the real spread-0.1.0 starter and synthetic fixtures; *not* a sponsor
practice result, win-rate estimate, or calibrated lateness probability.
"""
from __future__ import annotations

import copy
import random
import unittest

from uber_market_experiment import UberMarketDesk
from test_dispatch import FakeWorld, request, won_order


class UberMarketSDKContract(unittest.TestCase):
    def setUp(self):
        self.desk = UberMarketDesk(FakeWorld(), 8, 480)

    def test_neutral_quote_matches_validated_discovery_anchor(self):
        req = request()
        self.desk.quote(req)
        action = self.desk.outbox.pop()
        self.assertEqual(action["type"], "quote")
        self.assertEqual(action["requestId"], req["id"])
        option = next(x for x in req["options"] if x["kind"] == next(iter(action["prices"])))
        self.assertEqual(next(iter(action["prices"].values())),
                         (option["listPriceCents"] * 132 + 99) // 100)
        self.assertIn(req["id"], self.desk.pending_quotes)

    def test_unknown_driver_supply_is_safe_fallback(self):
        self.desk.roster = []
        req = request()
        self.desk.quote(req)
        price = next(iter(self.desk.outbox[-1]["prices"].values()))
        self.assertGreaterEqual(price, req["options"][0]["listPriceCents"] * 10)
        self.assertNotIn(req["id"], self.desk.pending_quotes)

    def test_virtual_batch_and_demand_raise_price(self):
        quotes = []
        for i in range(8):
            req = request()
            req["id"] = f"R{i}"
            self.desk.quote(req)
            quotes.append(next(iter(self.desk.outbox.pop()["prices"].values())))
        self.assertGreater(quotes[-1], quotes[0])
        self.assertEqual(len(self.desk.pending_quotes), 8)
        self.assertGreater(self.desk._pressure("A", 4), 0.0)

    def test_virtual_bipartite_matching_prevents_double_supply(self):
        # Every driver can reach both neighborhoods, but a driver cannot
        # simultaneously cover a waiting order in A and a new quote in B.
        self.desk.roads[("A", "B")] = 90
        self.assertEqual(self.desk._driver_count("B"), 4)
        for index in range(3):
            order = won_order(request())
            order["id"] = f"waiting-{index}"
            self.desk.orders[order["id"]] = order
        self.assertEqual(self.desk._virtual_free_supply("B"), 1)
        order = won_order(request())
        order["id"] = "waiting-3"
        self.desk.orders[order["id"]] = order
        self.assertEqual(self.desk._virtual_free_supply("B"), 0)

    def test_split_trade_in_reserves_two_virtual_gigs(self):
        self.desk.roads[("A", "B")] = 90
        order = won_order(request())
        order["legs"] = copy.deepcopy(order["legs"]) * 2
        order["deliveredAt"] = [None, None]
        order["legs"][1]["pickup"]["placeId"] = "B"
        self.desk.orders[order["id"]] = order
        self.desk.leg_gigs[order["id"]] = {0: "split-gig-a", 1: "split-gig-b"}
        self.assertEqual(self.desk._virtual_free_supply("B"), 2)
        self.desk.active_drivers["split-gig-b"] = "D0"
        self.assertEqual(self.desk._virtual_free_supply("B"), 2)

    def test_quote_reservation_releases_on_lost_and_expires(self):
        req = request()
        self.desk.quote(req)
        self.assertIn("R1", self.desk.pending_quotes)
        self.desk.handle({"seq": 1, "kind": "order_lost", "at": 485,
                          "requestId": "R1"})
        self.assertNotIn("R1", self.desk.pending_quotes)
        self.desk.quote(req)
        self.assertIn("R1", self.desk.pending_quotes)
        self.desk.now = req["respondBy"] + 21
        self.desk._expire_quotes()
        self.assertNotIn("R1", self.desk.pending_quotes)

    def test_censored_unbooked_offer_raises_tail_buffer(self):
        req = request()
        order = won_order(req)
        self.desk.orders[order["id"]] = order
        self.desk.now = 800
        self.desk.posts["open1"] = {"stops": [
            {"kind": "pickup", "leg": 0, "orderId": order["id"]}],
            "schedule": [{"at": 600, "feeCents": 10000}]}
        self.assertEqual(self.desk._censored_booking_buffer("A"), 125)
        self.desk.active_drivers["open1"] = "D1"
        self.assertEqual(self.desk._censored_booking_buffer("A"), 0)

    def test_service_debt_only_after_samples(self):
        self.desk.scored_completions = 20
        self.desk.late_completions = 3
        self.assertEqual(self.desk._service_debt_buffer(), 0)
        self.desk.scored_completions = 50
        self.desk.late_completions = 5
        self.assertGreater(self.desk._service_debt_buffer(), 0)

    def test_overdue_undelivered_counts_before_completion(self):
        self.desk.scored_completions = 30
        self.desk.late_completions = 0
        self.assertEqual(self.desk._service_debt_buffer(), 0)
        order = won_order(request())
        order["deadline"] = self.desk.now - 1
        self.desk.orders[order["id"]] = order
        self.assertGreater(self.desk._service_debt_buffer(), 0)
        self.desk.cancelled_won.add(order["id"])
        self.assertGreater(self.desk._service_debt_buffer(), 0)

    def test_negative_tail_risk_utility_is_not_accepted(self):
        req = request()
        req["referenceFeeCents"] = 11600
        req["options"] = [{"kind": "next_day", "deadline": 1485,
                            "listPriceCents": 12000}]
        self.assertEqual(self.desk._slack(req, req["options"][0]), 490)
        self.desk.quote(req)
        offer = next(iter(self.desk.outbox[-1]["prices"].values()))
        self.assertEqual(offer, 240000)  # intentionally uncompetitive fallback
        self.assertEqual(self.desk.market_counters["tail_veto"], 1)

    def test_fees_monotone_integer_and_budget_bounded(self):
        req = request()
        self.desk.requests["R1"] = req
        order = won_order(req)
        order["priceCents"] = 44000
        self.desk.orders["R1"] = order
        normal = self.desk.fees_for(order, 1)
        self.assertLessEqual(len(normal), 48)
        self.assertTrue(all(type(x["feeCents"]) is int for x in normal))
        self.assertEqual([x["feeCents"] for x in normal],
                         sorted(x["feeCents"] for x in normal))
        self.assertEqual([x["at"] for x in normal], sorted(x["at"] for x in normal))
        self.assertLessEqual(normal[-1]["feeCents"], order["priceCents"] * 85 // 100)
        self.desk.urgent.add("R1")
        rescue = self.desk.fees_for(order, 1)
        self.assertLessEqual(rescue[-1]["feeCents"], order["priceCents"] * 102 // 100)

    def test_real_sdk_order_won_posts_bounded_driver_offer(self):
        req = request()
        self.desk.quote(req)
        price = next(iter(self.desk.outbox[-1]["prices"].values()))
        self.assertLess(price, 10 * req["options"][0]["listPriceCents"])
        order = won_order(req)
        order["priceCents"] = price
        self.desk.handle({"seq": 1, "kind": "order_won", "at": 495,
                          "order": order})
        posts = [a for a in self.desk.outbox if a["type"] == "post"]
        self.assertEqual(len(posts), 1)
        schedule = posts[0]["schedule"]
        self.assertLessEqual(schedule[-1]["feeCents"], price * 85 // 100)
        self.assertNotIn(req["id"], self.desk.pending_quotes)

    def test_300_seeded_quote_fee_stress_cases(self):
        rng = random.Random(20261114)
        for index in range(300):
            desk = UberMarketDesk(FakeWorld(), 8, 480)
            req = request()
            req["id"] = f"stress-{index}"
            req["referenceFeeCents"] = rng.randint(8000, 49000)
            list_base = rng.randint(18000, 65000)
            for option, multiple in zip(req["options"], (1.2, 1.0, 0.8)):
                option["listPriceCents"] = round(list_base * multiple)
            desk.quote(req)
            action = desk.outbox[-1]
            self.assertEqual(action["requestId"], req["id"])
            option_kind, price = next(iter(action["prices"].items()))
            if price >= list_base * 10:
                continue  # explicit uncompetitive quote
            self.assertGreaterEqual(price * 100, req["referenceFeeCents"] * 135)
            self.assertGreaterEqual(price * 85, req["referenceFeeCents"] * 100)
            order = won_order(req)
            order["option"] = option_kind
            order["priceCents"] = price
            desk.orders[req["id"]] = order
            steps = desk.fees_for(order, 1)
            self.assertTrue(steps)
            self.assertLessEqual(len(steps), 48)
            self.assertEqual([step["feeCents"] for step in steps],
                             sorted(step["feeCents"] for step in steps))
            self.assertLessEqual(steps[-1]["feeCents"], price * 85 // 100)

    def test_underfunded_gig_counted_not_silent(self):
        req = request()
        self.desk.requests["R1"] = req
        order = won_order(req)
        order["priceCents"] = 9000
        self.desk.orders["R1"] = order
        self.desk.fees_for(order, 1)
        self.assertEqual(self.desk.market_counters["underfunded_gig"], 1)

    def test_late_outcome_is_idempotent_and_dedicated_debt(self):
        req = request()
        order = won_order(req)
        order["deliveredAt"] = [1900]  # deadline 1850, late
        self.desk._mark_complete(order)
        self.desk._mark_complete(order)
        self.assertEqual(self.desk.scored_completions, 1)
        self.assertEqual(self.desk.late_completions, 1)

    def test_renewed_historical_rejoin_does_not_double_count(self):
        req = request()
        order = won_order(req)
        self.desk.quote(req)
        self.desk.rejoin({"openRequests": [], "orders": [order], "gigs": [],
                          "now": 480, "driverPositions": []}, [
                              {"kind": "price_request", "seq": 0, "at": 480,
                               "request": req},
                              {"kind": "order_won", "seq": 1, "at": 495,
                               "order": order},
                          ])
        self.assertEqual(self.desk.scored_completions, 0)
        self.assertEqual(len(self.desk.demand_history), 1)
        # The historical order_won conclusively settles this reservation.
        # Unsettled recent requests are tested in the separate replay case.
        self.assertEqual(len(self.desk.pending_quotes), 0)

    def test_sdk_rejoin_open_request_demand_count_once(self):
        req = request()
        self.desk.rejoin({"openRequests": [req], "orders": [], "gigs": [],
                          "now": 480, "driverPositions": []}, [
                              {"kind": "price_request", "seq": 0, "at": 480,
                               "request": req}
                          ])
        self.assertEqual(len(self.desk.demand_history), 1)
        self.assertIn("R1", self.desk.pending_quotes)
        self.assertEqual(len([a for a in self.desk.outbox
                              if a["type"] == "quote"]), 1)


if __name__ == "__main__":
    unittest.main()
