# Pet collaboration contract v1

Source baseline: `SalesSquad/junction-pets` PR #4 `4099d930d0cc60b4caf54416317ea84c82f3f4c9`.

**This is a portable request/receipt contract, not proof of Chibi host consent or live provider execution.** `request.schema.json` permits metadata and context references, not raw data or credentials. `receipt.schema.json` describes host-issued outcomes; a shape-valid receipt is still untrusted until host attestation is verified.

Run `node --test contracts/pet-collaboration/v1/*.test.mjs` (Node 22+). `schema.test.mjs` uses optional Ajv Draft 2020-12 when installed; if unavailable, its behavioral schema tests explicitly skip.

## Authorization boundary

1. Chibi's private authenticated Rust/Cedar host—not this public repo, the model, or Aiven LangGraph—owns identity, effective entitlements, consent and policy.
2. Resolve `authorityRef` using a host-managed verifier. Bind grant and decision to authenticated tenant, actor, recipient, capability, exact request, conversation, parent/depth, context reference plus digest, effect, expiry, revocation, budget and **canonical approved `sourceSha`**. The SHA string in untrusted JSON is NOT source attestation.
3. The reference `authorizeAndReserve` adapter **denies by default** unless trusted host callbacks resolve authorization and atomically reserve `(tenantId,requestId)`. A process-local Set is test-only; production requires durable uniqueness.
4. Authorization here admits work to a queue only. Recheck policy immediately before every provider/tool call and after revocation. No silent `read` → `write` escalation or cross-pet memory pooling.
5. Sign/attest the final receipt at the host; bind immutable source SHA, detached attestation/signature references and provider/tool receipts. A completed receipt requires attestation and output digest; completed model/tool execution also requires corresponding provider/tool receipt references. `denied` can have no provider receipt. Shape-valid attestation references are still NOT cryptographic proof. Long-running orchestration needs separate leases, fencing and outbox semantics. LangGraph checkpointing alone is not exactly-once execution.

`tenant-private` is a reserved schema data class, **not** an automatic authorization to share private material. Never include tokens, secrets, user data or unpublished challenge assets in public demo fixtures.

## Adapters and source

An Aiven Python LangGraph/FastAPI runtime may consume authorized messages and checkpoint work; Codex Cloud environments build/test developer lanes, not runtime permissions. When adapting Aiven source, retain MIT notices and pinned attribution:
- `carabaestlein/aiven-prototype-agent` @ `8531f3cfb364121314c014e8ec8a72d84c82388e`
- `Aiven-Labs/aiven-runtime-langgraph` @ `fcb5ef8bf731b72fd557f3c326adbc58f18da8f7`

**Pre-release v1 compatibility note:** `request.sourceSha` and trusted host callback bindings (`conversationId`, `parentRequestId`, `depth`, `contextRef`) are now required; receipt producers must set `executionKind` and conditionally include host attestation/provider/tool refs. Older sample envelopes without these fields are invalid, not silently upgraded.

Use a full JSON Schema Draft 2020-12 validator and cross-language fixtures in production. The Node checker covers current explicit invariants and is not a cryptographic implementation.
