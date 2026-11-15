# M5 — Inference must pay rent

Work `J26-PF-ARDUINO-M5-INFERENCE-AUCTION-20261114`, Arduino M356/T45.
**SYNTHETIC / OFFBOARD. No UNO Q execution, real camera, physical actuation,
measured savings, calibrated model, or EdgeAI qualification.** This is a
from-scratch PyTorch occupancy experiment and paired policy falsification tool.
The existing [CONCEPT.md](CONCEPT.md), M3 and M4 remain unchanged.

## Reproduce

Run from the repository root, using Node 22+ and Python 3.12 with **already
installed** NumPy and PyTorch. No other Python packages, pretrained weights,
downloads, credentials, GPU provisioning or provider APIs are used by these
scripts. The coordinator selects the existing authorized Verda venv and GPU;
the scripts never start/stop infrastructure or spend credit themselves.

```sh
node --test solutions/arduino-green-edge/active/tests/test_export.mjs
node solutions/arduino-green-edge/active/export.mjs --days=4 --seed=1729 --out=solutions/arduino-green-edge/active/runs/data
python3.12 solutions/arduino-green-edge/active/train_gpu.py --data solutions/arduino-green-edge/active/runs/data --out solutions/arduino-green-edge/active/runs/model --device cuda --epochs 30 --batch 2048 --seed 42
python3.12 solutions/arduino-green-edge/active/eval_policy.py --data solutions/arduino-green-edge/active/runs/data --model solutions/arduino-green-edge/active/runs/model --out solutions/arduino-green-edge/active/runs/evaluation.json
```

Optional model-free shield/accounting smoke (NumPy only; fixed zero
probabilities are explicitly substituted, never a trained-model result):

```sh
python3.12 solutions/arduino-green-edge/active/tests/smoke_policy.py solutions/arduino-green-edge/active/runs/data
```

An optional **CPU training smoke only**, using the same generated four-day-per-cell
minimum data, is:

```sh
python3.12 solutions/arduino-green-edge/active/train_gpu.py --data solutions/arduino-green-edge/active/runs/data --out solutions/arduino-green-edge/active/runs/cpu-smoke --device cpu --epochs 2 --batch 8192 --seed 42
python3.12 solutions/arduino-green-edge/active/eval_policy.py --data solutions/arduino-green-edge/active/runs/data --model solutions/arduino-green-edge/active/runs/cpu-smoke --out solutions/arduino-green-edge/active/runs/cpu-smoke/evaluation.json
```

`--device cuda` refuses when CUDA is unavailable, with no CPU fallback. Metadata
records actual CUDA name, Torch/Python versions, deterministic seed, Adam/loss,
executed epochs, selected validation epoch, parameter count, dataset/source and
weight SHA-256. Deterministic algorithms are required; identical results across
different Torch/CUDA/hardware versions are not promised. CPU smoke is not GPU
evidence or a meaningful training qualification. Outputs are ignored working
artifacts; coordinator must preserve useful GPU results in the authorized
owner destination. No iCloud persistence is established by local output.

## Dataset and provenance

M4 parent/source pin: `eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4`.
M3 historical implementation: `7aee5bd372fa32fa92306f0db9fab39bd2ca1567`.
Exporter compares actual `sim/engine.mjs` and `core.mjs` bytes against the parent
Git objects before generation; manifest records their SHA-256 plus exporter
hash. Preserve this Git history on the executor. Training verifies source,
exporter and CSV hashes, exact day plan, complete minute rows and disjoint
seeds. Evaluation repeats provenance checks and loads weights with
`weights_only=True`. This is reproducible local provenance, not a signed or
independently authenticated execution receipt.

`--days` is an integer **4..48 per scenario per partition**, not total days.
`--seed` is integer 0..4294966295; sequential unique uint32 seeds never wrap.
There are three normal seasons (winter/summer/evening) each in train,
validation and **separate calibration**, and all four including fault in test.
At the minimum: 52 distinct days; 17,280 rows each in train/validation/calibration
and 23,040 in test. At maximum: 624 days, 898,560 total rows. Each original M3
8,640-slot day contributes exactly 1,440 minute rows. Fault never trains or
calibrates. Test seeds are never used for epoch selection or thresholds.

