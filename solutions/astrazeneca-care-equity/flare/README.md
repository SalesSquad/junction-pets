# Federated county statistics with NVIDIA FLARE (SYNTHETIC data)

Lane C, step 9 of `NVIDIA_OPTIONS.md`. All data here is SYNTHETIC (`data/eventlog/`, seed 20261114).
Nothing in this folder has touched real patient data. Result and numbers: `data/flare/RESULT.md`.

## What runs

- NVIDIA FLARE 2.9.1, simulator mode (`nvflare.recipe.SimEnv`), on one Mac. Python 3.12 venv at
  `flare/.venv` (`nvflare==2.9.1`, pandas, pyarrow, scipy). No container, no GPU, no cloud.
- 23 FLARE client sites, one per county code in `eventlog.schema.COUNTIES` (HVA01-HVA21, HVA90, HVA91).
- Each site (`flare/county_stats.py`, `CountyEventLogStatistics`) reads only its own Hive partition
  `data/eventlog/sample/year=*/county=<site>/` and its own roster rows, then derives intervals with the
  central pipeline's own `eventlog.intervals.derive`. The feature is the log duration exactly as
  `eventlog.aggregate.summarize` defines it: complete cases, `log(days)`, zero days logged as 0.5 day.
- The server runs FLARE's `StatisticsController` (count, sum, mean, stddev, histogram). Only aggregates
  leave a site, after FLARE's privacy result filters: `MinCountCleanser(min_count=5)` (SAMA's n < 5 rule),
  `AddNoiseToMinMax(0.1, 0.3)` and `HistogramBinsCleanser(max_bins_percent=10)`.
- Histogram: 9 uniform bins in log space, width log(3), with one edge at log(T + 0.5) for each interval's
  placeholder threshold T (primary care 90, diagnostic 60, treatment 30, total 180 days; the same
  assumptions as `eventlog.aggregate`). Durations are whole days, so the bins below that edge count
  exactly the intervals of at most T days: the share within target. The range is fixed in advance
  (0.5 day to 3,650 days), so no site has to reveal its own maximum.
- `precision=12`. FLARE's `StatsJob` rounds every statistic to 4 decimals by default (controller and
  executor `precision=4`); `PreciseStatsJob` in `run_fedstats.py` only exposes that parameter.

## Reproduce

```bash
flare/run_all.sh      # about 4 minutes; writes data/flare/*
```

or one run at a time:

```bash
flare/.venv/bin/python flare/run_fedstats.py --strata none --precision 12
flare/.venv/bin/python flare/compare.py      --strata none --precision 12
```

`--strata age_band` splits every county cell by age band (1,932 cells), so that cells with n < 5 exist
and MinCountCleanser has something to suppress. The committed central table has no such cells.

## Limits

- Simulation only: 23 sites as local processes reading one folder. No network between real
  organisations, no provisioning, no TLS certificates, no site-side approval of the job.
- Medians and their confidence intervals are not federated. FLARE's quantiles are T-digest
  approximations; `fastdigest` was not installed and quantiles were not tested.
- The national ("Global") row is exact only when no county is suppressed. See RESULT.md.
- Any legal route (Findata, the Secondary Use Act) is one possible route, to be confirmed with THL
  and Findata. Nothing here was checked with either.

## Comparability gate (added 14 November 2026, 23:05 UTC, SYNTHETIC data)

`BIG_PICTURE.md` DO #3 stretch. Result: `data/flare/gate-v1.json`; panel: `web/flare.mjs` (`flareGateHtml`).

- **Clock.** Referral to treatment, `REFERRAL_SENT` (the referral is sent) to `TREATMENT_START`, with a
  histogram edge at 42.5 days, so the bins below it count the pathways of at most 42 days. 42 days is a
  placeholder (OECD/EU-reported target); Finnish law allows up to six months and names no cancer-specific limit.
- **Completeness.** Share of started clocks with both dates, and share still open at the data cut.
- **Scribe error profile per county.** Stored predictions of `C-270m-all-v2data` on 700 SYNTHETIC test notes,
  raw and after the code resolver (`runs/diagnose/resolve_relative.py`), assigned to counties by sorted-id rank
  mod 23 (`flare/gate_prep.py`). No model is run.
- **Rule** (`flare/gate.py`, placeholder thresholds): a cell is "not comparable" when the median bias (median
  measured interval length minus median true length) is above 3 days either way, or the missed-event share is
  above 10%. The clock value stays visible.
- **Where it ran.** Clock, completeness, missed share, mean and SD of signed errors: NVIDIA FLARE 2.9.1 simulator,
  23 sites, one thread. Median bias: plain Python on the same site partitions, "FLARE-ready, not run in FLARE"
  (medians are not among the statistics run; FLARE's quantile is an approximate T-digest, package not installed).

```bash
flare/run_gate_all.sh   # prep, FLARE run, build, tests
```
