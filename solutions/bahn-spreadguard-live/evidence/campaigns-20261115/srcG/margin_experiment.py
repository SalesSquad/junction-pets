#!/usr/bin/env python3
"""Opt-in margin overlay on the frozen 139% / +240 min admission candidate.

Three independent, environment-switchable changes (unranked practice only):

* SPREAD_MARGIN_RAMP=1   fee raises pause from 21:00 to 07:00 and start on the
                         pickup day; with lots of slack the raise gaps double.
                         The last raise still lands before ``lastPickupAt`` - 3 h.
* SPREAD_MARGIN_TRUST_BPS=N  add N basis points of price per counted on-time
                         order to the dealer (level 8 trust is +1 % per order).
* SPREAD_MARGIN_REGION=1 raise the price in a region (pickup place and places
                         within 80 km) after a streak of wins, back off on loss.
                         Targets the unannounced competitor outage.

Defaults are the frozen ``vol360`` candidate: 139% of list + 0.8% per counted
on-time order to the dealer, slack floor 360 min (was 480), next-day buffer
SPREAD_ADMISSION_EXTRA_SLACK=120 (AdmissionDesk default; the old candidate used
240), backlog veto on, region pricing off, night-aware fee ramp on. Every other
admission veto of the 139% / +240 min candidate is kept.

Opt-in additions of 15 November (all off by default, so the defaults stay vol360):

* SPREAD_MARGIN_WEEKEND_EXTRA=N  the weekend (Sat 00:00 .. Mon 07:00) is not slack:
                         subtract it and require N minutes more for options that span it.
  SPREAD_MARGIN_WEEKEND_KINDS=next_day  limit that gate to some option kinds.
  SPREAD_MARGIN_WEEKEND_IF_BELOW=0.96  apply it only while on-time so far is below this.
* SPREAD_MARGIN_SWITCH=1 runtime gate controller: normal (vol360), tight (480/240) under
                         service pressure, loose (240/0) Wed..Fri 12:00 when comfortable.
* SPREAD_MARGIN_AI=jev|openai, SPREAD_MARGIN_AI_RISK=jev|openai  experimental typed-decision
                         gates (ai_decide.py). Practice only: an external call per decision
                         is not acceptable on the live final clock.

    python margin_experiment.py --level 8 --seed <seed>    # unranked practice
    python margin_experiment.py --final                    # only with owner approval
"""
from __future__ import annotations

import atexit
import math
import os
from collections import Counter, deque
from typing import Any

from spread import starter

from admission_experiment import AdmissionDesk
from dispatch import DAY, round_up_div

MARGIN_COUNTS: Counter[str] = Counter()
ACTIVE_FROM = 7 * 60
ACTIVE_TO = 21 * 60
OUTAGE_KM = 80.0


@atexit.register
def report_margin_aggregate() -> None:
    print("MARGIN_DECISIONS=" + repr(dict(sorted(MARGIN_COUNTS.items()))), flush=True)


def km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def advance_active(start: int, minutes: int) -> int:
    """`minutes` of driver-active time after `start`, skipping 21:00-07:00."""
    t = start
    left = minutes
    while left > 0:
        day = t // DAY
        tod = t % DAY
        if tod < ACTIVE_FROM:
            t = day * DAY + ACTIVE_FROM
            continue
        if tod >= ACTIVE_TO:
            t = (day + 1) * DAY + ACTIVE_FROM
            continue
        room = ACTIVE_TO - tod
        step = min(room, left)
        t += step
        left -= step
    return t