Exact CSV columns:

```text
day_id,partition,scenario,seed,second,time_sin,time_cos,temperature_c,rh_percent,connected,age_seconds,target_occupied
```

Only `time_sin,time_cos,temperature_c,rh_percent,connected,age_seconds` enter
the MLP. Day ID, partition, season, seed, raw second and target are excluded.
Clock phase uses a 24h period; age is observation clock minus M3 sample time.
These are plausible future clock + Thermo/transport inputs; this is not an
implemented hardware adapter. No lux, occupancy proxy, camera reading, truth,
future sample or lag crossing days enters inference. Float32 normalization
uses training means/stds only (constant-feature std becomes 1). No 8-bit
quantization or deployable firmware is claimed.

Binary synthetic true occupancy is a **training target and offline score**.
The 6→16→8→1 ReLU MLP is initialized randomly; Adam minimizes binary
cross-entropy. Validation loss chooses the epoch (patience 5); epochs 1..50,
batch 64..8192. Separate calibration selects the largest low-probability gate
from 0.01/0.025/0.05/0.1 with at least one empty prediction and zero occupied
calibration errors; otherwise the gate is zero. That empirical rule is not a
risk bound or safety certificate. Untouched test reports per-scenario balanced
accuracy, precision, recall, FNR and confusion counts at fixed 0.5, including
fault. Metrics are descriptive correlated-row metrics, not independent trials.
Different seeds still share authored seasonal templates; disjoint seeds do not
establish independent real-room coverage.

## Paired comparative evaluator

Evaluation privately regenerates the exact M3 heldout days via
`node active/export.mjs --evaluation=.../manifest.json`. This internal stream
contains truth for scoring and noisy proxy occupancy for query calls; **do not
use it as a training CSV**. Each day is paired across all five strategies and
four predeclared variants: nominal, +2h arrival/+2°C sensor-bias drift, sustained
10:00–16:00 correlated false-empty camera, and untrusted camera. Nominal M3
fault already includes false-empty 10:00–10:30, disconnect 11:00–12:00 and
40-second stale observations 14:00–14:30. Every variant and failed day stays
in the JSON; no best-seed selection.

| Strategy | Camera / AI behavior |
| --- | --- |
| A timer only | Unchanged M3 seasonal schedule; no camera, AI or incremental board charge |
| B always camera | 24h camera assumed ≥1W, reading each minute; no MLP |
| C fixed poll | One query every 10 minutes, including outside scheduled hours; no AI |
| D selective model | Current cheap features → probability; ask only when fan could be reduced, camera age >30s/invalid, and expected one-minute load value exceeds query cost |
| E hold + fixed poll | Fixed polling, requiring two successive valid zero observations; no AI; frames are **not** assumed independent |

D asks when occupancy probability is low or in [0.2,0.8] uncertainty, but
uncertain predictions **cannot permit OFF**. Its authored VOI proxy is
`(1-p) × 40W × 60s / 3600`, compared to assumed per-query Wh, not measured
utility or causal comfort value. Current/out-of-range cheap observations latch
fallback for the rest of that day; no future samples or whole-day labels enter
the policy. Offline acceptance separately rejects all known shifted/fault
regimes and any day outside training feature ranges; marginal range checks
cannot discover arbitrary hidden drift or camera corruption.

Camera occupancy is read **only inside `camera_call` when queried**, from the
original noisy M3 sample (never truth). Injected camera errors are correlated
across time. An untrusted/invalid reading cannot permit OFF. Every strategy
retains scheduled lights without a lux sensor. Fan OFF requires a valid fresh
zero camera (≤30s), connected/fresh Thermo, T<26°C and RH<68%; D additionally
requires calibrated low model probability and no observed cheap-input drift.
C/B use an explicitly declared no-AI fresh-camera ablation rule; E adds
corroboration, which does not establish independence. All uncertain/stale or
disconnected states retain the baseline schedule. The shield does not prove
that every plausible false-empty can be detected.

