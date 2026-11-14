# SAMA synthetic event log

Everything here is SYNTHETIC: simulated episodes under stated assumptions, not Finnish patients.
Nothing is for clinical use.

Run from the solution root with Python 3.12:

```sh
UV_CACHE_DIR=/private/tmp/sama-uv-cache uv venv --python 3.12 eventlog/.venv
UV_CACHE_DIR=/private/tmp/sama-uv-cache uv pip install --python eventlog/.venv/bin/python numpy==2.5.4 pyarrow==26.0.1
eventlog/.venv/bin/python -m eventlog.run_all
eventlog/.venv/bin/python -m unittest discover -s eventlog/tests -v > data/eventlog/tests-output.txt 2>&1
eventlog/.venv/bin/python -m eventlog.audit
```

`run_all` took about thirteen minutes on a busy 18-core laptop in the run of 14 November 2026
(`runs/eventlog.jsonl` has the elapsed time of each stage); the tests take about half a minute.
`run_all` writes `RESULTS.md` and the generated blocks of `DATA_COLLECTION.md` (between
`<!-- STUDY:... -->` markers). `audit` re-reads the files on disk, checks that those blocks are
current and that the tests passed, and writes the execution receipt.

NumPy, PyArrow, SciPy (for Student t quantiles) and the Python standard library are used at runtime. The simulator defaults to
37,000 new cases a year (`design_study.NATIONAL_CASES`), an assumption for sizing stated in
DATA_COLLECTION.md section 2, not an observed incidence; the CLI explicitly requests a smaller
sample. Run receipts go to `runs/eventlog.jsonl`, or to the file named by `EVENTLOG_RUNLOG`
(relative to the solution root; the review-fix run of 14 November used `runs/eventlog-fix.jsonl`). County allocations use the latest population year in the supplied snapshot, with
largest-remainder rounding. Study constants are model assumptions, not estimates about Finnish
patients.

## One pathway order

`schema.EVENT_TYPES` is the single order used by the simulator, the validator and
DATA_COLLECTION.md section 1:

```
SYMPTOM_ONSET_REPORTED <= FIRST_CONTACT <= PHYSICIAN_ASSESSMENT <= REFERRAL_SENT
<= REFERRAL_RECEIVED <= DIAGNOSIS <= MDT_DECISION <= SPECIALIST_VISIT <= TREATMENT_START
```

`SPECIALIST_VISIT` is the first visit to the treating specialist (the published cohort's milestone
just before treatment). Five route-specific log-normal steps run from symptom onset to first
contact, physician assessment, referral sent, that specialist visit and treatment start. The other
events are placed inside them: `REFERRAL_RECEIVED = REFERRAL_SENT + min(U(0,3) days, time to
DIAGNOSIS)`, `DIAGNOSIS = REFERRAL_SENT + 0.6 x (referral-to-specialist step)`, `MDT_DECISION`
uniform between `DIAGNOSIS` and `SPECIALIST_VISIT`, `TREATMENT_START = SPECIALIST_VISIT + last
step`.

`simulate.latent` builds every episode as a cumulative sum of non-negative gaps, so the order holds
by construction and survives rounding to whole days (ties are allowed). A slowdown multiplies the
gaps of one core interval and shifts later events (`simulate.plant`). The first implementation
followed timing rules that contradicted each other and its sample had 19,075 reversed pairs; the
rules above replace them. The validator still repairs nothing: it counts reversed pairs and names
the pair. The order is the simulator's convention, not a specification of real pathways, so the
validator has two modes: `order='strict'` (default, for simulator output) marks the file invalid on
any reversed pair, because there it can only be a simulator bug; `order='flag'` (for real records)
lists each episode with a reversed pair in `flagged_for_review` and keeps the file valid unless
something else is wrong.

Observation error can still break the order in the design study (month-precision dates taken at
mid-month, extraction errors). Those spans are negative and are excluded, never repaired.

## Intervals, logs and zero days

Primary care is `FIRST_CONTACT` to `REFERRAL_SENT`, diagnostic `REFERRAL_SENT` to `DIAGNOSIS`,
treatment `DIAGNOSIS` to `TREATMENT_START`; total is `FIRST_CONTACT` to `TREATMENT_START`. The
diagnostic interval is 0.6 of the referral-to-specialist step and the treatment interval the other
0.4 plus the last step, so the two are correlated but not identical.

Dates are whole days, so an interval can be zero days. One convention is used by the detector, the
measured standard deviations and the sample-size table: a zero-day interval is logged as 0.5 day,
positive intervals are logged unchanged, negative spans are excluded.

## Sample size per interval

