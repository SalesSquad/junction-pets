# Intel M330 — cross-batch software continuity (Nemotron M5)

**Scope:** private, synthetic, offline, non-actuating JavaScript prototype. Stack base: M4 PR #169 at `a31e2b314037f4a345ad4dbe3cd74a9e8df5712a`; source provenance: authenticated main `16947f0ccd33d6e3895f08619b7ba425bf453a59` (14 Nov 2026). Partner key `ignite-next-and-intel`, brief `M330`. Sponsor evaluation rubric formats remain contradictory. This is not an SO-101 / Anomalib / VLA / OpenVINO / real camera, physical robot or emergency-stop qualification.

## Problem and algorithm

M4's global latch prevents later software bowl placements **within one batch**, but a caller could create a new batch and recover routing without a durable operator reset. M5 wraps the unchanged M4 policy in a versioned immutable state ledger with **cross-batch STOP** until a distinct proposal and host-authorized rearm, monotonically incremented epoch, separate reusable physical item IDs (not merely same episode sequence), idempotent exact request keys, per-event SHA256 audit chain, and deterministic recomputation against the source policy. Ordinary local item STOP remains per-item; only a global STOP or sensor interlock latches the complete software session.

`genesis()` creates a synthetic session; `dispatch(snapshot,request,{authorize})` returns `ADMITTED`, `CACHED` or `DENIED`. `verifyLedger(snapshot)` fully reconstructs the bounded chain. Each RUN has unique globally stable `itemIds` in episode order, `batchId`, `batchRequest` (existing M2 plan), and `batchControl` (M4 `globalStopEpisodeId` or empty). Expected operational revision and epoch are required for CAS integration. An event ID is idempotent **only for an identical full request**. Same ID/different body, stale revisions, stale epochs, global latch, replayed batch/item IDs, missing authorization and invalid sensor input fail closed. Post-trip *sensor recovery alone* does not clear the latch.

A proposed rearm does not authorize routing. The trusted host must **authenticate an operator/device externally**, bind an approval to the exact `{scope,requestHash,previousRoot,revision,epoch}`, and **durably CAS** the result against the previous root before acknowledging. The `authorize` callback represents a host-supplied decision, **not a signature or secure proof**; never accept an untrusted client's callback or approval envelope. This module does **not implement persistence, filesystem audit logs, host authentication, cryptographic receipt signatures, distributed consensus, replay protection against a malicious host, physical identity proof, or real hardware interlocks**. A forged host callback, state rollback, deleted ledger, copied item with a new ID, or non-atomic host storage defeats its software claims. Denials return separate deterministic `auditHash` for the external host to persist; denials themselves do not alter operational state. Every snapshot and ledger has conservative caps (64 admitted events, 1,024 unique items, 64 items per batch); caps exhaust **closed**, not auto-rearm. Host must independently persist the audit and enforce identifier namespaces and privacy minimization. Receipts are **unsigned SHA256**, not authenticity.

## How to reproduce

From repository root:

```sh
node --test solutions/intel-physical-ai/batch/continuity/continuity.test.mjs
node solutions/intel-physical-ai/batch/continuity/cohort.mjs
```

The bounded targeted suite exercises global vs local STOP, cross-batch deny, per-epoch rearm, invalid and forged host claims, stale/mutated request replay, invalid inputs, missing authority, negative fault families, deterministic receipts and the explicit **host CAS is not implemented** limitation.

The cohort runs exactly **18 synthetic comparisons** (six predefined faults at three positions), comparing M4's new-batch behavior with M5's refusal after a global latch. The numerator/denominator are controlled replays of one synthetic generator, **not independent episodes, measured safety, confidence intervals, or real throughput**. It prints case-by-case receipt roots and a JSON SHA256 so results can be reproduced. It makes no quality claim about real SORT accuracy, latency, energy, actuators, or sensor integration.

## Sponsor path after this software milestone

Integrate the M3 operator studio only after a single owner handles the PR stack; qualify the actual Intel station (SO-101 sensors, Anomalib output, VLA command staging, OpenVINO on Intel hardware) separately with physical safety authority and hardwired interlocks. Report true robot cycle time, correct-bowl rate and fault recovery on held-out physical runs with an approved supervisor and operator. No physical action may be inferred from a software STOP receipt.

**Model evidence:** MBP Verda-hosted Nemotron 3.5 Super VL generated two bounded **read-only** design/red-team analyses on 14 Nov 2026 (CLI exits 0). The first draft erroneously treated local STOP as global; the second explicitly corrected that. Implemented core here is human-reviewed source, **not model self-certification**. Provider token billing/actual cost unknown; no new GPU VM or credential export.


## Independent safety review repair — exact follow-up

An independent **Codex Plus read-only** review of original M5 commit
`399a491a0791dc3c319f1b4660d1c4c445791363` reproduced two defects:

- **P1:** a caller could mutate its LATCHED snapshot while asynchronous host
  authorization was pending, allowing an invalid software bowl before replay
  rejected the chain. **Fixed:** the snapshot is synchronously copied and
  rebuilt from its event history before further awaits; later logic uses ONLY
  the verified immutable rebuilt snapshot. The request and eventual host
  envelope are detached and validated too.
- **P2:** a JavaScript sparse item-ID array could bypass `.some()`, and
  unsigned hashing could equate `[undefined]` with `[]`. **Fixed:** strict
  dense/plain/finite JSON boundary validation before hashing or replay;
  unsupported values, sparse arrays, cyclic values and forbidden object
  properties are rejected.

The source-bound reproductions are retained as negative Node tests. The M5
cohort generator and demo were rerun on the corrected bytes: **15/15
targeted tests PASS**, live local software demo PASS, 18 fixed synthetic
comparisons **144 → 0** cross-batch software bowl outputs. This is **not**
physical safety validation. The host must still provide trusted durable CAS,
identity, operator proof, hardware E-stop and calibrated real sensors.
