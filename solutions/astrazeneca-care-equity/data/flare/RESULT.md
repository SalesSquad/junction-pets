# FLARE federated county statistics: result

Lane C, step 9 of `NVIDIA_OPTIONS.md`. Run on Saturday 14 November 2026, 21:42-21:58 UTC.
**All data is SYNTHETIC** (`data/eventlog/`, seed 20261114). No real patient data was used.

**Status: success criterion met.** NVIDIA FLARE 2.9.1 federated statistics over 23 simulated county
sites reproduce SAMA's central county table: 92 of 92 county x interval cells have the same count, and
mean and SD of log duration within 1e-6 (largest difference 5.0e-13). Suppressed cells are identical.
In the committed table no cell is suppressed, so a second, finer run (county x age band, 1,932 cells)
tests suppression: 40 cells with n < 5 are suppressed centrally, and the same 40 are suppressed by
FLARE's MinCountCleanser.

Every number below comes from `data/flare/summary.json` and `data/flare/equivalence-*.json`, written
by `flare/compare.py` and `flare/summarize_result.py`. The step log is `runs/laneC-step9.jsonl`.

## What ran

- NVIDIA FLARE 2.9.1 in simulator mode on one Mac (Python 3.12, `flare/.venv`). The install took about
  7 seconds with `uv`. No container, GPU or cloud resource was used, and no money was spent.
- 23 FLARE client sites, one per county code (HVA01-HVA21, HVA90, HVA91). Each site reads only its own
  partition `data/eventlog/sample/year=2025/county=<site>/`, derives intervals with SAMA's own
  `eventlog.intervals.derive`, and logs durations as `eventlog.aggregate.summarize` does.
- Statistics: count, sum, mean, SD and a histogram of log duration. Only aggregates leave a site, after
  three FLARE privacy filters: `MinCountCleanser(min_count=5)` (SAMA's n < 5 rule),
  `AddNoiseToMinMax` and `HistogramBinsCleanser(10%)`.
- Histogram: 9 bins of width log(3), with one edge at log(T + 0.5 days) for each interval's
  placeholder threshold T. Durations are whole days, so the bins below that edge count exactly the
  intervals of at most T days.

## Equivalence against the central table

| Run | Cells | Count equal; mean and SD within 1e-6 | Suppressed (central / FLARE) | Largest difference, mean / SD of log days |
|---|---|---|---|---|
| County x interval, precision 12 | 92 | 92 / 92 | 0 / 0 | 5.0e-13 / 5.0e-13 |
| County x interval x age band, precision 12 | 1,932 | 1,932 / 1,932 | 40 / 40, identical cells | 5.0e-13 / 5.0e-13 |
| County x interval, FLARE default precision 4 | 92 | 0 / 92 | 0 / 0 | 5.0e-5 / 4.9e-5 |

- The national row of the county run also matches a pooled central calculation: 4 of 4 intervals
  within 1e-6 (the committed table has no national row, so `compare.py` computes it with `summarize`).
- Share within the placeholder threshold, read from FLARE's histogram, equals the central share
  exactly (difference 0.0) in all 92 county cells and in the national row:

| Interval | Placeholder threshold | National n | Share within, FLARE = central | County range |
|---|---|---|---|---|
| Primary care | 90 days | 19,792 | 0.837 | 0.800-0.859 |
| Diagnostic | 60 days | 19,718 | 0.891 | 0.866-0.931 |
| Treatment | 30 days | 19,581 | 0.780 | 0.751-0.832 |
| Total | 180 days | 19,581 | 0.870 | 0.854-0.884 |

The thresholds are assumptions in SAMA's code, not national targets (measure 3.1.4 of the roadmap
has not defined them yet).

## Three things we learned

1. **FLARE rounds to 4 decimals by default.** `StatsJob` passes no precision, so the controller and
   each client round every statistic to 4 digits. With the default, 0 of 92 cells pass the 1e-6 test
   (largest error 5.0e-5). `flare/run_fedstats.py` sets `precision=12` on the same two FLARE classes;
   nothing else changes.
