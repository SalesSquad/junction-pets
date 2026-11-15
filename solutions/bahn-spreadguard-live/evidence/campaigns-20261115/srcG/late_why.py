"""Why were orders late? Usage: late_why.py <world_id> ... (ended practice worlds)."""
import collections, sys
from spread.client import Client

DAY = 1440
c = Client()
for wid in sys.argv[1:]:
    w = c.world(wid)
    ev = w.events()
    rev = w.reveal()
    orders = {}
    for e in ev:
        if e["kind"] in ("order_won", "order_changed"):
            orders[e["order"]["id"]] = e["order"]
    cancelled = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    delivered = collections.defaultdict(dict)
    closes, drops, fails, booked, expired = collections.Counter(), collections.Counter(), collections.Counter(), {}, collections.Counter()
    gig_order = {}
    for e in ev:
        k = e["kind"]
        if k == "delivered":
            delivered[e["orderId"]][e["leg"]] = e["at"]
            gig_order[e["gigId"]] = e["orderId"]
        elif k == "deadline_close":
            closes[e["orderId"]] += 1
        elif k == "visit_failed":
            fails[(e["orderId"], e["reason"])] += 1
        elif k == "picked_up":
            gig_order[e["gigId"]] = e["orderId"]
    first_book = {}
    for e in ev:
        if e["kind"] == "gig_booked":
            oid = gig_order.get(e["gigId"])
            if oid and oid not in first_book:
                first_book[oid] = e["at"]
    stats = collections.Counter()
    late_rows = []
    for oid, o in orders.items():
        if oid in cancelled:
            continue
        legs = len(o["legs"])
        d = delivered.get(oid, {})
        done = max(d.values()) if len(d) == legs else None
        late = done is None or done > o["deadline"]
        stats["orders"] += 1
        if not late:
            continue
        stats["late"] += 1
        stats["late_" + o["option"]] += 1
        stats["late_close" if closes[oid] else "late_noclose"] += 1
        f = [r for (x, r) in fails if x == oid]
        for r in f:
            stats["late_fail_" + r] += 1
        if done is None:
            stats["late_undelivered"] += 1
        won_day = (o["deadline"] // DAY)
        stats[f"late_deadline_day{won_day}"] += 1
        stats["late_origin_" + o["legs"][0]["pickup"]["placeId"]] += 1
        stats["late_private" if any(l["pickup"].get("privateAddress") or l["delivery"].get("privateAddress") for l in o["legs"]) else "late_dealer"] += 1
        stats["late_legs%d" % legs] += 1
        fb = first_book.get(oid)
        late_rows.append((oid, o["option"], o["legs"][0]["pickup"]["placeId"], o["legs"][0]["delivery"]["placeId"], o["deadline"], o.get("lastPickupAt"), fb, done, closes[oid], f))
    print(wid, dict(sorted(stats.items(), key=lambda kv: (-kv[1], kv[0]))))
    for row in sorted(late_rows, key=lambda r: r[4])[:60]:
        print("  ", row)
