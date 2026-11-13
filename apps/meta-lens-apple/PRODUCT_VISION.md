# Chibi Resume — product expansion for Meta AI glasses

**Proposed direction (14 Nov 2026):** **“The world paused. Your intention didn't.”**

Current executable Meta kernel is a careful `inspect/find/verify` source-backed
scan service. Our next product should be larger than a visual search tool:
**help someone resume an interrupted real-world task, notice what changed,
and finish only what the evidence actually supports.** This document is a
product/engineering decision proposal, not a claim that its future modules work.

## The killer demo: one interruption, one honest next step

| Time | On-screen / live beat | Proof the judge should see |
| --- | --- | --- |
| 0–10s | Start packing a 3-item camera bag, hands occupied. | Explicit task start; visible task checklist. |
| 10–20s | A judge interrupts and moves one charger, swapping another for a lookalike. | Change in the physical scene, no edited prerecorded clip claimed as live. |
| 20–35s | “Chibi, where did I leave off?” → one next useful instruction. | A past observation cited with time and zone, **not** a claim of current presence. |
| 35–45s | Glasses see two similar chargers → “I can't tell yet; show the unique connector label.” | Model abstains; task completion stays blocked. |
| 45–55s | Fresh evidence is admitted by the host; the owner explicitly confirms a step. | Show host receipt separately from model confidence. |
| 55–60s | The Mac timeline shows started → interrupted → changed → resumed. | Revocation, correction and manual fallback remain possible. |

The current synthetic replay can illustrate uncertainty but **cannot demo a
real Meta capture or trusted host identity proof**. For the live version, first
qualify a real device, the host receipt and the explicit task-state transition.

## Product architecture: one trustworthy state, four optional surfaces

| Surface | Role | Current qualification |
| --- | --- | --- |
| iOS + Meta DAT 1.0 | Camera/motion/audio transport, local candidate vision, accessible voice steps | SwiftUI source port only; official DAT adapter and physical device outstanding |
| macOS SwiftUI | Compose a 3–5-step task, replay evidence, show corrections and audit timeline | Source/typechecks only; GUI build/launch outstanding |
| Meta Ray-Ban Display web app | Glanceable next step, evidence age and explicit unknown state | Future independent web build; Display Simulator can test layout, not hardware |
| Meta AI Connectors (API/MCP) | Expose narrowly authorized Chibi task tools through Meta AI | **Early-access developer preview**; do not depend on access for MVP |

Meta documents DAT 1.0 camera, ASR/voice, motion and support across display
and displayless devices. Web apps and the separate WebMCP developer preview
offer another display route. These are official platform capabilities, **not
tested features of this repository, account or event hardware**.

Primary platform source: https://developers.meta.com/blog/meta-connect-recap-ai-glasses/
FAQ/Mock Device Kit: https://developers.meta.com/wearables/faq/

## Three products, one coherent expansion path

### P0 — Resume (build and demonstrate first)

One explicit task, 3–5 objects and one named area. The user starts/pauses,
the system stores scoped observations, and a bounded planner proposes exactly
one next step from approved task instructions. A changed/occluded object must
trigger uncertainty, not a “done” flag. Both voice and text can finish a task.

**Test:** same physical interruption with paper/phone checklist versus Chibi.
Randomize order. Measure time to correct next action, false completions,
unnecessary prompts and capture-to-suggestion latency. A demo script is not
a statistically valid usability study.

### P1 — Relay (a useful shared task, not a video-sharing feature)

One user hands off an evidence-bound incomplete step to another user. Share
only a scoped task capsule, timestamp and correction rights; require explicit
recipient acceptance and per-person tenant policy. If a charger moves during
handoff, old evidence cannot be replayed as a present-location or a completion.
**MVP:** one glasses sender, one iPhone recipient, Mac audit screen. No second
pair of glasses required. Measure follow-up questions and false stale-state
completions.

### P2 — Familiar (describe meaningful changes, never surveillance)

User establishes a target arrangement for a small tabletop/workbench. New
views classify **unchanged / changed / occluded / unknown**. Tell only relevant
differences, with a short voice reply and text alternative. Avoid safety-critical
navigation, ambient recording and employee monitoring claims. Measure change
precision/recall, false alerts, and occasions where occlusion was mistaken for
absence. No full-home spatial map required for first release.

