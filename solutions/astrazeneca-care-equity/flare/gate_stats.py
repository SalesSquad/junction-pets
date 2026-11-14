"""NVIDIA FLARE statistics generator for the comparability gate, one simulated county site (SYNTHETIC data).

Each FLARE client is one county (site name = county code). At start-up the site reads only
  - its own Hive partition of the SYNTHETIC event log, data/eventlog/sample/year=*/county=<site>/, and its
    own roster rows -> the referral-to-treatment clock (flare/gate.py rtt_records);
  - its own scribe partition, data/flare/gate-sites/county=<site>/scribe.json (flare/gate_prep.py), which
    holds the scribe's error profile on the SYNTHETIC notes assigned to this county, raw and with resolver.
Datasets and features (one feature name per dataset so FLARE's output stays unambiguous):
  rtt                   log_days_rtt       log(days), complete clocks only (zero days logged as 0.5)
  rtt_record            rtt_complete, rtt_open   0/1 per started clock (REFERRAL_SENT recorded)
  scribe_<arm>_events   <arm>_missed       0/1 per gold event
  scribe_<arm>_intervals <arm>_err_days, <arm>_err_gt3, <arm>_err_lt_m3   signed error of a found
                        within-note interval (scribe - true, days) and two 0/1 flags (beyond +3 / -3 days)
Only aggregates leave a site, after FLARE's privacy filters (MinCountCleanser, AddNoiseToMinMax,
HistogramBinsCleanser). Simulation only: every site runs on one Mac and reads partitions of one folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

import pandas as pd

from nvflare.apis.fl_context import FLContext
from nvflare.app_opt.statistics.df.df_core_statistics import DFStatisticsCore

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gate import ARMS, log_days, rtt_records  # noqa: E402


def site_frames(project_root: str, site: str) -> Dict[str, pd.DataFrame]:
    root = Path(project_root)
    import pyarrow.dataset as ds

    sample = ds.dataset(str(root / "data/eventlog/sample"), format="parquet", partitioning="hive")
    # Partition pruning: only this county's directory is read.
    ev = sample.to_table(filter=ds.field("county") == site, columns=["episode_id", "event_type", "event_date"]).to_pylist()
    roster = [e for e in json.loads((root / "data/eventlog/sample-roster.json").read_text()) if e["county"] == site]
    recs = rtt_records(ev, roster)
    days = [r["days"] for r in recs if r["days"] is not None]
    frames = {
        "rtt": pd.DataFrame({"log_days_rtt": [log_days(x) for x in days]}),
        "rtt_record": pd.DataFrame({"rtt_complete": [float(r["days"] is not None) for r in recs],
                                    "rtt_open": [float(r["open"]) for r in recs]}),
    }
    scribe = json.loads((root / "data/flare/gate-sites" / f"county={site}" / "scribe.json").read_text())
    for arm in ARMS:
        a = scribe["arms"][arm]
        frames[f"scribe_{arm}_events"] = pd.DataFrame({f"{arm}_missed": [float(e["missed"]) for e in a["events"]]})
        errs = [float(q["err"]) for q in a["intervals"]]
        frames[f"scribe_{arm}_intervals"] = pd.DataFrame({f"{arm}_err_days": errs,
                                                          f"{arm}_err_gt3": [float(x > 3) for x in errs],
                                                          f"{arm}_err_lt_m3": [float(x < -3) for x in errs]})
    # FLARE's mean is sum/count; an empty frame is not sent at all (reported as n = 0).
    return {k: v for k, v in frames.items() if len(v)}


class CountyGateStatistics(DFStatisticsCore):
    def __init__(self, project_root: str):
        super().__init__()
        self.project_root = project_root

    def initialize(self, fl_ctx: FLContext):
        self.load(fl_ctx.get_identity_name())

    def load(self, site: str):
        self.data = site_frames(self.project_root, site)

    def count(self, dataset_name: str, feature_name: str) -> int:
        return int(super().count(dataset_name, feature_name))
