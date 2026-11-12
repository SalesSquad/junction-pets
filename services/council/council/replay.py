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
    idempotency_key: str
    fence_token: int
    created: bool
    durable: bool


class ReplayStore(Protocol):
    def reserve(self, caller: Caller, first_request_id: str, envelope_digest: str,
                proposed_run_id: UUID) -> ReplayReservation:
        """Atomically reserve (tenant,user,requestId), compare payload digest.

        Return created=True only to the single owner of this execution fence;
        any replay of the same digest returns created=False, and different
        digest raises ReplayConflict. This must persist across restarts.
        """

    def is_current(self, caller: Caller, reservation: ReplayReservation) -> bool:
        """Verify this durable fence and idempotency key still belong to caller."""


def deterministic_run_id(caller: Caller, first_request_id: str) -> UUID:
    """Stable, UUID-formatted thread ID; not an authentication token."""
    return uuid5(_NAMESPACE,
                 f"chibi-council.v1:{caller.tenant_id}:{caller.user_id}:{first_request_id}")


def envelope_sha256(envelopes: list[dict]) -> str:
    import json
    return sha256(json.dumps(envelopes, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def valid_reservation(value: object, caller: Caller, first_request_id: str,
                      envelope_digest: str) -> bool:
    from re import fullmatch
    return (
        isinstance(value, ReplayReservation)
        and value.run_id == deterministic_run_id(caller, first_request_id)
        and value.envelope_digest == envelope_digest
        and isinstance(value.idempotency_key, str)
        and bool(fullmatch(r"[a-z0-9][a-z0-9._:-]{1,99}", value.idempotency_key))
        and type(value.fence_token) is int and value.fence_token > 0
        and type(value.created) is bool
        and value.durable is True
    )
