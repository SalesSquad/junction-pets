"""Small affected-path checks for next-day quote admission experiments."""
from __future__ import annotations

import unittest

from admission_experiment import AdmissionDesk


def make_desk(extra: int = 120, price: int = 132, surge: int = 0,
              next_day_slack: int = 550, slow_slack: int = 1100):
    desk = object.__new__(AdmissionDesk)
    desk.level = 8
    desk.now = 100
    desk.requests = {}
    desk.roster = []
    desk.outbox = []
    desk.quote_pct = price
    desk.extra_slack = extra
    desk.surge_per_backlog = surge
    desk._local_backlog = lambda _origin: 0
    desk._driver_count = lambda _origin: 20
    desk._booking_delay_buffer = lambda: 0
    desk._slack = lambda _request, opt: (
        next_day_slack if opt["kind"] == "next_day" else slow_slack
    )
    return desk


def request(options: list[str] | None = None):
    prices = {"next_day": 11000, "within_3_days": 8000, "same_day": 10000}
    return {"id": "R1", "respondBy": 115,
            "legs": [{"pickup": {"placeId": "helsinki"}}],
            "referenceFeeCents": 3500,
            "options": [{"kind": kind, "deadline": 2000 if kind == "next_day" else 4000,
                         "listPriceCents": prices[kind]}
                        for kind in (options or ["next_day", "within_3_days"])]}


class AdmissionQuoteTests(unittest.TestCase):
    def test_new_next_day_floor_selects_slower_accepted_option(self):
        desk = make_desk(extra=120)
        desk.quote(request())
        self.assertEqual(desk.outbox[0]["prices"], {"within_3_days": 10560})

    def test_zero_extra_matches_baseline_option_selection(self):
        desk = make_desk(extra=0)
        desk.quote(request())
        self.assertEqual(desk.outbox[0]["prices"], {"next_day": 14520})

    def test_rejected_next_day_still_submits_sponsor_safe_quote(self):
        desk = make_desk(extra=120)
        desk.quote(request(["next_day"]))
        self.assertEqual(desk.outbox[0]["prices"], {"next_day": 220000})

    def test_optional_price_lift_keeps_integer_cents(self):
        desk = make_desk(extra=0, price=139)
        desk.quote(request(["next_day"]))
        self.assertEqual(desk.outbox[0]["prices"], {"next_day": 15290})

    def test_time_exhausted_does_not_quote(self):
        desk = make_desk()
        req = request()
        req["respondBy"] = 100
        desk.quote(req)
        self.assertEqual(desk.outbox, [])

    def test_extra_slack_never_blocks_other_option_type(self):
        desk = make_desk(extra=720, slow_slack=490)
        desk.quote(request(["same_day"]))
        self.assertEqual(desk.outbox[0]["prices"], {"same_day": 13200})


if __name__ == "__main__":
    unittest.main()
