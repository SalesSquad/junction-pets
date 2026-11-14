# Architecture and method

## Data flow

```
THL Sotkanet API ─┐
Statistics Finland ┼─ pipeline/fetch_public_data.py ─ data/snapshot/public-v1.json ─┐
NORDCAN API ──────┘        (manifest: url, time, sha256 per request)                │
published studies ─ data/evidence/literature-v1.json (verified flag per row) ───────┤
THL municipal panel ─ ml/ (forecaster + backtest) ─ data/ml/forecast-v1.json ───────┤
                                                                                     ▼
                         src/analysis.mjs ─ src/recommend.mjs ─ src/build.mjs ─ web/data/app.json
                                                                                     │
                 web/ (static) ◄─────────────────────────────────────────────────────┘
                   └─ POST /api/verify-claims ─ src/claim-check.mjs ─ TypeSafe System One (optional)
```

`src/build.mjs` refuses to build if any action or assumption cites an evidence row that is missing
or not verified.

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

## Limits

- Ecological data: nothing here identifies individuals or supports individual-level conclusions.
- Mortality reflects incidence and survival together. County incidence by site is not in the open
  sources used, so excess mortality may be driven by risk factors as well as by care.
- The population structure of 2024 is applied to the whole 2021-2025 window.
- Region codes follow the 2026 classification; one municipality is unmapped in the projection table.
- Numeric national target times for cancer treatment (THL guidance 21/2016) were not confirmed at
  source; the tool therefore does not assert a legal threshold.
