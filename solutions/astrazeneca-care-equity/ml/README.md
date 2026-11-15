# Equal Care early-warning forecasts

Public THL Sotkanet annual observations, 2000–2025: eight target indicators and
19 potential input covariates, municipalities, wellbeing counties and Finland.
Fetch is standard-library-only; response URLs, retrieval times, byte counts and
SHA256 digests are retained in `data/panel.json`. No private patient data.

## Current qualification status — 15 November 2026

The original artifacts below are historical, not a qualified holdout evaluation.
Their validation target year 2023 was reused in test scoring. The original
colorectal selection was null (zero validation observations), but the exporter
substituted persistence and produced 44 collapsed bands across 22 counties.
The audit in `../data/ml/forecast-v1-audit.json` is bound to the saved forecast's
SHA-256; the demo withholds that artifact. It has not been edited or relabelled.

The new `split_policy.py` fixes the calendar protocol before any new run:

| Use | Origins | Target years |
| --- | --- | --- |
| Training | Through 2020 | Capped at 2021 |
| Validation / selection / calibration | 2021 | 2022 and 2023 |
| Test | 2023 | 2024 and 2025 |

Window slots and targets now refer to calendar years; missing years remain missing.
The exporter requires the evaluated panel digest and protocol, positive validation
and test counts for each horizon, and effective training support for transformer or
ridge. Persistence/drift do not require fitted-model training counts. A null winner
stays null. Nonfinite, unordered or collapsed bands are not exported; interpolated
quantile probabilities are not presented as calibrated risk.

New default outputs are `ml/artifacts/target-year-disjoint-v1/` and
`data/ml/forecast-v2.json`, leaving the historical runs untouched. The builder prefers
v2 only when present and applies the same admission checks. Use a fresh `--tag` for a
new experiment; do not point corrected runs at historical artifact directories.
Indicators ending in 2024 may lack test h2 labels. Preserve n=0 and abstention.
These already-inspected calendar years can support a corrected **development**
evaluation; an untouched prospective performance claim requires new held-out data.
No corrected public-data run or model improvement is claimed by this source change.

## Run

Local Python 3.12 CPU setup:

```sh
UV_CACHE_DIR=/tmp/astra-uv uv venv --python 3.12 ml/.venv
UV_CACHE_DIR=/tmp/astra-uv uv pip install --python ml/.venv/bin/python -r ml/requirements.txt
ml/.venv/bin/python ml/fetch_panel.py
ml/.venv/bin/python -m unittest discover -s ml/tests -v
ml/.venv/bin/python ml/train_forecaster.py --device cpu --epochs 8 --seeds 2
ml/.venv/bin/python ml/evaluate.py --device cpu --epochs 8 --seeds 2
ml/.venv/bin/python ml/export_forecasts.py --device cpu --epochs 8 --seeds 2
```

Fresh Ubuntu GPU host (Python3, pip, compatible NVIDIA driver required):
`bash ml/run_all.sh`. It bootstraps venv (virtualenv fallback), installs torch and
numpy, fetches, trains, evaluates and exports. Default: CUDA, 100 maximum epochs,
five seeds. Override with `--device cpu --epochs 8 --seeds 2`, or `--smoke`.
PyTorch's Linux wheel supplies CUDA runtime dependencies; it cannot supply a GPU
or host driver. CUDA execution has not been qualified on the local CPU host.

## Method and validation

Eight-step windows contain standardized values, observation masks, category
embeddings, calendar-year index and learned time position. A three-layer,
four-head, 128-wide transformer predicts change from last observed target via
five sorted quantiles. Observed inputs are randomly hidden with probability .15.
AdamW, cosine learning-rate decay, validation pinball early stopping (patience
10), deterministic seeds, ensemble mean. Missing targets/anchors are masked.
Normalization uses only training windows. No temporal interpolation or future
covariates. Baselines: last value, mean last three observed adjacent annual
changes, and pooled ridge with intercept and three recent annual values (missing
recent values filled from the last observation). Ridge penalty is fixed at 1.

The enforced split and output-admission rules are specified above. All methods use
common finite cells; report category, horizon, MAE, pinball, coverage and sample count.
Validation-based intervals are empirical and may not generalise. Selection is based
only on validation scores, with stable baseline-first ties. Transformer/ridge
candidates without effective training support cannot win. A selected model can be
refitted on available labels for future prediction, but that refit is not a new
holdout evaluation. Unsupported horizons remain unavailable.

## Bounded GPU sweep

From the repository root on a fresh Ubuntu NVIDIA host:

```sh
bash ml/run_sweep.sh
```

