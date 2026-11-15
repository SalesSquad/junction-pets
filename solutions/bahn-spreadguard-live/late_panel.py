#!/usr/bin/env python3
"""Late-order causes in ended practice worlds: code tags, Jev and OpenAI Decisions judge.

    python late_panel.py <world_id> ... > late_panel.json

Code builds a compact record per late order and a deterministic cause tag; each
typed-decision provider picks a cause from the same record. Code aggregates and
reports agreement. Reads only ended unranked practice worlds; prints no secrets.
"""
from __future__ import annotations

import collections
import json
import sys

from spread.client import Client

import ai_decide

DAY = 1440
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CAUSES = [
    ("weekend_gap", "Won before the weekend with a deadline after it; the car only moved after the weekend."),
    ("slow_booking", "On working days no driver booked the gig for a long time (over about 8 working hours)."),
    ("failed_visit", "A pickup or delivery visit failed (no plates, licence, closed site) and had to be redone."),
    ("tight_deadline", "Little time from win to deadline: the drive barely fits even if booked at once."),
    ("other", "None of the above clearly fits."),
]
QUESTION = ai_decide.Question(
    "cause", "This car-transport order was delivered late (or not at all). Times are minutes into a "
    "simulated fortnight starting Monday 00:00; drivers mostly work 07:00-21:00 on weekdays. "
    "Which is the main cause of the lateness?", CAUSES)


def hm(t: int | None) -> str | None:
    return None if t is None else f"{WD[(t // DAY) % 7]} {t % DAY // 60:02d}:{t % 60:02d} (day {t // DAY})"


def records(client: Client, wid: str) -> list[dict]:
    w = client.world(wid)
    ev = w.events()
    orders, won_at = {}, {}
    for e in ev:
        if e["kind"] in ("order_won", "order_changed"):
            orders[e["order"]["id"]] = e["order"]
            if e["kind"] == "order_won":
                won_at[e["order"]["id"]] = e["at"]
    cancelled = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    delivered: dict[str, dict[int, int]] = collections.defaultdict(dict)
    closes, fails = collections.Counter(), collections.defaultdict(list)
    gig_order, first_book = {}, {}
    for e in ev:
        k = e["kind"]
        if k == "delivered":
            delivered[e["orderId"]][e["leg"]] = e["at"]
        if k in ("delivered", "picked_up") and "gigId" in e:
            gig_order[e["gigId"]] = e["orderId"]
        if k == "deadline_close":
            closes[e["orderId"]] += 1
        if k == "visit_failed":
            fails[e["orderId"]].append(e["reason"])
    for e in ev:
        if e["kind"] == "gig_booked":
            oid = gig_order.get(e["gigId"])
            if oid and oid not in first_book:
                first_book[oid] = e["at"]
    out = []
    for oid, o in orders.items():
        if oid in cancelled:
            continue
        d = delivered.get(oid, {})
        done = max(d.values()) if len(d) == len(o["legs"]) else None
        if done is not None and done <= o["deadline"]:
            continue
        won = won_at.get(oid, 0)
        fb = first_book.get(oid)
        if fails[oid]:
            tag = "failed_visit"
        elif won // DAY <= 4 and o["deadline"] >= 7 * DAY:
            tag = "weekend_gap"
        elif fb is not None and fb - won > 480:
            tag = "slow_booking"
        elif o["deadline"] - won < 600:
            tag = "tight_deadline"
        else:
            tag = "other"
        out.append({"world": wid, "order": oid, "code_tag": tag, "record": {
            "option": o["option"], "legs": len(o["legs"]),
            "won_at": hm(won), "deadline": hm(o["deadline"]),
            "hours_win_to_deadline": round((o["deadline"] - won) / 60, 1),
            "first_driver_booked": hm(fb),
            "hours_win_to_first_booking": None if fb is None else round((fb - won) / 60, 1),
            "delivered_at": hm(done) if done is not None else "not delivered",
            "hours_late": None if done is None else round((done - o["deadline"]) / 60, 1),
            "deadline_warnings": closes[oid], "failed_visits": fails[oid],
        }})
    return out


def main() -> None:
    client = Client()
    rows = [r for wid in sys.argv[1:] for r in records(client, wid)]
    for r in rows:
        for prov in ("jev", "openai"):
            try:
                ans, _, _ = ai_decide.decide(prov, r["record"], [QUESTION], timeout=15.0)
                r[prov] = ans["cause"].choice
            except Exception as exc:  # noqa: BLE001
                r[prov] = "error:" + type(exc).__name__
    agg = {k: collections.Counter(r[k] for r in rows) for k in ("code_tag", "jev", "openai")}
    agree = {p: round(sum(r[p] == r["code_tag"] for r in rows) / max(1, len(rows)), 3) for p in ("jev", "openai")}
    agree["jev_vs_openai"] = round(sum(r["jev"] == r["openai"] for r in rows) / max(1, len(rows)), 3)
    print(json.dumps({"late_orders": len(rows), "worlds": len(sys.argv) - 1,
                      "counts": {k: dict(v.most_common()) for k, v in agg.items()},
                      "agreement": agree, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
