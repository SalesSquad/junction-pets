"""Equivalence diff: FLARE federated statistics against SAMA's central table (SYNTHETIC data).

Usage (from the solution folder):
  flare/.venv/bin/python flare/compare.py --strata none --precision 12
  flare/.venv/bin/python flare/compare.py --strata age_band --precision 12

Central reference:
  strata none     -> data/eventlog/county-intervals.json (the committed central county x interval table)
                     plus a national pooled row computed with eventlog.aggregate.summarize, since the
                     committed table has no national row.
  strata age_band -> eventlog.aggregate.summarize on data/eventlog/sample-intervals.parquet grouped by
                     county x age band (age band taken from the event log). The committed table has no
                     strata; this is the same function on a finer grouping, so cells with n < 5 exist.
Success: count equal, mean and SD of log duration within 1e-6, suppressed cells identical, and the
histogram reproduces n and the share within the threshold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import pyarrow.parquet as pq  # noqa: E402

from county_stats import INTERVALS, dataset_name, feature_name  # noqa: E402
from eventlog.aggregate import summarize  # noqa: E402
from eventlog.parquet_io import read_dataset  # noqa: E402

TOL = 1e-6
THRESHOLDS = dict(primary_care=90, diagnostic=60, treatment=30, total=180)


def central_cells(strata: str):
    """{(county, interval, stratum): summarize-dict}; stratum None for the county table."""
    cells = {}
    if strata == "none":
        table = json.loads((ROOT / "data/eventlog/county-intervals.json").read_text())
        for s in table["statistics"]:
            cells[(s["county"], s["interval"], None)] = s
        return cells, "data/eventlog/county-intervals.json"
    iv = pq.read_table(ROOT / "data/eventlog/sample-intervals.parquet").to_pylist()
    ev = read_dataset(ROOT / "data/eventlog/sample").select(["episode_id", "age_band"]).to_pylist()
    age = {}
    for r in ev:
        age.setdefault(r["episode_id"], r["age_band"])
    groups = defaultdict(list)
    for r in iv:
        for k in INTERVALS:
            key = (r["county"], k, age[r["episode_id"]])
            groups[key]  # mirror eventlog.aggregate: a cell exists for every row's group
            x = r["days_" + k]
            if not r["censored_" + k] and x is not None:
                groups[key].append(x)
    for key, v in groups.items():
        cells[key] = summarize(v, THRESHOLDS[key[1]])
    return cells, "summarize(data/eventlog/sample-intervals.parquet by county x age_band)"


def national_cells():
    iv = pq.read_table(ROOT / "data/eventlog/sample-intervals.parquet").to_pylist()
    out = {}
    for k in INTERVALS:
        v = [r["days_" + k] for r in iv if not r["censored_" + k] and r["days_" + k] is not None]
        out[k] = summarize(v, THRESHOLDS[k])
    return out


def get(fl, stat, site, ds):
    return fl.get(stat, {}).get(site, {}).get(ds)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strata", choices=["none", "age_band"], default="none")
    p.add_argument("--precision", type=int, default=12)
    a = p.parse_args()
    tag = f"{a.strata}-p{a.precision}"
    flare = json.loads((ROOT / "data/flare" / f"fedstats-{tag}.json").read_text())
    meta = json.loads((ROOT / "data/flare" / f"fedstats-{tag}.meta.json").read_text())
    edge_idx = meta["histogram_threshold_edge_index"]
    central, source = central_cells(a.strata)

    rows, fails = [], []
    n_cells = n_supp = n_zero = n_hist_dropped = 0
    max_dmean = max_dsd = max_dshare = 0.0
    for (county, interval, stratum), c in sorted(central.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        f = flare[feature_name(interval)]
        ds = dataset_name(interval, stratum)
        n_f = get(f, "count", county, ds)
        mean_f, sd_f, hist_f = get(f, "mean", county, ds), get(f, "stddev", county, ds), get(f, "histogram", county, ds)
        row = dict(county=county, interval=interval, stratum=stratum, n_central=c["n"], n_flare=n_f,
                   suppressed_central=bool(c["suppressed"]))
        n_cells += 1
        if c["n"] == 0:
            n_zero += 1
            row["suppressed_flare"] = n_f is None
            ok = n_f is None  # FLARE site sends nothing for an empty cell
            row["ok"] = ok
            if not ok:
                fails.append(row)
            rows.append(row)
            continue
        supp_f = n_f is not None and mean_f is None and sd_f is None
        row["suppressed_flare"] = supp_f
        ok = n_f == c["n"] and supp_f == bool(c["suppressed"])
        if c["suppressed"]:
            n_supp += 1
            ok = ok and hist_f is None
        else:
            dmean = abs(mean_f - c["mean_log_duration"])
            dsd = abs(sd_f - c["sd_log_duration"])
            max_dmean, max_dsd = max(max_dmean, dmean), max(max_dsd, dsd)
            row.update(mean_central=c["mean_log_duration"], mean_flare=mean_f, abs_diff_mean=dmean,
                       sd_central=c["sd_log_duration"], sd_flare=sd_f, abs_diff_sd=dsd)
            ok = ok and dmean <= TOL and dsd <= TOL
            limit = round(c["n"] * 10 / 100)
            bins = meta["statistic_configs"]["histogram"][feature_name(interval)]["bins"]
            if hist_f is None:
                n_hist_dropped += 1
                row["histogram"] = "dropped by HistogramBinsCleanser"
                ok = ok and bins >= limit  # must be the filter's own rule, not a missing value
            else:
                total = sum(b[2] for b in hist_f)
                within = sum(b[2] for b in hist_f[: edge_idx[feature_name(interval)]])
                share = within / total
                dshare = abs(share - c["share_within"])
                max_dshare = max(max_dshare, dshare)
                row.update(hist_total=total, share_within_central=c["share_within"], share_within_flare=share)
                ok = ok and total == c["n"] and dshare <= 1e-12
        row["ok"] = ok
        if not ok:
            fails.append(row)
        rows.append(row)

    # Cells FLARE reported that the central table does not have.
    extra = []
    for interval in INTERVALS:
        for site, dss in flare[feature_name(interval)]["count"].items():
            if site == "Global":
                continue
            for ds in dss:
                stratum = None if "|" not in ds else ds.split("|", 1)[1]
                if (site, interval, stratum) not in central:
                    extra.append([site, ds])

    # FLARE's "Global" row when some counties are suppressed. MinCountCleanser keeps the count but
    # removes the sum, so the global count includes suppressed counties while the global sum does not.
    global_rows = None
    if a.strata != "none":
        by_ds = defaultdict(list)
        for r in rows:
            by_ds[(r["interval"], r["stratum"])].append(r)
        n_with_supp = count_incl = mean_is_sum_over_all = 0
        max_gap = 0.0
        worst = None
        for (interval, stratum), cs in by_ds.items():
            f = flare[feature_name(interval)]
            ds = dataset_name(interval, stratum)
            g_count = f["count"]["Global"].get(ds)
            g_mean = f["mean"].get("Global", {}).get(ds)
            n_all = sum(r["n_central"] for r in cs)
            count_incl += g_count == n_all
            kept = [r for r in cs if not r["suppressed_central"]]
            if len(kept) == len(cs) or not kept or g_mean is None:
                continue
            n_with_supp += 1
            s_kept = sum(r["mean_central"] * r["n_central"] for r in kept)
            n_kept = sum(r["n_central"] for r in kept)
            mean_is_sum_over_all += abs(g_mean - s_kept / n_all) <= TOL
            gap = abs(g_mean - s_kept / n_kept)
            if gap > max_gap:
                max_gap = gap
                worst = dict(dataset=ds, flare_global_count=g_count, n_suppressed_counties=len(cs) - len(kept),
                             flare_global_mean=g_mean, mean_of_unsuppressed_counties=s_kept / n_kept)
        global_rows = dict(
            datasets=len(by_ds),
            datasets_with_a_suppressed_county=n_with_supp,
            global_count_includes_suppressed_counties=count_incl,
            global_mean_equals_unsuppressed_sum_over_all_counts=mean_is_sum_over_all,
            max_abs_gap_global_mean_vs_unsuppressed_mean_log=max_gap,
            worst=worst,
            note="County rows are exact. FLARE's national row for a stratum with a suppressed county divides the "
                 "sum of unsuppressed counties by a count that still includes suppressed counties; do not use it as-is.",
        )

    national = []
    if a.strata == "none":
        for k, c in national_cells().items():
            f = flare[feature_name(k)]
            g = dict(interval=k, n_central=c["n"], n_flare=f["count"]["Global"][k],
                     mean_central=c["mean_log_duration"], mean_flare=f["mean"]["Global"][k],
                     sd_central=c["sd_log_duration"], sd_flare=f["stddev"]["Global"][k])
            g["abs_diff_mean"] = abs(g["mean_flare"] - g["mean_central"])
            g["abs_diff_sd"] = abs(g["sd_flare"] - g["sd_central"])
            g["ok"] = g["n_flare"] == g["n_central"] and g["abs_diff_mean"] <= TOL and g["abs_diff_sd"] <= TOL
            national.append(g)

    summary = dict(
        synthetic=True,
        strata=a.strata,
        precision=a.precision,
        tolerance=TOL,
        central_source=source,
        central_inputs_sha256={x: hashlib.sha256((ROOT / x).read_bytes()).hexdigest() for x in
                               ["data/eventlog/county-intervals.json", "data/eventlog/sample-intervals.parquet"]},
        flare_inputs_sha256=meta["inputs_sha256"],
        flare_output=f"data/flare/fedstats-{tag}.json",
        cells=n_cells,
        cells_ok=n_cells - len(fails),
        cells_failed=len(fails),
        cells_suppressed_central=sum(1 for r in rows if r["suppressed_central"]),
        cells_suppressed_flare=sum(1 for r in rows if r["suppressed_flare"]),
        suppressed_sets_identical=all(r["suppressed_central"] == r["suppressed_flare"] for r in rows),
        cells_with_n_0=n_zero,
        cells_with_1_to_4=n_supp,
        histograms_dropped_by_bins_cleanser=n_hist_dropped,
        max_abs_diff_mean_log=max_dmean,
        max_abs_diff_sd_log=max_dsd,
        max_abs_diff_share_within=max_dshare,
        flare_cells_not_in_central=len(extra),
        national_pooled=national,
        national_ok=all(g["ok"] for g in national) if national else None,
        flare_global_rows_with_suppression=global_rows,
        success=len(fails) == 0 and not extra and (all(g["ok"] for g in national) if national else True),
    )
    out = ROOT / "data/flare" / f"equivalence-{tag}.json"
    out.write_text(json.dumps(dict(summary=summary, failures=fails[:50], extra=extra[:50], cells=rows), indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "national_pooled"}, indent=1))
    sys.exit(0 if summary["success"] else 1)


if __name__ == "__main__":
    main()
