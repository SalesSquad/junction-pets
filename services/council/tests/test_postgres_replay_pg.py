"""Explicit real-PG gate, not a skipped/default pytest fixture or mock success.

Run with PYTHONPATH=services/council and JUNCTION_COUNCIL_TEST_DATABASE_URL set.
Missing/unsafe test DB exits 3. Uses only an explicit separate local test DB;
never provisions accounts, connects to Aiven or prints the connection string.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import os
import re
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

from council.core import Caller
from council.postgres_replay import PostgresReplayStore
from council.replay import ReplayConflict, deterministic_run_id


def require(value, label):
    if not value:
        raise AssertionError(label)


def checked_test_dsn(value):
    if not isinstance(value, str) or not value:
        raise ValueError("TEST_DB_UNAVAILABLE")
    parsed = conninfo_to_dict(value)
    host = parsed.get("host", "")
    local_host = host in {"localhost", "127.0.0.1", "::1"} or (
        host.startswith("/") and "," not in host and "\x00" not in host)
    if (not re.fullmatch(r"junction_council_test_[a-z0-9_]+", parsed.get("dbname", ""))
            or not local_host
            or not parsed.get("user")
            or set(parsed) - {"dbname", "host", "port", "user", "password", "sslmode", "connect_timeout"}):
        raise ValueError("UNSAFE_TEST_DB")
    return value


def run_pg_gate(dsn):
    dsn = checked_test_dsn(dsn)
    # Explicit host/user/db are mandatory, and inherited libpq configuration
    # must not silently redirect a supposedly disposable local connection.
    if any(key.startswith("PG") and key not in {"PGDATA", "PGBIN"} for key in os.environ):
        raise ValueError("INHERITED_LIBPQ_CONFIGURATION")
    factory = lambda: psycopg.connect(dsn, connect_timeout=3)
    with factory() as connection:
        connection.execute(Path(__file__).parents[1].joinpath(
            "migrations/001_replay_reservations.sql").read_text())
    store = PostgresReplayStore(factory)
    unique = uuid4().hex
    caller = Caller("tenant." + unique, "user.synthetic", "junction.aiven")
    request_id = "request.concurrent"
    run_id = deterministic_run_id(caller, request_id)
    envelope, handoffs = "a" * 64, "b" * 64
    barrier = Barrier(8)

    def simultaneous_reserve(_):
        barrier.wait(timeout=10)
        return store.reserve(caller, request_id, envelope, run_id, handoffs)

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(simultaneous_reserve, range(8)))
    require(sum(result.created for result in results) == 1, "exactly one concurrent execution owner")
    original = next(result for result in results if result.created)
    require(all(replace(result, created=True) == original for result in results), "identical concurrent bindings")
    require(store.is_current(caller, original), "reservation is durable after closed connections")
    fresh_store = PostgresReplayStore(factory)
    replay = fresh_store.reserve(caller, request_id, envelope, run_id, handoffs)
    require(not replay.created, "connection restart cannot create another owner")
    require(fresh_store.is_current(caller, replay), "created flag is not part of durable identity")

    # A fresh Python worker independently reads the committed reservation.
    child = """import os,psycopg
from council.core import Caller
from council.postgres_replay import PostgresReplayStore
from council.replay import deterministic_run_id
c=Caller(os.environ['TEST_TENANT'],'user.synthetic','junction.aiven')
s=PostgresReplayStore(lambda:psycopg.connect(os.environ['JUNCTION_COUNCIL_TEST_DATABASE_URL'],connect_timeout=3))
r=s.reserve(c,'request.concurrent','a'*64,deterministic_run_id(c,'request.concurrent'),'b'*64)
if r.created or not s.is_current(c,r):raise SystemExit(1)
print('durable-replay-ok')
"""
    child_env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    child_env.update(JUNCTION_COUNCIL_TEST_DATABASE_URL=dsn, TEST_TENANT=caller.tenant_id,
                     PYTHONPATH=str(Path(__file__).parents[1]))
    observed = subprocess.run([sys.executable, "-c", child], env=child_env,
                              capture_output=True, text=True, timeout=20)
    require(observed.returncode == 0 and observed.stdout.strip() == "durable-replay-ok",
            "new worker process reads immutable original reservation")

    for changed_envelope, changed_handoffs in [("c" * 64, handoffs), (envelope, "c" * 64)]:
        try:
            store.reserve(caller, request_id, changed_envelope, run_id, changed_handoffs)
        except ReplayConflict:
            pass
        else:
            raise AssertionError("changed digest did not conflict")
    for changed in [replace(original, envelope_digest="c" * 64),
                    replace(original, handoffs_digest="c" * 64),
                    replace(original, fence_token=2),
                    replace(original, idempotency_key="host.run.forged")]:
        require(not store.is_current(caller, changed), "forged checkpoint is not current")
    other = replace(caller, tenant_id="other." + unique)
    require(not store.is_current(other, original), "tenant isolation")
    other_reservation = store.reserve(other, request_id, envelope,
                                     deterministic_run_id(other, request_id), handoffs)
    require(other_reservation.created, "different tenant owns independent reservation")
    require(not store.is_current(replace(caller, user_id="user.other"), original), "user isolation")
    require(not store.is_current(replace(caller, active_pet="junction.other"), original), "active pet isolation")
    try:
        store.reserve(replace(caller, active_pet="junction.other"), request_id,
                      envelope, run_id, handoffs)
    except ReplayConflict:
        pass
    else:
        raise AssertionError("active pet change reused reservation")

    with factory() as connection:
        try:
            with connection.transaction():
                connection.execute("UPDATE junction_council.replay_reservations SET envelope_digest=%s WHERE run_id=%s",
                                   ("c" * 64, run_id))
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise AssertionError("database allowed immutable digest update")
    require(store.is_current(caller, original), "failed tamper leaves original current")
    require(store.invalidate(caller, original), "host terminal invalidation")
    require(not store.invalidate(caller, original), "stale cancellation cannot advance fence")
    require(not store.is_current(caller, original), "invalidated fence rejects stale worker")
    try:
        store.reserve(caller, request_id, envelope, run_id, handoffs)
    except ReplayConflict:
        pass
    else:
        raise AssertionError("invalidated request was resurrected")
    with factory() as connection:
        row = connection.execute("SELECT fence_token,active FROM junction_council.replay_reservations WHERE run_id=%s",
                                 (run_id,)).fetchone()
    require(row == (2, False), "terminal fence advanced exactly once")
    with factory() as connection:
        for operation in ["DELETE FROM junction_council.replay_reservations WHERE run_id=%s",
                          "UPDATE junction_council.replay_reservations SET active=true,fence_token=fence_token+1 WHERE run_id=%s"]:
            try:
                with connection.transaction():
                    connection.execute(operation, (run_id,))
            except psycopg.errors.CheckViolation:
                pass
            else:
                raise AssertionError("database allowed tombstone deletion or resurrection")
    return {"status": "pass", "evidence": "real-local-postgresql", "concurrent_connections": 8,
            "new_worker_process_replay": True, "chibi_host_verified": False,
            "aiven_service_verified": False, "provider_execution_verified": False}


if __name__ == "__main__":
    import json
    try:
        result = run_pg_gate(os.environ.get("JUNCTION_COUNCIL_TEST_DATABASE_URL"))
    except (ValueError, psycopg.Error):
        print("TEST_DB_UNAVAILABLE_OR_UNSAFE", file=sys.stderr)
        raise SystemExit(3) from None
    print(json.dumps(result, sort_keys=True))
