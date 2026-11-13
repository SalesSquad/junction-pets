# Runnable Aiven public developer workflow

Work ID: `junction.demo.aiven-spine`. This finite CLI joins pinned public Aiven documentation, the existing synthetic MariaDB analyzer, one tools-disabled Claude response and durable PostgreSQL replay. It is a **public/synthetic developer demonstration**, not an authenticated Chibi service, a trained model, Aiven account access or a signed provider receipt. It starts no daemon and creates no account or provider resource.

## Run

Use Node 22+, the existing Council Python environment installed from `services/council/requirements-dev.txt`, the already authorized Claude CLI login, and an existing **disposable local** PostgreSQL 14+ database. Its name must match `junction_council_test_[a-z0-9_]+`; only one normalized absolute Unix socket path, `127.0.0.1` or `::1` is accepted. An explicit database user is required; comma-separated/fallback hosts and all inherited nonempty `PG*` settings except `PGDATA`/`PGBIN` are refused. The CLI never provisions PostgreSQL. Supply its DSN through the existing host secret/session environment as `JUNCTION_DEMO_DATABASE_URL`; do not put it in source, logs or command arguments.

First commit/preserve the implementation on a task branch. Both stages refuse a dirty checkout, wrong source SHA or wrong repository origin. `FINAL_SHA` below means the exact clean commit containing this implementation, not its earlier planning base.

```sh
# Default preview: no DB, network or model. No Council dependencies required.
python3 services/demo-host/aiven_workflow.py --source-commit FINAL_SHA

# Explicit disposable-database setup, using the pinned Council Python environment.
/path/to/council-venv/bin/python services/demo-host/aiven_workflow.py \
  --source-commit FINAL_SHA --init-db

# Fixed public question and synthetic SQL data; one bounded Haiku call at most.
/path/to/council-venv/bin/python services/demo-host/aiven_workflow.py \
  --source-commit FINAL_SHA --request-id public-demo-1 --execute

# Repeat the same command: replayed:true, original stored result, zero new model calls.
/path/to/council-venv/bin/python services/demo-host/aiven_workflow.py \
  --source-commit FINAL_SHA --request-id public-demo-1 --execute
```

`--init-db` explicitly applies `services/council/migrations/001_replay_reservations.sql` and the inline demo-result DDL. Setup is a separate operator action; requests do not migrate schemas. Results are immutable JSON text/digest rows in `junction_council.demo_public_results`, bound to tenant/user/run, both request/source digests, source SHA and fence. The fixed caller IDs say `synthetic-public-demo` / `synthetic-developer`; they are labels for this isolated local demonstration and confer no user permission.

## Actual sequence and recovery

1. Verify clean source/origin, then commit a PostgreSQL replay reservation before external work.
2. Fetch exactly the existing two public Aiven raw-document URLs and require the existing original-byte SHA-256 gates. Rank-only source metadata is insufficient.
3. Execute the existing MariaDB analyzer over its authored synthetic EXPLAIN fixture. Estimates remain estimates; no SQL connection or query runs.
4. Recheck source and the entire current database reservation. Invoke one `haiku` CLI response with tools, MCPs, customizations and session persistence disabled, in a newly empty temporary directory. Public summaries and synthetic classifications are the only prompt context. Require bounded JSON output and a finite reported cost at or below USD 0.25. The model alias and CLI-reported cost do not attest an exact backend model or billing.
5. Recheck source/current reservation, atomically store the bounded original result and its digest while holding a share lock on the current reservation, then return it.
6. Identical replay reads that exact stored result under the current full binding; it never invokes a second model. A changed source/payload/helper digest for the same scoped request conflicts. A reservation with no result returns an explicit unknown/in-progress outcome and permits **no automatic retry**. Stage failures are retained as immutable failures; failure cannot be retried silently by the same request ID. Invalidated/stale fences cannot store or return a result.

Database DSNs and inherited `PG*` variables are removed before the Node/model subprocesses. SQL and provider exceptions are redacted. No raw private user data is accepted or persisted. Only this fixed public developer response is stored. Temporary CLI working directories are removed after return; no repository response file is created.

The reservation prevents concurrent duplicate admission but does not promise exactly-once external effects across a model/DB crash gap. An interrupted attempt can consume a model response without storing it; its durable reservation deliberately blocks automatic reexecution. PostgreSQL persistence proves the scoped local demo, not Aiven-managed hosting, Chibi identity/Cedar policy or provider-signed consumption.

## Verification

```sh
node --test services/demo-host/workflow.test.mjs
python3 -m py_compile services/demo-host/aiven_workflow.py
```

Eight deterministic tests cover verified-source shape refusal, fixed prompt/input binding, useful SQL classification, isolated tools-off model invocation, malformed/error/budget output, a zero-provider preview, replay/collision/unknown-outcome/revocation and an explicit missing-dependency failure. Injected transports/stores are labelled synthetic; they do not qualify real HTTP, PostgreSQL or model execution. Run the actual commands above on a clean final SHA and inspect the first result and replay before claiming the real demo passed.
