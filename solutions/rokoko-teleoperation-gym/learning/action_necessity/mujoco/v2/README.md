# MuJoCo adaptive-v2: recover from negative real-physics evidence

Work ID `J26-ROKOKO-MUJOCO-PHYSICS-V2-20261114`. Stacked on immutable
**MuJoCo v1 PR #162** at `cd7b2446c5f8d0e96761524f8a26a20ac4cbf44d`.
Only new `mujoco/v2/` files; no modifications to the published v1 experiment.

## Why change? Actual CRACI evidence, not a design assumption

Preserved negative baseline: [CRACI #43627944236](https://github.com/SalesSquad/junction-pets/actions/runs/43627944236),
artifact `craci-rokoko-mujoco-dev-rokoko-mujoco-dev-43627944236-1`,
`artifacts/rokoko-mujoco/dev-physics.json`, source v1 SHA pinned above.

Real MuJoCo 3.3.7 on 8 dedicated **dev** worlds `129000..129007`:

| Controller | Goal success | Unsafe | Physical integration |
|---|---:|---:|---:|
| Constant `PUSH_MEDIUM` | 5/8 | 0 | 38,090 `mj_step` |
| Original multiaction teacher | 0/8 | 0 | 48,000 `mj_step` |

Original teacher's paired improvement: **negative 62.5 percentage points**;
bootstrap95% descriptive interval `[-87.5,-25]`. On five worlds where
constant succeeded (129000, 129001, 129002, 129005, 129007), teacher spent
all 60 options repeating ALIGN/PUSH_SLOW and accumulated thousands of contacts,
but still missed goal. Constant arrived in 37–46 options. Three common-failure
worlds had 52–56 medium shield refusals, suggesting masked-forward behavior
is worth improving. This diagnosis is *dev-only* and not a holdout result.

## Fixed intervention, before any further evaluation

The adaptive controller receives only the same 18-float noisy sensor vector
and 7-option shared shield mask as the baseline. It never accesses true mover
frequency, contact hidden state, world parameters, MuJoCo itself, or training.

1. Choose `PUSH_MEDIUM` whenever the shield allows. Do not waste the successful
   medium contact path on repeated alignment, slow push or retreat. Near-goal
   contact must continue until the original 250-physics-tick dwell criterion.
2. If medium is vetoed but slow push is allowed (e.g. pusher proximity), choose
   `PUSH_SLOW` to avoid unnecessary shield refusals.
3. Only when *both* forward options are masked, try the already-available
   oblique lateral approach opposite the noisy mapped obstacle. Reconsider
   side after ten low-progress options; honor stale/deadman hold first.
4. Same-physics, same-world counterfactuals: unchanged constant `PUSH_MEDIUM`
   and the original negative teacher, each reset to an identical latent world.

No change to collision thresholds, success dwell, hazard definition, existing
trained weights or MuJoCo physical scene. This is a new *hypothesis*, **not a
proven algorithmic gain**.

## Run bounded CPU development and calibration

Use full-history checkout of the exact v2 draft PR head, Python 3.11+, NumPy
and `mujoco==3.3.7`:

```bash
python -m pip install 'numpy>=1.26,<3' 'mujoco==3.3.7'
python -m unittest discover -v \
  -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v2 \
  -p test_contract.py
python solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v2/run.py \
  --split dev --episodes 8 --max-options 60 --require-git \
  --expected-head EXACT_V2_HEAD_SHA \
  --output /tmp/rokoko-mujoco-v2-dev-unique.json
```

`--output` uses exclusive-create and **never overwrites an earlier receipt**.
The runner reports proposed action histogram, masked proposals, no-contact
stalls, per-option contacts/progress, final dwell, physical `mj_step` counts,
paired bootstrap95, per-world latent identity hash, and SHA256 for both
versions' source files. It writes the negative result *before* returning exit
code **2** when scientific qualification fails. Preserve that receipt even on
failure; an infrastructure success is not evidence of goal improvement.

Falsifiable qualification requires **positive paired goal gain, no unsafe
regression and strictly positive paired 95% bootstrap lower bound** on the
chosen sample. Calibration `229000..229999` stays development-only and must
not silently move the criterion.

Locked `test` `329000..329199` and `ood` `429000..429199` are deliberately
untouched. To evaluate them *once after exact source freeze*, this v2 CLI
requires all of `--permit-holdout --require-git --expected-head EXACT_SHA`.
Absent source history or MuJoCo physical API always fails closed. A positive
synthetic score is not physical robot safety or a causal deployment claim.
