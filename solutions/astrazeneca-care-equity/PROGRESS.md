# Progress

**Stage:** public-aggregate research demo; evidence/evaluation update under review.
**Owner:** `astrazeneca`. **Merged baseline:** SalesSquad/junction-pets#113.
**Current task branch:** `codex/sama-evidence-evaluation-20261115`. Last updated 15 November 2026.

## Current follow-up — evidence and evaluation (15 November 2026)

Work ID `junction.astrazeneca.evidence-evaluation-20261115`. Base
`6d2efadb22678c259dfaf6817b43c883974a9eab`; branch
`codex/sama-evidence-evaluation-20261115`. This is a task-owned draft change;
Portfolio PR Recovery remains the integrator.

- Added an actionable county decision view and matching export with named proposed
  owner, 30/90-day plan, denominator, evidence, unknowns and human-review status.
- Added source-scoped national lung recording context and Goal 3.1/3.2 mapping;
  precision diagnostics/BioNeMo remain an unimplemented future direction.
- Historical forecasts are withheld. Fixed validation/test target overlap,
  calendar-gap windows, null-winner fallback and per-horizon export evidence.
  The original forecast and GPU artifacts are unchanged.
- Verification and reproducible demo route: [EVIDENCE_UPDATE.md](EVIDENCE_UPDATE.md).
  Corrected public-data training/evaluation, clinical review and publication remain open.

## Historical milestone evidence (14 November 2026)

The table below records the earlier implementation, not verification of this update.
The original sweep selected two transformers, five baselines and **no winner** for
colorectal screening; its exporter incorrectly substituted persistence. Original
forecast results have overlapping validation/test targets and are not qualified.

## Done and verified

| What | Evidence | Where it ran |
| --- | --- | --- |
| Public snapshot: 23 counties, 20 indicators, 10 cancer sites, NORDCAN survival; 57 requests with SHA-256 | `npm run data`; expected deaths sum to observed nationally within 0.1% | MacBook Pro |
| Analysis, recommendations, optimiser, evidence binding, brief, guardrails | `npm test`: 50 of 50 pass | MacBook Pro, Node 26 |
| Goal 3 wording and indicators | read from the strategy PDF (Figure 1, section 3) | fican.fi |
| Claim check on the real service | 650 calls to TypeSafe `jev-1.14.0`: 161 of 190 true sentences auto-passed, 29 to human review, 0 wrongly rejected; 460 of 460 corrupted sentences stopped | `data/claim-check/eval-v1.json` |
| Finnish plain-language summaries | Claude Haiku wrote 139 sentences for 23 counties; 91 passed the number match and the TypeSafe check and are shown, 48 were dropped | `data/narratives/fi-v1.json` |
| Early-warning forecaster, first run | 5 seeds on a Tesla V100, rolling-origin backtest | Verda spot GPU, `ml/artifacts/metrics.json` |
| Forecaster sweep | 14 configurations x 3 seeds, with and without 150 extra covariates: no transformer beats the best baseline by more than the seed-to-seed spread on any indicator; validation picks a transformer for 2 of 8 indicators and a baseline for 6 | Verda spot GPU, `ml/artifacts/gpu-sweep/SWEEP_REPORT.md` |
| Python tests for the forecaster | `python -m unittest discover -s ml/tests`: 10 pass | MacBook Pro |
| Demo renders with real numbers and no console errors, all eight sections, at 1280 px and 375 px | built-in browser | MacBook Pro |

## Tried and not included

- An open-weight model (Qwen3-32B-AWQ on vLLM) on a rented A100 in Finland as a second summary
  writer: the server failed during start-up and the spot machine was reclaimed before a fix.
  Zero sentences were generated, so nothing from it is in the product (`data/narratives/raw-open/RUN.json`).

## Not verified

- Dark mode, screen-reader pass and the print stylesheet.
- Numeric national target times for cancer treatment (THL guidance 21/2016): not read at source.
- Health-content review by an oncologist or epidemiologist. No AstraZeneca mentor input is included.
- The claim-check pass rate moves by one or two sentences between runs near the 0.8 threshold.
- No hosted deployment. The demo runs locally only.

## Known limits (see ARCHITECTURE.md)

Ecological data; mortality mixes incidence and survival; the route gap is one DLBCL cohort; costs are
planning assumptions; the scenario lower bound is zero. For yearly indicators the forecasting limit
is the data, not the compute.

## Next

1. Mentor review of the action library and the cost assumptions.
2. County incidence by site and stage from the Finnish Cancer Registry statistics application, to
   separate risk from care in the mortality ratios.
3. Confirm the THL target times and add them as the threshold for the treatment-stage indicator.
4. Hosted demo, once the owner decides on publication.

## Spend for this task

Verda: under USD 1 (spot V100 for about 1.5 hours, spot A100 for about 12 minutes; both machines and
their disks deleted). TypeSafe: about 1.6 million tokens, under USD 0.10. Haiku: under USD 0.20.