MLP proposals and camera queries occur every 60s. The deterministic hard shield
rechecks current cheap sensors and camera expiry at each **original 10s
interval**, so a fresh OFF permission reverts to schedule when its camera
exceeds 30s or sensors become hot/humid/disconnected. The model never receives
those intermediate samples as inference inputs. All six intervals are scored.
This is an offboard supervisory experiment, **not M1 `evaluate`**: its 60s
cadence cannot satisfy M1's 15s watchdog or claim M1 debounce. HOLD means no
physical command; schedule fallback is only hypothetical accounting. True
occupied demand is scored using M3 semantics: fan required if occupied and
T≥27°C or RH≥70%. Each day reports total misses, baseline misses and **extra
missed fan seconds specifically while the schedule supplied service**.
Improvements elsewhere cannot cancel an extra missed interval. A fan changes
no room conditions in this model; no HVAC/cooling/humidity effect is inferred.

Accounting is Wh: assumed load 40W fan + 20W light, each original slot
`W × 10/3600`. Gross = baseline load − policy load; net = gross − board −
camera − cheap inference. B–E each pay constant assumed 4W×24h = **96Wh/day**;
A needs no incremental board. B also pays ≥1W×24h = 24Wh/day camera standby.
All queries additionally cost assumed **0.01Wh/query** (incremental acquisition/
processing, separate from B's standby); D pays assumed 0.000001Wh per cheap
inference. These are hypotheses, **not UNO Q or camera measurements**. Cost
flags must stay finite within 0..30, with board≥4W, continuous camera≥1W and
positive per-query energy; no physical power calibration is implied.

Every day rejects a candidate for net≤0, any extra missed required fan service,
or outside verified synthetic support. Mean and worst-day net, mean queries
and worst extra misses are reported across the complete cohort. Overall D
also must beat both C and E in mean net and queries with no worse extra service
on any paired day. Otherwise stdout and JSON say **NO_GO**. Because stress
regimes are deliberately unverified, this full qualification campaign is
expected to veto; do not relabel a nominal result as deployment approval.

## Validation and limits

The source worker actually ran six focused Node exporter checks, model-free
320-record shield accounting and Python syntax checks. The coordinator then
executed the actual training and evaluation on an existing authenticated Verda
Tesla V100, using the exact pinned M3/M4 sources without loosening validators.
Thirty real CUDA epochs trained the from-scratch six-feature model. Synthetic
test false-negative rates: winter 2.92%, summer 50.54%, evening 26.96% and
fault 58.81%. The complete 320-paired-result stress evaluation returned NO_GO.
At the assumed 4W board load, selective inference reduced camera queries to
10.9/day but still yielded -96.11 Wh/day versus a zero-incremental-board timer.
Model artifacts and exact SHA-256/experiment conditions are retained in
evidence/VERDA_RECEIPT.md; see the source-bound metadata and JSON evidence.
This is GPU execution evidence ONLY, not measured device energy, physical
Arduino inference or a field safety qualification.

The evaluator can also read a SHA-256-checked, full M3 source-bound compressed
offline JSONL packet stream with --packets-gzip and --packets-sha256 when an
authorized GPU executor lacks Node; this is an alternative transport, not a
permission to skip manifest/source or packet completeness checks. It rejects
unexpected, missing, duplicate or reordered day/10-second samples. The
off-board policy has no lookahead: scenario/shift labels only affect retrospective
acceptance, not real-time decisions. The run used this checked pathway.

The more promising post-review route is a human-in-the-loop Open-Window Heat
Sentinel. Its separately runnable SYNTHETIC/OFFBOARD 90-second kernel lives
under active/window/; it is not a real on-board image classifier, sensor
integration, MCU driver or measured environmental result.

The owner authorized up to USD20 incremental Verda compute, USD20 Opus
and USD5 Haiku. Actual itemized provider billing remains unknown; the V100
machine was already running and was not terminated or repurposed for others.
The independent Opus/Haiku code challenges returned model-specific
list-price estimates only, not confirmed Anthropic API invoices. See the
task-owned evidence record for exact measured runs, limitations and balances.
No new paid instance, secret transfer, root manifest or CI edits, deployment,
physical output or external submission was created.
