"""No-key contract checks against the genuine spread-0.1.0 SDK."""
import copy
import unittest

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


if __name__ == "__main__":
    unittest.main()
