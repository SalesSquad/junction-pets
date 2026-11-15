#!/usr/bin/env python3
"""Opt-in reliability ablations on the unmodified official Spread SDK.

The default is the frozen 139% / +240-minute admission baseline. ``deadline``
changes option selection only; ``capacity`` changes supply/booking admission
only; ``learned`` adds an explicitly loaded logistic model to capacity admission;
``trust`` changes pricing only. None is a claim of 98--99% service or a final
promotion. Driver payouts, API behavior, and the existing runners stay intact.

The learned model predicts late-or-undelivered conditional on the training
policy winning an order. A threshold is an experimental decision parameter,
not a calibrated service guarantee, especially under a changed policy.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from spread import starter

from admission_experiment import AdmissionDesk
from dispatch import DAY, DRIVER_POSITION_TTL_MINUTES, SpreadGuardDesk, round_up_div


FEATURE_NAMES = (
    "slack_hours", "drive_hours", "ready_delay_hours", "eligible_supply",
    "backlog", "pending_quotes", "legs", "private", "premium", "manual",
    "low_charge_ev", "kind_next_day", "kind_3days", "weekday", "hour",
    "unbooked_age_hours",
)
MODES = ("baseline", "deadline", "capacity", "learned", "trust")
DEFAULT_LATE_THRESHOLD = 0.05
NEARBY_MINUTES = 150
MANUAL_NOTE = re.compile(r"manual|manuaal|manuell|käsivaiht", re.IGNORECASE)


def _manual_required(request: Mapping[str, Any]) -> bool:
    return bool(MANUAL_NOTE.search((request.get("note") or {}).get("text", "")))


def _near(desk: Any, a: str, b: str) -> bool:
    return a == b or desk.roads.get((a, b), math.inf) <= NEARBY_MINUTES


def _same_market(desk: Any, a: str, b: str) -> bool:
    # Nearby origins can compete for the same drivers on a directed road map.
    return _near(desk, a, b) or _near(desk, b, a)


def _outstanding(order: Mapping[str, Any]) -> bool:
    # The official starter updates deliveredAt, but leaves the old status on
    # completed orders. Never count completed work as current capacity demand.
    delivered = order.get("deliveredAt", [])
    return order.get("status") != "cancelled" and bool(delivered) and any(
        at is None for at in delivered
    )


def eligible_driver_ids(request: Mapping[str, Any], desk: Any) -> list[str]:
    """Observable eligible nearby drivers, before virtual quote reservations.

    An old position falls back to home, as in the frozen baseline. That is an
    uncertainty limitation, not evidence that the driver really returned home.
    No driver is assigned and no invitation is sent by this function.
    """
    origin = request["legs"][0]["pickup"]["placeId"]
    premium = any(leg["car"].get("premium", False) for leg in request["legs"])
    manual = _manual_required(request)
    active = set(desk.active_drivers.values())
    candidates = []
    for driver in desk.roster:
        driver_id = driver["id"]
        if driver_id in active:
            continue
        if manual and driver.get("licence") != "manual":
            continue
        if premium and (driver.get("rating", 0) < 4.8
                        or driver.get("completedGigs", 0) < 50):
            continue
        observed = desk.driver_place_observed_at.get(driver_id, -10000)
        place = (desk.driver_places.get(driver_id, driver["homePlaceId"])
                 if 0 <= desk.now - observed <= DRIVER_POSITION_TTL_MINUTES
                 else driver["homePlaceId"])
        distance = 0 if place == origin else desk.roads.get((place, origin), math.inf)
        if distance <= NEARBY_MINUTES:
            candidates.append((distance, driver_id))
    return [driver_id for _, driver_id in sorted(candidates)]


def _pending(request: Mapping[str, Any], desk: Any) -> list[dict[str, Any]]:
    origin = request["legs"][0]["pickup"]["placeId"]
    return [reservation for request_id, reservation in
            getattr(desk, "pending_quotes", {}).items()
            if request_id != request["id"] and reservation["expires_at"] > desk.now
            and _same_market(desk, origin, reservation["origin"])]


def outstanding_backlog(request: Mapping[str, Any], desk: Any) -> int:
    origin = request["legs"][0]["pickup"]["placeId"]
    return sum(_outstanding(order) and _same_market(
        desk, origin, order["legs"][0]["pickup"]["placeId"]
    ) for order in desk.orders.values() if order.get("legs"))


def unbooked_age_minutes(request: Mapping[str, Any], desk: Any) -> int:
    """Largest observed current wait, including gigs that never booked.

    This is a lower bound on an unresolved waiting time, not a fitted survival
    quantile. Current leg_gigs filters withdrawn, superseded and delivered work;
    historical entries retained in the SDK's posts dictionary do not count.
    """
    origin = request["legs"][0]["pickup"]["placeId"]
    oldest = 0
    held = set(getattr(desk, "booked", set())) | set(desk.active_drivers)
    posted_at = getattr(desk, "_posted_at", {})
    unbooked_since = getattr(desk, "_unbooked_since", {})
    for order_id, legs in desk.leg_gigs.items():
        order = desk.orders.get(order_id)
        if not order or not _outstanding(order):
            continue
        for leg_index, gig_id in legs.items():
            if gig_id in held or order["deliveredAt"][leg_index] is not None:
                continue
            pickup = order["legs"][leg_index]["pickup"]["placeId"]
            if not _same_market(desk, origin, pickup):
                continue
            post = desk.posts.get(gig_id, {})
            schedule = post.get("schedule", [])
            start = unbooked_since.get(gig_id, posted_at.get(
                gig_id, schedule[0]["at"] if schedule else desk.now
            ))
            oldest = max(oldest, max(0, desk.now - start))
    return int(oldest)


def features_for(request: Mapping[str, Any], option: Mapping[str, Any],
                 desk: Any) -> dict[str, float]:
    """Pure decision-time features in FEATURE_NAMES order; no future labels.

    Call before adding this request's own reservation. Only public request
    fields and the desk's already-observed event state are read. A retrospective
    caller must reconstruct that state chronologically; a final snapshot leaks.
    """
    legs = request["legs"]
    ready = max(desk.now, *(leg["pickup"]["window"]["from"] for leg in legs))
    values = (
        desk._slack(request, option) / 60,
        desk._route_minutes(request) / 60,
        (ready - desk.now) / 60,
        len(eligible_driver_ids(request, desk)),
        outstanding_backlog(request, desk),
        len(_pending(request, desk)),
        len(legs),
        any(leg[stop].get("privateAddress", False) for leg in legs
            for stop in ("pickup", "delivery")),
        any(leg["car"].get("premium", False) for leg in legs),
        _manual_required(request),
        any(leg["car"].get("electric", False)
            and leg["car"].get("chargePercent") is not None
            and leg["car"]["chargePercent"] < 30 for leg in legs),
        option["kind"] == "next_day", option["kind"] == "within_3_days",
        (desk.now // DAY) % 7, (desk.now % DAY) / 60,
        unbooked_age_minutes(request, desk) / 60,
    )
    result = dict(zip(FEATURE_NAMES, map(float, values)))
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("non-finite decision-time feature")
    return result


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _threshold(value: Any) -> float:
    value = _number(value, "late threshold")
    if not 0 < value < 1:
        raise ValueError("late threshold must be strictly between 0 and 1")
    return value


def _vector(value: Any, label: str, size: int) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must contain exactly {size} numbers")
    return tuple(_number(item, label) for item in value)


@dataclass(frozen=True)
class LogisticRiskModel:
    center: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]  # intercept first, standardized inputs
    training: dict[str, Any]
    threshold: float

    def predict(self, features: Mapping[str, float]) -> float:
        try:
            values = [_number(features[name], name) for name in FEATURE_NAMES]
        except KeyError as error:
            raise ValueError(f"missing model feature: {error.args[0]}") from error
        z = self.coefficients[0] + math.fsum(
            coefficient * ((value - center) / scale)
            for coefficient, value, center, scale in
            zip(self.coefficients[1:], values, self.center, self.scale)
        )
        if not math.isfinite(z):
            raise ValueError("non-finite model score")
        # Stable sigmoid also handles extreme but finite fixture/model scores.
        return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def load_model(path: str | Path) -> LogisticRiskModel:
    """Strict explicit artifact loading; never silently use a missing model."""
    artifact_path = Path(path)
    if artifact_path.stat().st_size > 1_048_576:
        raise ValueError("model JSON exceeds 1 MiB")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(artifact, dict) or type(artifact.get("schemaVersion")) is not int \
            or artifact["schemaVersion"] != 1:
        raise ValueError("model schemaVersion must be integer 1")
    if artifact.get("featureNames") != list(FEATURE_NAMES):
        raise ValueError("model featureNames do not match the decision-time contract")
    center = _vector(artifact.get("center"), "center", len(FEATURE_NAMES))
    scale = _vector(artifact.get("scale"), "scale", len(FEATURE_NAMES))
    if any(value <= 0 for value in scale):
        raise ValueError("every model scale must be positive")
    coefficients = _vector(artifact.get("coefficients"), "coefficients", len(FEATURE_NAMES) + 1)
    training = artifact.get("training")
    if not isinstance(training, dict) or not re.fullmatch(
        r"[0-9a-f]{40}", str(training.get("source_sha", ""))
    ):
        raise ValueError("model training.source_sha must identify its source commit")
    worlds = training.get("world_ids")
    if not isinstance(worlds, list) or not worlds or any(
        not isinstance(world, str) or not world for world in worlds
    ) or len(set(worlds)) != len(worlds):
        raise ValueError("model training.world_ids must be nonempty unique strings")
    return LogisticRiskModel(center, scale, coefficients, training,
                             _threshold(artifact.get("threshold", DEFAULT_LATE_THRESHOLD)))


class ReliabilityDesk(AdmissionDesk):
    """Explicit ablations with the same official SDK and frozen fee policy."""

    def __init__(self, world: Any, level: int, now: int, *, mode: str | None = None,
                 model_path: str | Path | None = None, late_threshold: float | None = None):
        self.mode = mode or os.getenv("SPREAD_RELIABILITY_MODE", "baseline")
        if self.mode not in MODES:
            raise ValueError(f"reliability mode must be one of {MODES}")
        model_path = model_path or os.getenv("SPREAD_RELIABILITY_MODEL")
        self.model = load_model(model_path) if model_path else None
        if self.mode == "learned" and self.model is None:
            raise ValueError("learned mode requires an explicit model JSON")
        if late_threshold is None and os.getenv("SPREAD_RELIABILITY_LATE_THRESHOLD"):
            late_threshold = float(os.environ["SPREAD_RELIABILITY_LATE_THRESHOLD"])
        self.late_threshold = _threshold(late_threshold if late_threshold is not None else
                                        self.model.threshold if self.model else DEFAULT_LATE_THRESHOLD)
        if os.getenv("SPREAD_GUARD_POLICY", "risk_budget") != "risk_budget":
            raise ValueError("reliability ablations require the frozen risk_budget fee policy")
        self.pending_quotes: dict[str, dict[str, Any]] = {}
        self._posted_at: dict[str, int] = {}
        self._unbooked_since: dict[str, int] = {}
        self.counts: Counter[str] = Counter()
        # AdmissionDesk's initializer only loads its configurable knobs. Call
        # its state-owning parent directly so unrelated old admission env vars
        # cannot silently change this frozen comparison or its validations.
        SpreadGuardDesk.__init__(self, world, level, now)
        self.quote_pct, self.extra_slack, self.surge_per_backlog = 139, 240, 0

    def feature_vector(self, request: dict[str, Any], option: dict[str, Any]) -> list[float]:
        features = features_for(request, option, self)
        return [features[name] for name in FEATURE_NAMES]

    def _free_candidates(self, request: Mapping[str, Any]) -> list[str]:
        available = eligible_driver_ids(request, self)
        # A reservation is planning capacity, never an actual SDK assignment.
        reservations = [item for request_id, item in self.pending_quotes.items()
                        if request_id != request["id"] and item["expires_at"] > self.now]
        held = {item["driver_id"] for item in reservations if item["driver_id"] is not None}
        available = [driver for driver in available if driver not in held]
        unknown = sum(item["driver_id"] is None for item in _pending(request, self))
        return available[unknown:]

    def _record_intent(self, request: Mapping[str, Any], competitive: bool) -> None:
        self.pending_quotes = {key: item for key, item in self.pending_quotes.items()
                               if item["expires_at"] > self.now and key != request["id"]}
        if competitive:
            candidates = self._free_candidates(request)
            self.pending_quotes[request["id"]] = {
                "expires_at": request["respondBy"],
                "origin": request["legs"][0]["pickup"]["placeId"],
                "driver_id": candidates[0] if candidates else None,
            }

    def quote(self, request: dict[str, Any]) -> None:
        if self.mode == "baseline" or self.level < 7:
            before = len(self.outbox)
            super().quote(request)
            if len(self.outbox) > before:
                prices = self.outbox[-1]["prices"]
                competitive = any(prices.get(option["kind"], math.inf)
                                  < option["listPriceCents"] * 20 for option in request["options"])
                self._record_intent(request, competitive)
            return
        self.requests[request["id"]] = request
        self.counts["requests"] += 1
        if self.now >= request["respondBy"] or not request["options"]:
            self.counts["expired"] += 1
            self._record_intent(request, False)
            return
        origin = request["legs"][0]["pickup"]["placeId"]
        capacity = self.mode in ("capacity", "learned")
        backlog = outstanding_backlog(request, self) if capacity else self._local_backlog(origin)
        nearby = len(self._free_candidates(request)) if capacity else self._driver_count(origin)
        booking_buffer = self._booking_delay_buffer()
        if capacity:
            booking_buffer = max(booking_buffer, min(720, unbooked_age_minutes(request, self)))
        factor_bps = 13900
        if self.mode == "trust" and self.level >= 8:
            # Capture only a conservative fraction of the published acceptance
            # premium. Conversion and future trust value still require evidence.
            factor_bps += min(1000, max(0, self.trust[request["dealerId"]]) * 40)
        eligible = []
        for option in request["options"]:
            slack = self._slack(request, option)
            floor = 480 + booking_buffer + (240 if option["kind"] == "next_day" else 0)
            if slack < floor:
                self.counts["time_veto"] += 1
                continue
            if (capacity or self.roster) and nearby < 2:
                self.counts["driver_veto"] += 1
                continue
            if backlog >= 5 and slack < 900:
                self.counts["backlog_veto"] += 1
                continue
            price = round_up_div(option["listPriceCents"] * factor_bps, 10000)
            if price * 100 < request["referenceFeeCents"] * 135:
                self.counts["fee_veto"] += 1
                continue
            projected = price - round_up_div(request["referenceFeeCents"] * 120, 100)
            risk = self.model.predict(features_for(request, option, self)) if self.mode == "learned" else None
            if risk is not None and risk > self.late_threshold:
                self.counts["model_veto"] += 1
                continue
            # Timely-contribution proxy; not the sponsor's exact expected P&L.
            score = projected * (1 - risk) if risk is not None else projected + min(300, slack // 10)
            eligible.append({"option": option, "price": price, "projected": projected,
                             "slack": slack, "score": score})
        if eligible:
            if self.mode == "deadline":
                best_margin = max(item["projected"] for item in eligible)
                choices = [item for item in eligible if item["projected"] * 100 >= best_margin * 90]
                chosen = max(choices, key=lambda item: (min(1440, item["slack"]),
                                                        item["projected"], item["option"]["deadline"]))
            else:
                chosen = max(eligible, key=lambda item: (item["score"], item["option"]["deadline"]))
            prices = {chosen["option"]["kind"]: chosen["price"]}
            self.counts["competitive"] += 1
        else:
            option = request["options"][0]
            prices = {option["kind"]: min(2**31 - 1, option["listPriceCents"] * 20)}
            self.counts["declined"] += 1
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})
        self._record_intent(request, bool(eligible))

    def carry(self, action: dict[str, Any], gig_id: str) -> None:
        self._posted_at.setdefault(gig_id, self.now)
        self._unbooked_since.setdefault(gig_id, self._posted_at[gig_id])
        super().carry(action, gig_id)

    def read_results(self, actions: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
        super().read_results(actions, results)
        for action, result in zip(actions, results):
            if action["type"] == "quote" and result.get("ok") is False:
                self.pending_quotes.pop(action["requestId"], None)

    def handle(self, event: dict[str, Any]) -> None:
        if event["seq"] in self.seen:
            return
        if event["kind"] in ("order_won", "order_changed"):
            self.pending_quotes.pop(event["order"]["id"], None)
        elif event["kind"] == "order_lost":
            self.pending_quotes.pop(event["requestId"], None)
        elif event["kind"] == "order_cancelled":
            self.pending_quotes.pop(event["orderId"], None)
        elif event["kind"] == "gig_booked":
            self._unbooked_since.pop(event["gigId"], None)
        elif event["kind"] in ("gig_dropped", "no_show"):
            # Booked time is not censored waiting time. A reopened gig begins
            # a new unresolved interval at the observable drop/no-show event.
            self._unbooked_since[event["gigId"]] = event["at"]
        super().handle(event)

    def rejoin(self, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        self.pending_quotes.clear()
        self._posted_at = {gig["id"]: gig["postedAt"] for gig in snapshot["gigs"]}
        self._unbooked_since = dict(self._posted_at)
        for event in history:
            if event["kind"] == "gig_booked":
                self._unbooked_since.pop(event["gigId"], None)
            elif event["kind"] in ("gig_dropped", "no_show"):
                self._unbooked_since[event["gigId"]] = event["at"]
        super().rejoin(snapshot, history)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument("--mode", choices=MODES, default=os.getenv("SPREAD_RELIABILITY_MODE", "baseline"))
    parser.add_argument("--model", default=os.getenv("SPREAD_RELIABILITY_MODEL"))
    parser.add_argument("--late-threshold", type=float, default=None)
    args, sdk_args = parser.parse_known_args(argv)
    if "--help" in sdk_args or "-h" in sdk_args:
        parser.print_help()
    else:
        # Validate before starter.main creates or joins any official world.
        try:
            model = load_model(args.model) if args.model else None
            if args.mode not in MODES:
                raise ValueError(f"unknown reliability mode {args.mode!r}")
            if args.mode == "learned" and model is None:
                raise ValueError("learned mode requires --model or SPREAD_RELIABILITY_MODEL")
            if args.late_threshold is not None:
                _threshold(args.late_threshold)
            elif os.getenv("SPREAD_RELIABILITY_LATE_THRESHOLD"):
                _threshold(float(os.environ["SPREAD_RELIABILITY_LATE_THRESHOLD"]))
            if os.getenv("SPREAD_GUARD_POLICY", "risk_budget") != "risk_budget":
                raise ValueError("reliability ablations require risk_budget")
        except (OSError, ValueError) as error:
            parser.error(str(error))

    class ConfiguredDesk(ReliabilityDesk):
        def __init__(self, world: Any, level: int, now: int):
            super().__init__(world, level, now, mode=args.mode, model_path=args.model,
                             late_threshold=args.late_threshold)

    previous_desk, previous_argv = starter.Desk, sys.argv
    starter.Desk, sys.argv = ConfiguredDesk, [sys.argv[0], *sdk_args]
    try:
        starter.main()
    finally:
        starter.Desk, sys.argv = previous_desk, previous_argv


if __name__ == "__main__":
    main()
