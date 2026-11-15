"""No-key contract checks against the genuine spread-0.1.0 SDK."""
import copy
import os
import unittest
from unittest.mock import patch

from dispatch import SpreadGuardDesk


class FakeClient:
    def map(self):
        return {"roads": [
            {"from": "A", "to": "A", "km": 0, "minutes": 0},
            {"from": "B", "to": "B", "km": 0, "minutes": 0},
            {"from": "A", "to": "B", "km": 145, "minutes": 180},
            {"from": "B", "to": "A", "km": 145, "minutes": 180},
        ]}


class FakeWorld:
    def __init__(self):
        self.client = FakeClient()

    def roster(self):
        return [{"id": f"D{i}", "homePlaceId": "A", "rating": 4.9,
                 "licence": "manual", "completedGigs": 100, "drops": 0}
                for i in range(4)]

    def act(self, actions):
        return [{"ok": True, "id": f"g{i}"} for i, _ in enumerate(actions)]


def request():
    pickup = {"placeId": "A", "privateAddress": False,
              "window": {"from": 550, "to": 4200}, "hours": None}
    delivery = {"placeId": "B", "privateAddress": False,
                "window": {"from": 550, "to": 4200}, "hours": None}
    return {"id": "R1", "dealerId": "dealer1", "batchId": None,
            "arrivedAt": 480, "respondBy": 495,
            "legs": [{"car": {"premium": False, "electric": False,
                              "chargePercent": 100},
                      "pickup": pickup, "delivery": delivery}],
            "options": [
                {"kind": "same_day", "deadline": 900, "listPriceCents": 45000},
                {"kind": "next_day", "deadline": 1850, "listPriceCents": 40000},
                {"kind": "within_3_days", "deadline": 3500,
                 "listPriceCents": 31000},
            ],
            "referenceFeeCents": 12000,
            "note": {"language": "en", "text": "manual gearbox, no plates"}}


def won_order(req):
    return {"id": req["id"], "dealerId": req["dealerId"],
            "option": "next_day", "priceCents": 51200,
            "deadline": 1850, "legs": req["legs"],
            "status": "waiting", "deliveredAt": [None],
            "lastPickupAt": 1450}


