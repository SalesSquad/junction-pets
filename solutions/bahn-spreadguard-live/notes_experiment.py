"""Opt-in notes ablation over the frozen ReliabilityDesk baseline.

Only fully scoped, unambiguous notes containing supported readiness/release or
licence/plate facts are handled here. Other notes keep the baseline behavior.
The module does not install itself into the SDK or start any sponsor world.
"""
from __future__ import annotations

from collections import Counter
import os
from typing import Any

from spread import starter

from reliability_experiment import ReliabilityDesk
from typed_notes import NoteConstraints, note_adjusted_request, parse_notes


SUPPORTED = ("readyAt", "releaseAt", "manualRequired", "platesRequired")
UNSUPPORTED = ("pickupBefore", "pickupHours", "deliveryHours", "noteDeadline", "summerTyres")


def supported_constraints(request: dict[str, Any]) -> tuple[NoteConstraints | None, str]:
    """All-or-note admission keeps unsupported timing out of this first ablation.

Unknown can include harmless filler. This intentionally sacrifices coverage
and exposes counts rather than treating missing parser assertions as false.
"""
    constraints = parse_notes(request)
    if len(request.get("legs", [])) != 1 or constraints.scope != "single_leg":
        return None, "unscoped"
    if constraints.ambiguous:
        return None, "ambiguous"
    if constraints.unknown:
        return None, "unknown"
    if any(getattr(constraints, name) is not None for name in UNSUPPORTED):
        return None, "unsupported_field"
    fields = [name for name in SUPPORTED if getattr(constraints, name) is not None]
    if not fields:
        return None, "no_supported_fact"
    if any(not constraints.evidence.get(name) for name in fields):
        return None, "missing_evidence"
    return constraints, "supported"


class NotesDesk(ReliabilityDesk):
    """Baseline prices/fees, with bounded note-aware slack and single-car posts.

`mode="notes"` is accepted only as a study-harness label. The inherited policy
always runs `mode="baseline"`; learned/capacity/trust mixtures are rejected.
"""

    def __init__(self, world: Any, level: int, now: int, *, mode: str = "notes",
                 model_path: str | None = None, late_threshold: float | None = None):
        if mode not in ("notes", "baseline"):
            raise ValueError("NotesDesk is a standalone notes-versus-baseline ablation")
        if model_path or os.getenv("SPREAD_RELIABILITY_MODEL"):
            raise ValueError("NotesDesk does not combine the notes ablation with a learned model")
        super().__init__(world, level, now, mode="baseline", model_path=None,
                         late_threshold=late_threshold)
        self.note_counts: Counter[str] = Counter()
        self.note_seen_requests: set[str] = set()
        self.note_eligible_requests: set[str] = set()
        self.note_changed_post_orders: set[str] = set()
        self.note_wire_changed_orders: set[str] = set()

    def quote(self, request: dict[str, Any]) -> None:
        constraints, reason = supported_constraints(request)
        if request["id"] not in self.note_seen_requests:
            self.note_seen_requests.add(request["id"])
            self.note_counts["requests"] += 1
            self.note_counts["eligibility_" + reason] += 1
            if constraints is not None:
                self.note_eligible_requests.add(request["id"])
        super().quote(request)

    def _slack(self, request: dict[str, Any], option: dict[str, Any]) -> int:
        constraints, _ = supported_constraints(request)
        if constraints is None:
            return super()._slack(request, option)
        try:
            adjusted = note_adjusted_request(request, constraints)
        except ValueError:
            # A proven lower bound beyond the slot is infeasible, not licence
            # to widen a private pickup or silently ignore the note.
            return -10000
        adjusted["note"] = None
        adjusted_option = next(item for item in adjusted["options"] if item["kind"] == option["kind"])
        return super()._slack(adjusted, adjusted_option)

    def post(self, order: dict[str, Any], legs: list[int],
             retry: starter.Retry = starter.Retry()) -> None:
        request = self.requests[order["id"]]
        constraints, reason = supported_constraints(request)
        if constraints is None or len(order["legs"]) != 1 or legs != [0]:
            self.note_counts["post_baseline_" + reason] += 1
            super().post(order, legs, retry)
            return
        lower = max(retry.pickup_from,
                    constraints.readyAt if constraints.readyAt is not None else 0,
                    constraints.releaseAt if constraints.releaseAt is not None else 0)
        pickup = order["legs"][0]["pickup"]
        if pickup.get("privateAddress", False) and lower > pickup["window"]["to"]:
            # Normal quote admission rejects this case. If an already-won order
            # changes into it, never invent an extended private seller slot.
            self.note_counts["unrepresentable_private_bound"] += 1
            return
        bounded_retry = starter.Retry(
            lower,
            manual_licence=retry.manual_licence or constraints.manualRequired is True,
            plates=retry.plates or constraints.platesRequired is True,
        )
        # The order is deliberately ORIGINAL. Passing a modified order would
        # make narrower() consider the new readiness part of the base window
        # and omit the lower bound from the actual API action.
        stops = starter.without_windows(starter.stops_for(order, legs, None, bounded_retry), self.now)
        audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]),
                    "manualLicence": bounded_retry.manual_licence}
        action = {"type": "post", "stops": stops, "audience": audience,
                  "schedule": self.fees_for(order, len(legs))}
        # For one leg the pinned SDK baseline only appends one action; it does
        # not send. Replace that unsent action, allowing exact wire comparison
        # without duplicating its parser or changing its fee policy.
        before = len(self.outbox)
        super().post(order, legs, retry)
        if len(self.outbox) != before + 1 or self.outbox[-1].get("type") != "post":
            raise RuntimeError("Pinned single-leg baseline post contract changed")
        baseline_action = self.outbox.pop()
        self.outbox.append(action)
        if action != baseline_action:
            self.note_wire_changed_orders.add(order["id"])
            self.note_counts["post_actions_differing_from_baseline"] += 1
        self.note_counts["supported_posts"] += 1
        # Report actual wire-action change against the note-free, same-retry
        # action; eligibility and genuine constraint additions are distinct.
        if lower > max(retry.pickup_from, pickup["window"]["from"]) \
                or (constraints.manualRequired is True and not retry.manual_licence) \
                or (constraints.platesRequired is True and not retry.plates):
            self.note_changed_post_orders.add(order["id"])
            self.note_counts["constraint_added_posts"] += 1

    def notes_summary(self) -> dict[str, Any]:
        return {"counts": dict(sorted(self.note_counts.items())),
                "unique_requests": len(self.note_seen_requests),
                "eligible_requests": len(self.note_eligible_requests),
                "orders_with_added_post_constraints": len(self.note_changed_post_orders),
                "orders_with_changed_post_actions": len(self.note_wire_changed_orders),
                "fallback_policy": "baseline_for_any_unknown_ambiguous_or_unsupported_note",
                "supported_fields": list(SUPPORTED),
                "official_deadlines_changed": False}
