"""Run NVIDIA FLARE 2.9.1 federated statistics over 23 simulated county sites (SYNTHETIC data).

Usage (from the solution folder):
  flare/.venv/bin/python flare/run_fedstats.py --strata none --precision 12
  flare/.venv/bin/python flare/run_fedstats.py --strata none --precision 4      # FLARE's default rounding
  flare/.venv/bin/python flare/run_fedstats.py --strata age_band --precision 12 # small cells -> MinCountCleanser

Writes data/flare/fedstats-<strata>-p<precision>.json (FLARE's own JSON output, copied from the
simulator workspace) and data/flare/fedstats-<strata>-p<precision>.meta.json (config, timing).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from county_stats import INTERVALS, CountyEventLogStatistics, feature_name  # noqa: E402

from nvflare.app_common.executors.statistics.statistics_executor import StatisticsExecutor  # noqa: E402
from nvflare.app_common.workflows.statistics_controller import StatisticsController  # noqa: E402
from nvflare.job_config.stats_job import StatsJob  # noqa: E402
from nvflare.recipe import SimEnv  # noqa: E402
from nvflare.recipe.spec import Recipe  # noqa: E402

# Same 23 county codes as eventlog.schema.COUNTIES.
COUNTIES = [f"HVA{i:02}" for i in range(1, 22)] + ["HVA90", "HVA91"]
# Same placeholder thresholds as eventlog.aggregate.aggregate (assumptions, not national targets).
THRESHOLDS = dict(primary_care=90, diagnostic=60, treatment=30, total=180)
ZERO_DAY = 0.5
CAP_DAYS = 3650  # histogram upper bound fixed in advance (10 years); no site reveals its max
FACTOR = 3.0  # bin width in log space = log(3): edges at (T + 0.5) * 3**k days


def histogram_config(threshold: int) -> dict:
    """Uniform log-duration bins with one edge at log(T + 0.5).

    Durations are whole days, so log(x) < log(T + 0.5) exactly when x <= T: the bins below that
    edge hold the intervals within target, the central table's `x <= threshold` rule.
    """
    edge = math.log(threshold + 0.5)
    w = math.log(FACTOR)
    below = math.ceil((edge - math.log(ZERO_DAY)) / w)
    above = math.ceil((math.log(CAP_DAYS) - edge) / w)
    return {"bins": below + above, "range": [edge - below * w, edge + above * w], "threshold_edge_index": below}


class PreciseStatsJob(StatsJob):
    """StatsJob with the rounding precision exposed (FLARE's default rounds every statistic to 4 digits)."""

    def __init__(self, *args, precision: int = 4, **kwargs):
        self.precision = precision
        super().__init__(*args, **kwargs)

    def get_stats_controller(self) -> StatisticsController:
        return StatisticsController(
            statistic_configs=self.statistic_configs,
            writer_id=self.writer_id,
            enable_pre_run_task=False,
            precision=self.precision,
            result_wait_timeout=60,
        )

    def setup_clients(self, sites):
        for site_id in sites:
            gen_id = self.to(self.stats_generator, site_id, id=self.stats_generator_id_prefix)
            executor = StatisticsExecutor(generator_id=gen_id, precision=self.precision)
            self.to(executor, site_id, tasks=["fed_stats_pre_run", "fed_stats"])
            self.add_privacy_result_filters(site_id)


class CountyStatsRecipe(Recipe):
    def __init__(self, job: StatsJob, sites):
        job.setup_clients(sites)
        Recipe.__init__(self, job)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strata", choices=["none", "age_band"], default="none")
    p.add_argument("--precision", type=int, default=12)
    p.add_argument("--min-count", type=int, default=5)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--workspace", default=str(HERE / "workspace"))
    a = p.parse_args()

    tag = f"{a.strata}-p{a.precision}"
    name = f"sama_county_stats_{a.strata}_p{a.precision}"
    hist = {feature_name(k): histogram_config(THRESHOLDS[k]) for k in INTERVALS}
    statistic_configs = {
        "count": {},
        "sum": {},
        "mean": {},
        "stddev": {},
        "histogram": {f: {"bins": c["bins"], "range": c["range"]} for f, c in hist.items()},
    }
    generator = CountyEventLogStatistics(project_root=str(ROOT), data_cut="2026-12-31", strata=a.strata)
    job = PreciseStatsJob(
        name=name,
        statistic_configs=statistic_configs,
        stats_generator=generator,
        output_path=f"statistics/{name}.json",
        min_count=a.min_count,
        min_noise_level=0.1,
        max_noise_level=0.3,
        max_bins_percent=10,
        precision=a.precision,
    )
    recipe = CountyStatsRecipe(job, COUNTIES)
    env = SimEnv(clients=COUNTIES, num_threads=a.threads, workspace_root=a.workspace)

    inputs = {
        "data/eventlog/sample-roster.json": sha256(ROOT / "data/eventlog/sample-roster.json"),
        "data/eventlog/county-intervals.json": sha256(ROOT / "data/eventlog/county-intervals.json"),
    }
    parts = sorted(glob.glob(str(ROOT / "data/eventlog/sample/year=*/county=*/*.parquet")))
    inputs["data/eventlog/sample/*"] = hashlib.sha256(b"".join(sha256(Path(x)).encode() for x in parts)).hexdigest()

    t0 = time.monotonic()
    run = recipe.execute(env)
    result_dir = run.get_result(clean_up=False)
    status = run.get_status()
    elapsed = time.monotonic() - t0

    found = glob.glob(os.path.join(a.workspace, name, "**", f"{name}.json"), recursive=True)
    out = ROOT / "data/flare" / f"fedstats-{tag}.json"
    meta = dict(
        synthetic=True,
        nvflare=__import__("nvflare").__version__,
        strata=a.strata,
        precision=a.precision,
        min_count=a.min_count,
        sites=COUNTIES,
        simulator_threads=a.threads,
        statistic_configs=statistic_configs,
        histogram_threshold_edge_index={f: c["threshold_edge_index"] for f, c in hist.items()},
        thresholds_days=THRESHOLDS,
        privacy_filters=["MinCountCleanser(min_count)", "AddNoiseToMinMax(0.1, 0.3)", "HistogramBinsCleanser(10%)"],
        inputs_sha256=inputs,
        run_status=status,
        result_dir=os.path.relpath(result_dir, ROOT) if result_dir else None,
        elapsed_seconds=round(elapsed, 2),
        output=str(out.relative_to(ROOT)) if found else None,
    )
    if found:
        shutil.copyfile(found[0], out)
        meta["output_sha256"] = sha256(out)
    (ROOT / "data/flare" / f"fedstats-{tag}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ["strata", "precision", "run_status", "elapsed_seconds", "output"]}))
    if not found:
        sys.exit(2)


if __name__ == "__main__":
    main()
