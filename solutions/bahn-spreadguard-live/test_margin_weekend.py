#!/usr/bin/env python3
"""Offline checks for the 15 November margin additions (no network, no world).

    python test_margin_weekend.py
"""
from __future__ import annotations

from types import SimpleNamespace

import ai_decide
from margin_experiment import DAY, MarginDesk


def weekend(now: int, deadline: int) -> int:
    return MarginDesk._weekend_minutes(SimpleNamespace(now=now), deadline)


def test_weekend_minutes() -> None:
    fri_15 = 4 * DAY + 15 * 60
    mon_17 = 7 * DAY + 17 * 60
    assert weekend(fri_15, mon_17) == 2 * DAY + 7 * 60          # Sat 00:00 .. Mon 07:00
    assert weekend(fri_15, 5 * DAY + 600) == 600                 # deadline Saturday 10:00
    assert weekend(2 * DAY, 4 * DAY) == 0                        # Wed .. Fri, no weekend
    assert weekend(6 * DAY + 600, mon_17) == DAY - 600 + 7 * 60  # from Sunday 10:00
    assert weekend(7 * DAY + 600, 8 * DAY) == 0                  # Monday after 07:00


def service(now: int, orders: list[dict]) -> tuple[int, int]:
    return MarginDesk._service(SimpleNamespace(now=now, orders={str(i): o for i, o in enumerate(orders)}))


def test_service_counts_overdue_as_late() -> None:
    orders = [{"deadline": 100, "deliveredAt": [90]},          # on time
              {"deadline": 100, "deliveredAt": [90, 120]},     # late (last leg)
              {"deadline": 100, "deliveredAt": [None]},        # overdue at now=200
              {"deadline": 500, "deliveredAt": [None]}]        # still open, not counted
    assert service(200, orders) == (1, 2)


def mode_after(mode: str, share: float, warn: float, now: int, since: int = 0, loose: bool = True) -> str:
    ns = SimpleNamespace(mode=mode, mode_since=since, now=now, tight_share=0.94, switch_loose=loose)
    ns._recent = lambda: (100, int(warn * 100))
    ns._service = lambda: (int(share * 1000), 1000 - int(share * 1000))
    MarginDesk._update_mode(ns)
    return ns.mode


def test_switch_transitions() -> None:
    wed = 2 * DAY + 600
    assert mode_after("normal", 0.93, 0.01, wed) == "tight"
    assert mode_after("normal", 0.99, 0.10, wed) == "tight"
    assert mode_after("normal", 0.98, 0.02, wed) == "loose"
    assert mode_after("normal", 0.98, 0.02, DAY) == "normal"          # loose only from Wednesday
    assert mode_after("loose", 0.98, 0.02, 4 * DAY + 13 * 60) == "normal"  # never after Fri 12:00
    assert mode_after("tight", 0.96, 0.03, wed, since=wed - DAY + 1) == "tight"  # under 24 h
    assert mode_after("tight", 0.96, 0.03, wed, since=wed - DAY) == "normal"
    assert mode_after("normal", 0.98, 0.02, wed, loose=False) == "normal"   # guard never goes loose


def test_wire_and_normalize() -> None:
    q = [ai_decide.Question("take", "Quote it?", [("take", "yes"), ("refuse", "no")]),
         ai_decide.Question("late", "Late?")]
    jev = ai_decide.wire("jev", {"a": 1}, q)
    assert jev["questions"]["take"]["criteria"] == {"take": "yes", "refuse": "no"}
    assert jev["questions"]["late"]["type"] == "noul"
    oa = ai_decide.wire("openai", {"a": 1}, q)
    assert oa["questions"][0]["choices"][1] == {"value": "refuse", "description": "no"}
    assert oa["questions"][1]["type"] == "predicate" and isinstance(oa["input"], str)
    a = ai_decide.normalize("jev", {"answers": {"take": {"type": "choice", "choice": "take",
                                                         "probabilities": {"take": 0.7, "refuse": 0.3}}}})
    assert a["take"].probabilities["take"] == 0.7
    b = ai_decide.normalize("openai", {"answers": [{"name": "take", "type": "choice", "choice": "refuse",
                                                    "probabilities": [{"value": "take", "probability": 0.2},
                                                                      {"value": "refuse", "probability": 0.8}]},
                                                   {"name": "late", "type": "predicate", "probability": 0.4}]})
    assert b["take"].choice == "refuse" and b["late"].yes == 0.4


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
