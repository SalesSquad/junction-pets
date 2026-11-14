# The data Finland needs to collect, and how much of it

SAMA's main finding is a blind spot: no open statistic says how long any cancer patient in any
county waits between referral, diagnosis and first treatment. This note specifies the smallest
data collection that closes the blind spot, why it must be patient-level events, how many records
make it statistically useful, and whether a small open model (Gemma) might, after validation on
real text, help fill it from notes that already exist. Everything generated from this
specification is SYNTHETIC until real data arrives, and nothing here is for clinical use.

The figures between `<!-- STUDY:... -->` markers are written by `eventlog/audit.py` from
`data/eventlog/design-study-v1.json`; they are not typed by hand.

## 1. Format: a pathway event log in Parquet

One row per event, long format. Table `pathway_events`:

| column | type | values |
| --- | --- | --- |
| `episode_id` | string | pseudonymous cancer episode key (salted hash; never a personal identity code) |
| `event_type` | dictionary | `SYMPTOM_ONSET_REPORTED`, `FIRST_CONTACT`, `PHYSICIAN_ASSESSMENT`, `REFERRAL_SENT`, `REFERRAL_RECEIVED`, `DIAGNOSIS`, `MDT_DECISION`, `SPECIALIST_VISIT`, `TREATMENT_START` (in pathway order) |
| `event_date` | date32 | calendar date |
| `date_precision` | dictionary | `DAY`, `MONTH` |
| `county` | dictionary | `HVA01`..`HVA21`, `HVA90`, `HVA91` (residence) |
| `entry_route` | dictionary | `PUBLIC_PRIMARY`, `OCCUPATIONAL`, `PRIVATE`, `EMERGENCY`, `SCREENING` |
| `cancer_site` | dictionary | `lung`, `colorectal`, `breast`, `prostate`, `haematological`, `other` |
| `age_band` | dictionary | five-year bands |
| `source` | dictionary | `STRUCTURED_FIELD`, `TEXT_EXTRACTED`, `PATIENT_REPORTED` |
| `extraction_confidence` | float32 | null unless `TEXT_EXTRACTED` |
| `verified_by_human` | bool | |
| `synthetic` | bool | true for every simulated row |

**One pathway order.** The simulator builds every episode so that each event is on or after the one
before it. Dates are whole days and ties are allowed:

```
SYMPTOM_ONSET_REPORTED <= FIRST_CONTACT <= PHYSICIAN_ASSESSMENT <= REFERRAL_SENT
<= REFERRAL_RECEIVED <= DIAGNOSIS <= MDT_DECISION <= SPECIALIST_VISIT <= TREATMENT_START
```

`SPECIALIST_VISIT` is the first visit to the treating specialist, the milestone the published
cohort reports just before treatment. Diagnosis and the multidisciplinary decision come before it.
The simulator, the validator (`eventlog/validate.py`) and this document use this one order
(`eventlog/schema.py`); the validator counts every reversed pair and repairs nothing.

This order is the simulator's convention, chosen to match one cohort's milestones. It is not a
specification that every real pathway obeys. On real records a reversed pair is a flag for review,
not an error: `validate(..., order='flag')` counts each reversed pair by pair type, lists its
episode in `flagged_for_review` and leaves the file valid unless something else is wrong (schema,
enumerations, duplicates, impossible dates). The default `order='strict'` is for the simulator's own
output, where a reversed pair can only be a simulator bug. Cases to settle with clinicians before
the validator is used on real data: a first specialist visit before the diagnosis is confirmed; an
emergency presentation that is diagnosed before any referral exists; a screening case with no
symptom onset; treatment started before a multidisciplinary decision is recorded.

**Core four** (the minimum): `FIRST_CONTACT`, `REFERRAL_SENT`, `DIAGNOSIS`, `TREATMENT_START`, plus
`entry_route`. They define three intervals: primary care (`FIRST_CONTACT` to `REFERRAL_SENT`),
diagnostic (`REFERRAL_SENT` to `DIAGNOSIS`) and treatment (`DIAGNOSIS` to `TREATMENT_START`).

