# Architecture and method

> **15 November evidence update:** the application now adds source-scoped decision
> briefs (`src/decisions.mjs`) and forecast admission (`src/forecast-integrity.mjs`).
> National recording-gap evidence never enters county scores or the optimiser.
> Historical v1 forecasts below are preserved but withheld; a new v2 artifact must
> carry disjoint-target evaluation evidence. See `ml/SPEC.md` for the current contract.

## Data flow

The product (top) is built from public aggregate data. The three supporting tracks (bottom) are
bundled into the same `app.json` by `src/tracks.mjs` but never feed the analysis, the
recommendations or the brief.

```
PRODUCT (public aggregate data)
THL Sotkanet API ─┐
Statistics Finland ┼─ pipeline/fetch_public_data.py ─ data/snapshot/public-v1.json ─┐
NORDCAN API ──────┘        (manifest: url, time, sha256 per request)                │
published studies ─ data/evidence/literature-v1.json (verified flag per row) ───────┤
THL municipal panel ─ ml/ (forecaster + backtest) ─ data/ml/forecast-v1.json ───────┤
                                                                                     ▼
                         src/analysis.mjs ─ src/recommend.mjs ─ src/build.mjs ─ web/data/app.json
                                                                   ▲                 │
                 web/ (static) ◄───────────────────────────────────┼─────────────────┘
                   └─ POST /api/verify-claims ─ src/claim-check.mjs ─ TypeSafe System One (optional)
                                                                   │
SUPPORTING TRACKS (SYNTHETIC or RESEARCH)                  src/tracks.mjs (required fields checked;
                                                                   │      absent file → app.trackProblems)
1. Data collection (SYNTHETIC)                                     │
   eventlog/simulate.py ─ validate.py ─ design_study.py ─ data/eventlog/design-study-v1.json ─┤
                     ▲                    (sizes, design grid, nulls, early warning)          │
                     └── measured per-event error of the scribe adapters ◄── scribe evals    │
                                                                                              │
2. Pathway scribe (SYNTHETIC)                                                                 │
   scribe/sample.py (answer keys) ─ NVIDIA Nemotron teacher on Verda (writes Finnish notes)   │
     ─ code check ─ blind read-back ─ TypeSafe Jev gate ─ Parquet datasets                    │
     ─ Claude Haiku: second writer (other-writer test notes) and label auditor                │
   v1: scribe/mlx_fallback.py, laptop, Gemma 3 1B ─ data/scribe/eval-v1.json (history) ───────┤
   v2: scribe/v2/run_ablation.py on one A100 ─ data/scribe/v2/ablation-v1.json ───────────────┤
   v3: scribe/teacher2 (round 2) ─ scribe/judges (benchmark) ─ scribe/v3/gate.py ─ audit      │
       ─ post-ablation students (pre-registered) ─ data/scribe/v3/student/compare-v1.json ────┤
       ─ scribe/v3/cascade.py (student + Jev / Decisions at inference) ─ cascade-v1.json      │
       ─ scribe/v3/summarise.py ─ data/scribe/v3/summary-v1.json ─────────────────────────────┤
   serving: serve/ (vLLM + LoRA, structured outputs, guard.py) ─ serve/smoke/smoke-*.json ────┤
   training figures: scribe/v2/training_figures.py ─ data/scribe/v2/training-figures-v1.json ─┤
                                                                                              │
3. Genomics (RESEARCH)                                                                        │
   genomics/fetch_data.py (Findlay 2018 table, GRCh37) ─ score_evo2.py on the A100 (Evo 2 7B, │
   open weights) ─ analyse.py ─ data/genomics/brca1-evo2-v1.json ─────────────────────────────┘
```

`src/build.mjs` refuses to build if any action or assumption cites an evidence row that is missing
or not verified. `src/tracks.mjs` refuses to build if a track's result file lacks a field the page
needs, and leaves a part out (with the reason in `app.trackProblems`) if the file is absent. The
page renders the product first and the tracks after it; every figure in the tracks is wrapped with
its label chip, and `tests/tracks.test.mjs` fails if a figure in those sections is typed into the
code instead of coming from data.

## Gap detection

**Indicators.** For each county the level is the mean of the last three years. Its uncertainty is
the pooled year-to-year noise of that indicator, `sd = sqrt(Var(first differences) / 2)`, which
ignores smooth trends. Two separate questions are asked: is the county worse than the national
value (county flag, Benjamini-Hochberg at 10% within the indicator), and does it miss the strategy
target (needs 95% probability). Keeping them apart matters: colorectal screening misses the target
everywhere, so it is a national problem, while only two counties are worse than the country.

