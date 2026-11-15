#!/usr/bin/env python3
"""Read-only analysis of recorded Bahn Spread practice worlds (json.gz bundles).

Usage: python3 bahn_analyze.py <glob-of-json.gz> ...
Prints aggregate evidence about pricing, fees, timing and lateness.
"""
import collections
import glob
import gzip
import json
import statistics
import sys

DAY = 1440
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon2", "Tue2", "Wed2"]


def q(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1)))]


def main(paths):
    worlds = []
    for pattern in paths:
        worlds += sorted(glob.glob(pattern, recursive=True))
    seen_ids = set()
    agg = collections.defaultdict(list)
    day_win = collections.defaultdict(lambda: [0, 0])  # (world, day) -> [won, quoted]
    region_day = collections.defaultdict(lambda: [0, 0])
    totals = collections.Counter()
    fee_ratio_first = []
    fee_ratio_booked = []
    booked_step0_fast = 0
    booked_total = 0
    delay_by_hour = collections.defaultdict(list)
    step_idx = collections.Counter()
    dealer_series = collections.defaultdict(list)
    option_mix = collections.Counter()
    option_offered = collections.Counter()
    margin_by_option = collections.defaultdict(lambda: [0, 0, 0])
    per_world = []
    for path in worlds:
        try:
            d = json.load(gzip.open(path))
        except Exception as exc:  # noqa: BLE001
            print("skip", path, exc)
            continue
        wid = d.get("world_id")
        if wid in seen_ids or "events" not in d:
            continue
        seen_ids.add(wid)
        ev = d["events"]
        reqs = {e["request"]["id"]: e["request"] for e in ev if e["kind"] == "price_request"}
        rev = {r["request"]["id"]: r for r in d["reveal"]["requests"]}
        gigs = {g["id"]: g for g in d["snapshot"]["gigs"]}
        orders = {o["id"]: o for o in d["snapshot"]["orders"]}
        # --- quotes and wins
        wins = losses = 0
        for rid, r in rev.items():
            quote = r.get("quote") or {}
            req = r["request"]
            for opt in req["options"]:
                option_offered[opt["kind"]] += 1
            competitive = [k for k, v in quote.items()
                           for o in req["options"] if o["kind"] == k and v < 3 * o["listPriceCents"]]
            if not competitive:
                totals["declined_or_unquoted"] += 1
                continue
            k = competitive[0]
            lp = next(o["listPriceCents"] for o in req["options"] if o["kind"] == k)
            ratio = quote[k] / lp
            day = req["arrivedAt"] // DAY
            won = r["outcome"] == "won"
            wins += won
            losses += (not won)
            day_win[(wid, day)][0] += won
            day_win[(wid, day)][1] += 1
            origin = req["legs"][0]["pickup"]["placeId"]
            region_day[(wid, day, origin)][0] += won
            region_day[(wid, day, origin)][1] += 1
            dealer_series[(wid, req["dealerId"])].append((req["arrivedAt"], won))
            agg["quote_ratio"].append(ratio)
            if won:
                option_mix[r.get("option") or k] += 1
        # --- fees and bookings
        ledger = collections.Counter()
        order_fee = collections.Counter()
        for e in ev:
            if e["kind"] == "ledger":
                line = e["line"]
                ledger[line["kind"]] += line["cents"]
                if line["kind"] == "driver_fee" and line.get("orderId"):
                    order_fee[line["orderId"]] += -line["cents"]
        first_view = {}
        for e in ev:
            if e["kind"] == "gig_viewed":
                first_view.setdefault(e["gigId"], e["at"])
            if e["kind"] != "gig_booked":
                continue
            g = gigs.get(e["gigId"])
            if not g:
                continue
            oid = g["stops"][0]["orderId"]
            req = reqs.get(oid)
            if not req:
                continue
            cars = len({(s["orderId"], s["leg"]) for s in g["stops"]})
            total_legs = len(req["legs"])
            ref = req["referenceFeeCents"] * cars / total_legs
            sched = g["schedule"]
            idx = max(i for i, s in enumerate(sched) if s["at"] <= e["at"]) if any(s["at"] <= e["at"] for s in sched) else 0
            step_idx[idx] += 1
            booked_total += 1
            fee_ratio_booked.append(e["feeCents"] / ref)
            fee_ratio_first.append(sched[0]["feeCents"] / ref)
            delay = e["at"] - g["postedAt"]
            delay_by_hour[(g["postedAt"] % DAY) // 60].append(delay)
            if idx == 0 and delay <= 10:
                booked_step0_fast += 1
        for oid, o in orders.items():
            if o.get("status") == "cancelled" or oid not in reqs:
                continue
            price = o.get("priceCents") or 0
            m = margin_by_option[o.get("option")]
            m[0] += 1
            m[1] += price
            m[2] += order_fee.get(oid, 0)
        sc = d.get("score", {})
        per_world.append((wid, d.get("policy"), sc.get("wonOrders"), round(sc.get("onTimeShare", 0), 4),
                          sc.get("marginCents", 0) / 100, wins, losses,
                          {k: round(v / 100) for k, v in ledger.items()}))
    print("WORLDS", len(per_world))
    for row in per_world:
        print("  ", row)
    print("\nQUOTE ratio to list p10/p50/p90:", q(agg["quote_ratio"], .1), q(agg["quote_ratio"], .5), q(agg["quote_ratio"], .9))
    print("declined/unquoted requests:", totals["declined_or_unquoted"])
    print("\nOPTIONS offered by dealers:", dict(option_offered))
    print("OPTIONS won:", dict(option_mix))
    print("\nMARGIN by won option (orders, revenue €, driver fees €, fee/revenue):")
    for k, (n, revc, fee) in margin_by_option.items():
        print(f"   {k}: {n} orders, rev €{revc/100:,.0f}, fees €{fee/100:,.0f}, fee share {fee/max(1,revc):.3f}")
    print("\nWIN RATE by world/day (won/quoted):")
    by_world = collections.defaultdict(list)
    for (wid, day), (w, n) in sorted(day_win.items()):
        by_world[wid].append(f"{DOW[day] if day < len(DOW) else day}:{w}/{n}={w/max(1,n):.2f}")
    for wid, cells in by_world.items():
        print("  ", wid, " ".join(cells))
    print("\nREGION-DAY cells with >=5 quotes and win rate >=0.9 (possible outage):")
    hot = [(k, v) for k, v in region_day.items() if v[1] >= 5 and v[0] / v[1] >= 0.9]
    for (wid, day, place), (w, n) in sorted(hot)[:40]:
        print(f"   {wid} {DOW[day]} {place}: {w}/{n}")
    # dealer adaptation: win rate in first vs second half of dealer's requests
    first = [0, 0]
    second = [0, 0]
    for key, series in dealer_series.items():
        series.sort()
        half = len(series) // 2
        for i, (_, won) in enumerate(series):
            target = first if i < half else second
            target[0] += won
            target[1] += 1
    print(f"\nDEALER win rate first half {first[0]}/{first[1]}={first[0]/max(1,first[1]):.3f}, second half {second[0]}/{second[1]}={second[0]/max(1,second[1]):.3f}")
    print("\nBOOKINGS:", booked_total, "booked at schedule step:", dict(sorted(step_idx.items())))
    print("  booked at opening fee within 10 min:", booked_step0_fast, f"({booked_step0_fast/max(1,booked_total):.2%})")
    print("  opening fee / ref p10/p50/p90:", round(q(fee_ratio_first, .1), 3), round(q(fee_ratio_first, .5), 3), round(q(fee_ratio_first, .9), 3))
    print("  booked fee / ref  p10/p50/p90:", round(q(fee_ratio_booked, .1), 3), round(q(fee_ratio_booked, .5), 3), round(q(fee_ratio_booked, .9), 3))
    print("  booking delay (min) by posting hour: hour n p25 p50 p75")
    for h in sorted(delay_by_hour):
        xs = delay_by_hour[h]
        print(f"   {h:02d} {len(xs):4d} {q(xs,.25):5.0f} {q(xs,.5):5.0f} {q(xs,.75):5.0f}")


if __name__ == "__main__" and (len(sys.argv) < 2 or sys.argv[1] != "--extra"):
    main(sys.argv[1:])


def extra(paths):
    """Fee step by posting/booking period, trust headroom, dealer counts."""
    worlds = []
    for pattern in paths:
        worlds += sorted(glob.glob(pattern, recursive=True))
    cells = collections.defaultdict(lambda: [0, 0.0, 0])  # key -> n, sum ratio, overnight
    trust_bins = collections.defaultdict(lambda: [0, 0])
    dealers_per_world = []
    orders_per_dealer = []
    monday = [0, 0]
    for path in worlds:
        d = json.load(gzip.open(path))
        ev = d["events"]
        reqs = {e["request"]["id"]: e["request"] for e in ev if e["kind"] == "price_request"}
        gigs = {g["id"]: g for g in d["snapshot"]["gigs"]}
        orders = {}
        for e in ev:
            if e["kind"] == "order_won":
                orders[e["order"]["id"]] = e["order"]
        for e in ev:
            if e["kind"] != "gig_booked":
                continue
            g = gigs.get(e["gigId"])
            if not g:
                continue
            oid = g["stops"][0]["orderId"]
            req = reqs.get(oid)
            if not req:
                continue
            cars = len({(s["orderId"], s["leg"]) for s in g["stops"]})
            ref = req["referenceFeeCents"] * cars / len(req["legs"])
            ph = (g["postedAt"] % DAY) // 60
            overnight = (g["postedAt"] // DAY) != (e["at"] // DAY)
            key = ("post>=14" if ph >= 14 else "post<14", "next-day-booking" if overnight else "same-day-booking")
            c = cells[key]
            c[0] += 1
            c[1] += e["feeCents"] / ref
        # trust headroom: on-time deliveries to dealer before request vs win
        ontime = collections.Counter()
        timeline = []
        rev = {r["request"]["id"]: r for r in d["reveal"]["requests"]}
        done_at = {}
        for e in ev:
            if e["kind"] == "delivered":
                o = orders.get(e["orderId"])
                if o is None:
                    continue
                o.setdefault("_dl", {})[e["leg"]] = e["at"]
                if len(o["_dl"]) == len(o["legs"]):
                    done_at[o["id"]] = (max(o["_dl"].values()), max(o["_dl"].values()) <= o["deadline"], o["dealerId"])
        events_t = sorted(done_at.values())
        dealer_orders = collections.Counter(o["dealerId"] for o in orders.values())
        dealers_per_world.append(len({r["request"]["dealerId"] for r in rev.values()}))
        orders_per_dealer += list(dealer_orders.values())
        for rid, r in rev.items():
            q_ = r.get("quote") or {}
            req = r["request"]
            comp = [k for k, v in q_.items() for o in req["options"] if o["kind"] == k and v < 3 * o["listPriceCents"]]
            if not comp:
                continue
            t = req["arrivedAt"]
            count = 0
            for at, ok, dealer in events_t:
                if at > t:
                    break
                if dealer != req["dealerId"]:
                    continue
                count = min(25, count + 1) if ok else count // 2
            b = min(count // 3, 5)
            trust_bins[b][0] += r["outcome"] == "won"
            trust_bins[b][1] += 1
    print("\nBOOKED FEE/REF by posting time and booking day:")
    for k, (n, s, _) in sorted(cells.items()):
        print(f"   {k}: n={n} mean booked/ref={s/max(1,n):.3f}")
    print("\nWIN RATE by dealer trust bucket (count//3):")
    for b, (w, n) in sorted(trust_bins.items()):
        print(f"   trust {b*3}-{b*3+2}: {w}/{n} = {w/max(1,n):.3f}")
    print("\nDealers per world:", dealers_per_world)
    print("Won orders per dealer p25/p50/p75/max:", q(orders_per_dealer, .25), q(orders_per_dealer, .5), q(orders_per_dealer, .75), max(orders_per_dealer))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--extra":
    extra(sys.argv[2:])