class SpreadGuardSDKContract(unittest.TestCase):
    def setUp(self):
        self.world = FakeWorld()
        self.desk = SpreadGuardDesk(self.world, 8, 480)
        self.request = request()

    def test_quote_price_and_driver_fee_schedule(self):
        self.desk.quote(self.request)
        self.assertEqual(self.desk.outbox, [{"type": "quote", "requestId": "R1",
                                             "prices": {"next_day": 51200}}])
        self.desk.handle({"kind": "order_won", "seq": 1, "at": 495,
                          "order": won_order(self.request)})
        posts = [a for a in self.desk.outbox if a["type"] == "post"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["audience"], {"experienced": False,
                                                "manualLicence": True})
        self.assertTrue(posts[0]["stops"][0]["withPlates"])
        schedule = posts[0]["schedule"]
        self.assertEqual(schedule[0]["feeCents"], 18600)
        self.assertLessEqual(len(schedule), 48)
        self.assertEqual([s["at"] for s in schedule],
                         sorted(s["at"] for s in schedule))
        self.assertEqual([s["feeCents"] for s in schedule],
                         sorted(s["feeCents"] for s in schedule))
        self.assertTrue(all(type(s["feeCents"]) is int for s in schedule))

    def test_tight_window_is_not_quoted_at_winning_price(self):
        self.request["options"] = [self.request["options"][0]]
        self.desk.quote(self.request)
        self.assertEqual(self.desk.outbox[0]["prices"]["same_day"], 900000)

    def test_unprofitable_request_is_declined(self):
        self.request["referenceFeeCents"] = 100000
        self.desk.quote(self.request)
        self.assertEqual(self.desk.outbox[0]["prices"]["same_day"], 900000)

    def test_closed_weekend_delivery_waits_until_monday(self):
        place = {"placeId": "B", "privateAddress": False,
                 "window": {"from": 0, "to": 11000},
                 "hours": {"opens": 540, "closes": 1020,
                           "weekdays": [0, 1, 2, 3, 4], "saturday": None}}
        # Saturday, Sunday closed: first accepted dealer delivery is Monday 09:00.
        saturday_noon = 5 * 1440 + 720
        monday_open = 7 * 1440 + 540
        self.assertEqual(self.desk._open_at(place, saturday_noon,
                                             monday_open + 100, None, "delivery"),
                         monday_open)
        self.assertIsNone(self.desk._open_at(place, saturday_noon,
                                             monday_open - 1, None, "delivery"))

    def test_private_trade_in_pickup_may_follow_original_slot(self):
        place = {"placeId": "B", "privateAddress": True,
                 "window": {"from": 990, "to": 1050}, "hours": None}
        self.assertIsNone(self.desk._open_at(place, 1100, 1300, None, "pickup"))
        self.assertEqual(self.desk._open_at(place, 1100, 1300, None, "pickup",
                                            trade_in_customer_pickup=True), 1100)

    def test_drop_then_deadline_rescue_is_repriced(self):
        self.desk.quote(self.request)
        self.desk.handle({"kind": "order_won", "seq": 1, "at": 495,
                          "order": won_order(self.request)})
        post = next(x for x in self.desk.outbox if x["type"] == "post")
        self.desk.carry(post, "g1")
        self.desk.outbox.clear()
        self.desk.handle({"kind": "gig_booked", "seq": 2, "at": 520,
                          "gigId": "g1", "driverId": "D1", "feeCents": 18600})
        self.desk.handle({"kind": "gig_dropped", "seq": 3, "at": 550,
                          "gigId": "g1", "driverId": "D1"})
        self.desk.handle({"kind": "deadline_close", "seq": 4, "at": 560,
                          "orderId": "R1", "lastPickupAt": 1450})
        prices = [x for x in self.desk.outbox if x["type"] == "reprice"]
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0]["gigId"], "g1")
        self.assertEqual(prices[0]["schedule"][0]["feeCents"], 24600)

    def test_trust_once_and_idempotent_rejoin(self):
        order = won_order(self.request)
        won = {"kind": "order_won", "seq": 1, "at": 495, "order": order}
        delivered = {"kind": "delivered", "seq": 2, "at": 1100,
                     "gigId": "g1", "orderId": "R1", "leg": 0,
                     "placeId": "B"}
        self.desk.quote(self.request)
        self.desk.handle(won)
        self.desk.handle(delivered)
        self.desk.handle(delivered)
        self.assertEqual(self.desk.trust["dealer1"], 1)
        snap_order = {**order, "status": "delivered", "deliveredAt": [1100]}
        fresh = SpreadGuardDesk(self.world, 8, 480)
        fresh.rejoin({"openRequests": [], "orders": [snap_order], "gigs": []},
                     [{"kind": "price_request", "seq": 0,
                       "at": 480, "request": self.request}, won, delivered])
        self.assertEqual(fresh.trust["dealer1"], 1)
        self.assertEqual(fresh.outbox, [])

    def test_quote_bound_is_enforced_by_actual_driver_schedule(self):
        req = copy.deepcopy(self.request)
        req["referenceFeeCents"] = 24000
        self.desk.requests[req["id"]] = req
        order = won_order(req)
        order["priceCents"] = 48000
        self.desk.orders[order["id"]] = order
        routine = self.desk.fees_for(order, 1)
        self.assertEqual(routine[0]["feeCents"], 37200)
        self.assertEqual(routine[-1]["feeCents"], 40800)  # 85% of sale
        self.assertEqual([x["feeCents"] for x in routine],
                         sorted(x["feeCents"] for x in routine))
        self.desk.urgent.add(order["id"])
        rescue = self.desk.fees_for(order, 1)
        self.assertEqual(rescue[-1]["feeCents"], 48960)  # 102% of sale
        self.assertEqual([x["feeCents"] for x in rescue],
                         sorted(x["feeCents"] for x in rescue))

    def test_active_bookings_position_and_release(self):
        self.desk.quote(self.request)
        self.desk.handle({"kind": "order_won", "seq": 1, "at": 495,
                          "order": won_order(self.request)})
        post = next(x for x in self.desk.outbox if x["type"] == "post")
        self.desk.carry(post, "g1")
        self.assertEqual(self.desk._driver_count("A"), 4)
        self.desk.handle({"kind": "gig_booked", "seq": 2, "at": 515,
                          "gigId": "g1", "driverId": "D1", "feeCents": 18600})
        self.assertEqual(self.desk._driver_count("A"), 3)
        self.desk.handle({"kind": "picked_up", "seq": 3, "at": 560,
                          "gigId": "g1", "orderId": "R1", "leg": 0,
                          "placeId": "B"})
        self.desk.handle({"kind": "delivered", "seq": 4, "at": 1100,
                          "gigId": "g1", "orderId": "R1", "leg": 0,
                          "placeId": "B"})
        self.desk.now = 1100
        self.assertNotIn("g1", self.desk.active_drivers)
        self.assertEqual(self.desk.driver_places["D1"], "B")
        self.assertEqual(self.desk._driver_count("A"), 3)
        self.desk.now = 1300
        self.assertEqual(self.desk._driver_count("A"), 4)  # stale GPS expires

    def test_paid_and_committed_fees_are_not_double_counted(self):
        req = copy.deepcopy(self.request)
        req["referenceFeeCents"] = 20000
        self.desk.requests["R1"] = req
        order = won_order(req)
        order["priceCents"] = 70000
        order["legs"] = order["legs"] * 2
        order["deliveredAt"] = [None, None]
        self.desk.orders["R1"] = order
        self.desk.posts["g1"] = {"stops": [{"orderId": "R1", "leg": 0}]}
        self.desk.active_drivers["g1"] = "D1"
        self.desk.booked_fees["g1"] = 16000
        first = self.desk._remaining_fee_budget(order, 1)
        self.assertEqual(first, 43500)  # other leg already funded
        self.desk.handle({"seq": 1, "at": 500, "kind": "ledger",
                          "line": {"kind": "driver_fee", "cents": -12000,
                                   "orderId": "R1", "gigId": "g1"}})
        self.assertEqual(self.desk._remaining_fee_budget(order, 1), first)
        self.desk.handle({"seq": 1, "at": 500, "kind": "ledger",
                          "line": {"kind": "driver_fee", "cents": -12000,
                                   "orderId": "R1", "gigId": "g1"}})
        self.assertEqual(self.desk.paid_by_order["R1"], 12000)
        self.desk.handle({"seq": 2, "at": 520, "kind": "ledger",
                          "line": {"kind": "failed_visit", "cents": -5000,
                                   "orderId": "R1", "gigId": "g2"}})
        self.assertEqual(self.desk.expenses_by_order["R1"], 17000)
        self.assertEqual(self.desk._remaining_fee_budget(order, 1), 38500)

    def test_failed_pickup_releases_driver_for_next_order(self):
        self.desk.quote(self.request)
        self.desk.handle({"kind": "order_won", "seq": 1, "at": 495,
                          "order": won_order(self.request)})
        post = next(x for x in self.desk.outbox if x["type"] == "post")
        self.desk.carry(post, "g1")
        self.desk.handle({"kind": "gig_booked", "seq": 2, "at": 515,
                          "gigId": "g1", "driverId": "D1", "feeCents": 18600})
        self.assertEqual(self.desk._driver_count("A"), 3)
        self.desk.handle({"kind": "visit_failed", "seq": 3, "at": 560,
                          "gigId": "g1", "orderId": "R1", "leg": 0,
                          "reason": "not_ready"})
        self.assertNotIn("g1", self.desk.active_drivers)
        self.assertEqual(self.desk._driver_count("A"), 4)

    def test_baseline_switch_retains_original_unbounded_fee_ramp(self):
        with patch.dict(os.environ, {"SPREAD_GUARD_POLICY": "baseline"}):
            baseline = SpreadGuardDesk(self.world, 8, 480)
            baseline.requests["R1"] = self.request
            order = won_order(self.request)
            order["priceCents"] = 15000
            self.assertEqual(baseline.fees_for(order, 1)[-1]["feeCents"],
                             27600)

    def test_rejoin_rebuilds_fees_and_driver_positions(self):
        order = won_order(self.request)
        gig = {"id": "g1", "status": "booked", "driverId": "D1",
               "feeCents": 18600, "postedAt": 500, "stops": [
                   {"orderId": "R1", "leg": 0, "kind": "pickup"}],
               "audience": {"experienced": False, "manualLicence": False},
               "schedule": [{"at": 500, "feeCents": 18600}]}
        self.desk.rejoin({"openRequests": [], "orders": [order], "gigs": [gig],
                          "now": 480,
                          "driverPositions": [{"driverId": "D1", "placeId": "B",
                                               "gigId": "g1"}]},
                         [{"kind": "price_request", "seq": 1, "at": 480,
                           "request": self.request},
                          {"kind": "ledger", "seq": 2, "at": 530,
                           "line": {"kind": "driver_fee", "cents": -4000,
                                    "orderId": "R1", "gigId": "g1"}}])
        self.assertEqual(self.desk.driver_places["D1"], "B")
        self.assertEqual(self.desk.active_drivers["g1"], "D1")
        self.assertEqual(self.desk.paid_by_order["R1"], 4000)
        self.assertEqual(self.desk._driver_count("A"), 3)


if __name__ == "__main__":
    unittest.main()
