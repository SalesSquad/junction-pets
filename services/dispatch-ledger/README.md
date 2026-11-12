# Junction Council — durable dispatch ledger

This is an **independent, source-bound first slice**, not a running cloud service.

It supplies PostgreSQL 14+ DDL and dependency-free JavaScript functions that
accept a `pg`-compatible `{ query(sql, values) }` object. The caller owns the
connection pool, schema migrations, authentication and process supervision.

## Trust boundary: host-only database credentials

Only an authenticated, authorized **Chibi host dispatcher** may hold a database
connection and call `claimNextJob`. Its claim requires both `tenantId` and
`petId`; a missing or different scope is rejected before any query. The host
must derive those values from authenticated policy context, never from a pet's
untrusted output. A pet's Codex Cloud workspace is for **development**, not
a privileged runtime: never distribute PostgreSQL credentials to pet workers,
plugin packages or public Junction submission bundles.

## Execution contract

1. The scheduler enqueues a job with an immutable source commit, input digest,
   tenant, pet and scoped idempotency key. Duplicate input returns the same job;
   a conflicting digest is rejected.
2. A worker atomically claims one eligible job with `FOR UPDATE SKIP LOCKED`;
   each claim increments a **monotonic fencing token**. A stale worker cannot
   heartbeat, emit an effect intent, complete or fail the newer lease.
3. The Chibi host verifies current tenant identity, scopes, consent and
   revocation with its own Rust/Cedar policy engine. The dispatch ledger **never
   issues authority**. It stores a digest of the host's authorization receipt.
4. Effects are immutable outbox intents, not provider calls. Immediately before
   dispatching an effect, the Chibi host must reauthorize the requested action.
   External providers must support the stable effect idempotency key (or an
   equivalent reconciliation protocol). Otherwise external exactly-once delivery
   is **not guaranteed**, even with PostgreSQL transactions.
5. A provider receipt can be recorded against a live lease. Completion is
   refused while any effect remains pending. The result and completion state
   are written atomically; only opaque SHA-256 digests are persisted.
6. The recovery worker requeues expired leases or moves exhausted attempts to
   `dead_letter`. A new claim gets a larger fencing token. The supervisor must
   run recovery periodically and surface dead-letter items to Mission Control.

## Quick verification

`node --test services/dispatch-ledger/*.test.mjs`

Local tests are **fake-adapter contract tests**, not proof of cross-process
PostgreSQL locking or provider-side idempotency. The separate opt-in gate below
executes the SQL on real PostgreSQL and simulates a worker crash by expiring its
lease. Chibi revocation, actual OS process-kill recovery and external provider
idempotency remain separate host/runtime qualification gates.

## Real PostgreSQL release gate (explicitly opt-in)

Run the two-connection integration suite with `psql` 14+ and an **already
authorized, separate disposable database** whose name begins with
`junction_dispatch_test_`. The runner uses existing DB access only: it
does not provision a server, create accounts, install dependencies or connect
to Chibi production. It adds the migration and synthetic rows only inside
that explicitly named test DB.

```sh
node --check services/dispatch-ledger/pg-integration.mjs
node --test services/dispatch-ledger/ledger.test.mjs
JUNCTION_DISPATCH_TEST_DATABASE_URL="<owner-provided-test-database-URI>" \
  node services/dispatch-ledger/pg-integration.mjs
```

Use an authorized secret store or session environment for the test URI; do not
paste credentials into GitHub, CI logs or shell history. Remote test databases
also require `JUNCTION_DISPATCH_TEST_ALLOW_REMOTE=1`. The runner refuses
non-test database names, excludes inherited libpq credentials, and passes the
connection through child-process environment variables rather than argv.
When the test DB is absent it **fails with TEST_DB_UNAVAILABLE (exit 3)**;
there is no mocked green result or skipped real-DB assertion.

The real suite checks independent PostgreSQL connections, SKIP LOCKED
contention, a held-row lock blocking effect receipt writes, monotonic fencing,
lease expiry/recovery, stale worker rejection, and unique outbox/result rows.
It does not establish Chibi grant enforcement, real provider retry semantics
or production readiness; those need separate source-bound host tests.
Synthetic test records are left in the designated disposable database for
evidence; database cleanup is not performed automatically.

No API keys, model transcripts, private user payloads or provider identities are
stored. It is intentionally not imported into the public Chibi host runtime.
