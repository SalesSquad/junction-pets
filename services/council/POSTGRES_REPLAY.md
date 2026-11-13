# Durable Council replay adapter

`council/postgres_replay.py` implements the existing `ReplayStore` interface
with PostgreSQL 14+. It uses the already pinned psycopg dependency. It is
host-injected source, not a deployed Aiven service or an authenticated Chibi route.

## Host integration

An authorized host administrator applies
`migrations/001_replay_reservations.sql` to its intended database explicitly.
No request or adapter constructor creates tables, roles or connections. Supply
an exclusive idle psycopg connection context factory; a dedicated connection
pool's `connection` method is suitable. Do not lend an existing business
transaction: the adapter refuses non-idle connections.

```python
from council.postgres_replay import PostgresReplayStore

replay_store = PostgresReplayStore(host_private_pool.connection)
# Inject the SAME store into build_graph(...) and create_app(...).
```

The private host retains credentials, authentication, Cedar authorization,
current consent/revocation, artifact access, provider calls and model accounting.
This module supplies none of those capabilities. A PostgreSQL/Aiven project
must already be authorized; this slice provisions no cloud resources.

## Invariants and recovery

- Uniqueness is `(tenant_id, user_id, first_request_id)`. Active pet, deterministic
  run ID, both exact SHA-256 digests and idempotency key are immutable bindings.
- An `INSERT ... ON CONFLICT DO NOTHING` followed by a fresh read-committed
  statement gives exactly one `created=True` reservation under contention.
  The transaction commits before `durable=True` reaches the caller; a commit
  failure returns no reservation. Synchronous commit is enabled for this
  transaction; database/WAL/storage guarantees remain host responsibilities.
- Identical requests return `created=False`, including after a worker restart.
  A changed digest or active pet raises `ReplayConflict`; no input is overwritten.
  `created` is a local response flag, not part of the durable identity.
- `is_current` queries the host-persisted tenant/user/pet/run, both digests,
  idempotency key, positive int64 fence and active state every time. A caller's
  self-consistent modified checkpoint does not make a grant current.
- Optional host-only `invalidate(caller, reservation)` terminally cancels an
  exact active reservation and increments its database fence. Stale callers
  cannot advance it again. SQL triggers reject immutable-field changes,
  tombstone deletion and reactivation. Administrative retention/schema changes
  need a deliberate separate migration; this adapter offers no deletion path.
- There is no automatic lease takeover or provider retry. A crash between a
  provider call and its checkpoint remains unresolved until the host reconciles
  provider idempotency and its durable outbox. This does not promise exactly-once
  model execution. Recheck the fence and policy at the actual privileged read.

## Checks

Use the isolated Python environment described in the Council README:

```sh
python -m pytest -q services/council/tests/test_postgres_replay.py
python -m pytest -q services/council/tests
```

Those tests include fault injection and **do not** prove SQL concurrency.
The separate explicit gate uses an already-created disposable **local** database
named `junction_council_test_<suffix>` and a user allowed to create its schema.
The DSN must explicitly name its local host/socket, database and user. Inherited
libpq `PG*` configuration other than `PGDATA`/`PGBIN` is refused. Supply the URI
through the authorized executor environment, never a committed file or log.

```sh
PYTHONPATH=services/council python services/council/tests/test_postgres_replay_pg.py
```

Set `JUNCTION_COUNCIL_TEST_DATABASE_URL` before this command. Missing/unsafe or
unreachable DB exits **3**; no integration assertions are skipped or mocked.
The explicit script is not collected as a default pytest test because it
requires that separately authorized disposable DB. It checks eight concurrent
connections, a new Python worker reading the original committed reservation,
conflicting digests, tenant/user/pet isolation, forged checkpoints, database
immutability, monotonic invalidation and deletion/resurrection refusal. It leaves
only synthetic scoped IDs/digests in that database; it performs no automatic
database deletion. Results establish local PostgreSQL behavior only, not Aiven
hosting, server crash/storage recovery, Chibi identity, model quality or recipient
acceptance.
