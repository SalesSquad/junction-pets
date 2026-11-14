# Progress

**Stage:** working demo on real public data. **Owner:** `astrazeneca`. **PR:** SalesSquad/junction-pets#113.
**Branch:** `codex/j26-astra-equity-m1-20261114`. Last updated 14 November 2026.

## Done and verified

| What | Evidence | Where it ran |
| --- | --- | --- |
| Public snapshot: 23 counties, 20 indicators, 10 cancer sites, NORDCAN survival; 57 requests with SHA-256 | `npm run data`; expected deaths sum to observed nationally within 0.1% | MacBook Pro |
| Analysis, recommendations, optimiser, evidence binding, brief | `npm test`: 50 of 50 pass | MacBook Pro, Node 26 |
| Goal 3 wording and indicators | read from the strategy PDF (Figure 1, section 3) | fican.fi |
| Claim check on real service | 650 calls to TypeSafe `jev-1.14.0`: 161 of 190 true sentences auto-passed, 29 to human review, 0 wrongly rejected; 460 of 460 corrupted sentences stopped | TypeSafe API, `data/claim-check/eval-v1.json` |
| Early-warning forecaster | 5 seeds on a Tesla V100; rolling-origin backtest; baselines win or tie for 7 of 8 indicators, so the product ships the validated winner per indicator | Verda spot GPU, `ml/artifacts/metrics.json` |
| Demo renders with real numbers, no console errors, all eight sections | built-in browser at 1280 px | MacBook Pro |

## Not verified

- Layout at 380 px and in dark mode, screen-reader pass, print stylesheet.
- Numeric national target times for cancer treatment (THL guidance 21/2016): not read at source.
- Health-content review by an oncologist or epidemiologist. No AstraZeneca mentor input is included.
- The claim-check pass rate moves by one or two sentences between runs near the 0.8 threshold.
- No hosted deployment. The demo runs locally only.

## Known limits (see ARCHITECTURE.md)

Ecological data; mortality mixes incidence and survival; the route gap is one DLBCL cohort; costs are
planning assumptions; scenario lower bound is zero.

## Next

1. Mentor review of the action library and the cost assumptions.
2. County incidence by site and stage from the Finnish Cancer Registry statistics application, to
   separate risk from care in the mortality ratios.
3. Confirm the THL target times and add them as the threshold for the treatment-stage indicator.
4. Hosted demo, once the owner decides on publication.

## Spend

Verda: one spot V100 for the training runs (about USD 0.12 an hour). TypeSafe: about 1.2 million
tokens. Haiku: Finnish summaries for 23 counties. All within the limits given for this task.
