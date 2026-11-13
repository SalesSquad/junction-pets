"""Host-injected PostgreSQL replay reservations; no connection or authority default.

The host supplies an exclusive, idle psycopg connection context factory (for
example a dedicated pool's ``connection`` method). This adapter never obtains
credentials, migrates schemas, calls a provider or takes over an existing run.
"""
from __future__ import annotations

from contextlib import contextmanager
import re
from typing import Callable, ContextManager, Iterator
from uuid import UUID

from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from .core import Caller
from .replay import ReplayConflict, ReplayReservation, deterministic_run_id


_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{1,99}")
_DIGEST = re.compile(r"[a-f0-9]{64}")
_MAX_FENCE = 9223372036854775807
_COLUMNS = "run_id, envelope_digest, handoffs_digest, idempotency_key, fence_token, active_pet, active"


class ReplayStoreUnavailable(RuntimeError):
    """A safe bounded failure; database exceptions/connection strings stay private."""


def _caller_valid(caller: object) -> bool:
    return isinstance(caller, Caller) and all(
        isinstance(value, str) and _ID.fullmatch(value) is not None
        for value in (caller.tenant_id, caller.user_id, caller.active_pet)
    )


def _reservation_valid(reservation: object) -> bool:
    return (
        isinstance(reservation, ReplayReservation)
        and isinstance(reservation.run_id, UUID)
        and all(isinstance(value, str) and _DIGEST.fullmatch(value) is not None
                for value in (reservation.envelope_digest, reservation.handoffs_digest))
        and reservation.idempotency_key == "host.run." + reservation.run_id.hex
        and type(reservation.fence_token) is int
        and 0 < reservation.fence_token <= _MAX_FENCE
        and type(reservation.created) is bool
        and reservation.durable is True
    )


class PostgresReplayStore:
    """Implements ReplayStore with committed, immutable PostgreSQL reservations.

    An identical replay is never a fresh execution claim. Invalidations are
    terminal: no lease expiry or automatic provider retry is inferred here.
    """

    def __init__(self, connection_factory: Callable[[], ContextManager[Connection]]):
        if not callable(connection_factory):
            raise TypeError("A host-owned connection context factory is required")
        self._connection_factory = connection_factory

    @contextmanager
    def _cursor(self) -> Iterator:
        try:
            with self._connection_factory() as connection:
                if connection.info.transaction_status != TransactionStatus.IDLE:
                    raise ReplayStoreUnavailable("Replay store requires an exclusive idle connection")
                with connection.transaction():
                    with connection.cursor(row_factory=dict_row) as cursor:
                        # A separate SELECT after a conflicting INSERT must see
                        # the winner's committed row, including under contention.
                        cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                        cursor.execute("SET LOCAL synchronous_commit = on")
                        cursor.execute("SET LOCAL statement_timeout = '5s'")
                        cursor.execute("SET LOCAL lock_timeout = '2s'")
                        yield cursor
            # The transaction AND connection context have exited before callers
            # can receive durable=True. A failed commit cannot return a claim.
        except (ReplayConflict, ReplayStoreUnavailable):
            raise
        except Exception:
            raise ReplayStoreUnavailable("PostgreSQL replay store unavailable") from None

    def reserve(self, caller: Caller, first_request_id: str, envelope_digest: str,
                proposed_run_id: UUID, handoffs_digest: str) -> ReplayReservation:
        if (not _caller_valid(caller) or not isinstance(first_request_id, str)
                or _ID.fullmatch(first_request_id) is None
                or not all(isinstance(value, str) and _DIGEST.fullmatch(value) is not None
                           for value in (envelope_digest, handoffs_digest))
                or not isinstance(proposed_run_id, UUID)
                or proposed_run_id != deterministic_run_id(caller, first_request_id)):
            raise ValueError("Invalid replay reservation scope")
        idempotency_key = "host.run." + proposed_run_id.hex
        with self._cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO junction_council.replay_reservations
                    (tenant_id, user_id, first_request_id, active_pet, run_id,
                     envelope_digest, handoffs_digest, idempotency_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id,user_id,first_request_id) DO NOTHING
                    RETURNING {_COLUMNS}""",
                (caller.tenant_id, caller.user_id, first_request_id, caller.active_pet,
                 proposed_run_id, envelope_digest, handoffs_digest, idempotency_key),
            )
            row = cursor.fetchone()
            created = row is not None
            if row is None:
                cursor.execute(
                    f"""SELECT {_COLUMNS} FROM junction_council.replay_reservations
                        WHERE tenant_id=%s AND user_id=%s AND first_request_id=%s
                        FOR SHARE""", (caller.tenant_id, caller.user_id, first_request_id),
                )
                row = cursor.fetchone()
            if row is None:
                raise ReplayStoreUnavailable("Replay reservation not readable")
            if (row["run_id"] != proposed_run_id or row["envelope_digest"] != envelope_digest
                    or row["handoffs_digest"] != handoffs_digest
                    or row["active_pet"] != caller.active_pet
                    or row["idempotency_key"] != idempotency_key or row["active"] is not True):
                raise ReplayConflict("Request scope conflicts with its durable reservation")
            reservation = ReplayReservation(
                run_id=row["run_id"], envelope_digest=row["envelope_digest"],
                handoffs_digest=row["handoffs_digest"], idempotency_key=row["idempotency_key"],
                fence_token=row["fence_token"], created=created, durable=True,
            )
            if not _reservation_valid(reservation):
                raise ReplayStoreUnavailable("Invalid persisted replay reservation")
        return reservation

    def is_current(self, caller: Caller, reservation: ReplayReservation) -> bool:
        if not _caller_valid(caller) or not _reservation_valid(reservation):
            return False
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT first_request_id FROM junction_council.replay_reservations
                   WHERE tenant_id=%s AND user_id=%s AND active_pet=%s AND run_id=%s
                     AND envelope_digest=%s AND handoffs_digest=%s AND idempotency_key=%s
                     AND fence_token=%s AND active=true""",
                self._bindings(caller, reservation),
            )
            row = cursor.fetchone()
            # A legacy delimiter-derived persisted ID must not bypass the v2
            # tuple check through direct store use outside the graph validator.
            current = row is not None and deterministic_run_id(
                caller, row["first_request_id"]) == reservation.run_id
        return current

    def invalidate(self, caller: Caller, reservation: ReplayReservation) -> bool:
        """Host-only terminal cancellation; does not grant retry or model access."""
        if (not _caller_valid(caller) or not _reservation_valid(reservation)
                or reservation.fence_token == _MAX_FENCE):
            return False
        with self._cursor() as cursor:
            cursor.execute(
                """UPDATE junction_council.replay_reservations
                   SET active=false, fence_token=fence_token+1
                   WHERE tenant_id=%s AND user_id=%s AND active_pet=%s AND run_id=%s
                     AND envelope_digest=%s AND handoffs_digest=%s AND idempotency_key=%s
                     AND fence_token=%s AND active=true RETURNING fence_token""",
                self._bindings(caller, reservation),
            )
            invalidated = cursor.fetchone() is not None
        return invalidated

    @staticmethod
    def _bindings(caller: Caller, reservation: ReplayReservation) -> tuple:
        return (caller.tenant_id, caller.user_id, caller.active_pet, reservation.run_id,
                reservation.envelope_digest, reservation.handoffs_digest,
                reservation.idempotency_key, reservation.fence_token)
