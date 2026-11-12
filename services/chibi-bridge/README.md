# Chibi private-host boundary — public Junction adapter (Wave 2)

This directory defines a minimal **read-only, fail-closed client boundary** between public `SalesSquad/junction-pets` company companions and the separately owned **private Chibi Rust/Cedar runtime**. It contains no private host routes, auth credentials, deployment configuration, provider SDK or user data. It does **not** claim that a Chibi host is connected.

## Inputs and trust model

`bridge.mjs` accepts the v1 `request.schema.json` envelope from `../../contracts/pet-collaboration/v1/` and calls only host-owned injected adapters:

| Adapter | Required responsibility |
| --- | --- |
| `verifyHostGrant(query)` | Private Chibi Rust/Cedar authenticates identity, owner, adoption, consent, capability, context digest, budget, expiry and revocation; returns fully-bound decision |
| `reserveReplay({tenantId,requestId,...})` | Private durable store atomically reserves the idempotency key before any dispatch (not a process-local Set) |
| `transport(payload,{signal})` | Host-owned MCP/HTTP gateway performs only authorized read action; bearer/session secrets held **out of band**, never inside payload |
| `verifyHostReceipt({receipt,receiptSha256,sourceSha,requestId})` | Trusted private host verifier checks receipt's signature/audit evidence, issuer and exact digest; injected response must bind the source and request |

The public adapter validates the portable envelope and host **claim shapes** but cannot authenticate credentials or cryptographic signatures itself. Code using it MUST wire the callbacks to a verified private host; a stub callback returning `verified: true` is test-only and not live proof.

The adapter:

1. Rejects missing host dependencies or authenticated identity before any dispatch; the caller-pinned `sourceSha` must exactly match the v1 request's `sourceSha`.
2. Handles only `requestedEffect: "read"`. Proposals and writes require separate human and Chibi host approval.
3. Calls the versioned contract's `authorizeAndReserve` and revalidates the same bound grant immediately before and after transport, including source SHA, conversation/delegation depth and context reference; revocation stops the response.
4. Supplies a tenant-scoped `idempotencyKey` and an `AbortSignal`. The private host must implement durable deduplication, fencing and cancellation; timeout here is best-effort and does not prove the remote service stopped.
5. Rejects unknown, mismatched or tampered receipt fields, host issuer/proof mismatch, and any `externalEffects: true` in a read-only request.
6. Returns only host receipt metadata, content digest and opaque references. Raw private context, credentials and model text never enter the public result or diagnostic error.

`sourceSha` must be a **GitHub-verified** 40-character commit injected by the caller. Structural SHA validation in this package does not independently verify GitHub, signatures, active consent or provider execution.

## Intended Aiven LangGraph integration

The Python `services/council/` graph should produce **a v1 request proposal**, pause for Chibi's policy decision and call an authenticated private service adapter implementing this interface. It must not pass model-authored authorization, fabricate a decision reference or call `transport` directly. A checkpointed graph may resume only after the host resolves the current grant again. No active route is hard-coded in the public submission.

To run portable mock tests:

```sh
node --test services/chibi-bridge/bridge.test.mjs
```

The tests cover cross-tenant identities, missing host integrations, replay, source binding, tampered receipts, fake attestation, revocation before/after dispatch, timeout and cancellation. Their host adapters are synthetic; **no actual provider/model/tool calls occurred**. A real pilot additionally requires an authenticated Chibi user, host Rust/Cedar receipt verifier, durable replay storage, true provider request ID, consent revoke test, and separate exact-HEAD test qualification.

## Current scope limits

- Only read-only capability handoffs; no external writes, billing, device control or child/private data transmission.
- No deployed Chibi gateway, network transport, signing key, durable ledger or live Codex environment is created by this package.
- Host proof is an injected opaque attestation shape; production cryptographic verification and audit trust anchors remain private.
- The existing `lib/pet-collaboration.mjs` simulation remains a deterministic public demo. Passing these tests cannot be reported as live inter-pet cooperation.