class MarginDesk(AdmissionDesk):
    def __init__(self, world: Any, level: int, now: int):
        super().__init__(world, level, now)
        self.ramp_on = os.getenv("SPREAD_MARGIN_RAMP", "1") == "1"
        self.trust_bps = int(os.getenv("SPREAD_MARGIN_TRUST_BPS", "80"))
        self.trust_cap_bps = int(os.getenv("SPREAD_MARGIN_TRUST_CAP_BPS", "1600"))
        self.region_on = os.getenv("SPREAD_MARGIN_REGION", "0") == "1"
        self.region_step = int(os.getenv("SPREAD_MARGIN_REGION_STEP_BPS", "400"))
        self.region_cap = int(os.getenv("SPREAD_MARGIN_REGION_CAP_BPS", "3000"))
        self.region_loss = int(os.getenv("SPREAD_MARGIN_REGION_LOSS_BPS", "800"))
        self.price_cap_bps = int(os.getenv("SPREAD_MARGIN_PRICE_CAP_BPS", "18500"))
        self.slack_floor = int(os.getenv("SPREAD_MARGIN_FLOOR", "360"))
        self.backlog_veto = os.getenv("SPREAD_MARGIN_BACKLOG", "1") == "1"
        self.base_bps = int(os.getenv("SPREAD_MARGIN_BASE_BPS", "13900"))
        self.fee_pct = int(os.getenv("SPREAD_MARGIN_FEE_PCT", "100"))
        self.weekend_ramp = os.getenv("SPREAD_MARGIN_RAMP_WEEKEND", "0") == "1"
        # Quote every eligible option and let the dealer choose (default: best one only).
        self.multi = os.getenv("SPREAD_MARGIN_MULTI", "0") == "1"
        # Adaptive admission: loosen the time gates while recent orders find
        # drivers easily, tighten them as deadline warnings pile up.
        self.adapt = os.getenv("SPREAD_MARGIN_ADAPT", "0") == "1"
        self.adapt_lo = float(os.getenv("SPREAD_MARGIN_ADAPT_LO", "0.04"))
        self.adapt_hi = float(os.getenv("SPREAD_MARGIN_ADAPT_HI", "0.08"))
        self.win_times: deque[int] = deque()
        self.close_times: deque[int] = deque()
        self.closed_orders: set[str] = set()
        # Switch controller: normal (= vol360 gates), tight (480/240) under
        # service pressure, loose (240/0, no backlog veto) Wed..Fri 12:00 when
        # service is comfortable. Off by default.
        self.switch = os.getenv("SPREAD_MARGIN_SWITCH", "0") == "1"
        self.mode = "normal"
        self.mode_since = now
        self.mode_checked = -10**9
        # Extra slack (minutes) for options whose window spans the weekend;
        # the weekend itself is not counted as slack. 0 = off.
        self.weekend_extra = int(os.getenv("SPREAD_MARGIN_WEEKEND_EXTRA", "0"))
        # Option kinds the weekend gate applies to (comma list; empty = all kinds).
        self.weekend_kinds = {k for k in os.getenv("SPREAD_MARGIN_WEEKEND_KINDS", "").split(",") if k}
        # Conditional weekend gate: only while service is under pressure (0 = always on).
        self.weekend_if_below = float(os.getenv("SPREAD_MARGIN_WEEKEND_IF_BELOW", "0"))
        self.weekend_warn_above = float(os.getenv("SPREAD_MARGIN_WEEKEND_WARN_ABOVE", "1"))
        self._press_checked = -10**9
        self._pressed = True
        # Experimental typed-decision gate for borderline requests: "", jev, openai.
        self.ai = os.getenv("SPREAD_MARGIN_AI", "")
        self.ai_max = int(os.getenv("SPREAD_MARGIN_AI_MAX", "400"))
        self.ai_accept = float(os.getenv("SPREAD_MARGIN_AI_ACCEPT", "0.6"))
        self.ai_cache: dict[tuple, bool] = {}
        self.ai_calls = 0
        # Experimental: the typed model may refuse orders that pass the gates but span the weekend.
        self.ai_risk = os.getenv("SPREAD_MARGIN_AI_RISK", "")
        self.tight_share = float(os.getenv("SPREAD_MARGIN_SWITCH_TIGHT_SHARE", "0.94"))
        if (self.ai not in ("", "jev", "openai") or self.ai_risk not in ("", "jev", "openai")
                or not 0 <= self.weekend_extra <= 1440 or not 0.9 <= self.tight_share <= 0.99):
            raise ValueError("switch/weekend/ai parameter outside its safe range")
        if not 60 <= self.fee_pct <= 120:
            raise ValueError("SPREAD_MARGIN_FEE_PCT outside 60..120")
        if not (0 <= self.trust_bps <= 120 and 0 <= self.region_cap <= 5000
                and 13900 <= self.price_cap_bps <= 20000):
            raise ValueError("margin overlay parameter outside its safe range")
        self.neighbours: dict[str, set[str]] = {}
        try:
            places = {p["id"]: p for p in world.client.map().get("places", [])}
            for pid, place in places.items():
                self.neighbours[pid] = {q for q, other in places.items()
                                        if km(place, other) <= OUTAGE_KM}
        except (starter.SpreadError, KeyError, TypeError, OSError):
            self.region_on = False
        self.region_bump: Counter[str] = Counter()
        self.region_streak: Counter[str] = Counter()
        self.region_day = now // DAY
        self.quoted_origin: dict[str, str] = {}

    # ------------------------------------------------------------- pricing
    def _region_bps(self, origin: str) -> int:
        if not self.region_on:
            return 0
        if self.now // DAY != self.region_day:
            self.region_day = self.now // DAY
            self.region_bump.clear()
            self.region_streak.clear()
        return self.region_bump[origin]

    def _learn_region(self, origin: str, won: bool) -> None:
        if not self.region_on:
            return
        self._region_bps(origin)  # day reset
        for place in self.neighbours.get(origin, {origin}):
            if won:
                self.region_streak[place] += 1
                if self.region_streak[place] >= 3:
                    self.region_bump[place] = min(self.region_cap,
                                                  self.region_bump[place] + self.region_step)
            else:
                self.region_streak[place] = 0
                self.region_bump[place] = max(0, self.region_bump[place] - self.region_loss)

    def quote(self, request: dict[str, Any]) -> None:
        if self.level < 8:
            super().quote(request)
            return
        self.requests[request["id"]] = request
        MARGIN_COUNTS["requests"] += 1
        if self.now >= request["respondBy"] or not request["options"]:
            MARGIN_COUNTS["expired"] += 1
            return
        origin = request["legs"][0]["pickup"]["placeId"]
        backlog = self._local_backlog(origin)
        nearby = self._driver_count(origin)
        trust = min(self.trust_cap_bps, self.trust_bps * self.trust[request["dealerId"]])
        region = self._region_bps(origin)
        factor_bps = min(self.price_cap_bps, self.base_bps + trust + region)
        if trust:
            MARGIN_COUNTS["trust_priced"] += 1
        if region:
            MARGIN_COUNTS["region_priced"] += 1
        slack_floor, extra_slack, backlog_veto = self._gates()
        eligible: list[tuple[int, dict[str, Any], int]] = []
        borderline: list[tuple[int, dict[str, Any], int, int, str]] = []
        buffer = self._booking_delay_buffer()
        for option in request["options"]:
            slack = self._slack(request, option)
            weekend = (self._weekend_minutes(option["deadline"])
                       if self.weekend_extra and (not self.weekend_kinds or option["kind"] in self.weekend_kinds)
                       and self._weekend_pressed()
                       else 0)
            if weekend:
                slack -= weekend
            floor = slack_floor + buffer
            if self.roster and nearby < 2:
                continue
            price = round_up_div(option["listPriceCents"] * factor_bps, 10000)
            if price * 100 < request["referenceFeeCents"] * 135:
                continue
            projected = price - round_up_div(request["referenceFeeCents"] * 120, 100)
            rank = projected + min(300, slack // 10)
            veto = ""
            if slack < floor:
                veto = "slack_floor"
            elif backlog_veto and backlog >= 5 and slack < 900:
                veto = "local_backlog"
            elif option["kind"] == "next_day" and slack < floor + extra_slack:
                veto = "next_day_buffer"
            elif weekend and slack < floor + extra_slack + self.weekend_extra:
                veto = "weekend_buffer"
                MARGIN_COUNTS["weekend_veto"] += 1
            if (not veto and self.ai_risk and self.ai_calls < self.ai_max
                    and self._weekend_minutes(option["deadline"]) > 0
                    and not self._ai_take(request, option, price, slack, "spans_weekend",
                                          backlog, nearby, provider=self.ai_risk)):
                veto = "ai_weekend_risk"
                MARGIN_COUNTS["ai_risk_refuse"] += 1
            if not veto:
                eligible.append((rank, option, price))
            elif self.ai and slack >= 240 + buffer:
                borderline.append((rank, option, price, slack, veto))
        if not eligible and borderline and self.ai_calls < self.ai_max:
            rank, option, price, slack, veto = max(borderline, key=lambda e: (e[0], e[1]["deadline"]))
            if self._ai_take(request, option, price, slack, veto, backlog, nearby):
                eligible.append((rank, option, price))
                MARGIN_COUNTS["ai_take"] += 1
            else:
                MARGIN_COUNTS["ai_refuse"] += 1
        if eligible:
            _, option, price = max(eligible, key=lambda e: (e[0], e[1]["deadline"]))
            prices = {option["kind"]: price}
            if self.multi and len(eligible) > 1:
                prices = {opt["kind"]: p for _, opt, p in eligible}
                MARGIN_COUNTS["multi_option"] += 1
            self.quoted_origin[request["id"]] = origin
            MARGIN_COUNTS["competitive"] += 1
        else:
            option = request["options"][0]
            prices = {option["kind"]: min(2**31 - 1, option["listPriceCents"] * 20)}
            MARGIN_COUNTS["declined"] += 1
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    SWITCH_GATES = {"tight": (480, 240, True), "normal": (360, 120, True), "loose": (240, 0, False)}

    def _recent(self) -> tuple[int, int]:
        horizon = self.now - DAY
        while self.win_times and self.win_times[0] < horizon:
            self.win_times.popleft()
        while self.close_times and self.close_times[0] < horizon:
            self.close_times.popleft()
        return len(self.win_times), len(self.close_times)

    def _service(self) -> tuple[int, int]:
        """(on time, late) over won orders that are delivered or already overdue."""
        on_time = late = 0
        for order in self.orders.values():
            done = order["deliveredAt"]
            if all(t is not None for t in done):
                if max(done) <= order["deadline"]:
                    on_time += 1
                else:
                    late += 1
            elif order["deadline"] < self.now:
                late += 1
        return on_time, late

    def _weekend_minutes(self, deadline: int) -> int:
        """Minutes of Sat 00:00 .. Mon 07:00 between now and the deadline."""
        total = 0
        week = self.now // (7 * DAY)
        while week * 7 * DAY < deadline:
            start = week * 7 * DAY + 5 * DAY
            end = week * 7 * DAY + 7 * DAY + ACTIVE_FROM
            total += max(0, min(deadline, end) - max(self.now, start))
            week += 1
        return total

    def _weekend_pressed(self) -> bool:
        if self.weekend_if_below <= 0:
            return True
        if self.now - self._press_checked >= 30:
            self._press_checked = self.now
            on_time, late = self._service()
            wins, closes = self._recent()
            share = on_time / (on_time + late) if on_time + late >= 20 else 1.0
            warn = closes / wins if wins >= 15 else 0.0
            self._pressed = share < self.weekend_if_below or warn > self.weekend_warn_above
        MARGIN_COUNTS["weekend_pressed" if self._pressed else "weekend_relaxed"] += 1
        return self._pressed

    def _update_mode(self) -> None:
        wins, closes = self._recent()
        warn = closes / wins if wins >= 15 else 0.0
        on_time, late = self._service()
        share = on_time / (on_time + late) if on_time + late >= 20 else 1.0
        loose_ok = 2 * DAY <= self.now < 4 * DAY + 12 * 60
        mode = self.mode
        if share < self.tight_share or warn > 0.08:
            mode = "tight"
        elif mode == "tight":
            if self.now - self.mode_since >= DAY and warn < 0.04:
                mode = "normal"
        elif mode == "loose":
            if warn > 0.05 or share < 0.95 or not loose_ok:
                mode = "normal"
        elif loose_ok and wins >= 15 and share > 0.97 and warn < 0.03:
            mode = "loose"
        if mode != self.mode:
            MARGIN_COUNTS[f"switch_{self.mode}_to_{mode}"] += 1
            self.mode = mode
            self.mode_since = self.now

    def _ai_take(self, request: dict[str, Any], option: dict[str, Any], price: int, slack: int,
                 veto: str, backlog: int, nearby: int, provider: str = "") -> bool:
        import ai_decide
        provider = provider or self.ai
        wins, closes = self._recent()
        on_time, late = self._service()
        day, tod = divmod(self.now, DAY)
        state = {
            "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day % 7],
            "hour": tod // 60,
            "option": option["kind"],
            "veto": veto,
            "slack_hours": round(slack / 60 * 2) / 2,
            "weekend_before_deadline": self._weekend_minutes(option["deadline"]) > 0,
            "deadline_days_ahead": option["deadline"] // DAY - day,
            "legs": len(request["legs"]),
            "local_backlog": min(backlog, 10),
            "drivers_nearby": min(nearby, 10),
            "warnings_per_win_24h": round(closes / wins, 2) if wins else 0.0,
            "late_so_far": late,
            "on_time_share_so_far": round(on_time / (on_time + late), 3) if on_time + late else 1.0,
            "dealer_trust_orders": self.trust[request["dealerId"]],
            "price_over_reference_fee": round(price / max(1, request["referenceFeeCents"]), 1),
        }
        key = tuple(sorted(state.items()))
        if key in self.ai_cache:
            MARGIN_COUNTS["ai_cache"] += 1
            return self.ai_cache[key]
        question = ai_decide.Question(
            "take",
            "A car-transport desk decides whether to quote this order. Gross margin only counts if the "
            "world's on-time share stays at least 90%, and a late order halves this dealer's trust bonus. "
            "`slack_hours` is the estimated buffer between a cautious delivery estimate and the promised "
            "deadline; nights and weekends count as time although few drivers work then. The order failed "
            "the desk's normal safety gate for the reason in `veto`. Should the desk quote it anyway?",
            [("take", "Enough real working-hour buffer, drivers nearby, low recent warning rate and healthy "
                      "service so far: expected margin outweighs the lateness risk."),
             ("refuse", "Thin real buffer (night or weekend inflated slack, local backlog, few drivers) or "
                        "service and warnings already under pressure: a late delivery is a real risk.")])
        self.ai_calls += 1
        try:
            answers, _, _ = ai_decide.decide(provider, state, [question], timeout=6.0)
            take = answers["take"].probabilities.get("take", 0.0) >= self.ai_accept
        except Exception:  # noqa: BLE001 - fall back to the deterministic refusal
            MARGIN_COUNTS["ai_error"] += 1
            take = False
        self.ai_cache[key] = take
        return take

    def _gates(self) -> tuple[int, int, bool]:
        if self.switch:
            if self.now - self.mode_checked >= 30:
                self.mode_checked = self.now
                self._update_mode()
            MARGIN_COUNTS["gate_" + self.mode] += 1
            return self.SWITCH_GATES[self.mode]
        if not self.adapt:
            return self.slack_floor, self.extra_slack, self.backlog_veto
        won, _ = self._recent()
        if won < 15:
            MARGIN_COUNTS["gate_warmup"] += 1
            return 360, 120, True
        rate = len(self.close_times) / won
        if rate <= self.adapt_lo:
            MARGIN_COUNTS["gate_loose"] += 1
            return 240, 0, False
        if rate <= self.adapt_hi:
            MARGIN_COUNTS["gate_mid"] += 1
            return 360, 120, True
        MARGIN_COUNTS["gate_tight"] += 1
        return 480, 240, True

    # ---------------------------------------------------------------- fees
    def fees_for(self, order: dict[str, Any], cars: int) -> list[dict[str, int]]:
        steps = super().fees_for(order, cars)
        if self.level >= 7 and order["id"] not in self.urgent and self.fee_pct != 100:
            scaled = []
            for step in steps:
                fee = max(1, step["feeCents"] * self.fee_pct // 100)
                if scaled and fee <= scaled[-1]["feeCents"]:
                    continue
                scaled.append({"at": step["at"], "feeCents": fee})
            steps = scaled or steps
        if (not self.ramp_on or self.level < 7 or order["id"] in self.urgent
                or len(steps) <= 1):
            return steps
        legs = [leg for i, leg in enumerate(order["legs"])
                if order["deliveredAt"][i] is None] or order["legs"]
        ready = min(leg["pickup"]["window"]["from"] for leg in legs)
        anchor = self.now
        if ready // DAY > self.now // DAY:
            anchor = max(self.now, (ready // DAY) * DAY + ACTIVE_FROM)
            MARGIN_COUNTS["ramp_future_day"] += 1
        limit = order.get("lastPickupAt")
        limit = limit - 180 if isinstance(limit, int) else None
        scale = 2 if limit is not None and limit - self.now > 20 * 60 else 1
        if self.weekend_ramp and order["deadline"] // DAY - self.now // DAY > 1:
            scale = 1  # a weekend or more lies ahead: keep the base raise speed
            MARGIN_COUNTS["ramp_weekend"] += 1
        out = [steps[0]]
        n = len(steps)
        for i, step in enumerate(steps[1:], 1):
            t = advance_active(anchor, (step["at"] - self.now) * scale)
            if limit is not None:
                t = min(t, limit - (n - 1 - i) * 20)
            t = max(t, out[-1]["at"] + 1, self.now + i)
            out.append({"at": t, "feeCents": step["feeCents"]})
        if out[-1]["at"] != steps[-1]["at"]:
            MARGIN_COUNTS["ramp_shifted"] += 1
        return out

    # -------------------------------------------------------------- events
    def handle(self, event: dict[str, Any]) -> None:
        kind = event.get("kind")
        if event.get("seq") not in self.seen:
            if kind == "order_won":
                self.win_times.append(event["at"])
            elif kind == "deadline_close" and event["orderId"] not in self.closed_orders:
                self.closed_orders.add(event["orderId"])
                self.close_times.append(event["at"])
        if kind in ("order_won", "order_lost") and event.get("seq") not in self.seen:
            rid = event["order"]["id"] if kind == "order_won" else event["requestId"]
            origin = self.quoted_origin.pop(rid, None)
            if origin is not None:
                self._learn_region(origin, kind == "order_won")
        super().handle(event)

    def rejoin(self, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        # After a restart, rebuild the admission controller from server history.
        for event in history:
            if event["kind"] == "order_won":
                self.win_times.append(event["at"])
            elif event["kind"] == "deadline_close" and event["orderId"] not in self.closed_orders:
                self.closed_orders.add(event["orderId"])
                self.close_times.append(event["at"])
        super().rejoin(snapshot, history)


if __name__ == "__main__":
    starter.Desk = MarginDesk
    starter.main()
