"""Minimal official-SDK fixture contract for the isolated fee-discovery trial."""
import copy
import unittest

from discovery_experiment import DiscoveryDesk
from test_dispatch import FakeWorld, request, won_order


class DiscoverySmoke(unittest.TestCase):
    def test_recovers_high_reference_fee_with_long_deadline(self):
        world = FakeWorld()
        desk = DiscoveryDesk(world, 8, 480)
        req = copy.deepcopy(request())
        req["referenceFeeCents"] = 24000
        desk.quote(req)
        quote = desk.outbox.pop()
        self.assertEqual(quote["type"], "quote")
        self.assertNotEqual(next(iter(quote["prices"].values())),
                            req["options"][0]["listPriceCents"] * 20)
        order = won_order(req)
        order["priceCents"] = next(iter(quote["prices"].values()))
        fees = desk.fees_for(order, 1)
        self.assertEqual(fees[0]["feeCents"], 24000)
        self.assertLessEqual(fees[-1]["feeCents"], order["priceCents"] * 85 // 100)


if __name__ == "__main__":
    unittest.main()
