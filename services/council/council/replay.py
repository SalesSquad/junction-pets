"""Host-owned atomic replay/fencing boundary. No production store is bundled.

A reservation is an authenticated host result, NEVER a bearer grant supplied by a
model or incoming JSON. Durable atomic reserve and is_current are indispensable
for avoiding concurrent duplicate execution. They do not provide exactly-once
provider side effects across the invoke/checkpoint crash gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid5

from .core import Caller


_NAMESPACE = UUID("e46bd5c2-25aa-4da7-bdf8-189f2e85e7a1")


class ReplayConflict(Exception):
    """The same scoped request ID was already reserved for different bytes."""


@dataclass(frozen=True)
class ReplayReservation:
    run_id: UUID
    envelope_digest: str
    handoffs_digest: str
    idempotency_key: str
    fence_token: int
    created: bool
    durable: bool


class ReplayStore(Protocol):
    def reserve(self, caller: Caller, first_request_id: str, envelope_digest: str,
                proposed_run_id: UUID, handoffs_digest: str) -> ReplayReservation:
        """Atomically bind the raw v1 envelope AND normalized graph handoffs.

        A host must persist both digests in an immutable reservation record.
        Return created=True to one owner; a replay with either digest changed
        raises ReplayConflict. The host must verify both digests independently
        of checkpoint-supplied reservation metadata, across restarts.
        """

    def is_current(self, caller: Caller, reservation: ReplayReservation) -> bool:
        """Compare the ENTIRE reservation to host-persisted immutable record.

        Include envelope_digest AND handoffs_digest along with run ID,
        idempotency key and monotonic fence. The checkpoint cannot self-attest.
        """


def deterministic_run_id(caller: Caller, first_request_id: str) -> UUID:
    """Version-2 JSON-tuple UUID; not an authentication token.

    Length-delimited JSON strings prevent ':' in one scoped ID from being
    confused with the next field. The explicit domain/algorithm version is
    independent of the v1 collaboration envelope schema. Legacy run IDs are
    not tried as a fallback; existing checkpoints need an explicit migration.
    """
    import json
    name = json.dumps(["chibi-council.run-id", 2, caller.tenant_id,
                       caller.user_id, first_request_id],
                      ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return uuid5(_NAMESPACE, name)


def envelope_sha256(envelopes: list[dict]) -> str:
    import json
    return sha256(json.dumps(envelopes, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def valid_reservation(value: object, caller: Caller, first_request_id: str,
                      envelope_digest: str, handoffs_digest: str) -> bool:
    from re import fullmatch
    return (
        isinstance(value, ReplayReservation)
        and value.run_id == deterministic_run_id(caller, first_request_id)
        and isinstance(envelope_digest, str)
        and bool(fullmatch(r"[0-9a-f]{64}", envelope_digest))
        and value.envelope_digest == envelope_digest
        and isinstance(handoffs_digest, str)
        and bool(fullmatch(r"[0-9a-f]{64}", handoffs_digest))
        and value.handoffs_digest == handoffs_digest
        and isinstance(value.idempotency_key, str)
        and bool(fullmatch(r"[a-z0-9][a-z0-9._:-]{1,99}", value.idempotency_key))
        and type(value.fence_token) is int and value.fence_token > 0
        and type(value.created) is bool
        and value.durable is True
    )
