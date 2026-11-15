"""Planted label errors. Code changes the CLAIMED answer, never the note. Deterministic by id."""

import calendar
import copy
import datetime as dt
import hashlib

from core import ROUTES, TYPES

KINDS = ["date_shift_days", "date_shift_month", "type_swap", "event_removed", "event_added", "route_swap"]

# most confusable neighbour of each event type (fixed by hand before any judge answer was seen)
NEIGHBOUR = {
    "SYMPTOM_ONSET_REPORTED": "FIRST_CONTACT",
    "FIRST_CONTACT": "PHYSICIAN_ASSESSMENT",
    "PHYSICIAN_ASSESSMENT": "SPECIALIST_VISIT",
    "REFERRAL_SENT": "REFERRAL_RECEIVED",
    "REFERRAL_RECEIVED": "REFERRAL_SENT",
    "SPECIALIST_VISIT": "PHYSICIAN_ASSESSMENT",
    "DIAGNOSIS": "MDT_DECISION",
    "MDT_DECISION": "TREATMENT_START",
    "TREATMENT_START": "MDT_DECISION",
}
assert set(NEIGHBOUR) == set(TYPES)


def h(tag, ident):
    return int(hashlib.sha256(f"{tag}:{ident}".encode()).hexdigest(), 16)


def eligible(claim):
    """A note can take any of the six corruptions."""
    ev = claim["events"]
    types = [e["type"] for e in ev]
    return 2 <= len(ev) <= 8 and len(set(types)) == len(types) and any(e["precision"] == "DAY" for e in ev)


def _shift_month(date, sign):
    y, m = date.year + (date.month - 1 + sign) // 12, (date.month - 1 + sign) % 12 + 1
    return dt.date(y, m, min(date.day, calendar.monthrange(y, m)[1]))


def corrupt(kind, claim, note_date, ident):
    """(new claim, change). `claim` is {entry_route, events:[{type,date,precision}]} and is not modified."""
    new = copy.deepcopy(claim)
    ev = new["events"]
    nd = dt.date.fromisoformat(note_date)
    k = h("corrupt:" + kind, ident)
    if kind == "date_shift_days":
        idx = [i for i, e in enumerate(ev) if e["precision"] == "DAY"]
        i = idx[k % len(idx)]
        delta = (1 + (k >> 8) % 3) * (1 if (k >> 16) % 2 else -1)
        old = dt.date.fromisoformat(ev[i]["date"])
        if old + dt.timedelta(days=delta) > nd:
            delta = -abs(delta)
        ev[i]["date"] = (old + dt.timedelta(days=delta)).isoformat()
        return new, dict(kind=kind, index=i, field="date", old=old.isoformat(), new=ev[i]["date"], delta_days=delta)
    if kind == "date_shift_month":
        i = k % len(ev)
        sign = 1 if (k >> 8) % 2 else -1
        old = dt.date.fromisoformat(ev[i]["date"])
        if _shift_month(old, sign) > nd:
            sign = -1
        ev[i]["date"] = _shift_month(old, sign).isoformat()
        return new, dict(kind=kind, index=i, field="date", old=old.isoformat(), new=ev[i]["date"], delta_months=sign)
    if kind == "type_swap":
        present = {e["type"] for e in ev}
        idx = [i for i, e in enumerate(ev) if NEIGHBOUR[e["type"]] not in present] or list(range(len(ev)))
        i = idx[k % len(idx)]
        old = ev[i]["type"]
        ev[i]["type"] = NEIGHBOUR[old]
        return new, dict(kind=kind, index=i, field="type", old=old, new=ev[i]["type"])
    if kind == "event_removed":
        i = k % len(ev)
        gone = ev.pop(i)
        return new, dict(kind=kind, index=i, removed=gone)
    if kind == "event_added":
        free = [t for t in TYPES if t not in {e["type"] for e in ev}]
        t = free[k % len(free)]
        taken = {e["date"] for e in ev}
        n = 7 + (k >> 8) % 300
        while (nd - dt.timedelta(days=n)).isoformat() in taken:
            n += 1
        added = dict(type=t, date=(nd - dt.timedelta(days=n)).isoformat(), precision="DAY")
        ev.append(added)
        return new, dict(kind=kind, index=len(ev) - 1, added=added)
    if kind == "route_swap":
        others = sorted(r for r in ROUTES if r != claim["entry_route"])
        new["entry_route"] = others[k % len(others)]
        return new, dict(kind=kind, field="entry_route", old=claim["entry_route"], new=new["entry_route"])
    raise ValueError(kind)