Derived table `pathway_intervals`: one row per episode, `days_<interval>` (whole days, zero is a
valid value), a censoring flag and `day_precision_<interval>` (both dates known to the day). Files are partitioned `year=YYYY/county=HVAxx/` with zstd
compression.

Why patient-level events and not county medians: medians are not additive across stages, cannot be
re-standardised for case mix, hide censoring (patients still waiting are exactly the ones that
matter) and cannot be pooled across periods. Event rows are the sufficient statistics of a
progressive multi-state model; every published indicator can be recomputed from them, and
aggregates can still be released with small-cell suppression (n < 5).

Why Parquet: typed columns with dictionary encoding for the enumerations, partition pruning by
county and year, and schema evolution without breaking readers. Whether the secure environments
used for Finnish secondary use of health data read Parquet directly was not checked. Volume is
small: up to nine events for each new cancer case. The simulated sample of section 3 is 20,000
episodes and 177,958 rows; the national row count scales with the number of new cases a year, for
which this note uses an assumption (section 2), not an observed figure.

## 2. How many records make it useful

Step durations are right-skewed; model `log T` as normal with standard deviation `s`.

**Detecting that a county is slower by a ratio `r` in one interval.** Estimator: difference of mean
log-duration, county vs country. `Var = s^2 (1/n + 1/N) ~ s^2 / n`. Required complete episodes:

```
n >= s^2 (z_{1-a/2} + z_{power})^2 / (ln r)^2
```

With 23 counties x 3 intervals = 69 comparisons, Bonferroni `a = 0.05/69` gives `z = 3.38`; power
0.8 gives `z = 0.84`. That family is one look at one stratum; repeated looks and site strata are
treated below.

<!-- STUDY:SIZES:BEGIN -->
**Which `s`, and where each value comes from.** Computed from the cohort: in the Finnish DLBCL cohort (Kuitunen 2026, doi:10.1002/cam4.71920) the mean and median from symptom onset to treatment are 207 and 127 days on the public route and 123 and 76 days on the private or occupational route. A single log-normal with that mean and median has `s = sqrt(2 ln(mean/median))`: 0.988 and 0.981. Computed from the simulator: the per-interval values of the next paragraph, which the per-interval columns use. Neither: the simulator's own step value `s = 0.96` is an input chosen near the cohort figures; neither route reproduces it, so it is a modelling choice, not a derived number. The `s = 0.96` column is kept only to show what that input alone would give.

`s = 0.96` describes one log-normal step in one population. None of the three intervals is that: each mixes the entry routes, primary care is a sum of two steps, and treatment is part of one step plus all of another. Mixing routes widens the log-duration, summing steps narrows it. So `s` is measured for each interval in 50,000,000 simulated episodes (section 3; whole-day dates; a zero-day interval is logged as 0.5 day before taking logs, which touches 0.001%, 0.029% and 0.001% of the primary-care, diagnostic and treatment intervals; positive intervals are unchanged). Result: primary care 0.938, diagnostic 0.977, treatment 0.803. Wider than the single-step value: diagnostic; narrower: primary care, treatment.

Complete episodes per county and period (both dates of the interval known to the day), for one look, against a reference so large that its own error can be ignored:

| county slower by | simulator step input (s = 0.96) | primary care (s = 0.938) | diagnostic (s = 0.977) | treatment (s = 0.803) | one step, cohort spread (s = 0.988) |
| --- | --- | --- | --- | --- | --- |
| 10% | 1,809 | 1,728 | 1,874 | 1,267 | 1,917 |
| 20% | 495 | 473 | 513 | 347 | 524 |
| 30% | 239 | 228 | 248 | 168 | 253 |
| 50% | 100 | 96 | 104 | 70 | 106 |

The per-interval columns are SYNTHETIC: they follow from the simulator's assumptions (45% of episodes on the fast route, the published step means, log-SD 0.96 per step, the diagnosis placed at 0.6 of the referral-to-specialist step, the multidisciplinary decision placed uniformly after it) and must be re-measured once real event data exist.

