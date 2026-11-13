> Recovered historical analyst draft. Ideas and any pending-transcription statements may be superseded by official-briefs.md and fable-review.md. Referenced original contact-sheet paths were not recovered in this slice.

# Challenge video analysis A

Read-only study of six clips, five company agents, against monorepo main `61f10a44cfd833e02fa64462dfc7429046fff210`. All six small.en transcripts and contact sheets were read; source video hashes are in media/manifest.json. ASR is automatic and may mishear names and technical terms. Current authenticated official briefs in research/spaces/platform_main_index.json govern over ASR errors. No implementation or real-model outcome is claimed.

## Key corrections

- IMG_9211 is Aalto University, confirmed by full-resolution logo and official humanoid brief; it is not Ignite Next.
- Aalto has two distinct challenges. This clip corresponds to Aaltonomous Humanoid, not Beyond the Clinic.
- Aalto requires autonomy. Rokoko requires teleoperation; they can share capture/training evidence but cannot share the same runtime-control claim.
- IMG_9214 lasts less than one second; it is a Verda fragment with no dependable spoken requirement.
- Current agent helpers are primarily offline declared-data validation. A real measured product journey remains necessary.

## Meta — AI Glasses for Everyone, Everyday

Agent `junction.meta`; clips IMG_9210.

### Verified requirements

- First-person perspective must enable a useful everyday interaction beyond mirroring a phone screen; state problem and audience. Evidence: official brief + video 00:02–00:40.
- Working prototype and deck; creativity, technical execution, real-world impact and inclusive interaction design. Evidence: official brief + video 00:40–00:49.
- Display/audio-first, web app/Device Access Toolkit mobile integrations have equal footing; handle permissions, errors, performance trade-offs, connectivity and device state changes. Evidence: official brief; video 00:49–00:57 corroborates supported experience categories.

### Proposed direction

Hands Free Recovery Coach: For one tabletop assembly task, first-person seeing lets a hands-occupied user get short contextual steps and recover from a deliberately wrong placement without touching a phone.

Demo moment: The assistant detects the wrong part in the real scene, explains the mismatch and resumes from the corrected step.

Scope: One object, bounded step graph, real capture path with labelled fallback; voice and text controls, explicit interrupt/cancel.

Rationale: Concrete wearable benefit plus demonstrated recovery and accessibility, not another general image narrator.

Current gap: Existing wearable-permission.mjs is synthetic consent-history replay, not glasses integration or a user journey.

### Decisive proof

- task completion versus checklist
- wrong-step detection precision and recovery completion
- end-to-end latency and interruption count
- device disconnect/reconnect, permission denial and cancel

### Failure modes

- SDK/device capability must be verified; mobile prototype is allowed but must not be claimed as glasses-qualified.
- Do not promise universal accessibility from one test.

Next action: Implement one verified capture adapter plus bounded assembly state machine and measured replay case.

## Aalto University — Aaltonomous Humanoid

Agent `junction.aalto-university`; clips IMG_9211.

### Verified requirements

- Autonomously sort 3–5 randomly positioned/rotated red, yellow and blue cubes/cylinders/triangular prisms into three fixed boxes within 2 minutes. Evidence: official brief.
- Fixed color mapping and unseen text instructions; two 7-DoF arms and Dex3 hands, legs/waist stiff; head color/depth, wrist cameras and joint states available; return joint targets at 30 Hz. Evidence: official brief.
- Isaac Sim first; real-robot Hugging Face datasets linked in Discord; Docker policy server through organizer safety filter; hidden simulation evaluation then real-robot finalists. Evidence: official brief + video 00:00–00:11.

The same Aalto sponsor also has Beyond the Clinic for at-home depression maintenance. That is a distinct brief and is not represented by IMG_9211.

### Proposed direction

Instruction Grounded Skill Compiler: Exploit the structured scene with a hybrid system: typed instruction map, calibrated depth/color perception, task-space grasp/place planning and a fast feedback controller. Use learned components only where they outperform this baseline.

Demo moment: An unseen natural-language sorting instruction changes the destination map, then a perturbed grasp is detected and recovered while the 30 Hz controller remains stable.

Scope: Reach fixed-mapping baseline first, then unseen instructions, then robustness; hole insertion is stretch only.

Rationale: Reliability on hidden layouts and sim-to-real gap matters more than a spectacular but fragile VLA demo.

Current gap: Aalto manifest is generic research/experiment guidance; a robust perception/control policy server is absent from this reviewed source slice.

### Decisive proof

- completed correct placements and total time across held-out seeds
- wrong-box count and dropped objects
- 30 Hz control timing and action bounds
- grasp verification and retry success
- separate real-robot outcomes from simulation

### Failure modes

- Do not run an LLM in the 30 Hz control loop.
- Teleoperation is data collection only here; human control at runtime contradicts autonomy requirement.
- Simulator train/test leakage and unverified hardware APIs.

Next action: Obtain exact policy-server contract, build a deterministic perception+control baseline, then compare learned refinements on held-out scenes.

## Rokoko — The Robot Teleoperation Challenge

Agent `junction.rokoko`; clips IMG_9212.

### Verified requirements

- Use Rokoko motion capture to control robotic hands, arms or humanoids; physical hardware or simulation permitted. Evidence: official brief + video 00:04–00:26.
- Create a useful, unexpected or impressive real-time teleoperation application; can combine other event hardware/challenges. Evidence: official brief + video 00:09–00:29.