**Mortality.** Observed deaths 2021-2025 by cancer site and county (Statistics Finland 13u5).
Expected deaths by indirect standardisation: national age-specific deaths (11az) times the county's
share of each five-year age group (14wx, aggregated from municipalities). The ratio has an exact
Poisson interval and is then shrunk towards the national ratio with a gamma-Poisson empirical Bayes
model (Marshall 1991). Counties with fewer than 20 expected deaths for a site are suppressed.
Check: expected deaths sum to observed deaths nationally within 0.1% for every site.

**Gradient.** Slope index of inequality across counties ranked by education index,
population-weighted, bootstrap interval. It describes places, not people.

**Goal 3.** NORDCAN five-year relative survival, Finland against the mean of Sweden and Norway (the
strategy's own benchmark), with history. Mortality target against a demographic projection: the
same age-specific rates applied to the official 2030 and 2035 populations.

## Locating the gap

Six stages: detection, primary care, referral, diagnosis, treatment start, outcome. Three have
public county indicators. For each county the tool reports the earliest measured stage that is
flagged and the stage with the worst standardised score. Diagnosis and treatment start have no
public county statistic for any cancer; they are drawn as empty on purpose and listed in
`analysis.dataGaps`. A county with excess mortality and no flagged measured stage is reported as
"not locatable from public data".

## Scenario model (every output labelled SCENARIO)

For a county with `D` cancer deaths a year:

```
deaths postponed = D × s × [ p × R(h, d_all) + (1 − p) × R(h, d_timed) ]  +  D_lung × a × (1 − rr)
R(h, d) = 1 − h^(−d / 28)
```

- `s` share of deaths in patients who entered through symptoms and primary care (assumption, 0.3-0.7);
- `p` public-route share, `1 −` fast-route share (0.45 from the Kuitunen cohort, scaled by the
  county's private-referral share relative to the national value);
- `h` mortality hazard ratio per four weeks of delay: 1.06, range 1.00-1.13 (Hanna 2020). Hanna
  measured delay of treatment; applying it to days saved before diagnosis is an assumption, and the
  lower bound means no effect;
- `d` days saved: timed pathways 17 (15-19, Jensen 2015); equal fast lane = share closed × route gap
  of 84 days (Kuitunen 2026); navigation = share of work-ups stalled beyond 90 days × their mean
  excess × `(1 − 1/1.51)` (Freund 2014). Overlapping actions combine as
  `G × (1 − Π(1 − d_i / G))`, so they never save more than the route gap `G`;
- low-dose CT: `rr` 0.76 (NELSON), reach `a` an assumption (0.1-0.4).

**External check.** For a 17-day shorter interval the model implies a hazard ratio of 0.965. Denmark
observed 0.86 (0.73-1.01) for pathway-referred patients. The model is more conservative and lies
inside the observed interval.

## Optimiser

Choose actions per county under a yearly budget to maximise `Σ w_r × deaths postponed_r`, with
`w_r = (shrunk mortality ratio)^ε`. `ε = 0` is pure efficiency; larger values move benefit towards
counties with excess mortality. The objective is submodular with a knapsack constraint. Three
constructions are compared (benefit-per-euro greedy, absolute-gain greedy, and greedy seeded with
each single item) and the best is kept; a test bounds the gap to the exhaustive optimum at 10%.
Three hundred parameter draws give each pick a range and a stability score (how often it stays in
the re-optimised portfolio). The efficiency-equity frontier is reported for ε in {0, 1, 3, 6, 10}.

The detection track (screening) is reported separately as percentage points and share of the 80%
target gap closed. No mortality effect is claimed for it.

## Claim check

The brief is generated by templates from `app.json`. The server rebuilds each sentence itself, so
the browser cannot supply text or evidence. One TypeSafe Choice question per sentence:
supports / contradicts / says nothing. `SUPPORTED` needs probability 0.8 or more; everything else
is routed to a human. No key, no verdict.

## Early-warning forecaster

Small transformer over eight years of a unit's indicator history (municipalities, counties,
country), quantile outputs for one and two years ahead, five-seed ensemble, split-conformal
calibration. Rolling-origin backtest with no target year in training. Baselines: persistence,
drift, pooled ridge. Selection by validation error per indicator. Yearly health indicators are
strongly autocorrelated, so a baseline often wins; that result is reported, not hidden.

## Supporting track 1: the data to collect (SYNTHETIC)

**Format.** `pathway_events`, one row per dated event (Parquet): nine event types in one pathway
order, county, entry route, cancer site, age band, date precision (`DAY` or `MONTH`), source
(`STRUCTURED_FIELD`, `TEXT_EXTRACTED`, `PATIENT_REPORTED`), extraction confidence and a
human-verified flag. Four core events define three intervals: primary care (first contact to
referral sent), diagnostic (referral sent to diagnosis) and treatment (diagnosis to treatment start).

**Sizing.** Log-durations are treated as normal; a county is compared with the country by the
difference of mean log-duration, Welch test with t critical values, Bonferroni over 23 counties x 3
intervals, minimum 30 complete day-precision episodes. Required n per interval uses the
log-duration spread measured in simulated episodes, checked by simulation at those sizes, against
an infinite reference and against the rest of the country.

**Design study.** `eventlog/design_study.py` simulates counties with a planted slowdown in one
interval under four collection designs (today's indicators, two timestamps, the core events, all
events), sizes, missingness and month-precision shares, plus null experiments (no slowdown),
repeated quarterly looks, early warning and assumed text-extraction error rates. The measured
per-event error of the scribe adapters (wrong-date share, missing share, signed date errors from
their test notes) is fed into the same detector. Everything is simulated; the national case count,
route shares and step distributions are assumptions.

## Supporting track 2: the pathway scribe (SYNTHETIC)

**Data.** Code samples an answer key (entry route and dated events). A teacher model (NVIDIA
Nemotron, served on Verda) writes a Finnish note for it; code checks that the stated dates are
present and nothing extra is claimed; a blind second call of the teacher reads the note back without
the key; one repair is allowed. A judge (TypeSafe Jev) gates each pair; OpenAI Decisions is measured
alongside but is not in the rule. Claude Haiku writes a second set of notes (a different writer, for
test) and audits samples of accepted and rejected notes. Labels are exact for the sampled key;
whether a note states exactly that key is judged by models, not by people.

**Training.** LoRA on Gemma 3 (attention and MLP projections), loss on the answer, greedy decoding,
output as JSON with absolute dates. Version 1 ran as a laptop fallback (Gemma 3 1B, MLX) because the
planned GPU stopped answering; it is kept as history. Version 2 ran a staged ablation on one A100 in
a fixed budget (sizes, LoRA variants, output format, data mix), selected on validation exact match
with paired McNemar tests, then read the test notes once. After the ablation, data and size arms
were pre-registered (`data/scribe/v3/student/preregistration.json`) and compared with the frozen
reference on the same test notes (exact McNemar, Holm over the pre-registered comparisons). All runs
use the same number of optimisation steps, so a larger training set means fewer epochs.

**Teaching loop and cascade.** Round 2 of the teacher targets weak spots by curriculum (hard
standard notes, careful notes, notes without events, long multi-visit notes, terse notes). A judge
benchmark plants one error in a note's claimed answer and measures how often each judge catches it
and how often it rejects a clean pair, on a held-out half. At inference, a cascade pre-fills a note for
one-click confirmation only when a score (student confidence, Jev score, or a logistic combination)
passes a threshold chosen on validation notes only for a target error; a person still confirms every
note, and every other note is marked as needing editing; test notes never reach a fit or a
threshold (`scribe/v3/cascade.py` raises if they do). Differences are paired bootstrap intervals,
also with the thresholds re-chosen on resampled validation notes.

**Serving.** `serve/` runs vLLM with the base model and the LoRA adapter, OpenAI-compatible chat
completions with optional structured outputs (JSON schema), a bearer-key guard on every route but
`/health`, and a client that sends every note to human review unless a calibrated threshold exists.
The smoke test measured validity, exact match and latency on 100 held-out notes and compared each
answer with the offline evaluation of the same adapter.

## Gemma reads, code counts; Nemotron reads and plans (added 15 November)

The plan in `NVIDIA_OPTIONS.md` section 3 ran in three lanes; the integrator bundles their result
files into `app.json` with the same rules as the other tracks (required fields, absent file named in
`app.trackProblems`, every figure copied, none typed).

```
runs/diagnose/diagnose-v1.json ─────────────── scribe.gemmaAlone   (Gemma alone on relative dates)
scribe/v3/resolve.py + lexicon.py (frozen, sha256 in data/scribe/v4/resolver/freeze.json)
  ─ reproduce ─ data/scribe/v4/resolver/reproduce-v1.json ─ scribe.resolver
  ─ serve/client.py (default arm A'), scribe/v3/cascade.py (--resolve)
scribe/mlx2 (MLX arms A, B, C on this Mac) ─ data/scribe/v4/mlx/validation-v1.json
scribe/stress (Nemotron writes, code gate, Jev gate; frozen + preregistered) ─ data/scribe/stress/
scribe/v4/eval8.py (each system scored once; cascade thresholds on validation only)
  ─ data/scribe/v4/eval/results-v1.json ─ scribe.evaluation
scribe/nemotron/reader.py (v0 ... v3, one change at a time) ─ data/scribe/nemotron/reader-v1.json ─ scribe.reader
src/planner (4 SAMA tools, number check, Jev gate, off-limits guard) ─ data/planner/plans-v1.json ─ planner
src/planner/vision_6b.py ─ data/planner/vision/vision-6b-v1.json ─ planner.vision
eventlog/extraction_intervals.py ─ data/eventlog/design-study-v1.json (measured_interval_extraction) ─ insight
serve/demo (Gemma 3 270M + adapter on CPU, resolver A') ─ POST /api/scribe in web/serve.mjs
flare/ (NVIDIA FLARE 2.9.1 simulator, 23 SYNTHETIC sites) ─ data/flare/ ─ flareGate
```

**Resolver.** Gemma copies the date phrase it read; code computes the date from the note date. The
rule (`scribe-v3-relative-resolver-v1`) was frozen and hashed before the stress set existed. Arm A
resolves digits only; arm A' adds a small Finnish lexicon and sends vague phrases ("pari viikkoa
sitten", "viime kuussa") to a person instead of guessing.

**Evaluation.** Arms were selected on validation notes only. The 700 test notes had been read before,
so their figures are post hoc. The stress set (new phrasings: number words seven to twelve,
"toissapäivänä", vague phrases) was frozen with a preregistration before any system read it, and
each system read it once. `src/tracks.mjs` refuses to bundle the evaluation unless its own hash
checks passed (`verify.all_ok`).

**Two readers, one person.** A note is pre-filled for one-click confirmation only when the
code-resolved Gemma answer and the Nemotron reader agree exactly; otherwise it needs editing. The
configuration was chosen on validation notes only (`scribe/v3/cascade.py` leak guard). A person
confirms every note either way.

**County planner.** Nemotron 3.5 Super VL calls four SAMA tools (`get_county_brief`,
`get_portfolio`, `get_evidence`, `get_roadmap_measure`) and drafts a plan per area. Code drops every
sentence with a number that is not in a tool output of the same run; TypeSafe Jev drops unfaithful or
overclaiming sentences; nothing is repaired. The page fetches the full drafts; `app.json` carries the
summary. Because the drafts were written on an earlier build, `src/build.mjs` (`plannerToolCheck`)
re-runs every stored tool call on the current build and names the areas whose tool outputs changed;
the page shows a "read with care" note for exactly those.

**Insight.** `eventlog/extraction_intervals.py` feeds the scribe's measured within-note interval
errors (as is, and with resolver arm A) into the repository's county detector. `buildInsight` looks
up each row it shows by its labels and fails the build if one is missing.

## Supporting track 3: Evo 2 on BRCA1 (RESEARCH)

The open Evo 2 7B model (Arc Institute weights, run directly without a vendor key) scores each
single-letter change of the Findlay et al. 2018 saturation genome editing table as the drop in mean
log-likelihood of a window around the variant (alternate against reference, GRCh37 plus strand).
Separation of loss-of-function from functional variants is measured by AUROC with position-cluster
bootstrap intervals, compared on the same variants with CADD, phyloP and a consequence-class lookup.
Evidence strength follows the ACMG/AMP Bayesian framework: likelihood ratios per score bin with
one-sided bounds, against the Tavtigian 2018 and Pejaver 2022 targets. The headline is computed on
missense variants only, the class a computational criterion is meant for. The run is partial (time
budget) and used a shorter window than the published notebook (memory cap).

## Limits

- Ecological data: nothing here identifies individuals or supports individual-level conclusions.
- Mortality reflects incidence and survival together. County incidence by site is not in the open
  sources used, so excess mortality may be driven by risk factors as well as by care.
- The population structure of 2024 is applied to the whole 2021-2025 window.
- Region codes follow the 2026 classification; one municipality is unmapped in the projection table.
- Numeric national target times for cancer treatment (THL guidance 21/2016) were not confirmed at
  source; the tool therefore does not assert a legal threshold.
- Supporting tracks: every scribe and event-log figure comes from simulated people and
  model-written notes; nothing there is evidence about real clinical text or Finnish patients. The
  genomics benchmark is research only and partial.
