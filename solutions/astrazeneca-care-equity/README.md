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

All figures in this table are in `web/data/app.json` (built from `data/snapshot/public-v1.json` and
`data/evidence/literature-v1.json`).

## Supporting tracks (below the product, never feeding it)

Three studies sit under the product on the same page. None of them changes a county figure, a
recommendation or the brief (`tests/tracks.test.mjs` checks this). Each is labelled on the page and
in `app.json` as `SYNTHETIC` or `RESEARCH` and names the JSON file every figure is copied from.
`src/build.mjs` fails if a cited file lacks a field it needs, and leaves a part out, with the reason
in `app.trackProblems`, if the file is absent.

**1. The data to collect** (SYNTHETIC; `data/eventlog/design-study-v1.json`, `DATA_COLLECTION.md`).
A pathway event log in Parquet, one row per dated event, and a simulation study of how many records
make it useful. To find a county 20% slower in one interval at 80% power with 69 comparisons
controlled, a county needs 473 (primary care), 513 (diagnostic) and 347 (treatment) complete
episodes. Under an assumed 37,000 cases a year, 5 of 23 counties could detect a 20% slowdown in
every interval within a quarter and 20 within a year. Fed with the scribe's measured errors (version-2
adapter, teacher-written notes), a 500-episode county locates a planted 30% slowdown in 48.6% to
77.7% of runs, against 99.7% to 99.9% with confirmed dates, and a county whose dates come from text
while the rest of the country uses structured fields is flagged in 100% of runs when nothing is wrong.
Simulated people under stated assumptions; not Finnish patients.

**2. Pathway scribe: Gemma on synthetic notes** (SYNTHETIC; `TRAINING.md`, `scribe/TEACHING.md`).
A small Gemma model with a LoRA adapter proposes dated pathway events from a Finnish note, and a
person confirms each one. Every note was written by a language model.
- Version-2 ablation on one A100 (`data/scribe/v2/ablation-v1.json`): selected Gemma 3 270M LoRA r16
  (validation exact match 36.1%, n = 310); test exact match 42.0% on 500 teacher-written (Nemotron)
  notes and 13.0% on 200 notes by a different writer (Haiku). The 1B and 4B sizes and every later
  arm were dropped for time.