### Proposed direction

Skill Capsule Teleoperation: Turn a real-time human teleoperation session into a portable, replayable robot skill with task constraints and verified motion provenance.

Demo moment: A human operates one hand/arm; the same captured intent is retargeted to a differently proportioned simulated body, with live tracking-quality overlay and clutch/stop.

Scope: One meaningful manipulation or articulated gesture, real Rokoko stream, measured retargeting; autonomous learned replay is extra, not a substitute for live teleoperation.

Rationale: Shows a new capability while exposing where motion transfer succeeds or fails, instead of only copying an avatar pose.

Current gap: retargeting.mjs checks declarations; it does not transform actual captured poses or demonstrate robot movement.

### Decisive proof

- pose-to-action latency and jitter
- joint limits and stop/clutch handling
- end-effector error on target movement
- replay repeatability and coordinate/unit correctness

### Failure modes

- Aalto autonomous task and Rokoko teleoperation are distinct objectives; do not merge runtime semantics.
- Hardware availability, calibration, coordinate frames and SDK license need verification.

Next action: Acquire the real Rokoko SDK sample and capture contract; replace declaration-only comparison with one real stream-to-simulator path.

## AstraZeneca — Equal Care Across Finland

Agent `junction.astrazeneca`; clips IMG_9213.

### Verified requirements

- Identify cancer-care access/outcome gap, locate its care-pathway stage and recommend concrete evidence-based improvement. Recommendations are the most important part. Evidence: official brief + video 00:28–00:56.
- Cover at least one indicator connected to Goal 3 of national cancer strategy, cite every claim using reliable public data and/or mentor insight, and deliver a working demo. Evidence: official brief.
- Support equal effective care and target diagnosis/treatment timeframes wherever people live in Finland. Evidence: official brief + video 00:11–00:26.

### Proposed direction

Same Chance Decision Desk: A policy analyst workspace links a source-backed regional/time disparity to a specific pathway stage, then ranks implementable actions with owners, capacity assumptions and uncertainty.

Demo moment: A user moves one referral-capacity assumption; the proposed action and uncertainty change while every claim stays linked to its source and a mentor can challenge the explanation.

Scope: One verified Goal 3 indicator, a comparable cohort/time window, two or more regions, and one actionable intervention. Use an explicit scenario model when impact is not empirically identified.

Rationale: It answers what to do, rather than stopping at a disparity map; it shows exactly which evidence supports the action and where causal certainty ends.

Current gap: fictional evidence-card structural checker and generic research companion do not address pathway gaps or actions.

### Decisive proof

- Goal 3 mapping validated against official strategy/mentor
- same cohort, cancer type, period and adjustment method for comparisons
- all displayed claims resolve to source or labelled scenario assumption
- do not infer referral/treatment delay from survival alone
- recommendations include implementable actor/action and evaluation metric

### Failure modes

- Ecological/causal inference from aggregated data.
- Small regional counts or incompatible periods make rankings misleading.
- A map or generic medical chatbot fails the explicit actionable-recommendation requirement.

Next action: Resolve one Goal 3 indicator and its data first; implement source-bound comparison and action model before broadening geography or adding generative chat.

## Verda — Best use of Verda

Agent `junction.verda`; clips IMG_9214, IMG_9216.

### Verified requirements

- Any Junction challenge using any Verda service can enter; document process and submit through official platform; show hard problem and scale beyond prototype. Evidence: https://verda.com/blog/junction-2026 read 2026-11-13.
- Free participant credits are advertised; individual access/redemption is not established by the clip or announcement. Evidence: official event article; video 00:09–00:27 is supportive but garbled.

IMG_9214 is 0.973s and its two ASR passes disagree. It has no dependable spoken requirement and is only a visual fragment linked to IMG_9216.

### Proposed direction

Reproducible Product Replay: Make Verda materially strengthen the selected product, then demonstrate quality, latency, failure handling and scale using identical hashed cases and pinned configuration.

Demo moment: One product experience runs interactively, then the same workload scales under load with visible quality/performance trade-offs and reproducible receipts.

Scope: A real workload from the chosen challenge; one verified service integration plus measured scale experiment, not a generic infrastructure dashboard.

Rationale: It makes infrastructure essential to a user outcome and documents the scaling path.

Current gap: gpu-run-plan.mjs is invented plan arithmetic, not authenticated Verda service use.

### Decisive proof

- input/model/config hashes
- quality parity and failure count
- p50/p95 latency and throughput under stated load
- actual usage/cost units when available; unknown stays unknown

### Failure modes

- Do not treat sponsor credits as redeemed or fictional resource plans as execution.
- Do not consume compute without a product hypothesis and stopping condition.

Next action: Verify existing entitlement; bind chosen challenge workload to real Verda service receipt and a small reproducible scale experiment.

## Independent challenge prompts

Ask Fable to reject unsupported challenge assumptions and unmeasured product claims. In particular: does the Aalto baseline beat a fragile end-to-end policy on hidden scenes; does Meta demonstrate a wearable benefit; is AstraZeneca’s recommended action supported rather than merely plausible; and is Verda essential to the user outcome?

Sources: authenticated official Junction brief index, source-pinned pet manifests and helper files, user-provided video/audio, current official Verda article. The prior Space cards remain useful navigation but are dated previews, not final challenge requirements.
