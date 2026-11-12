# Chibi Council — Aiven-inspired LangGraph adapter

Experimental **host-injected** Python runtime for two sequential pet handoffs
and an interruptible human review. It complements, but does not silently replace,
the portable synthetic-only `lib/pet-collaboration.mjs` simulation.

## Upstream and license

Adaptation of the design in
[carabaestlein/aiven-prototype-agent](https://github.com/carabaestlein/aiven-prototype-agent)
at commit `8531f3cfb364121314c014e8ec8a72d84c82388e`:
`workflow.py` blob `db5755c00080aff6fa0e7aee76685d6f42de265d`,
`service.py` blob `1427a7761bf7e766901955485701d8168a1909b5`.
Its foundation is
[Aiven-Labs/aiven-runtime-langgraph](https://github.com/Aiven-Labs/aiven-runtime-langgraph)
at `fcb5ef8bf731b72fd557f3c326adbc58f18da8f7`.
MIT attribution is retained in [LICENSE-UPSTREAM](LICENSE-UPSTREAM).
This code is independently adapted for Junction; neither an Aiven endorsement
nor an Aiven service connection is implied. No Aiven logo or private demo data
is redistributed.

## Local checks

Requires Python 3.12 or 3.13 and package installation in a **separate** virtual
environment. This is a source-only unit test, not a live Chibi/provider test:

```sh
python3.12 -m venv /tmp/junction-council-venv
/tmp/junction-council-venv/bin/python -m pip install -r services/council/requirements-dev.txt
/tmp/junction-council-venv/bin/python -m pytest -q services/council/tests
```

The FastAPI builder deliberately has **no anonymous or in-memory replay default**:
`create_app(graph, authenticator, replay_store)` requires a host-injected identity
resolver and an **atomic, persistent** replay store. The same host replay store
must be injected into `build_graph(policy, executor, checkpointer, replay_store)`
so every delegated call verifies that its monotonic fence remains active.
`POST /runs` accepts exactly two canonical `pet-collaboration.v1` request
envelopes under `{"requests":[...,...]}`. `bridge.py` checks the version,
parentage, tenant, `sourceSha` (exact lowercase 40-hex), effect, TTL, data-class and budget against
`contracts/pet-collaboration/v1/request.schema.json`; it refuses writes,
private context and unbounded grants. It converts the portable `sha256:<hex>`
digest to the graph's internal 64-character digest, retaining the opaque
`authorityRef` and context reference for exact Chibi policy binding.
A client-provided `sourceSha` is untrusted metadata, not a proof of provenance.
The injected Chibi host must verify that exact commit against its approved
source registry and return a decision bound to the same SHA **and the complete
conversation, parent, depth, maxDepth, maxTokens, effect, time window and
idempotency/fence scope**. A model cannot create or prolong its own grant.
The host executor receives the bounded maxTokens field, and its metadata-only
receipt must report tokens used within budget and repeat the approved SHA.
Both delegated steps re-check the five-minute request TTL at execution/resume.
The graph builder also requires a trusted `HostPolicy`, an effect-free
read-only `PetExecutor`, a checkpointer, the durable replay/fence store
**and** a host-private `HostArtifactStore`. A real application must inject
all five through its authenticated Chibi gateway; this directory provides no
production `uvicorn app:app`, model API keys or permissive demo policy.

### Actual parent-result dependency (Wave 3)

The second pet is **not** an independent invocation. After its fresh Chibi
policy decision, Council accepts exactly the first completed metadata-only
receipt, matches its canonical `parentRequestId`, conversation, context and
approved source, and asks `HostArtifactStore.authorize_parent_read(...)`
to verify that exact artifact against the *host's own durable producer output*.
The host must bind the resulting expiring `ParentArtifactAccess` to the
authenticated tenant/user, deterministic run ID, producer+consumer request IDs,
both decisions, current fencing token, source SHA, context and per-request token
budget. Council validates those bindings, rechecks policy, TTL and fence, then
passes `prior_artifact=<trusted metadata>` to the second `PetExecutor.invoke`.

At the actual read, the **host executor must independently recheck CURRENT**
producer and consumer consent, source, expiry, fencing token and the immutable
producer-output digest; Council's preflight is not sufficient against a revoke
between lookup and read. A changed decision ID triggers a new artifact
authorization; an old grant is never silently carried to a new decision.
The metadata object is not a bearer grant. Raw parent output is never passed
to LangGraph, public request envelopes, checkpoint snapshots, API responses
or logs.

After the second invocation, Council calls mandatory
`HostArtifactStore.verify_consumption(...)` and accepts its output **only** if
a trusted host attests an independently recorded private read event bound to
the exact producer artifact, current child decision, tenant/user/run, fence,
source and child output digest. The Council stores only the opaque
`parent_consumption_ref`; a second executor that merely accepts the optional
argument or fabricates an answer without reading the parent is **denied**.
The in-memory test fake demonstrates an actual deterministic content dependency
and forged/revoked/missing evidence denial. It is **not cryptographic proof**
that a real model semantically used the context: production must validate
host-signed read/model-input receipts against its immutable durable store.

This repository supplies the host interface and synthetic tests, **not** a
deployed private Chibi adapter, signature verifier, provider model call or
persistent PostgreSQL/artifact ledger. A pre-checkpoint crash remains
at-least-once for provider calls. Failure after the model ran but before
consumption verification rejects the result without automatically retrying;
a real durable outbox/idempotent provider adapter remains mandatory for safe
recovery. External writes are forbidden.

## Execution boundary

- The host resolves the real signed-in caller, tenant and active pet adoption.
  Client-supplied IDs are never treated as authentication.
- The graph passes only exact task IDs and a digest of the scoped context,
  not private Chibi memory, bearer credentials or open-ended model text.
- Before **every** delegated read-only operation, `ReplayStore.is_current()`
  must validate the durable run fence and `HostPolicy.decide()` must consult
  Chibi Cedar/PEP status, including revocation. A missing, mismatched, expired,
  re-fenced or write-capable decision always denies execution.
- `ReplayStore.reserve()` must atomically bind (tenant, user, firstRequestId)
  to **two independent SHA-256 digests**: the parsed v1 request pair's
  canonical sorted-key, whitespace-free UTF-8 JSON encoding (`envelope_digest`,
  **not** the original HTTP wire bytes) and the canonical normalized
  two-handoff dictionaries stored in LangGraph (`handoffs_digest`).
  At initial execution **and every checkpoint resume**, Council recomputes
  `handoffs_digest` from the actual saved handoffs. The injected host's
  `is_current()` must independently compare both supplied digests, run ID,
  owner, idempotency key and fence to its **immutable durable reservation**:
  changing both a checkpoint handoff and its checkpoint digest cannot create
  a new grant. A host ReplayStore lacking this revised interface must reject
  execution until upgraded, not silently ignore `handoffs_digest`.
  One worker claims the deterministic run/thread ID; concurrent/repeated POST
  returns that ID **without another invocation**. Reusing the request ID with
  different canonical v1 content or normalized handoffs is HTTP 409. The repository contains only
  a locked *ephemeral test fake*, not a durable production ReplayStore or live
  Postgres implementation.
- `PetExecutor.invoke()` runs only after that decision, and is forbidden from
  producing write/effect receipts. The host remains responsible for actual tool
  routing, scoped data retrieval, provider timeouts, rate limits and accounting.
- LangGraph checkpoints contain **only opaque host-private artifact references,
  SHA-256 output digests and narrowly scoped receipt metadata**. Raw provider
  responses, generated text, private tool data and credentials must never enter
  the graph state, API response, logs or checkpoint. A host stores raw outputs
  separately under its own scoped access policy; a metadata-only executor
  receipt is mandatory and extra response fields are rejected.
- LangGraph checkpoints support explicit resume after failure and `interrupt`
  supports proposal review. A checkpoint **is not a durable worker queue**.
  POST idempotency prevents concurrent re-entry, but a provider invocation may
  succeed **before** a checkpoint commits. Subsequent crash/retry is thus
  **at least once** unless an external executor enforces its own idempotency;
  this prototype makes **no exactly-once guarantee**. Recovery must verify
  durable lease ownership, fencing, an idempotent provider request key and the
  ledger/outbox before it is enabled. The Council rejects *all* external writes,
  including for synthetic context. No live side effects are enabled here.
- Future production use requires a durable ledger/outbox, policy signature
  verification, cross-language envelope schema, PostgresSaver instance, crash
  replay tests, authenticated Chibi E2E tests and an explicit deployment decision.

The human `approve` decision means **accept the prepared result for review**;
it is *never* a provider write or permission elevation.

## Current qualification

The tests use an in-memory LangGraph checkpointer, a **locked but not durable**
ReplayStore fake, a fake Chibi authorization adapter and a deterministic fake
pet executor. They verify complete request/decision scope, maxDepth and token
budget, expiry at execution/resume, stale fences, missing grants, revocation,
checkpointed recovery, secret canaries, double-POST, conflicting replay digests,
concurrent reservation and stale review rejection. They do not prove a live
model call, a production atomic replay store, provider idempotency, user
connection, persistent PostgreSQL deployment, browser/voice behavior or an
installed plugin.