`power.sample_size(r, sigma)` is the formula of DATA_COLLECTION.md section 2. With `sigma = 0.96`
(the simulator's step input, a modelling choice: `design_study.published_cohort` computes 0.988 and
0.981 from the cohort's public and private/occupational mean and median, and neither is 0.96) it
gives the "simulator step input" column. `design_study.calibrate` measures the standard deviation of
log-duration of each interval in a large simulated sample and the same formula then gives the
per-interval columns. `design_study.sample_size_check` simulates the power at exactly those n in
two ways: with the measured SD treated as known (the formula's own setting) and with the detector
as run (variance estimated in the county). Both gaps are reported in `RESULTS.md`; they are small
but, at 200,000 replications, not all within Monte Carlo error. The per-interval values depend on
the assumed route shares and step distributions.

## What changed after review (14 November 2026)

- **Test.** The detector is a Welch test with Student t critical values (`detect.test_moments`).
  The normal quantile used before let small counties raise false flags at up to two and a half
  times the nominal rate; `design_study.small_county_null` measures both.
- **Month-precision dates** are no longer tested at their mid-month value. An interval is tested
  only when both dates are known to the day (`day_precision_<interval>` in the derived table), and
  a county needs 30 such episodes to be tested. The formula counts those pairs out of `n`.
- **Repeated looks.** `design_study.repeated_looks_null` measures how often some county is flagged
  within twelve quarterly looks when nothing is wrong; the early-warning experiment now counts its
  twelve looks in the Bonferroni family.
- **Comparator.** `power.sample_size(..., national=N)` sizes against the rest of the country, and
  `design_study.rest_of_country_check` simulates it in full.
- **Family-wise null** is measured for three county layouts and two date precisions.
- **Cohort check.** `calibrate` compares the simulated public-route total with the published mean
  and median; the simulator matches the mean only.
- **County table.** `design_study.county_detectability` gives, per county, the smallest slowdown
  detectable in a quarter and in a year under the assumed national case count. Real county case
  counts are not in this repository; the table describes the assumption.

## What changed after the second review (14 November 2026)

- **Month precision, single county.** `design_study.small_county_month_null` measures the
  single-county false-positive rate with half of the dates at month precision, next to the
  day-precision rates, and reports how often small counties are not tested at all.
- **Family-wise null** rates are printed with their 95% intervals.
- **Where each `s` comes from.** The cohort-implied values are computed for both routes; the
  simulator's 0.96 is labelled as an input.
- **Validator modes** (`order='strict'` / `order='flag'`), see above.
- **Measured extraction error** fed back into the design study (`measured_extraction_study`), with
  its own random stream so that every earlier experiment keeps its draws.

## Current adapter and the code date resolver (14 November 2026, evening)

- `extraction_intervals.interval_extraction_study` (own random stream `[seed, 3]`) feeds the
  within-note interval errors of `C-270m-all-v2data` into the detector, as is and after the
  product's frozen relative-date resolver (`scribe/v3/resolve.py`, arm A). The pairs are recomputed
  from the stored predictions with the diagnosis code's matching and must equal
  `runs/diagnose/intervals-*.json`; the profile counts must equal `runs/diagnose/interval-impact-v1.json`.
- Extra predicted events are measured per writer and event type and modelled as a second event of
  the same type, which `intervals.derive` cannot pair (it needs exactly one start and one end
  event). An extra standing in for a missing true event is not modelled.
- Conditions: planted 30% (n = 500, 2,000), 20% at the section-2 n, and null runs with the county
  read from notes against a country read the same way, against structured fields, and with the
  county written like Haiku-written notes against a country written like Nemotron-written notes.
- `audit.interval_block` writes the result, including the "fake county inequality" headline, into
  the `STUDY:EXTRACTION` block of `DATA_COLLECTION.md`; every number comes from the study file.

## Other choices and limits

The specification does not enumerate derived-table columns or age-band limits; `schema.py`
documents those choices. Partition year is episode onset year, retained in the companion roster;
event calendar years can cross boundaries. Event enums remain dictionary encoded on read,
including the county partition key.

Administrative censoring is distinguished from randomly missing events using the synthetic episode
roster (including episodes with no observed events). Derived censored durations are lower bounds;
complete-case descriptive summaries exclude them. These are not survival-adjusted estimators. The
sample CLI uses DAY precision; the design study varies month precision. MONTH dates represent
ranges; they are stored at mid-month and flagged, intervals with a MONTH endpoint are left out of
the test, and the validator rejects only definitively reversed ranges.

A fixed independent synthetic country reference (4,000,000 episodes per observation condition) is
reused across Monte Carlo trials. Reported probabilities are conditional on that reference; its
variance enters the test's standard error and the reported Monte Carlo standard errors. The
family-wise and repeated-look null experiments and the rest-of-country check generate whole
countries and exclude the target county from its comparator. Missingness is independent per event: two required endpoints survive with squared
retention probability. Grid n is the latent complete cohort size before missingness, and effective
n is also reported.

D1 has no detector or timing estimates. D2 measures only referral-received to treatment and cannot
identify a core interval. D3 and D4 share the same prespecified core-interval detector and
multiplicity family; D4 observes the additional events but they provide no extra independent
core-interval information in this model. D1 structural grid cells have null outcomes, rather than
fabricated zeros.

Extraction error is applied to TEXT_EXTRACTED observations in both county and reference.
Wrong-type collisions cause endpoint abstention, and median bias is measured against each
replication's exact latent median. `extraction_study` uses assumed error rates;
`measured_extraction_study` uses the per-event date errors measured for the pathway scribe
(version-2 selected adapter on Nemotron- and Haiku-written test notes, recomputed from its stored
predictions and checked against its stored event recall; version-1 adapter from the scribe's own
evaluator), drawn independently per date, and adds a null run in which only the county's dates are
extracted.

Early warning uses rolling windows, counts its twelve planned looks in the multiple-comparison
family, and ignores pre-onset alarms for the post-onset delay, reporting those alarms separately. Undetected replications are right-censored at the end; an unconditional
median is null when fewer than half detect. Conditional medians are labelled separately.

Run receipts are append-only in `runs/eventlog.jsonl`; local execution incurs no metered model/API
cost. Generated outputs are in `data/eventlog/`, with no git operations or changes to other product
paths. No real-patient, provider, production, external-model or clinical validation is claimed.
