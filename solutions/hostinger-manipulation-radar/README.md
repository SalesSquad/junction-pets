# Signal Desk — Hostinger Manipulation Radar

An offline analyst dashboard for **possible coordinated campaigns**, with inspectable evidence, explicit counterevidence and an honest error ledger. **SYNTHETIC / OFFLINE_DETERMINISTIC. Maturity 2/6: functional local prototype, not independently or live-host qualified.** No real AI or provider calls. Independent work, not Hostinger endorsement.

## Run without installation

Node >=22, no packages or build step:

```sh
cd solutions/hostinger-manipulation-radar
node server.mjs
# Open http://127.0.0.1:4173
# Ctrl-C stops the server. Optional PORT selects a different local port.
node --test tests/*.test.mjs
node benchmark.mjs
```

The server binds **127.0.0.1 only**, exposes an exact read-only allowlist and never logs observations. The initial restricted Codex executor denies loopback binding (`EPERM`), but a **separate authorized Mac Mini coordinator runner confirmed actual local HTTP smoke** and 15/15 focused tests. Browser rendering and remote/public Hostinger deployment remain NOT VERIFIED. No server was left running.

## Walk the complete investigation

1. Start with **Synchronized launch swarm**. Rank findings by score, observation time or account count. Inspect event-linked score contributions and the temporal cluster.
2. Open the event ledger and pairwise links. Every positive and negative signal lists supporting event IDs; the ledger shows exact payloads, ages, destinations and amplification targets. Timeline bars represent event order, not time bins.
3. Remove timing or another signal in the what-if panel. The score and review decision recalculate at fixed threshold. Removing counterevidence may increase the score. This is rule ablation, not causal inference.
4. Switch to **The wire-service trap** and **Organic viral workshop**. Repetition and popularity are insufficient to establish malicious intent. Supplied attribution is unverified and can be spoofed.
5. Use **Mixed investigation desk** to investigate three independent groups. Mark a group Needs investigation, Likely benign or Insufficient context, or reset it. Only disposition enums and synthetic IDs enter localStorage; a denied store falls back to session memory. No text/account observations are persisted.
6. Download a structured JSON report with synthetic observations, signal evidence, base SHA, review dispositions and ablation selections. Benchmark metrics and exact denominators remain visible in the quality ledger. Native controls support keyboard use; layout adapts to narrow screens. Actual visual, screen-reader and device behavior still needs browser qualification.

There is intentionally no arbitrary-file import or live data ingestion. This keeps the demo bounded and avoids collecting personal data before licensing, consent and data-governance work exists.

## Development benchmark, not a field claim

Policy v1 is fixed at **65 points**, a positive timing signal and at least three positive signal families. No keyword, belief, identity or protected-trait features enter Radar scoring. Labels are separate fixture files used only by the benchmark; held-out observations are outside the public server allowlist. The naive baseline flags any repeated text appearing at least three times, or `shocking`, `urgent`, `exposed`.

Unit: a scenario is positive if any group receives analyst review. Eight development scenarios and twelve separate held-out synthetic parameter cases share a generator; this is **not an independent, blinded or representative evaluation**. Labels describe authored intent, which may be behaviorally indistinguishable (benign volunteers). The fixed threshold was not fitted to held-out results. Metrics report exact counts, with null for undefined ratios.

| Split / method | TP / FP / TN / FN | Precision | False-positive rate | Recall |
| --- | --- | --- | --- | --- |
| Development Radar | 3 / 0 / 5 / 0 | 3/3 = 100% | 0/5 = 0% | 3/3 = 100% |
| Development baseline | 3 / 2 / 3 / 0 | 3/5 = 60% | 2/5 = 40% | 3/3 = 100% |
| Held-out Radar | 4 / 1 / 6 / 1 | 4/5 = 80% | 1/7 = 14.3% | 4/5 = 80% |
| Held-out baseline | 4 / 3 / 4 / 1 | 4/7 = 57.1% | 3/7 = 42.9% | 4/5 = 80% |

Radar misses `h-evasive` (delayed adversary) and flags `h-volunteers` (benign coordinated activity). These are exposed, not suppressed. False-positive controls reduce fixture false alarms but do not establish deployment efficacy, bot identity or intent. Expect drift and adaptive evasion. One additional error would materially change these tiny denominators.

## Source and challenge fit

Task `J26-HOSTINGER-M2-20261114`, immutable base `b7a51ee7acc3b1923fa0506b31a0f2eafb56f402`, branch `codex/j26-hostinger-manipulation-radar-20261114`. Sources were read from the supplied clone, with no remote refresh or provider login. `partnerEvidenceKey: hostinger`, snapshot **2026-11-14**. [Official M357: Decode the Noise](https://hackjunction.app/participate/45/challenges/357), recorded in `../../docs/challenge-research/current-source-catalog.json` and routed by `../../docs/AGENT_SOURCE_INDEX.json`.

M357 weights detection quality, false positives and explainability at **40%** and technical execution / live Hostinger deployment at **25%** (originality 20%, clarity 15%). This prototype addresses the first category through timing, account similarity, text/URL reuse and amplification evidence. It does not satisfy the AI-powered or live-deployment requirements.

The latest supplied clarification states: team booth coupon → KVM 2 for one month → 5000 AI credits and Instant web scraping. VPS, AI Router and possible AI Builder activation are separate. **Own-account activation, all real Hostinger integrations and public deployment: NOT VERIFIED.** No benefit was redeemed or claimed available.

Acceptance and exact execution evidence are in [PROGRESS.md](PROGRESS.md); trust boundaries and scoring rules are in [ARCHITECTURE.md](ARCHITECTURE.md). Next dependency: **valid licensed labelled data + authorized live coupon / Hostinger deployment access**, owned by the coordinator/data and deployment owner. No deployment artifact, submission or production efficacy is claimed.
