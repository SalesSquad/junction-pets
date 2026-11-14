# Early-warning forecaster: specification

Purpose: give every wellbeing services county a calibrated one- and two-year-ahead
forecast for the public indicators that sit on the cancer pathway, so that an
emerging delay or a falling screening rate is flagged before it shows in outcomes.
Real open data only. The model must beat simple baselines on a held-out backtest,
or the product ships the baseline instead and says so.

## Data (ml/fetch_panel.py, stdlib only)

THL Sotkanet REST API, base `https://sotkanet.fi/rest/1.1`, header `User-Agent: care-equity-navigator/1.0`.
- `GET /regions` -> units with `category` in `KUNTA` (municipality), `HYVINVOINTIALUE`
  (wellbeing services county; code `01`..`21`, `90`, `91`; our id is `HVA<code>`), `MAA` (country).
- `GET /json?indicator=<id>&years=<y>&years=<y>...&genders=total` -> rows
  `{indicator, region, year, gender, value, absValue}`.
- Years 2000..2025. One request per indicator. Retry with backoff. Record url + sha256 per response.

Target indicators (forecast these):
| id | key | direction | threshold |
| --- | --- | --- | --- |
| 3621 | screen_breast | higher better | 80 |
| 3620 | screen_cervix | higher better | 80 |
| 6103 | screen_colorectal | higher better | 80 |
| 6411 | gp_wait_over_7d | lower better | none |
| 6410 | gp_wait_over_3m | lower better | none |
| 3336 | specialist_wait_over_6m | lower better | none |
| 13 | referral_handled_3d | higher better | none |
| 5033 | referral_handled_over_21d | lower better | none |

Covariates (inputs only): 127, 1068, 180, 181, 3099, 3126, 5102, 5641, 5643, 5659, 326, 3562, 237, 2475, 3054, 3051, 3055, 189, 228.
Keep whatever of these the API returns; skip ids that fail, and list them in the output.

Write `ml/data/panel.json`:
`{units:[{id, category, name}], indicators:[{id,key,isTarget}], years:[...], values:{<indicatorId>:{<unitId>:{<year>:value}}}, manifest:[{url,sha256,bytes,retrievedAt}]}`.
Unit ids: `HVA<code>` for counties, `KU<code>` for municipalities, `FI` for the country.

## Model (ml/train_forecaster.py, PyTorch)

- One sample = one unit and one forecast origin year `t`. Input: the unit's last `L=8` years
  up to and including `t`, for all indicators: z-scored value (per indicator, statistics from
  training origins only), a missing mask, plus unit-category embedding and year index.
- Target: each target indicator at `t+1` and `t+2` (masked when unobserved).
- Network: small transformer encoder over the 8 time steps (d_model 128, 3 layers, 4 heads,
  dropout 0.1), mean-pooled, linear head -> `n_targets x 2 horizons x 5 quantiles`
  (0.05, 0.25, 0.5, 0.75, 0.95). Predict the CHANGE from the last observed value (in z units)
  so that persistence is the zero function. Loss: pinball loss over observed targets only.
- Training augmentation: randomly mask 15% of observed inputs. AdamW, cosine schedule, early
  stopping on validation pinball loss. Train 5 seeds and average quantiles (deep ensemble).
- Flags: `--device cuda|cpu`, `--epochs`, `--seeds`, `--smoke` (1 seed, 2 epochs, small batch).
- Deterministic seeding. No leakage: an input window may never contain a year > t.

## Backtest (ml/evaluate.py)

Rolling origin, split by origin year so that no test target year is ever seen in training:
train origins <= 2020, validation origin 2021, test origins 2022 and 2023 (targets 2023..2025).
Baselines on exactly the same test cells: (a) persistence, (b) drift = last value + mean of the
last 3 yearly changes, (c) unit-pooled ridge regression on the last 3 values.
Baseline intervals: empirical quantiles of that baseline's validation errors per indicator and horizon.
Report per indicator and horizon, for county-level cells and separately for municipality cells:
MAE of the median, mean pinball loss, empirical coverage of the 90% and 50% intervals, n.
Then apply split-conformal widening on validation residuals so that the nominal 90% interval
has >= 90% validation coverage, and report test coverage after it.
Selection rule (honesty): for each target indicator choose the method with the lowest
validation MAE; the product uses that method. Write `ml/artifacts/metrics.json`.

## Product output (ml/export_forecasts.py)

Refit the chosen method on all origins and write `data/ml/forecast-v1.json`:
```
{ "schemaVersion":"care-equity-forecast-v1", "generatedAt":..., "trainedOn":{"device":..., "seeds":..., "epochs":...},
  "skippedIndicators":[...],
  "metrics": { <key>: { "chosen":"transformer|persistence|drift|ridge", "h1":{ "<method>":{"mae":..,"pinball":..,"cov90":..,"cov50":..,"n":..}, ...}, "h2":{...} } },
  "forecasts": { <key>: { "HVA01": { "lastYear":2024, "lastValue":..,
        "h1":{"year":2025,"q05":..,"q25":..,"q50":..,"q75":..,"q95":..},
        "h2":{"year":2026, ...},
        "pBelowThreshold": {"h1":..,"h2":..} | null,      // screening indicators: P(value < 80), from the quantile curve
        "pWorse": {"h1":..,"h2":..} } } } }               // P(indicator moves in the bad direction vs lastValue)
```
Probabilities come from linear interpolation of the predictive quantile function, clipped to [0.02, 0.98].

## Tests (ml/tests, `python -m unittest`)

- windowing never leaks: for a synthetic panel where value == year, no input contains a value > origin year;
- pinball loss equals a hand-computed value; quantile outputs are monotone after sorting;
- baselines reproduce hand-computed forecasts on a 3-unit toy panel;
- probability interpolation returns 0.5 at the median and is monotone in the threshold;
- `--smoke` end-to-end run on a tiny synthetic panel finishes and writes a schema-valid forecast file.

## Deliverables

`ml/fetch_panel.py`, `ml/train_forecaster.py`, `ml/evaluate.py`, `ml/export_forecasts.py`, `ml/common.py`,
`ml/tests/`, `ml/requirements.txt` (torch, numpy only), `ml/run_all.sh` (fetch -> train -> evaluate -> export,
passes through `--device`), `ml/README.md` (what is trained, on what, how it is validated, limits).
Do not touch anything outside `ml/` and `data/ml/`.
