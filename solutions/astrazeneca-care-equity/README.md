# SAMA: Care Equity Navigator

**Junction 2026, AstraZeneca challenge M344 "Equal Care Across Finland".** *Sama* is Finnish for
"the same": the same cancer pathway for everyone, wherever they live and however they enter care.

SAMA answers the three questions of the brief on real public data, with a source for every number:

1. **Identify the gap.** 23 wellbeing services counties, 20 open indicators, cancer deaths by site
   2021-2025, and Nordic survival benchmarks.
2. **Locate it on the pathway.** Detection, primary care, referral, diagnosis, treatment start,
   outcome. Where public data cannot see a stage, the tool says so and treats that as a finding.
3. **Recommend what to do.** Eight evidence-bound actions with owner, mechanism, cost assumption,
   scenario effect with a range, the indicator to monitor and what is not known; a budget optimiser
   with an explicit inequality-aversion weight; and a claim check on every sentence of the brief.

It is decision support for planners. It makes no diagnosis, no patient-level inference and no
causal claim about a county.

## What the data shows (snapshot of 14 November 2026)

| Finding | Value | Source |
| --- | --- | --- |
| Five-year lung cancer survival, men, 2020-2024 | Finland 17.9% vs Sweden-Norway mean 31.1% (gap 13.2 points) | NORDCAN |
| Cancer deaths per year, 2021-2025 mean | 13,289; strategy target 11,960 (minus 10%) | Statistics Finland |
| Same age-specific death rates on the 2035 population | 15,798 deaths a year | Statistics Finland projection |
| Colorectal screening below the 80% target | 22 of 22 counties with data | THL Sotkanet |
| Cervical screening below the 80% target | 20 of 23 counties | THL Sotkanet |
| Highest age-standardised cancer mortality | Satakunta 1.10 and Kymenlaakso 1.10 times the national level, about 59 and 46 more deaths a year | Statistics Finland |
| Lung cancer mortality, Lapland | 1.24 times the national level | Statistics Finland |
| Symptom to treatment, public vs private or occupational route | mean 207 vs 123 days in a Finnish DLBCL cohort | Kuitunen et al. 2026 |
| Time from referral to treatment, by county | not published for any cancer | (data gap) |

Goal 3 of the National Cancer Strategy 2026-2035 ("Ensuring equal and effective cancer care") is
covered by all three of its indicators: Nordic-level survival for poor-prognosis cancers, cancer
mortality minus 10%, and treatment within target times. The third cannot be computed from open
data, which is why the first recommended action is to record four pathway timestamps nationally.

## Run it

```bash
npm test            # 50 tests: statistics, real-data analysis, optimiser, evidence binding, guardrails
npm run data        # refetch the public snapshot (THL Sotkanet, Statistics Finland, NORDCAN)
npm run build       # analysis + recommendations -> web/data/app.json
npm start           # http://127.0.0.1:4179
```

Node 22 or newer; the product has no runtime dependencies. `npm run data` needs Python 3.10+
(standard library only). The claim check uses TypeSafe when `TYPESAFE_API_KEY` is set in the
server environment; without it the interface reports "not configured" and nothing is guessed.

## How it works

- `pipeline/fetch_public_data.py` builds `data/snapshot/public-v1.json`. Every request URL, its
  retrieval time and the SHA-256 of the raw response are kept in the manifest.
- `src/stats.mjs`, `src/analysis.mjs`: exact Poisson intervals, indirect age standardisation,
  gamma-Poisson empirical Bayes shrinkage, false-discovery-rate control, slope index of inequality.
  Small counts are suppressed instead of ranked.
- `src/recommend.mjs`: the action library, the scenario model and the budget optimiser. Effects come
  from `data/evidence/literature-v1.json`; costs are planning assumptions the user can change. Each
  scenario number has a range from 300 parameter draws, and a stability score.
- `src/claims.mjs`, `src/claim-check.mjs`: the county brief is templated from the analysis (no
  language model writes numbers). A TypeSafe System One model answers two narrow questions per
  sentence: is it faithful to its facts and evidence, and does it overclaim? Anything short of a
  confident pass goes to a human. Measured on this product (`src/eval-claim-check.mjs`, 650 real
  calls, `jev-1.14.0`): 161 of 190 true sentences passed automatically, none was wrongly rejected,
  and all 460 deliberately corrupted sentences (flipped direction, changed number, wrong county,
  added causal claim) were stopped.
- `src/narratives.mjs`: plain-language Finnish summaries written by Claude Haiku. A sentence is
  shown only if every number in it occurs in its source claims and the TypeSafe check passes;
  failed sentences are dropped, never repaired.
- `ml/`: an early-warning forecaster for the pathway indicators, trained on the THL municipal panel
  with a rolling-origin backtest against persistence, drift and ridge baselines. The product ships
  whichever method wins on validation, and says so when a baseline wins.
- `web/`: static demo with a self-only content security policy.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the model equations and limits, and
[PROGRESS.md](PROGRESS.md) for what was verified and what is still open.

## What it does not claim

- A county difference is a measured difference between populations, not proof of worse care and
  not a statement about any patient.
- "Deaths postponed" is a scenario under stated assumptions. Its honest lower bound is zero.
- The route gap comes from one Finnish cohort of one cancer (n=160) and is used as a prior.
- Costs are placeholders for planning, not prices.
- AstraZeneca sponsors the challenge. No AstraZeneca data or product information is used, and no
  medicine is recommended.

## Disclosure

The `engine.mjs` guardrail module and its 14 tests were written earlier in the event as milestone 1
on invented fixtures (`fixtures/regions.json`, still labelled synthetic). Everything else here was
built during Junction 2026 on public data. Built with Claude Code and Codex CLI.
