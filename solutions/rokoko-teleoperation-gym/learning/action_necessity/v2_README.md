# Rokoko v2 — nonlinear fitted-policy recovery, frozen qualification protocol

Work ID `J26-ROKOKO-POLICY-V2-20261114`; parent Rokoko [PR #153](https://github.com/SalesSquad/junction-pets/pull/153)
SHA `312130c9f0b63b9623e4cc9401ace74539296733`.

## Honest negative control (why this experiment exists)

The v1 PR #153 fitted softmax had development gain +18.5pp but **failed** its
pre-registered +15pp threshold on the first actual locked CRACI test:
181/300 vs unchanged shielded constant154/300, +9.0pp paired95% [2.0,16.333].
Its OOD result was 89/200 vs41/200, +24pp paired95% [16.5,31.5], synthetic
unsafe26 vs51. Do not tune or report a v2 score on already exposed v1 locked
test320000..320299 or OOD420000..420199. Source-bound CRACI run is
[43625995894](https://github.com/SalesSquad/junction-pets/actions/runs/43625995894).

## v2 model (code is pure Python standard library)

The new model trains **11 randomized nonlinear classification trees** on
450 RuleTeacher demonstration worlds plus one on-policy **DAgger** pass on
150 disjoint worlds. Both labeled datasets use **only observations and
training-world actions**; the physical simulator's hidden true friction,
future obstacle state and shield geometry are not model inputs. The teacher is
never called during inference. This is genuinely *fitted supervised imitation*,
**not** a Double-DQN, RL, diffusion, MuJoCo, NVIDIA GPU or hardware claim.

Fixed producer hyperparameters are in `v2_policy.py` and score reservations
in `v2_run.py`. The unchanged underlying `Arena` and `make_world` physics,
geometry, local safety shield and constant FORWARD policy come from PR #153.

| Slice | Generator and immutable seeds | Usage |
|---|---|---|
| Teacher train | dev `123000..123449` | Fit only |
| DAgger train | dev `123450..123599` | Fit only |
| Development | dev `124000..124199` | Tuning allowed before freeze |
| Calibration | cal `221000..221199` | Tuning allowed before freeze |
| **v2 locked test** | **test `326000..326299`** | **Once after code freeze via independent CRACI** |
| **v2 locked OOD** | **ood `426000..426199`** | **Once after code freeze via independent CRACI** |

Other agent experiments reserve test325000/OOD425000; v1 exposed test320000/
OOD420000. The v2 windows above must not be opened locally before frozen
CRACI. No source edits/threshold changes after seeing sealed results.

Reproducible local *calibration only*:

```bash
cd solutions/rokoko-teleoperation-gym/learning/action_necessity
python3 -m unittest -q v2_test.py
python3 v2_run.py --split cal --episodes 200 --output /tmp/rokoko-v2-cal.json
```

## Pre-lock observations (local standard-library executor)

The first fixed-parameter v2 calibration ran on 14 Nov 2026 before any v2
test/OOD exposure. It fitted **18,107 teacher demonstration states** (450
training worlds) plus **6,197 DAgger-labeled student states** (150 disjoint
training worlds). Model SHA256:
`1bab986c10be062cf87a4848916917cbab3a78b53e78cda8c2f8673f62d4cc55`.

| Evaluation worlds | Fitted v2 | Shielded constant | Teacher | Paired v2 gain | Unsafe v2 / constant |
|---|---:|---:|---:|---:|---:|
| Cal `221000..221199` | 154/200 | 100/200 | 176/200 | +27.0pp, 95% [18.5,35.5] | 1 / 24 |
| Dev `124000..124199` | 167/200 | 102/200 | 168/200 | +32.5pp, 95% [25.0,40.0] | 2 / 21 |

Five targeted tests passed. Both pre-lock results meet the stated **toy**
criterion, but neither is an independent sealed score or a physical result.
The model, split ranges and parameters are now frozen for the next independent
CRACI evaluation; no v2 test/OOD worlds have been read locally.

Once head is frozen, the integrator independently dispatches the full lockbox:

```bash
python3 v2_run.py --split locked_test --episodes 300 --output /tmp/rokoko-v2-locked-test.json
python3 v2_run.py --split locked_ood --episodes 200 --output /tmp/rokoko-v2-locked-ood.json
```

The CLI refuses duplicate outputs, records producing source SHA256, exact
trained model SHA256, train/DAgger counts, per-world paired outcomes,
counterexamples, unsafe and refused motions and world-paired bootstrap CI.
Test acceptance stays **+15pp fitted vs constant, 95% lower >0, unsafe no
worse**. This is explicitly a *synthetic action-necessity* diagnostic;
separate calibrated MuJoCo/robot/sponsor data gates remain unqualified.
