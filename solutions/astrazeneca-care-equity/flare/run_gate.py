"""Run the comparability-gate statistics in NVIDIA FLARE 2.9.1 over 23 simulated county sites (SYNTHETIC data).

Usage (from the solution folder, after flare/gate_prep.py):
  flare/.venv/bin/python flare/run_gate.py --threads 1

Same job class, privacy filters and precision as flare/run_fedstats.py (Lane C step 9), with the gate's
datasets from flare/gate_stats.py. Writes data/flare/fedstats-gate-p12.json (FLARE's own JSON output) and
data/flare/fedstats-gate-p12.meta.json (config, timing, input hashes). One simulator thread by default to
keep memory small on a shared Mac.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from gate import ARMS, COUNTIES, MIN_COUNT, RTT_THRESHOLD_DAYS  # noqa: E402
from gate_stats import CountyGateStatistics  # noqa: E402
from run_fedstats import CountyStatsRecipe, PreciseStatsJob, histogram_config, sha256  # noqa: E402

from nvflare.recipe import SimEnv  # noqa: E402

BINARY = {"bins": 2, "range": [-0.5, 1.5]}  # bin 0 counts the 0s, bin 1 the 1s
WIDE = {"bins": 2, "range": [-3650.5, 3650.5]}  # signed errors; the gate does not read this histogram


def statistic_configs():
    rtt = histogram_config(RTT_THRESHOLD_DAYS)
    hist = {"log_days_rtt": {"bins": rtt["bins"], "range": rtt["range"]}, "rtt_complete": BINARY, "rtt_open": BINARY}
    for arm in ARMS:
        hist[f"{arm}_missed"] = BINARY
        hist[f"{arm}_err_days"] = WIDE
        hist[f"{arm}_err_gt3"] = BINARY
        hist[f"{arm}_err_lt_m3"] = BINARY
    return {"count": {}, "sum": {}, "mean": {}, "stddev": {}, "histogram": hist}, rtt["threshold_edge_index"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--precision", type=int, default=12)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--workspace", default=str(HERE / "workspace"))
    a = p.parse_args()

    tag = f"gate-p{a.precision}"
    name = f"sama_gate_p{a.precision}"
    configs, edge_index = statistic_configs()
    job = PreciseStatsJob(
        name=name,
        statistic_configs=configs,
        stats_generator=CountyGateStatistics(project_root=str(ROOT)),
        output_path=f"statistics/{name}.json",
        min_count=MIN_COUNT,
        min_noise_level=0.1,
        max_noise_level=0.3,
        max_bins_percent=10,
        precision=a.precision,
    )
    recipe = CountyStatsRecipe(job, COUNTIES)
    env = SimEnv(clients=COUNTIES, num_threads=a.threads, workspace_root=a.workspace)

    inputs = {k: sha256(ROOT / k) for k in ["data/eventlog/sample-roster.json", "data/flare/gate-sites/assignment.json"]}
    parts = sorted(glob.glob(str(ROOT / "data/eventlog/sample/year=*/county=*/*.parquet")))
    inputs["data/eventlog/sample/*"] = hashlib.sha256(b"".join(sha256(Path(x)).encode() for x in parts)).hexdigest()
    sites = sorted(glob.glob(str(ROOT / "data/flare/gate-sites/county=*/scribe.json")))
    inputs["data/flare/gate-sites/county=*/scribe.json"] = hashlib.sha256(b"".join(sha256(Path(x)).encode() for x in sites)).hexdigest()

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
        precision=a.precision,
        min_count=MIN_COUNT,
        sites=COUNTIES,
        simulator_threads=a.threads,
        statistic_configs=configs,
        rtt_threshold_days=RTT_THRESHOLD_DAYS,
        rtt_histogram_threshold_edge_index=edge_index,
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
    print(json.dumps({k: meta[k] for k in ["precision", "run_status", "elapsed_seconds", "output"]}))
    if not found:
        sys.exit(2)


if __name__ == "__main__":
    main()