The script reuses `ml/.venv`, installs the existing requirements, sets
`CUBLAS_WORKSPACE_CONFIG=:4096:8`, fetches base and extended panels, runs
14 configurations × 3 seeds on CUDA (100 maximum epochs, validation early
stopping), then refits and exports validation-selected methods to
`data/ml/forecast-v2.json`. A compatible NVIDIA driver and Python venv/pip
support are prerequisites. Existing architecture-specific wheel guidance above
still applies. This new full GPU sweep has **not been run locally**.

The extended panel is `ml/data/panel-extended.json`. Extra covariates are
considered in ascending Sotkanet indicator ID order from `GET /indicators`;
targets and existing covariates are excluded. Candidates need municipality
classification, observations in at least 15 distinct years in 2000–2025,
and at least 250 municipalities in their latest observed year (including any
later country/county observation when establishing that year). Fetching uses
a 200 ms request delay and four attempts with exponential backoff; failed and
ineligible IDs are recorded with reasons. Up to 150 eligible extras are added;
the actual count and response hashes are retained. This availability screen
uses the requested 2000–2025 coverage metadata, not forecast error or outcomes
for selection. It is retrospective feature availability, not proof of what
would have been published at an historical forecast origin.

New sweep artifacts go under `ml/artifacts/target-year-disjoint-v1/gpu-sweep/`:
`selection.json` is written before test scoring, `sweep.json` and
`SWEEP_REPORT.md` contain the comparison, and each `config-NN/` retains
its configuration, panel digest and seed ensemble checkpoint. Standalone
`python ml/sweep.py` writes to `ml/artifacts/target-year-disjoint-v1/`; use `--tag NAME`
to isolate a run. Choose a fresh tag; do not overwrite retained evidence.

The seven paired (base/extended) architectures are
(window, width, layers): (5,64,2), (8,64,3), (12,64,2), (5,128,3),
(8,128,3), (12,128,2), (8,256,3). Four heads, learning rate .0005,
dropout .1 and input mask rate .15 retain the original defaults.
All shared commands accept `--d-model`, `--layers`, `--heads`,
`--window`, `--lr`, `--dropout`, `--mask-rate`, `--panel` and `--tag`.
Checkpoints retain architecture settings for prediction. Without these flags,
the original model and command defaults are unchanged.

Validation comparison uses the intersection of finite cells across every
configuration and baseline. Baselines retain the original eight-year base-panel
inputs. As required by SPEC, one method/config is selected **per indicator** by
pooled validation MAE across both horizons and all unit categories, weighted by
observed cell count; horizon-specific validation MAEs are displayed separately.
Stable exact ties prefer persistence, drift, ridge, then config order.
No test score enters selection. Only the validation-best transformer receives
test scores for that indicator, alongside all three baselines; the verdict
compares against the validation-best baseline, never a test-selected baseline.
Test tables use identical finite cells for those compared methods.

The verdict reports baseline MAE minus transformer MAE and the max-minus-min
test MAE of the winning transformer's individual seeds. It also records these
seed MAEs separately by horizon. An improvement must exceed that range to
receive the corresponding descriptive flag; fewer than two usable seeds means
spread is unavailable. This range is **not** a confidence interval or a
significance test. Fourteen configurations share a single validation origin;
validation selection can overfit. The existing shared-calendar-year limitation
between validation h2 and test h1 still applies.

To rerun export alone after a completed sweep:

```sh
ml/.venv/bin/python ml/export_forecasts.py --device cuda --tag gpu-sweep --sweep
```

Export verifies panel digests, refits each selected transformer configuration
once, and refits baseline winners on all labeled origins. Each indicator's
`trainedOn.chosenConfigs` and `metrics.chosenConfig` identify its method,
panel and hyperparameters; sweep test metrics are explicitly labeled as pooled
across unit categories. Baseline winners remain baselines. Export does not
select or reselect using test results. Product output is updated only when this
command executes successfully; CPU synthetic tests do not replace real forecasts.

For a bounded custom/smoke grid, supply `--grid PATH` to `sweep.py`:
a JSON list such as
`[{"window":5,"d_model":8,"layers":1,"heads":2}]`.
Allowed overrides are panel, window, d_model, layers, heads, lr, dropout,
mask_rate. Each config inherits other CLI flags; different panels must have
identical units, target order, validation/test origins and target observations.
Use `--panel SYNTHETIC.json --device cpu --epochs 1 --seeds 2 --tag smoke`
with that grid. The test suite generates its own synthetic panel, runs two
configs with two seeds, changes only held-out years 2024–2025, reruns and
asserts identical validation scores/winners, exercises baseline and transformer
export, and rejects a changed panel digest:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tests -v
```
