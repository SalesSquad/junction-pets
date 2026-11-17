# Valio Trusted Trade — PostgreSQL Durable Crash Lab

**Work ID:** `J26-VALIO-PG-CHAOS-20261114`; stacked on synthetic payment PR #130 at source `d45f450a38ec6c8fb2f73b96d181454458ae3928`.

This is a **self-contained, disposable PostgreSQL experiment**, not the application's current in-memory payment service and **not a bank integration**. It models invented buyers, suppliers, balances, orders, Ed25519 verification *output hashes* and human-payment approval *output hashes*. The caller must validate actual signed quote, approval, buyer ownership, expiry, stock/price and sponsor permissions **before** passing the frozen intent into this lab. Its 64-character inputs are hash-format checks, **not independent signature verification or authentic payment mandates**. The existing `../src/settlement.mjs` remains unchanged. No actual Valio account, money movement, card, PSP, bank, supplier API or production tenant is connected.

## Concrete invariants

1. `SERIALIZABLE` transactions with bounded retries for SQLSTATE `40001` and `40P01`. Account rows lock in sorted order, debit is conditionally nonnegative in SQL, and every cent is represented by corresponding supplier/buyer postings.
2. A **deferred PostgreSQL constraint trigger** rejects a batch unless its committed entries count at least two and net to exactly zero. Ledger batch/entry rows refuse updates, deletes and truncation; a second trigger blocks any later insertion into an already outbox-sealed batch. Outbox receipts cannot be deleted, retargeted or truncated; only the one-time `delivered_at` transition from unset to set may advance. Payment order IDs and keys are unique; a different key for a settled order is refused.
3. Replaying a command with identical frozen terms gives its original persisted response; changing frozen terms under the same key is refused. A refund is a **new compensating balanced batch**, never an erasure; only one refund per order.
4. A database outbox row is inserted atomically with each payment/refund. One unique outbox row per batch is guaranteed; **external delivery is not implemented**. A future dispatcher must use at-least-once retries and downstream idempotency, not claim exactly-once network delivery.
5. Test namespaces are unique `j26_*` schemas in an explicitly disposable PostgreSQL database. The harness drops only the exact namespace it created, unless `--keep-schema` is provided for inspection. Never point `VALIO_TEST_DATABASE_URL` at a production database.

## Portable local/CRACI execution

Prerequisites: Node 22+, PostgreSQL 14+ with an **ephemeral, isolated test database and schema-create privilege**, and the checked-in package lock pinning `pg@8.13.1` and its resolved transitive packages. Use a preconfigured job-local PostgreSQL service/container on authorized CRACI runners (or a developer-owned disposable database). An example Ubuntu service setup is PostgreSQL 16 official package/service; **do not provision production credentials or connect a sponsor database**. Docker is optional and not assumed installed.

If an authorized Ubuntu runner already has Docker, one bounded local example is below (password generated per-run, no volume, localhost-only port; the image download requires existing approved registry access):

```sh
export VALIO_LAB_PASSWORD="$(openssl rand -hex 16)"
docker run --rm -d --name valio-j26-ledger-lab \
  -e POSTGRES_USER=valio_lab -e POSTGRES_PASSWORD="$VALIO_LAB_PASSWORD" \
  -e POSTGRES_DB=valio_lab -p 127.0.0.1:55432:5432 postgres:16
export VALIO_TEST_DATABASE_URL="postgres://valio_lab:$VALIO_LAB_PASSWORD@127.0.0.1:55432/valio_lab"
# Wait for pg_isready before invoking the CLI, then remove only this named container.
```

Do not print `VALIO_LAB_PASSWORD` or the connection URL in CI logs. A CRACI job with a pre-existing PostgreSQL service does not need Docker; pass its **test-only** connection URL through an ephemeral job environment, not a committed file.