2. **The national row is wrong when a county is suppressed.** MinCountCleanser keeps a suppressed
   county's count but removes its sum. FLARE's national mean then divides the other counties' sum by a
   count that still includes the suppressed county. In the age-band run this affected 40 of 84
   national rows, with an error of up to 0.0196 in mean log duration (about 2% in the geometric mean), worst in `total|10-14`.
   County rows are exact. A production version must compute the national row from unsuppressed
   county rows only.
3. **The histogram filter needs about 95 cases per cell for 9 bins.** HistogramBinsCleanser drops a
   histogram when the bin count is at least 10% of the cell size. In the age-band run it dropped 1,758
   of the 1,892 unsuppressed histograms. County-level cells (107 cases or more) all keep theirs.

## Limits

- Simulation only. The 23 sites are local processes reading partitions of one SYNTHETIC folder. There
  is no network between organisations, no provisioning, no certificates and no site-side approval.
- Medians and their confidence intervals are not federated. FLARE's quantiles are T-digest
  approximations; they were not installed or tested.
- The histogram range (0.5 to 3,650 days) is fixed in advance, so no site reveals its maximum. A value
  beyond it would drop out of the histogram; the check `histogram total = n` passed in every kept cell.
- Output files list sites in arrival order, so a rerun gives different bytes. A full rerun with
  `flare/run_all.sh` (4 min 22 s) reproduced every equivalence number above.

## Path to scale (design, not deployed)

Each county would run a FLARE client inside its own environment next to its event log, and only the
filtered aggregates above would leave it. A national server would combine them, with the national row
computed from unsuppressed county rows (finding 2). Who hosts the server, and under which permit, is
open. The Finnish Secondary Use Act and a Findata permit are one possible route, to be confirmed with
THL and Findata. Nothing here was checked with either.

## Reproduce

```bash
flare/run_all.sh          # from the solution folder; about 4-5 minutes on a Mac
```

Files: `flare/county_stats.py` (site), `flare/run_fedstats.py` (job and simulator),
`flare/compare.py` (equivalence diff), `flare/summarize_result.py`, `flare/README.md`.
Outputs: `data/flare/fedstats-*.json` (FLARE's own output), `data/flare/equivalence-*.json`,
`data/flare/summary.json`, `data/flare/run-*.log`.


## Comparability gate (added 14 November 2026, 23:05 UTC; SYNTHETIC)

Every number in this section is read from `data/flare/gate-v1.json`, written by `flare/build_gate.py`; the step
log is `runs/ship-flare.jsonl`.

- NVIDIA FLARE 2.9.1 ran the new statistics on 23 simulated county sites (FINISHED:COMPLETED,
  179.63 s, one simulator thread). 253 of 253 county x feature cells equal the
  plain-Python central reference (count equal, mean and SD within 1e-6; largest difference 4.9e-13);
  the share within 42 days read from FLARE's histogram equals the central share exactly in every county.
- Referral to treatment, 42 days = placeholder (OECD/EU-reported target): 11,510 of 19,581 SYNTHETIC
  pathways (0.588) within 42 days; started clocks complete 0.989, open at the data
  cut 0.011.
- Gate (placeholder thresholds: median bias beyond +/-3 days, or missed-event share above 10%), if a county's dates
  were read from notes by the scribe: raw scribe 15 of 23 counties not comparable; with the
  code resolver 1 of 23 (HVA04: three
  intervals from one note, each off by -365 days, with negative measured spans). The missed-share rule fires in no county.
- Median bias is computed in plain Python: FLARE-ready, not run in FLARE.
- Real data, areas only: stage is recorded for 42% of cancers nationally, 72% in Pirkanmaa, 60% in the Sisä-Suomi
  collaborative area and 33-42% elsewhere, against an aim of at least 70% (Syöpäjärjestöt, 17 Jun 2026, on the
  Syöpä 2024 report; re-opened 14 Nov 2026 22:56 UTC).
