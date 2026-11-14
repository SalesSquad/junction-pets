# Equal Care early-warning forecasts

Public THL Sotkanet annual observations, 2000–2025: eight target indicators and
19 potential input covariates, municipalities, wellbeing counties and Finland.
Fetch is standard-library-only; response URLs, retrieval times, byte counts and
SHA256 digests are retained in `data/panel.json`. No private patient data.

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

Training origins end in 2020, with labels capped at 2021. Validation origin is
2021; test origins are 2022 and 2023. Thus training never sees a test target.
The specified validation h2 and test h1 share calendar year 2023: these are
correlated, not independent cohorts. All four methods use identical finite test
cells. Metrics report county and municipality groups separately, both horizons,
MAE, pinball, 90% and 50% coverage, sample count and pre-conformal 90% coverage.
Validation error quantiles supply baseline intervals. Nonnegative finite-sample
split-conformal widening uses only validation scores; validation coverage is
also reported. Tiny or empty cohorts cannot establish population calibration.

Method selection uses lowest validation MAE pooled over units and horizons per
indicator, with deterministic method-order ties. It does not select on test
scores. Selected ridge is refit on all labeled origins; selected transformer is
refit on all labeled origins using the backtest epoch budget, with no new future
holdout. Backtest interval offsets/widening are retained for export. Each county
forecast starts from its own latest observed target year, which may be old.
Quantile-CDF interpolation has clipped tails [.02,.98]; ties use NumPy's
rightmost quantile convention. Probabilities are coarse distribution summaries,
not clinical risk or causal effects. No baseline win is disguised as a model win.

`artifacts/metrics.json`, logs and checkpoints retain actual run evidence;
`../data/ml/forecast-v1.json` is the product output. Unsupported indicators are
listed by fetch; unavailable evaluation cells are null with n=0, never invented.
CPU run configuration is reduced; the full GPU run remains unexecuted locally.

## Bounded GPU sweep

From the repository root on a fresh Ubuntu NVIDIA host:

```sh
bash ml/run_sweep.sh
```

The script reuses `ml/.venv`, installs the existing requirements, sets
`CUBLAS_WORKSPACE_CONFIG=:4096:8`, fetches base and extended panels, runs
14 configurations × 3 seeds on CUDA (100 maximum epochs, validation early
stopping), then refits and exports validation-selected methods to
`data/ml/forecast-v1.json`. A compatible NVIDIA driver and Python venv/pip
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

Artifacts go under `ml/artifacts/gpu-sweep/`, preserving the earlier backtest:
`selection.json` is written before test scoring, `sweep.json` and
`SWEEP_REPORT.md` contain the comparison, and each `config-NN/` retains
its configuration, panel digest and seed ensemble checkpoint. Standalone
`python ml/sweep.py` writes directly to `ml/artifacts/`; use `--tag NAME`
to isolate a run. Reusing a tag intentionally replaces that run's artifacts.

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