For Ubuntu's existing local PostgreSQL service with **Unix peer authentication**, the officially supported `pg-connection-string` socket form is `VALIO_TEST_DATABASE_URL='socket:/var/run/postgresql?db=postgres'`. Before using it, start the service and verify that PostgreSQL has a role matching the runner's OS account with `CREATE` privilege on a **disposable** test database. This socket form was parsed locally with the pinned `pg` dependency; no PostgreSQL server was present here to connect to. Never grant a production user elevated privileges for this test.

```sh
cd solutions/valio-trusted-trade/durable
npm ci --ignore-scripts --no-audit --no-fund
node --test test/contract.test.mjs
export VALIO_TEST_DATABASE_URL='postgres://<ephemeral-test-user>:<password>@127.0.0.1:5432/<ephemeral-db>'
node smoke.mjs --workers 8 --requests 1000
node --test test/postgres.test.mjs
```

The example is a placeholder; **never commit or print actual database credentials**. The CLI accepts `--workers 2..8`, `--requests 0..10000` (default 400) and `--keep-schema`. Use `--requests 1000` for a bounded qualification under 20 minutes; use 10000 only if the runner and existing credit reservation can support it. No new CRACI workflow is added here.

The harness creates eight distinct Node **OS processes** on one shared PostgreSQL schema, then verifies:

- two signed-intent *fixtures* competing for €2,500 with €1,500 simulated requests → one settlement, one overdraft refusal;
- a separate refund restores the winning transfer;
- two **different OS processes** attempt to refund that single order under distinct idempotency keys simultaneously; exactly one durable refund is posted, and the other is refused;
- one OS worker exits with code 42 **after PostgreSQL COMMIT but before replying**; another worker replays the exact key and reads the single persisted batch;
- 100 unique €7 payments plus 100 refunds and N mixed replays/conflicts; durable audit matches stored balances, zero-sum batches, no negative balances, exactly 203 outbox events for 203 committed ledger batches.
- **negative SQL tamper probes** attempt to DELETE, retarget and TRUNCATE the outbox seal, then append one cent to that previously committed batch; PostgreSQL must refuse every attack and the original audit must remain intact.

Proof is the **actual CLI JSON receipt plus PostgreSQL query** for an observed run, not a passing JavaScript format-only test. The simple local unit tests cover canonical intent validation only. If the executor lacks PostgreSQL or `VALIO_TEST_DATABASE_URL`, the integration test reports **BLOCKED/skipped**, and durable multi-process qualification remains unverified. PostgreSQL superusers can change schemas/triggers; this is test infrastructure, not an immutable external financial audit service.

**Retained real failure evidence (14 Nov 2026):** [CRACI run #43626421407](https://github.com/SalesSquad/junction-pets/actions/runs/43626421407) started an actual ephemeral PostgreSQL service and eight workers on PR #156 source `987c85c3373e5eb1982522f1bc283b539ffe4b01`, but failed the post-commit append negative control. The trigger's unqualified PL/pgSQL table lookup depended on the invoking session's `search_path`. The source repair now binds trigger-side queries to `TG_TABLE_SCHEMA` using PostgreSQL identifier quoting and bound parameters. This old failed run is **not** counted as a passed durable ledger test; a new source-pinned CRACI rerun is required.

## Exact SQL audit before cleaning retained test schema

For a `--keep-schema` run, use its `runId` (validate it matches `j26_[a-z0-9_]+`) to inspect the exact schema: `SET search_path` to that schema, then count `ledger_batches`, `ledger_entries`, `ledger_commands`, `ledger_outbox`, and `demo_settlements`. Compare balances with opening balances plus summed ledger deltas. Do not drop another session's schemas. `auditLab()` performs those checks automatically before the harness returns.

### Future application integration (not claimed in this PR)

Wire the existing server-owned verified quote/body and explicit approved payment digest into a durable adapter behind a capability/policy boundary; move order stock reservation and settlement into a coordinated transaction/outbox workflow; add sponsor-confirmed sandbox order-status reconciliation and independently authenticated authorization. The Chibi/BankMatch canonical finance ledger remains separate. No money/permissions/release authority is inferred from green synthetic chaos results.
