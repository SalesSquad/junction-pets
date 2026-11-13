> Current composition update: [all34 public knowledge packages and the Stoa→NVIDIA drawing recipe](AGENT_COMPOSITION.md). The four-pet deterministic demonstration below remains a dated synthetic example, not the complete current capability graph.

# Chibi Council — interoperable companion collaboration

This work adds a **portable, deterministic simulation** of four existing Junction pet packages delegating to each other's declared competencies. It is a usable interactive demo and an integration contract, **not** a live LLM, Chibi host, Codex Cloud session, voice assistant or provider connection.

## Run an independent demo

With Node 22+, `npm ci` and a clean repository snapshot:

```sh
node --test tests/pet-collaboration.test.mjs
node scripts/pet-collaboration-demo.mjs
```

The second command produces `dist/collaboration-demo/{index.html,style.css,app.js,trace.json}`. Serve that directory with a static HTTP server; relative `fetch('./trace.json')` intentionally fails closed when opened directly from a file URL. No API keys or external execution services are needed.

The demo's synthetic scenario is a *fictional* hands-free spatial maintenance assistant, **not an unpublished Junction challenge brief or Valmet dataset**:

1. **OpenAI/Codex → MariaDB:** `query-review` analyses what evidence a fictitious inventory SQL review would need. No query is executed.
2. **OpenAI/Codex → NVIDIA:** `performance-plan` outlines a reproducible synthetic 3D workload benchmark. No GPU is run.
3. **OpenAI/Codex → Meta:** `interaction-review` considers microphone, bystander consent, cancellation and accessible fallback, depending on the prior two plans. No wearable device is connected.
4. **OpenAI/Codex final review gate:** the coordinator can inspect all three recorded responses and present a source-bound handoff to the human reviewer. This last step is **not** a fourth privileged delegation or model computation.

Every displayed message is clearly labeled **synthetic**. The output bullets are deterministic illustrative copy, not chat responses. Existing pet source URLs are declared references, not a claim of live retrieval.

## Protocol v1

`lib/pet-collaboration.mjs` provides a pure, side-effect-free engine. A request is:

```json
{
  "id": "step.mariadb",
  "from": "junction.openai-codex",
  "to": "junction.mariadb",
  "capabilityId": "query-review",
  "tenantId": "synthetic-junction-demo",
  "mode": "synthetic",
  "parents": [],
  "context": {
    "dataClass": "synthetic",
    "fixtureId": "fixture.redacted-sql",
    "summary": "Entirely invented example; no customer data or SQL execution.",
    "evidence": {"kind":"synthetic-fixture","reference":"fixture.redacted-sql"}
  }
}
```

The companion catalog is the capability authority in this simulation. Each task also has a *matching*, one-use `syntheticGrant()` that binds tenant, actor, recipient, capability, request ID, data class and expiry. This grant is **explicitly not** a real Chibi authorization or entitlement. The simulator rejects cross-tenant attempts, private context, undeclared or connection-required capabilities, extra request/grant fields, expired/replayed grants, unknown/future dependencies, ancestor-recipient cycles and requests exceeding depth/message limits.

The trace contains per-message manifest/content SHA-256, immutable task/context digests, declared source URL list, dependency IDs and policy status. It does not contain user memories or permissions. Each output has `kind:synthetic-example`, `hostAuthorization:false`, `externalEffects:false`. The final state is `pending-human-review`.

The synthetic data-class declaration and simple credential-pattern rejection are **not a general data-loss-prevention system**. Only reviewed artificial fixtures belong in this demo. In production the authenticated Chibi host must enforce the actual context classification and grants before any text enters another pet's context.

## How to graduate to real multi-pet work

Keep this repository as the **agent package and protocol** source. Implement the actual authenticated transport in the separately owned Chibi Rust host and MCP/HTTP gateway. Do not move Cedar or Factory execution logic into this repo.

1. **Identity:** Chibi resolves real pet installation, user/tenant, pinned agent version, private context capsule and effective recipient adoption/entitlements. No pet can silently query another user's memory.
2. **Authorization:** Cedar/PEP validates *every* proposed delegation and tool action against task purpose, exact capability schema, recipient, scoped context, expiry, budget and consent. Deny by default, recheck just before dispatch and after revocation.
3. **Transport:** Introduce a signed/versioned `PetCollaborationMessage` envelope with immutable request ID and context digest. MCP tool calls/HTTP routes must carry host-issued authority, not a self-reported `syntheticGrant` fixture. Prevent replay, cycles, runaway depth/fanout and double execution.
4. **Execution:** Pet runtime invokes actual configured model/voice/transcription adapters only under host grants and a budget. Evidence includes provider request ID, source/agent version, model ID, tool receipt, failure/retry, cost and error handling. Refused/unavailable actions remain explicit.
5. **Memory:** Only approved, minimized task answers return. Cross-pet collaboration never merges private Passport histories. Any durable learning or memory sharing requires separate owner consent and visibility.
6. **Human approval:** Privileged actions (provider writes, purchases, deployment, physical actuation) remain proposals until the host obtains payload-bound authorization. The synthetic demo never approves them.

### Chat and voice adapters

The same inter-pet envelope can be surfaced as a chat transcript, a voice turn or a multimodal tool card. A voice layer supplies consent-verified transcript chunks and a `turnId`; it does **not** grant microphone/camera rights to arbitrary pets. The parent pet can narrate a delegated response with attribution and uncertainty. Before claiming a *live* demo, verify Chibi's real authenticated recipient path, speaker/device permissions, actual model output, handoff receipts and revocation through end-to-end tests.

### OpenAI Agents and Codex Cloud

Codex Cloud environments build and test the agents; they are not automatically runtime entitlements or network-connected pets. OpenAI Agents API/SDK could be an optional hosted task-execution adapter, but its billing, secrets and sandbox permissions need explicit project configuration and owner authority. Keep these backend concerns isolated from the portable protocol.

## Next acceptance gate

At least one real multi-pet request must succeed under an authenticated Chibi user, with source- and provider-bound receipts; another must fail after revocation. Do not call this an integrated multi-agent alpha before both results are captured. The 204 authored behavior-evaluation rubrics also need real model executions and human- or validated-grader judgments; their existence alone is not proof.
