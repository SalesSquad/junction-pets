# Intel Physical AI M5 — Nemotron-guided cross-batch continuity

**Source parent:** `SalesSquad/junction-pets` `main=16947f0ccd33d6e3895f08619b7ba425bf453a59`;
stacked on verified [M4 draft #169](https://github.com/SalesSquad/junction-pets/pull/169)
head `a31e2b314037f4a345ad4dbe3cd74a9e8df5712a`. Source route
`junction.intel`/`junction.ignite-next` →
`partnerEvidenceKey=ignite-next-and-intel`, `ownedBriefRefs=[M330]`.
Current 14 Nov partner clarification was read before the prior dated guidance;
Intel rubric conflict is unresolved.

## What was improved

The preceding M4 supervisor detects faults and stops later episodes **within
the same batch**, but creating a new batch resets that local latch. M5 adds a
pure, stateful **synthetic cross-batch continuity layer** that reuses M4 unchanged.
One corrupt/stale camera, dropped grip, low confidence or global operator STOP
latches the logical session. A newly constructed batch cannot bypass it.
A per-**item** STOP remains local; it does not become an emergency STOP.

Each admitted RUN consumes a globally unique batch ID and 1–64 **stable
item IDs** supplied by a trustworthy external host, preventing duplicate items
after a later rearm. Replayed event ID + identical bytes returns the original
receipt without re-execution. Same ID with changed content is refused.
All mutations bind to an exact operational revision **and epoch**; missing,
stale or conflicting versions fail closed. No time service, motor API,
camera stream or model inference is installed.

To rearm: (1) request a proposal while LATCHED, which does not clear anything;
(2) a distinct REARM confirmation calls a host-injected authorization
function, bound to the exact request digest, epoch, revision and preceding
ledger root; (3) only a matching positive host decision increments the epoch.
An external application must authenticate operator proof and must durably
compare-and-swap the returned snapshot root. A simple `true` or
`rearm:true` supplied by a client is NOT sufficient to this API.

The audit ledger hashes the original event/request/host decision, M4 replay
root, result, revision and previous root. `verifyLedger` regenerates M4
decisions and compares the complete ledger. Denied requests produce a
separate return envelope for host-side negative auditing and **never modify**
the operational snapshot, version or its latch.

## Try the synthetic M5 flow

```sh
node --test solutions/intel-physical-ai/batch/continuity/continuity.test.mjs
node solutions/intel-physical-ai/batch/continuity/demo.mjs
```

The demo's `hostStub` is **insecure test scaffolding only**. It shows a
sensor-trip → new-batch rejection → proposed/denied rearm → test-host-confirmed
rearm → new-epoch batch → retry idempotency. It cannot establish any
physical safety or authenticated operator permission.

## Model evidence and limits

Two actual read-only Nemotron 3.5 Super VL calls on the owner's already
authorized MBP `opencode-nemotron` (Verda-hosted) completed with exit 0 on
14 Nov. First produced an epoch/ledger proposal; second red-teamed it.
Corrections in this M5 source include **preserving local item STOP**,
rejecting reused IDs and conflicting idempotency keys, separating proposal from
host admission, and forbidding stale epoch/revision actions. Model prompts
were abstract source-safe descriptions without credentials, customer data
or source-code exports. No GPU VM was provisioned; actual provider cost and
remaining credits are **unknown**. Model output is design advice, not a
robot safety qualification or evidence that a trained anomaly model improved.


### Verifiable bounded Nemotron inference receipts (owner-private host)

Both calls used `/Users/mikaelervamaa/.local/bin/opencode-nemotron run
--model verda-nemotron/nemotron --agent plan` on the existing authorized MBP
under named tmux `j26-intel-nemotron-m5-20261114`, and returned process
**exit code 0**. Prompt and response bytes remain under owner-private
`/private/tmp/j26-intel-nemotron-20261114/` (not Git). SHA-256:

- plan prompt: `4d9ed0657609f72be356e1cad4de0660e8d7347d4c157fc3b0d7d36d0f2cca71` (2,139 bytes)
- plan response: `6788ccd83684bdbef5e592c1edb766cc4ec2fb1490cc824981b25309afcb5e30` (10,831 bytes)
- red-team prompt: `296268a967820845a4e52d3422a91ec99521255e98d5707890f5d8f6c310d365` (2,158 bytes)
- red-team response: `18a56cc0d1a4eb094a887f470f460f57bcbea4c21b5c1a63c20ba2b1ad28701e` (4,797 bytes)

Provider invoice and actual token charge were not visible; cost **unknown**.
Model advice was independently checked against the unchanged source contract;
passing source tests do not prove the external model is a trained robotics model.
\n**Hard limitations:** snapshots and SHA-256 chains are UNSIGNED and FORGEABLE
by an untrusted host. A caller-supplied fake authorization callback can grant
itself approval; therefore this code MUST be embedded inside a trusted,
host-owned authorization boundary with durable CAS, isolated signer
and independent physical emergency-stop/rearm hardware before any motion.
The library itself has **no** persistence, CAS, identity, clock calibration,
real camera timestamps, motor actuation, Intel CPU/GPU/NPU or OpenVINO,
Anomalib, VLA, Isaac Lab, or robot connection. It does not authenticate
physical item IDs, and it does not measure real safety probability, cycle
time or anomaly-detection quality. The 64-event and 1,024-item caps fail
closed; host migration/archive remains unspecified. There is no user
consent/data persistence in this software prototype.

**Next acceptance gate:** an authorized SO-101/Intel station with verified
camera synchronization, trained anomaly/vision models, actual external
host proof, durable snapshot CAS, a real physical E-stop and cross-batch rearm,
plus measured held-out correct-bowl and safety/latency outcomes. No
production deployment, physical task, sponsor submission or merge was made.
