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