## Agent-first ownership and proposed contracts

```
User task + scoped consent
    -> DAT iPhone observation proposal (local vision, untrusted)
    -> Chibi host source/device admission (Rust/Cedar, real authority)
    -> Reality Twin evidence/time/semantic-zone index
    -> bounded task planner (one proposed next step)
    -> Meta voice / phone / Mac / Display response
```

**PROPOSED, not registered tools:** `lens.task.start`, `lens.task.checkpoint`,
`lens.task.resume`, `lens.task.correct`, `lens.task.handoff` and
`lens.task.revoke`. Each must be assigned a host owner, versioned request and
response, actor/recipient/grant/source revision, bounded input, expiry,
idempotency, policy fence and a source-linked receipt before any live use.

Existing `meta.scan.inspect`, `meta.memory.find` and `meta.object.verify` remain
the only implemented kernel descriptors here. Reuse the real Chibi PetExecutor
for optional NVIDIA (image candidate), Qualia (consent audit), Reality Twin
(historical scene) and Taimi/other task-specialist calls. An agent's presence
in a composition graph **does not make it callable or authorized**. Never
send raw household video or private family memory to peers by default.

## Own models: train what the differentiation requires

1. **Frame candidates:** compact visual encoder/detector fine-tuned on a
   permissioned or appropriately licensed first-person dataset, with charger,
   cable and key lookalikes and negative/unknown examples. The current PR #70
   is a synthetic **numeric** ranker, not a camera model.
2. **Temporal identity/change:** association across sightings, moved/removed
   objects, partial occlusion and different lighting. Track “not observed”
   separately from “proven absent” and preserve provenance.
3. **Abstention calibration:** a model should ask for a unique visible marker
   whenever same-looking objects cannot be distinguished. Model confidence
   alone can never issue a physical identity proof or authorize task effects.
4. **Apple distribution:** quantize and benchmark a Core ML candidate model on
   the actual target iPhone; Mac is the replay/evaluation surface. Test memory,
   energy, P95 latency and bad network conditions separately from accuracy.

Training pipeline requires first-party explicit consent or checked dataset
licenses, pseudonymous session/object IDs, before-augmentation train/test split
by object/person/location/session, Blender scene seeds and asset licenses,
holdout with real glasses footage, checkpoints bound to git/dataset hashes,
and failure receipts. GPU experiments should be **short, capped, cancellable**
and launched on Verda only with a verified cost/credit entitlement and separate
authorization. Eight GPUs do not automatically mean a faster/smarter model.

Failure metrics: wrong-object acceptance per *independent task episode*;
abstention, unknown/absence confusion, ID switches, reidentification after
occlusion, recall, time to resume, prompt count, p50/p95 latency and power.
Current baseline's shifted false-candidate rate ~13.71% is a **deployment
stop**, not a probability of task success.

## Priority / acceptance

| Work package | Done when | Owner |
| --- | --- | --- |
| Native-1: real DAT | Mock permissions/revocation/reconnect + first real user-initiated frame on pinned iPhone/SDK | iOS source-port owner |
| Trust-1: Chibi bridge | Synthetic and real observations revalidated against user/session/source; unauthorized/stale replay rejected | Chibi host owner |
| Resume-1: task state | Real start/pause/resume/correct workflow, one next-step proposal, explicit confirmation | Meta task owner |
| ML-1: video candidate | Permitted dataset and shift test, no auto-verification, Core ML latency report | ML/Verda owner |
| UX-1: live comparison | 60s real-device demo, phone-only baseline, manual fallback and clear receipt provenance | Integrator/design owner |
| Surface-2: Display/Connector | Independent platform/tool access verified; no promise before access | Web/connector owner |

**Ruthless prioritization:** win the 60-second Resume experience before
shipping Relay, Familiar or a general-purpose spatial operating system.
The tangible moat is **task memory + correctable evidence + knowing when not
to claim a match**; a generic image-QA chatbot won't demonstrate that.
