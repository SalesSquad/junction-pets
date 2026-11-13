"""Unit tests. Real PostgreSQL proof is the explicit test_postgres_replay_pg gate."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
import importlib.util
from pathlib import Path

import psycopg
from psycopg.pq import TransactionStatus
import pytest

from council.core import Caller
from council.postgres_replay import PostgresReplayStore, ReplayStoreUnavailable
from council.replay import ReplayConflict, ReplayReservation, deterministic_run_id


CALLER = Caller("tenant.synthetic", "user.synthetic", "junction.aiven")
REQUEST = "request.synthetic"
RUN = deterministic_run_id(CALLER, REQUEST)
DIGEST = "a" * 64
HANDOFFS = "b" * 64


def stored_row(**overrides):
    return dict(run_id=RUN, envelope_digest=DIGEST, handoffs_digest=HANDOFFS,
                idempotency_key="host.run." + RUN.hex, fence_token=1,
                active_pet=CALLER.active_pet, active=True, **overrides)


def reservation(**overrides):
    values = dict(run_id=RUN, envelope_digest=DIGEST, handoffs_digest=HANDOFFS,
                  idempotency_key="host.run." + RUN.hex, fence_token=1,
                  created=True, durable=True)
    return ReplayReservation(**(values | overrides))


class StubConnection:
    """Fault-injection seam; does not simulate SQL locking or durability."""
    def __init__(self, rows, *, failure=None, status=TransactionStatus.IDLE):
        self.rows = iter(rows)
        self.events = []
        self.failure = failure
        self.info = SimpleNamespace(transaction_status=status)

    @contextmanager
    def connection(self):
        self.events.append("connection-enter")
        yield self
        self.events.append("connection-exit")

    @contextmanager
    def transaction(self):
        self.events.append("transaction-enter")
        yield
        if self.failure == "commit":
            raise psycopg.OperationalError("SECRET_DATABASE_URI")
        self.events.append("committed")

    @contextmanager
    def cursor(self, **kwargs):
        yield self

    def execute(self, sql, params=None):
        self.events.append((sql, params))
        if self.failure == "query":
            raise psycopg.OperationalError("SECRET_DATABASE_URI")

    def fetchone(self):
        return next(self.rows)


def reserve(store, **values):
    args = dict(caller=CALLER, first_request_id=REQUEST, envelope_digest=DIGEST,
                proposed_run_id=RUN, handoffs_digest=HANDOFFS)
    return store.reserve(**(args | values))


def test_returns_claim_only_after_transaction_and_connection_commit():
    connection = StubConnection([stored_row()])
    result = reserve(PostgresReplayStore(connection.connection))
    assert result == reservation()
    assert connection.events[-2:] == ["committed", "connection-exit"]
    sql_calls = [event for event in connection.events if isinstance(event, tuple)]
    assert sql_calls[0][0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
    assert any("synchronous_commit = on" in sql for sql, _ in sql_calls)
    assert sql_calls[-1][1] == (CALLER.tenant_id, CALLER.user_id, REQUEST, CALLER.active_pet,
                               RUN, DIGEST, HANDOFFS, "host.run." + RUN.hex)


def test_existing_identical_reservation_does_not_create_an_execution_claim():
    connection = StubConnection([None, stored_row()])
    result = reserve(PostgresReplayStore(connection.connection))
    assert result == reservation(created=False)


@pytest.mark.parametrize("change", [
    {"run_id": uuid4()}, {"envelope_digest": "c" * 64},
    {"handoffs_digest": "c" * 64}, {"active_pet": "junction.other"},
    {"idempotency_key": "host.run.other"}, {"active": False},
])
def test_existing_scope_mismatch_is_not_rewritten(change):
    row = stored_row() | change
    connection = StubConnection([None, row])
    with pytest.raises(ReplayConflict):
        reserve(PostgresReplayStore(connection.connection))
    assert not any("UPDATE" in event[0] for event in connection.events if isinstance(event, tuple))


@pytest.mark.parametrize("change", [
    {"caller": Caller("tenant\nunsafe", "user.synthetic", "junction.aiven")},
    {"first_request_id": "request'; DROP TABLE x;--"},
    {"proposed_run_id": uuid4()}, {"proposed_run_id": str(RUN)},
    {"envelope_digest": "A" * 64}, {"handoffs_digest": "x"},
])
def test_invalid_input_rejected_before_opening_database(change):
    connection = StubConnection([])
    with pytest.raises(ValueError):
        reserve(PostgresReplayStore(connection.connection), **change)
    assert connection.events == []


@pytest.mark.parametrize("failure", ["query", "commit"])
def test_query_or_commit_failure_never_returns_durable_claim_or_secret(failure):
    connection = StubConnection([stored_row()], failure=failure)
    with pytest.raises(ReplayStoreUnavailable) as caught:
        reserve(PostgresReplayStore(connection.connection))
    assert "SECRET_DATABASE_URI" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_existing_host_transaction_is_refused():
    connection = StubConnection([], status=TransactionStatus.INTRANS)
    with pytest.raises(ReplayStoreUnavailable, match="idle"):
        reserve(PostgresReplayStore(connection.connection))
    assert "transaction-enter" not in connection.events


@pytest.mark.parametrize("change", [
    {"fence_token": True}, {"fence_token": 0}, {"fence_token": 2**63},
    {"created": 1}, {"durable": False}, {"idempotency_key": "arbitrary"},
    {"handoffs_digest": "no"},
])
def test_invalid_reservation_denied_without_database_access(change):
    connection = StubConnection([])
    store = PostgresReplayStore(connection.connection)
    value = reservation(**change)
    assert store.is_current(CALLER, value) is False
    assert store.invalidate(CALLER, value) is False
    assert connection.events == []


def test_current_query_binds_every_host_scope_and_both_digests():
    connection = StubConnection([{"current": 1}])
    assert PostgresReplayStore(connection.connection).is_current(CALLER, reservation()) is True
    sql, params = [event for event in connection.events if isinstance(event, tuple)][-1]
    assert "active=true" in sql
    assert params == (CALLER.tenant_id, CALLER.user_id, CALLER.active_pet, RUN,
                      DIGEST, HANDOFFS, "host.run." + RUN.hex, 1)


def test_no_matching_persisted_record_is_stale():
    connection = StubConnection([None])
    assert PostgresReplayStore(connection.connection).is_current(CALLER, reservation()) is False


def test_terminal_invalidation_is_bound_to_exact_existing_fence():
    connection = StubConnection([{"fence_token": 2}])
    assert PostgresReplayStore(connection.connection).invalidate(CALLER, reservation()) is True
    sql, params = [event for event in connection.events if isinstance(event, tuple)][-1]
    assert "active=false, fence_token=fence_token+1" in sql
    assert params[-1] == 1


def test_invalidation_cannot_overflow_postgresql_bigint():
    connection = StubConnection([])
    assert PostgresReplayStore(connection.connection).invalidate(
        CALLER, replace(reservation(), fence_token=2**63 - 1)) is False
    assert connection.events == []


def _pg_gate_module():
    spec = importlib.util.spec_from_file_location("replay_pg_gate", Path(__file__).with_name("test_postgres_replay_pg.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("dsn", [None, "", "dbname=production host=localhost user=test",
    "dbname=junction_council_test_a host=db.example.com user=test",
    "dbname=junction_council_test_a user=test",
    "dbname=junction_council_test_a host=localhost",
    "dbname=junction_council_test_a host=localhost,db.example.com user=test",
    "dbname=junction_council_test_a host=localhost user=test service=production",
])
def test_real_gate_rejects_missing_remote_or_implicit_database(dsn):
    with pytest.raises(ValueError):
        _pg_gate_module().checked_test_dsn(dsn)


def test_real_gate_accepts_explicit_local_synthetic_socket_database():
    dsn = "dbname=junction_council_test_a host=/tmp/isolated-council-socket user=test"
    assert _pg_gate_module().checked_test_dsn(dsn) == dsn
