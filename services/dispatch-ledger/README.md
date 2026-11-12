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
PostgreSQL locking or provider-side idempotency. For the release gate, apply
`001_dispatch_ledger.sql` to an isolated test database and run concurrent claims,
revocation, process kill/resume and provider retry fixtures from independent
clients. Do not apply the migration to a production database without approval.

No API keys, model transcripts, private user payloads or provider identities are
stored. It is intentionally not imported into the public Chibi host runtime.