- After the ablation (`data/scribe/v3/student/compare-v1.json`, 700 pooled test notes): reference
  33.7%; V3-270m-nemotron, the pre-registered primary, 38.1% (other writer 13.0% to 29.0%, its
  no-event notes 0/33 to 21/33; teacher-written 42.0% to 41.8%, p 1.0); C-270m-all-v2data 43.6%
  (Holm p 8.7e-16, all of the gain on the other writer's notes; teacher-written 42.0% to 42.0%);
  V3-270m-all 39.6% (but 39.4% against 42.0% on teacher-written notes, p 0.007); Gemma 3 1B (post
  hoc) 38.6%. Every run had 324 optimisation steps, so a larger training set is seen for fewer
  epochs (1,716 notes 3.0, 2,354 notes 2.2, 3,222 notes 1.6, 3,860 notes 1.3); the data arms differ
  in epochs as well as in data. No 4B number: it ran out of GPU memory twice and a third attempt was
  stopped.
- Serving (`serve/smoke/smoke-guided.json`, `serve/smoke/smoke-plain.json`): vLLM on the A100,
  100 held-out notes at concurrency 8: valid JSON 100/100 with structured outputs and 98/100 without;
  exact match 22% both ways (half the notes are by the other writer); latency p50 1.28 s and p95
  1.80 s with structured outputs. Every note went to a person; no threshold was calibrated.
- Teaching loop (`data/scribe/v3/summary-v1.json`): the Nemotron teacher wrote notes for 1,600
  answer keys (4,042 requests); 1,589 passed the code check, 1,465 of those were read back exactly,
  and the Jev gate accepted 1,506 of 1,589. On planted errors the Jev rule caught 66/80 and rejected
  0/80 clean notes (its question set was designed after earlier results were seen); OpenAI Decisions
  caught 58/80 and rejected 11/80. A Haiku audit found 2/160 wrong labels among sampled accepted
  notes. Cascade at a 5% target on 700 test notes: the student's own confidence let 270 notes skip
  review with 28 of them wrong (10.4%, above the target); the Jev score let 263 skip with 7 wrong
  (2.7%). More notes skipping review: no, within noise. Lower error among them: outside
  test-sampling noise, but within noise once the thresholds are re-chosen on resampled validation
  notes.
- Version 1 (laptop fallback, Gemma 3 1B on MLX) stays on the page as history, marked superseded.

**3. Same variant, same answer? Evo 2 on BRCA1** (RESEARCH; `data/genomics/brca1-evo2-v1.json`,
`genomics/README.md`). The open Evo 2 7B model scored 2,150 of 3,893 single-letter BRCA1 changes (a
partial run, 4,096 bp window instead of the published 8,192) against the laboratory assay of
Findlay et al. 2018. Headline, missense variants only: the strongest evidence level reached is
**supporting** towards loss of function and none towards normal function, with both the Tavtigian
2018 and the Pejaver 2022 thresholds; missense AUROC 0.709 (0.658 to 0.759); Evo 2 minus CADD on the
same variants -0.048 (-0.103 to 0.004). Over all types of change the AUROC is 0.822 (0.790 to 0.855)
and the level "moderate", for reference only. Research use only; nothing here classifies a variant
or decides eligibility for any treatment.

## Run it

```bash
npm test            # 72 tests: statistics, real-data analysis, optimiser, evidence binding, guardrails, supporting tracks
npm run data        # refetch the public snapshot (THL Sotkanet, Statistics Finland, NORDCAN)
npm run build       # analysis + recommendations + supporting tracks -> web/data/app.json
npm start           # http://127.0.0.1:4179
```

Node 22 or newer; the product has no runtime dependencies. `npm run data` needs Python 3.10+
(standard library only). The claim check uses TypeSafe when `TYPESAFE_API_KEY` is set in the
server environment; without it the interface reports "not configured" and nothing is guessed.
`npm run build` reads the committed result files of the supporting tracks; re-running those studies
needs the Python environments, services and GPU described in `DATA_COLLECTION.md`, `TRAINING.md`,
`scribe/TEACHING.md` and `genomics/README.md`.

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
  failed sentences are dropped, never repaired. Of 139 generated sentences 91 are shown.
- `ml/`: an early-warning forecaster for the pathway indicators, trained on the THL municipal panel
  with a rolling-origin backtest against persistence, drift and ridge baselines. A GPU sweep of 14
  transformer configurations (3 seeds each, with and without 150 extra covariates) found none that
  beats the best baseline by more than the seed-to-seed spread, so the product ships the validated
  winner per indicator: a baseline for 6 of 8. For yearly indicators the limit is the data.
- `src/tracks.mjs`, `web/tracks.mjs`: the three supporting tracks, copied from their result files
  with a source and a label for every figure. A test fails if a figure on those sections is typed
  into the code instead of read from data.
- `web/`: static demo with a self-only content security policy. The main product comes first; the
  supporting tracks follow it.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the data flows, model equations and limits,
[PROGRESS.md](PROGRESS.md) for what was verified, what is synthetic, what failed and what is open,
and [runs/RUNLOG.md](runs/RUNLOG.md) for one line per run.

## What it does not claim

- A county difference is a measured difference between populations, not proof of worse care and
  not a statement about any patient.
- "Deaths postponed" is a scenario under stated assumptions. Its honest lower bound is zero.
- The route gap comes from one Finnish cohort of one cancer (n=160) and is used as a prior.
- Costs are placeholders for planning, not prices.
- Nothing from simulated people or model-written notes is a finding about Finnish patients, and no
  scribe result shows that the method works on real clinical text. Judges and auditors are models;
  their agreement is not ground truth.
- The genomics benchmark is research only: no variant classification, no treatment eligibility.
- AstraZeneca sponsors the challenge. No AstraZeneca data or product information is used, and no
  medicine is recommended.

## Disclosure

The `engine.mjs` guardrail module and its 14 tests were written earlier in the event as milestone 1
on invented fixtures (`fixtures/regions.json`, still labelled synthetic). Everything else here was
built during Junction 2026; the supporting tracks use simulated people, model-written notes and a
public laboratory benchmark, never patient data. Built with Claude Code and Codex CLI. Runtime
services of the product are TypeSafe System One (claim check) and Claude Haiku (Finnish summaries).
The supporting tracks also used NVIDIA Nemotron on Verda (teacher), TypeSafe Jev and OpenAI
Decisions (judges), Claude Haiku (second writer and auditor), Gemma 3 (student) and Evo 2
(genomics). GPU work ran on Verda; the A100 that ran the version-2 scribe runs, the vLLM smoke test
and the Evo 2 scoring was deleted at 19:27 UTC after its results were copied back.
