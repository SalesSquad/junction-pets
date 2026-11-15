# Bahn SpreadGuard campaign evidence (15 November 2026)

Raw outputs of the margin-overlay campaigns A–D, the late-order panel review and the pre-registered decision rule
([`PREREG_20261115.md`](PREREG_20261115.md)), rescued from a laptop scratch directory (`runs/`) and filed here.

- `camp*.jsonl`, `camp*.out`: per-campaign world results and console output.
- `panel_A.json.txt`, `late_panel.json.txt`: panel outputs. Each file holds several concatenated JSON documents (not one
  valid JSON document), so the extension is `.txt`. `late_panel.err` is the matching stderr.
- `switch.diff`: the policy switch used between campaigns.
- `srcC/`, `srcG/`: the as-run source snapshots for campaign C and the grid G. They match the solution files except
  `fork_weekend.py`, `margin_experiment.py`, `run_pair.py` and `summarize_ai_campaign.py`, which are the campaign variants.

Scripts such as `panel_review.py` and `summarize_ai_campaign.py` still expect these files under `./runs/`. Run them from a
working copy where this directory is linked or copied as `runs/`. Summary and analysis: [`../../MARGIN_OVERLAY_20261115.md`](../../MARGIN_OVERLAY_20261115.md).
