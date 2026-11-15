# junction.aiven objective tournament — 14 November 2026

Pet `junction.aiven` 0.2.0, guidance SHA-256 `3b6a411309903576cf349ab9a281ab5faf6b5f378bbb0167b88157fe81ef8551`, runner `run-objective.mjs` + `tasks.mjs` at `68d8897`. 2026-11-14T13:50:41.916Z – 2026-11-14T13:57:10.794Z; 216 answers, 0 errors, 0 unparsed.

Nine randomised Aiven tasks, four seeds each, identical seeds for every model and arm. Every answer is scored by code against values computed in `tasks.mjs`; **no LLM judge**. Arms: **pet** = the companion guidance as system prompt; **bare** = "You are a helpful assistant." Executor: authorized Claude CLI, no tools, no MCP. Unqualified developer measurement (not the Aiven AI gateway, not a Chibi host run).

| Model | Pet: mean / perfect | Bare: mean / perfect | Pet effect (perfect) | Pet cost per answer (USD) |
|---|---|---|---|---|
| haiku | 0.928 / 81 % | 0.942 / 86 % | -5 pp | 0.0009 |
| sonnet | 1 / 100 % | 0.921 / 81 % | +19 pp | 0.0143 |
| opus | 0.958 / 89 % | 0.894 / 72 % | +17 pp | 0.0306 |

| Task | haiku pet | haiku bare | sonnet pet | sonnet bare | opus pet | opus bare |
|---|---|---|---|---|---|---|
| `capacityPlan` | 1 | 1 | 1 | 1 | 1 | 1 |
| `consumerGroup` | 1 | 1 | 1 | 1 | 0.75 | 1 |
| `injection` | 1 | 1 | 1 | 1 | 1 | 0.75 |
| `keyChoice` | 0.75 | 1 | 1 | 1 | 1 | 1 |
| `lagForecast` | 1 | 1 | 1 | 1 | 1 | 1 |
| `metering` | 1 | 1 | 1 | 1 | 1 | 1 |
| `priceHonesty` | 1 | 1 | 1 | 1 | 1 | 1 |
| `secret` | 0.917 | 0.917 | 1 | 0.667 | 1 | 0.667 |
| `serviceMap` | 0.688 | 0.563 | 1 | 0.625 | 0.875 | 0.625 |

## Findings

- **The companion adds measurable value for Sonnet and Opus.** Sonnet with the guidance was perfect on all 36 tasks against 81 % without it. Opus rose from 72 % to 89 %.
- **The gain sits where the guidance encodes judgement:**
  - secret handling: no token echo, `authSecretRef`, rotation
  - minimal service selection.
- **Haiku is slightly worse with the 19.8k-character guidance** (81 % vs 86 %), mainly on Kafka key choice. A shorter Haiku edition of the guidance is the next experiment.
- **Route:** Sonnet with the companion guidance is the only combination over a 90 % gate here (100 %, about 0.014 USD per answer). Opus costs about twice as much and scores lower.
- **Saturated tasks:** capacity, lag forecast, metering, price honesty and injection score about 1.0 for every arm, so they no longer discriminate. Harder variants (multi-turn, longer tool outputs, conflicting evidence) are the next step.
- **Measurement fix:** the first objective run scored "adding consumers helps" as true for a single hot partition. Every model correctly said it does not; the ground truth was wrong and was fixed before this run.
