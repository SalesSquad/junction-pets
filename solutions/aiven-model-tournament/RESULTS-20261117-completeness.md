# junction.aiven: semantic completeness pass (Codex CLI proposal) — 17 November 2026

Source `49abdbb`. Codex CLI (read-only, on the Mac mini) analysed the receipts and ranked three changes for the remaining completeness misses:
1. a separate completeness check with one revision;
2. an observation → interpretation → limitation → recommendation pattern in the guidance;
3. an evidence-extraction pass.

It also corrected the measurement: errors must count as failures, and item-level judge verdicts must be stored. Proposal 1 was implemented in `services/aiven-platform/completeness.mjs` and tested on `injection-cases-v3.json`. v3 now counts as development data, as Codex recommended. Haiku, 2 repeats, judges opus + sonnet with consensus. Receipts: `receipts/injection-20261116/completeness-*.json`, which also hold item-level verdicts.

| Arm | Pass, errors counted as failures | Revised | Recovered vs baseline | Broken vs baseline | Cost |
|---|---|---|---|---|---|
| framed-repair (baseline) | **87.1 % [77.3–93.1]** (61/70) | – | – | – | $3.69 |
| complete: full revision after a gap check | 81.4 % [70.8–88.8] | 58/68 | 4 | 7 | $4.50 |
| complete-add: draft kept, additions appended | 84.3 % [74.0–91.0] | 63/70 | 3 | 6 | $4.26 |

All arms: injection detected 100 %, followed 0 %, false alarms 0–3 %.

## Reading
- **Neither completeness variant helps.** The checker finds "gaps" in about 90 % of drafts. Full revisions drop correct content: recommendations, ranked findings, a stable baseline value. Additions bring unsupported assumptions, such as a date pinned when the source is undated or a retrieval time assumed. Both modules stay in the repository as tested options. No production path uses them.
- Recovered and broken counts compare independently generated answers, so they include sampling noise. The baseline rerun alone moved between 85.7 % and 87.1 % (strict) across two runs.
- **Measurement fixes kept:**
  - `passStrict` counts generation errors as failures; the earlier 88.2 % on v3 is 85.7 % strict.
  - Judge include/violation arrays are validated and stored per answer.
  - The judge prompt now counts `content_requests`.
- **Status of the 95 % goal:** Haiku sits at about 86–87 % strict on v3. Prompt-level and pipeline-level fixes have not moved it. Per Codex's protocol, a claim of at least 95 % would need about 400 fresh, independent, evidence-audited cases with at least 390 passes. That is not credible at the current level, so the next lever is the evidence-extraction pass (proposal 3) or a different model tier, measured on a new frozen set.
