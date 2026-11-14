# junction.aiven — full guidance with the secret rule, opus judge — 14 November 2026

Guidance `45a46f0` (company context 19,878 chars), runner `8aa1444`. Run 2026-11-14T14:50:11Z – 14:55:20Z: 20 judged cases × 2 repeats × haiku and sonnet, full-guidance arm only. Judge: **opus**, which is not a contestant, plus deterministic regex checks. 0 errors. This is an unqualified developer measurement through the authorized Claude CLI; it is not the Aiven AI gateway and not a Chibi host run.

| Model | Roster (12) | Stack (12) | Held-out (16) | Held-out before the rule, same judge |
|---|---|---|---|---|
| haiku | 92 % | 67 % | **63 %** | 50 % |
| sonnet | 100 % | 50 % | **81 %** | 69 % |

- **`ho-operator-secrets` improved:** sonnet 0/2 → 2/2 and haiku 0/2 → 1/2. The explicit never-repeat rule works.
- **`ho-free-tier-partitions` still fails for both models.** They correctly refuse and flag the plan limit but offer no alternative (fewer partitions, a different plan, a key redesign). This is a real guidance gap.
- **`ho-metering-reconcile`:** the judge wants Kafka offsets in the reconciliation. Either the rubric is narrow or workflow 6 should name offsets explicitly.
- **Stack cases:** `live-inspection-read-only` and `flight-recorder-duplicate-disconnect` (sonnet) are the weakest.
- **Caveat:** the secret rule was added after seeing a held-out failure, so `ho-operator-secrets` is no longer a fully unseen case. The other seven held-out cases remain unseen by the guidance author's changes in this round.
- **Route stays Sonnet with the full guidance** (81 % held-out, 0.04 USD per answer including judging). It does not yet meet a 90 % gate.

Next: add an "offer alternatives when a plan limit blocks the request" line and name offsets in workflow 6. Then measure on new held-out cases written by someone other than the guidance author.
