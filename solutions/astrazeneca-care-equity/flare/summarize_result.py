"""Collect the headline numbers for data/flare/RESULT.md into data/flare/summary.json (SYNTHETIC data)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from compare import national_cells  # noqa: E402
from county_stats import INTERVALS, feature_name  # noqa: E402

fl = json.loads((ROOT / "data/flare/fedstats-none-p12.json").read_text())
meta = json.loads((ROOT / "data/flare/fedstats-none-p12.meta.json").read_text())
eq = {t: json.loads((ROOT / f"data/flare/equivalence-{t}.json").read_text())["summary"]
      for t in ["none-p12", "none-p4", "age_band-p12"]}
nat = national_cells()
rows = []
for k in INTERVALS:
    f = feature_name(k)
    hist = fl[f]["histogram"]["Global"][k]
    idx = meta["histogram_threshold_edge_index"][f]
    within = sum(b[2] for b in hist[:idx])
    total = sum(b[2] for b in hist)
    county_share = [r["share_within_flare"] for r in json.loads((ROOT / "data/flare/equivalence-none-p12.json").read_text())["cells"]
                    if r["interval"] == k]
    rows.append(dict(interval=k, threshold_days=meta["thresholds_days"][k], national_n=total,
                     national_share_within_flare=within / total, national_share_within_central=nat[k]["share_within"],
                     county_share_within_min=min(county_share), county_share_within_max=max(county_share)))
out = dict(synthetic=True, intervals=rows, equivalence={t: {k: s[k] for k in [
    "cells", "cells_ok", "cells_failed", "cells_suppressed_central", "cells_suppressed_flare", "suppressed_sets_identical",
    "histograms_dropped_by_bins_cleanser", "max_abs_diff_mean_log", "max_abs_diff_sd_log", "max_abs_diff_share_within",
    "national_ok", "success"]} for t, s in eq.items()},
    global_rows_with_suppression=eq["age_band-p12"]["flare_global_rows_with_suppression"],
    elapsed_seconds={t: json.loads((ROOT / f"data/flare/fedstats-{t}.meta.json").read_text())["elapsed_seconds"]
                     for t in ["none-p12", "none-p4", "age_band-p12"]})
(ROOT / "data/flare/summary.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out["intervals"], indent=1))
