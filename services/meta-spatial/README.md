# Chibi Lens — Find & Verify

First executable Meta scanning lane. The agent retrieves source-backed sightings,
proposes a grounded next step, and asks a host to verify a fresh object's identity.
It keeps **last observed**, **currently verified**, **not observed**, and spatial
registration distinct.

```sh
node --test services/meta-spatial/agent.test.mjs
node services/meta-spatial/demo.mjs
```

The demo uses a generated 10,002-object **synthetic** catalog and fake host/model
ports. It produces shelf/desk history, one grounded instruction, a tag-proof
verification, and a not-observed result. It connects no device/provider and
persists no private memory. Existing companion files and PRs 54–58 are unchanged.

## Host integration

`createScanLane(host, options)` returns `execute(trustedContext, request, {signal})`
and local capacity stats. `TOOL_DESCRIPTORS` in `contracts.mjs` maps the three
entry points to `inspect`, `find` and `verify`. The authenticated Chibi host derives
tenant/actor/source context; none comes from model output or a public request body.

| Required port | Host responsibility |
| --- | --- |
| `authorize(context, {signal})` | Fresh identity, scope, consent, source revision, revocation and session policy; strict boolean. Recheck atomically at the eventual privileged boundary. |
| `runJob(identity, execute, {signal})` | Atomic tenant+actor+request reservation and input-digest collision checks, durable result integrity, fencing, replay and policy-aware publication. |
| `resolveObservation(scope, {signal})` | Immutable observation by tenant-scoped reference; never trust client media metadata. |
| `validateCapture(scope, {signal})` | Current session generation, source provenance, capture permission and source-device binding. |
| `validateRegistration(scope, {signal})` | Actual calibrated glasses-to-map proof, expiry, coordinate conventions and revocation. Pairing/phone pose is insufficient. |
| `searchSightings(scope, {signal})` | Tenant-scoped, indexed, stable-snapshot pagination of memory held by the host. |
| `searchProcedures(scope, {signal})` | Approved source passages bound to visible entity IDs, immutable revisions and original document digests. |
| `propose(input, options)` | One bounded model call selecting entity/procedure IDs, without tool execution or generated action text. |
| `verifyIdentity(scope, {signal})` | Exact object/frame identity evidence, such as a host-verified unique tag. Visual similarity alone returns ambiguity. |

Ports receive cloned inputs; resolved values are snapshotted before later async
checks. Replayed envelopes are rebound to request/source/frame and current capture
and registration policy. Every result remains `host-injected-not-device-qualified`
and `actionAuthorized:false`; a proposal never creates a user grant.

Request IDs are scoped by host tenant+actor. Observations bind source, session,
generation, image digest and host receipt time. Device clock values must be
normalized by the capture adapter; the kernel does not compare glasses timestamps
with phone ARKit timestamps. `procedureDigest()` hashes the exact source record
excluding its own hash; `documentSha256` separately identifies the original file.

The local scheduler defaults to four active calls and 32 queued requests. It
does not supervise processes or implement a distributed queue. Reads are bounded
to two pages, eight records/page and 16KiB/page; at most 32 detected entities and
one model proposal enter a task. Host adapters must enforce limits before remote
response deserialization. Hosts must sort sightings newest-first and retain
stable snapshot cursors; `hasMore` asks the user to narrow the search.

Cancellation returns promptly. Capacity stays reserved until an uncooperative
port settles, preventing abandoned model calls from multiplying. Implement
provider timeouts/abort and bounded response bodies in the actual host adapter.

Use the existing `services/dispatch-ledger/` and the private Chibi Rust/Cedar
host for deployment. `synthetic-host.mjs` is deliberately a test adapter, not an
alternative account system, production memory store or durable scheduler.

## Next native slice

Wire Meta DAT buffers into the Lens observation/OCR contract; add routed speech,
host-owned append-only sightings and user correction. Then prove calibration and
marker registration separately. Source, scope and acceptance criteria live in
[the architecture](../../docs/META_SPATIAL_ARCHITECTURE.md) and the
[Discord source record](../../docs/evidence/meta-discord-20261113.json).


## Continuity observation integration

The [runnable SAM 3.1 → Nemotron → Resume guide](OBSERVATION.md) describes the
new task observation contract, worker bundle importer, fixed model profiles,
bounded loopback development server and visible advisory UI. Start with
`node services/meta-spatial/observation-server.mjs` for an explicitly synthetic
whole journey. The existing host/private identity boundary remains unchanged;
model output never confirms an item or task.