**The simulator is less spread than the cohort.** It reproduces the published mean but not the published median. On the public route, 2,000,000 simulated episodes give a mean of 207.1 days and a median of 174.0 days from symptom onset to treatment (log-SD 0.548), against 207 and 127 in the cohort (log-SD 0.99); on the private or occupational route 2,000,000 simulated episodes give 123.1 and 102.0 days (log-SD 0.577) against 123 and 76. Five independent steps add up to a total that is less skewed than the real one. Real intervals may therefore be more spread than the simulated ones, and every `n` grows with `s^2`. The last column of the table shows the size of that effect for one step.

**Against the rest of the country, not an infinite reference.** The detector compares a county with the other episodes of the same period, so `n(N - n)/N` takes the place of `n`, with `N` the national count of the period. With 37,000 new cases a year (an assumption for sizing, not an observed incidence):

| county slower by | period | primary care | diagnostic | treatment |
| --- | --- | --- | --- | --- |
| 10% | one year (N = 37,000) | 1,817 | 1,980 | 1,314 |
| 20% | one year (N = 37,000) | 479 | 520 | 350 |
| 30% | one year (N = 37,000) | 230 | 249 | 168 |
| 50% | one year (N = 37,000) | 96 | 104 | 71 |
| 10% | one quarter (N = 9,250) | 2,299 | 2,611 | 1,515 |
| 20% | one quarter (N = 9,250) | 499 | 545 | 361 |
| 30% | one quarter (N = 9,250) | 234 | 255 | 171 |
| 50% | one quarter (N = 9,250) | 97 | 105 | 71 |

"Not reachable" means no county size gives the power, because the rest of the country is then too small a comparator.
<!-- STUDY:SIZES:END -->

With a share `m` of episodes missing a timestamp, divide by `(1 - m)`. If instead each date is
missing independently with probability `m`, an interval needs both of its dates: divide by
`(1 - m)^2`.

<!-- STUDY:CHECKS:BEGIN -->
**How well the formula holds.** Simulated at exactly the per-interval `n` of the first table, 200,000 counties per cell, 12 cells, target power 0.80:

- With the measured `s` treated as known, as the formula assumes, power is 0.8001 to 0.8058. The largest gap to the formula is 0.0032 (diagnostic, 50% slowdown, n = 104); 1 of 12 cells is more than three Monte Carlo standard errors away.
- The detector as actually run estimates the variance inside the county and uses Student t critical values. Its power is 0.7570 to 0.8008. The largest gap is 0.0431 (treatment, 50% slowdown, n = 70), and 8 of 12 cells are more than three Monte Carlo standard errors away. The formula uses a normal quantile, so it is a little optimistic for small `n`.
- With the rest of the country as comparator, fully simulated (2,000 countries per cell): at the `n` of the first table the power is 0.759 to 0.783 for a 20% slowdown against one quarter and 0.761 to 0.783 for a 10% slowdown against one year; at the `n` of the second table it is 0.789 to 0.803 and 0.792 to 0.814.
- Across the wider design grid (n from 100 to 2,000, 1,000 simulated counties per cell) the largest gap with day-precision dates is 0.0557 with no missing dates and 0.0846 with 20% of dates missing; of the cells with formula power between 0.02 and 0.98, 1 of 30 and 5 of 33 are more than three Monte Carlo standard errors away.

