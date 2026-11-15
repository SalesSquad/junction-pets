"""NVIDIA FLARE statistics generator for one simulated county site (SYNTHETIC data only).

Each FLARE client is one county (site name = county code, e.g. HVA01). At start-up the
client reads only its own Hive partition of the SYNTHETIC event log
(data/eventlog/sample/year=*/county=<site>/) and its own roster rows, derives pathway
intervals with the same SAMA code the central pipeline uses (eventlog.intervals.derive),
and exposes one dataset per interval (or per interval and age band in the stratified run).

The feature is the log duration exactly as eventlog.aggregate.summarize defines it:
complete cases only (not censored, end point observed), log(days), and a zero-day interval
logged as eventlog.power.ZERO_DAY (0.5 day). Only aggregate statistics leave the site, after
FLARE's privacy result filters (MinCountCleanser, AddNoiseToMinMax, HistogramBinsCleanser).

This is a simulation: all 23 "sites" run on one machine and read partitions of one
SYNTHETIC folder. Nothing here has touched real patient data.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from nvflare.apis.fl_context import FLContext
from nvflare.app_opt.statistics.df.df_core_statistics import DFStatisticsCore

INTERVALS = ["primary_care", "diagnostic", "treatment", "total"]


def feature_name(interval: str) -> str:
    return f"log_days_{interval}"


def dataset_name(interval: str, stratum: Optional[str]) -> str:
    return interval if stratum is None else f"{interval}|{stratum}"


class CountyEventLogStatistics(DFStatisticsCore):
    def __init__(self, project_root: str, data_cut: str = "2026-12-31", strata: str = "none"):
        """
        project_root: absolute path of the SAMA solution folder (holds eventlog/ and data/eventlog/).
        data_cut: administrative cut-off date used by the central pipeline (ISO date).
        strata: "none" -> one dataset per interval; "age_band" -> one dataset per interval x age band.
        """
        super().__init__()
        self.project_root = project_root
        self.data_cut = data_cut
        self.strata = strata
        self.site_summary: Dict = {}

    # ------------------------------------------------------------------ data
    def _load_site_intervals(self, site: str) -> pd.DataFrame:
        root = Path(self.project_root)
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import pyarrow.dataset as ds

        from eventlog.intervals import derive
        from eventlog.schema import pathway_events

        sample = ds.dataset(str(root / "data/eventlog/sample"), format="parquet", partitioning="hive")
        # Partition pruning: only this county's directory is read.
        events = sample.to_table(filter=ds.field("county") == site)
        events = events.select(pathway_events.names).cast(pathway_events)
        roster = [e for e in json.loads((root / "data/eventlog/sample-roster.json").read_text()) if e["county"] == site]
        intervals = derive(events, roster, date.fromisoformat(self.data_cut)).to_pandas()
        ev = events.to_pandas()
        age = ev.groupby("episode_id", observed=True)["age_band"].first().astype(str)
        intervals["age_band"] = intervals["episode_id"].map(age)
        self.site_summary = dict(site=site, events=int(events.num_rows), episodes=len(roster))
        return intervals

    def initialize(self, fl_ctx: FLContext):
        self.load(fl_ctx.get_identity_name())

    def load(self, site: str):
        table = self._load_site_intervals(site)
        from eventlog.power import ZERO_DAY  # importable once _load_site_intervals set sys.path

        self.data = {}
        strata = [None] if self.strata == "none" else sorted(table[self.strata].dropna().unique())
        for interval in INTERVALS:
            days = table["days_" + interval]
            complete = (~table["censored_" + interval].astype(bool)) & days.notna()
            if (days[complete] < 0).any():
                raise ValueError(f"negative duration at {site}/{interval}; validate first")
            for stratum in strata:
                mask = complete if stratum is None else complete & (table[self.strata] == stratum)
                x = days[mask].to_numpy(dtype=float)
                if len(x) == 0:
                    # FLARE's mean is sum/count; an empty cell is not sent at all (reported as n = 0).
                    continue
                logs = np.log(np.where(x > 0, x, ZERO_DAY))
                self.data[dataset_name(interval, stratum)] = pd.DataFrame({feature_name(interval): logs})

    def count(self, dataset_name: str, feature_name: str) -> int:
        return int(super().count(dataset_name, feature_name))