**Month-precision dates cost episodes.** A date known only to the month is an interval, not a point. The earlier version of the detector put it at mid-month and tested anyway; its power then fell far below the formula (largest gap 0.5418 in that version's run, `runs/eventlog.jsonl`). The detector now tests an interval only when both of its dates are known to the day. With a share `q` of dates known to the month only, `(1 - q)^2` of the intervals remain: divide `n` by `(1 - q)^2`. With half of the dates at month precision a quarter of the intervals remain, so four times as many episodes are needed. With that correction in the formula the largest gap in the month-precision cells is 0.1577 with no missing dates and 0.0882 with 20% missing (largest over all conditions: 0.1577; treatment, n = 100, 50% slowdown, 0.038 of simulations against 0.196 from the formula). A county needs at least 30 testable episodes in an interval to be tested at all; 24 of the 240 core-four cells of the grid expect fewer and are not tested. An interval-censored analysis could use month-precision dates; this study does not do one. That remains the strongest argument for recording `date_precision = DAY`.

**False alarms when nothing is wrong.** One county against a large reference, 200,000 simulated counties per size and precision, any of its three tests rejecting (nominal at most 0.00217). With half of the dates at month precision only the day-precision pairs are tested, so small counties are often not tested at all:

| county n | day precision, t quantiles (as run) | day precision, normal quantile (first implementation) | half month precision, all counties | half month precision, among counties with a test (share with a test) |
| --- | --- | --- | --- | --- |
| 30 | 0.00191 | 0.00549 | 0.00000 | no county tested (0.000) |
| 50 | 0.00197 | 0.00393 | 0.00000 | no county tested (0.000) |
| 100 | 0.00189 | 0.00279 | 0.00036 | 0.00101 (0.350) |
| 250 | 0.00188 | 0.00218 | 0.00203 | 0.00203 (1.000) |
| 1,000 | 0.00168 | 0.00172 | 0.00218 | 0.00218 (1.000) |

With t quantiles the largest single-county rate at day precision is 0.00197 (n = 50; 95% interval 0.00178 to 0.00217), consistent with the nominal bound. With half of the dates at month precision the largest rate among counties that are tested is 0.00218 (n = 1,000; 95% interval 0.00199 to 0.00240), consistent with the nominal bound. Counties of 30, 50, 100 episodes are tested in fewer than half of the runs: month precision makes small counties silent rather than noisy.

All 23 counties tested at once against the rest of the country, share of 1,000 simulated countries with at least one false flag (target 0.05; 95% interval in brackets), for the core four (D3, 69 tests) and for two timestamps (D2, 23 tests), with day-precision dates and with half of the dates at month precision:

| county layout | D3, day precision | D3, half month precision | D2, day precision | D2, half month precision |
| --- | --- | --- | --- | --- |
| 23 counties x 250 | 0.042 (0.031 to 0.056) | 0.040 (0.030 to 0.054) | 0.044 (0.033 to 0.059) | 0.066 (0.052 to 0.083) |
| population-proportional, 9250 episodes (one quarter) | 0.027 (0.019 to 0.039) | 0.058 (0.045 to 0.074) | 0.044 (0.033 to 0.059) | 0.043 (0.032 to 0.057) |
| population-proportional, 37000 episodes (one year) | 0.034 (0.024 to 0.047) | 0.053 (0.041 to 0.069) | 0.049 (0.037 to 0.064) | 0.041 (0.030 to 0.055) |

1 of the 12 cells has a 95% interval entirely above the 5% target: 0.066 (0.052 to 0.083; D2, 23 counties x 250, half of the dates at month precision). With 12 intervals at 95% one such result can arise by chance, so this is a warning that the family-wise rate may not be controlled there, not a proof; more replications were not run. Every D3 cell's interval includes or lies below 5%.
<!-- STUDY:CHECKS:END -->

<!-- STUDY:LOOKS:BEGIN -->
**Repeated looks and strata are part of the family.** `a = 0.05/69` covers one look at one stratum: 23 counties x 3 intervals, once. It does not cover a quarterly report repeated over time, and it does not cover separate analyses by cancer site. Simulated with no slowdown anywhere, quarterly looks on a rolling four-quarter window (1,000 countries):

| county layout | threshold | false flag somewhere at the first look | within 4 looks | within 8 looks | within 12 looks |
| --- | --- | --- | --- | --- | --- |
| 23 counties x 250 per quarter | one look, a = 0.05/69 | 0.038 | 0.127 | 0.246 | 0.340 |
| 23 counties x 250 per quarter | 12 looks counted, a = 0.05/(69 x 12) | 0.002 | 0.014 | 0.025 | 0.033 |
| population-proportional, 9250 per quarter | one look, a = 0.05/69 | 0.050 | 0.138 | 0.239 | 0.335 |
| population-proportional, 9250 per quarter | 12 looks counted, a = 0.05/(69 x 12) | 0.008 | 0.017 | 0.030 | 0.043 |

Counting the planned looks in the family (Bonferroni over looks, an upper bound because rolling windows overlap) keeps the false-alarm probability over the horizon near 5%. It costs sample size: for a 20% slowdown the per-interval `n` rises from 473, 513, 347 to 624, 677, 458 (primary care, diagnostic, treatment) with 12 looks. The early-warning experiment of section 3 uses that threshold. A sequential boundary calibrated by simulation would cost less; it is not implemented. Each cancer-site stratum analysed separately multiplies the family again.
<!-- STUDY:LOOKS:END -->

**Share treated within a target time** (the Goal 3 indicator), national share `p0`, county `p1`:
`n >= (z_{1-a/2} sqrt(p0(1-p0)) + z_{power} sqrt(p1(1-p1)))^2 / (p0 - p1)^2`.
For 70% nationally vs 60% in a county: 385 episodes.

<!-- STUDY:COUNTIES:BEGIN -->
**Consequence, county by county.** The table takes 37,000 new cases a year (an assumption, not an observed incidence), shares them by 2025 population, and gives the smallest slowdown each county could detect in every interval with power 0.8 at one look (`a = 0.05/69`, rest of the country as comparator, every date known to the day, no missing dates). SYNTHETIC planning figures.

| county | assumed cases a year | smallest slowdown detectable in one quarter | in one year |
| --- | --- | --- | --- |
| City of Helsinki | 4,545 | 14% | 7% |
| Pirkanmaa | 3,593 | 16% | 8% |
| West Uusimaa | 3,314 | 16% | 8% |
| Southwest Finland | 3,258 | 16% | 8% |
| North Ostrobothnia | 2,736 | 18% | 9% |
| Vantaa and Kerava | 1,909 | 21% | 10% |
| Central Finland | 1,792 | 22% | 11% |
| North Savo | 1,627 | 23% | 11% |
| Satakunta | 1,375 | 25% | 12% |
| Central Uusimaa | 1,358 | 26% | 12% |
| Päijät-Häme | 1,339 | 26% | 12% |
| South Ostrobothnia | 1,240 | 27% | 13% |
| Ostrobothnia | 1,175 | 28% | 13% |
| Lapland | 1,153 | 28% | 13% |
| Kanta-Häme | 1,106 | 29% | 13% |
| North Karelia | 1,057 | 29% | 14% |
| Kymenlaakso | 1,022 | 30% | 14% |
| South Savo | 839 | 33% | 15% |
| South Karelia | 813 | 34% | 16% |
| East Uusimaa | 652 | 39% | 18% |
| Kainuu | 453 | 48% | 22% |
| Central Ostrobothnia | 442 | 48% | 22% |
| Åland | 202 | 79% | 34% |

So under these assumptions 5 of 23 counties could detect a 20% slowdown within one quarter, 20 within one year, and 5 could detect 10% within one year. The smallest county has about 50 cases a quarter. Quarterly all-cancer reporting is informative for slowdowns of roughly 14% or more in the largest county and 79% or more in the smallest; a rolling twelve months brings those to 7% and 34%. Missing or month-precision dates, repeated looks and site strata all push these figures up. Real case counts by county are not in this repository, so these rows describe the assumption, not the counties.
<!-- STUDY:COUNTIES:END -->

Site-specific figures divide every county's count further, so they need partial pooling across
periods and counties, which is the empirical Bayes machinery SAMA already uses for mortality. A
design that collects only referral and treatment dates cannot tell a primary-care problem from a
diagnostic one; that is tested in the design study (`eventlog/`).

## 3. Design study by simulation

`eventlog/` simulates episodes from five route-specific log-normal steps calibrated to the
published means (private or occupational: 42, 1, 34, 41, 5 days per step; public: 72, 22, 53, 57,
3; log-SD 0.96 per step; 45% of episodes on the fast route, which is an assumption). The steps run
from symptom onset to first contact, physician assessment, referral sent, first visit to the
treating specialist and treatment start. The remaining events are placed so that the order of
section 1 always holds:

- `REFERRAL_RECEIVED` = `REFERRAL_SENT` + min(0 to 3 days, time to `DIAGNOSIS`),
- `DIAGNOSIS` = `REFERRAL_SENT` + 0.6 x (referral-to-specialist step),
- `MDT_DECISION` uniformly between `DIAGNOSIS` and `SPECIALIST_VISIT`,
- `TREATMENT_START` = `SPECIALIST_VISIT` + last step.

The diagnostic interval is therefore 0.6 of the referral-to-specialist step, and the treatment
interval is the other 0.4 of it plus the last step. The 0.6 split and the uniform placement of the
multidisciplinary decision have no source; they are modelling constants, and the diagnostic and
treatment columns of section 2 depend on the first. Dates are rounded to whole days. The first
implementation used timing rules that contradicted each other and produced 19,075 order violations
in 20,000 episodes; with the single order the validated sample (20,000 episodes, 177,958 events)
has 0, and so do the 50,000,000 calibration episodes.

The study plants a known slowdown in one interval of one county (every gap inside that interval is
multiplied by the ratio, later events shift) and asks each collection design whether the analysis
finds the right county and the right interval:

- D1 today's public indicators (no patient timestamps),
- D2 two timestamps (referral received, treatment start),
- D3 the core four,
- D4 all nine events.

Outcomes: probability of locating the planted interval, and quarters until an emerging slowdown is
flagged, as functions of county size, effect size, missingness and date precision. The test is a
Welch test of mean log-duration with Student t critical values; it uses only intervals whose two
dates are known to the day, and the early-warning experiment counts its twelve quarterly looks in
the multiple-comparison family. The sample sizes of section 2 are checked against simulated power;
the agreement and the gap that remains are reported in section 2 and, cell by cell, in
`eventlog/RESULTS.md` and `data/eventlog/design-study-v1.json`. Text extraction is simulated twice:
with assumed error rates (up to 10% of event types wrong and up to 10% of dates shifted by 1 to
30 days) and with the error the pathway scribe was measured to make (section 4). All of it is
SYNTHETIC and none of it is for clinical use.

## 4. Filling the log without new forms: a Gemma "pathway scribe"

The premise, not tested here, is that many of the dates are already written in referral letters
and visit notes and that clinicians will not fill nine extra fields. The idea: a small open-weight
model that runs inside the hospital network proposes the events, and a person confirms each of
them (`source = TEXT_EXTRACTED`, `verified_by_human`). Everything below was measured on SYNTHETIC
Finnish notes written and labelled by language models; none of it shows that the idea works on
real clinical text.

**What was run (14 November 2026).**

| step | result | source |
| --- | --- | --- |
| Version 1 | The planned LoRA run on `unsloth/gemma-3-4b-it` did not happen: the GPU box stopped answering before training. A reduced fallback ran on a laptop with `mlx-community/gemma-3-1b-it-bf16` (1200 training notes seen once, 726 s). Note-level exact match 41.0% (34.4–47.9; n=200), 37.4% (33.3–41.7; n=500) on all test notes; 0.0% (0.0–3.4; n=110) on notes that contain a relative date, 91.1% (83.4–95.4; n=90) on notes with absolute dates only. | `scribe/RESULTS.md` |
| Version 2 | Ablation on an A100 within a 35-minute budget (34.6 min used); the 1B and 4B arms did not fit. Selected: Gemma 3 270M, LoRA r16 (`A-270m-lora-r16`). Test note-level exact match 42.0% (37.8-46.4) on 500 Nemotron-written notes and 13.0% (9.0-18.4) on 200 Haiku-written notes; event F1 0.675 and 0.413. | `scribe/v2/RESULTS.md`, `data/scribe/v2/ablation-v1.json` |
| Confidence threshold (version 2) | At a target of 1% error no threshold could be certified on the 310 calibration notes. The 5% threshold admitted 191 Nemotron-written test notes with 1 wrong (0.5%) but 13 Haiku-written notes with 2 wrong (15.4%). | `scribe/v2/RESULTS.md` |
| Serving | vLLM served the selected adapter on `unsloth/gemma-3-270m-it` with structured outputs (`serve/smoke/vllm.log`). On 100 held-out notes (50 Nemotron-written, 50 Haiku-written) all 100 outputs were valid; exact match 0.22 (95% interval 0.150 to 0.311), route accuracy 0.91, event F1 0.583, p95 latency 1.80 s. All 100 notes went to human review because no confidence threshold is calibrated. | `serve/smoke/smoke-guided.json` |
| Teaching round 2 | The teacher (Nemotron 3.5 Super VL) wrote 1,600 notes; 1,589 passed the code check and 1,465 of those were read back by a blind second call of the same model exactly as specified (0.922). On notes that should contain no event only 170 of 238 were read back as specified. | `data/scribe/v3/teacher/stats.json` |
| Judges | The gate accepted 1,506 of the 1,589 checked notes (Jev rule). On the report half of a benchmark with planted corruptions (80 corrupted, 80 clean pairs) the Jev rule with the second question set caught 66 of 80 corruptions and rejected none of the 80 clean pairs; with the first question set 60 of 80 and 1 of 80; the Decisions judge 58 of 80 and 11 of 80. The second question set was designed after the first set's results on both halves had been seen (`data/scribe/v3/judges/policy.json`), so its report-half figure is not a clean held-out estimate. The gate's thresholds were not calibrated for notes with no event, terse notes or long notes. | `data/scribe/v3/judges/benchmark-v1.json` (generated 2026-11-14T19:10:35Z), `data/scribe/v3/gate/gate-v1.json` |
| Student trained on round-2 notes | Pre-registered (`data/scribe/v3/student/preregistration.json`); no test result in the repository: not yet measured. | |

**Extraction accuracy now.** The best measured note-level exact match on held-out SYNTHETIC notes is
42.0% on notes written by the teacher model and 13.0% on notes written by a different model: most
notes have at least one wrong, missing or extra event. No confidence threshold could be certified at
1% error, and the 5% threshold gave an observed error of 15.4% (2 of 13) on the other writer's notes.

<!-- STUDY:EXTRACTION:BEGIN -->
**What the measured error does to the county indicator (design study, SYNTHETIC).** `eventlog/design_study.measured_extraction_study` replaces the assumed error rates of section 3 by the measured per-event error of the scribe. For every true event of a test note it takes the predicted event of the same type, if any, and the signed date error in days. Each simulated date then gets an error drawn independently from that list, and each event is lost with the measured share that was not found:

| model and test notes | true events | found with the right type | exact date among those | wrong-date share | not found | largest error, days | extra predicted events | check |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selected version-2 adapter, Gemma 3 270M LoRA r16, 500 Nemotron-written test notes | 1,251 | 1,232 | 842 | 0.317 | 0.015 | 365 | 10 (not modelled) | recomputed event recall 842/1251 equals the stored 0.6731 |
| selected version-2 adapter, Gemma 3 270M LoRA r16, 200 Haiku-written test notes | 407 | 295 | 179 | 0.393 | 0.275 | 281 | 154 (not modelled) | recomputed event recall 179/407 equals the stored 0.4398 |
| version-1 adapter, Gemma 3 1B LoRA (MLX), 200 Nemotron-written test notes | 479 | 440 | 295 | 0.330 | 0.081 | 277 | not counted | date errors as stored by the scribe evaluator |

A 30% slowdown planted in one interval of one county, 1,000 runs per cell. Located: share of runs in which the planted interval is the one flagged; bias: error of the county's median interval:

| county episodes | dates | located: primary care / diagnostic / treatment | median bias, days | testable episodes, mean |
| --- | --- | --- | --- | --- |
| 500 | every event confirmed by a person | 0.997 / 0.998 / 0.999 | +0.0 / +0.0 / +0.0 | 500 / 500 / 500 |
| 500 | Gemma 3 270M LoRA r16, 500 Nemotron-written test notes | 0.777 / 0.486 / 0.597 | +16.7 / +13.4 / +10.3 | 383 / 385 / 386 |
| 500 | Gemma 3 270M LoRA r16, 200 Haiku-written test notes | 0.269 / 0.090 / 0.103 | +24.3 / +20.5 / +16.1 | 193 / 194 / 194 |
| 500 | Gemma 3 1B LoRA (MLX), 200 Nemotron-written test notes | 0.642 / 0.439 / 0.469 | +15.1 / +12.9 / +10.0 | 334 / 336 / 337 |
| 2,000 | every event confirmed by a person | 1.000 / 1.000 / 1.000 | +0.0 / +0.0 / +0.0 | 2000 / 2000 / 2000 |
| 2,000 | Gemma 3 270M LoRA r16, 500 Nemotron-written test notes | 1.000 / 1.000 / 1.000 | +16.9 / +13.3 / +10.1 | 1543 / 1546 / 1558 |
| 2,000 | Gemma 3 270M LoRA r16, 200 Haiku-written test notes | 0.950 / 0.830 / 0.818 | +24.0 / +20.1 / +16.0 | 783 / 787 / 790 |
| 2,000 | Gemma 3 1B LoRA (MLX), 200 Nemotron-written test notes | 1.000 / 0.998 / 0.999 | +15.2 / +12.8 / +9.9 | 1346 / 1349 / 1361 |

No slowdown anywhere: share of runs in which the county is flagged (nominal at most 0.00217). Every event confirmed: 0.001 (500 episodes), 0.001 (2,000 episodes).

| model and test notes | county episodes | county and country extracted | only the county extracted, the rest from structured fields |
| --- | --- | --- | --- |
| Gemma 3 270M LoRA r16, 500 Nemotron-written test notes | 500 | 0.003 | 1.000 |
| Gemma 3 270M LoRA r16, 500 Nemotron-written test notes | 2,000 | 0.004 | 1.000 |
| Gemma 3 270M LoRA r16, 200 Haiku-written test notes | 500 | 0.002 | 1.000 |
| Gemma 3 270M LoRA r16, 200 Haiku-written test notes | 2,000 | 0.002 | 1.000 |
| Gemma 3 1B LoRA (MLX), 200 Nemotron-written test notes | 500 | 0.000 | 1.000 |
| Gemma 3 1B LoRA (MLX), 200 Nemotron-written test notes | 2,000 | 0.001 | 1.000 |

Reading. With the selected version-2 adapter's error on Nemotron-written notes, a county of 500 episodes locates the planted interval in 0.486 to 0.777 of runs instead of 0.997 to 0.999, and a county of 2,000 in 1.000. Across the three error profiles the median interval is off by +9.9 to +24.3 days at both county sizes; more episodes do not remove a bias. A county whose dates come from text while the others come from structured fields is flagged in 1.000 of runs when nothing is wrong. So at the measured error, text extraction is not accurate enough to fill the county indicator without a person confirming every extracted date.

Limits: The measured errors come from synthetic notes written and labelled by language models, not from clinical text. Errors are drawn independently per date; real errors cluster within a note. Extra predicted events are not modelled. The confirmed condition assumes that a person removes every error; that was not measured.
<!-- STUDY:EXTRACTION:END -->

**How it was built.** Ground truth (events, dates, route) comes from `scribe/sample.py`, a sampler
separate from the simulator of section 3 that still lists the event types in an older order: 313 of
2466 accepted version-1 episodes break the order of section 1 (`scribe/RESULTS.md`). A teacher model
writes a Finnish note for each sampled tuple; code checks and a judge (TypeSafe Jev) keep the pair
only if the note appears to state exactly that tuple; a LoRA adapter on Gemma is trained on the
kept pairs and scored on held-out notes (note-level exact match, event F1, route accuracy, Wilson
intervals). Labels are exact for the sampled tuple, but whether a note states exactly that tuple is
estimated by models, not checked by people: a stricter second Jev pass disagreed with 43 of 60
accepted version-1 notes, while a second model reading 60 notes in full judged 2 labels wrong. The
test therefore measures agreement with the teacher-and-judge pipeline, not truth.

No real patient text is used anywhere. The adapters are research artefacts, not medical devices.
Gemma and anything derived from it, including the adapters, are subject to the Gemma Terms of Use
and the Gemma Prohibited Use Policy, which restricts automated decisions in healthcare. Every
extraction therefore stays a proposal until a person confirms it, and a threshold for skipping
confirmation would first have to be validated on real, human-labelled notes.
