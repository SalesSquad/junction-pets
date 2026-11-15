# V10 hybrid real MuJoCo prospective runner — separate unexecuted source

**State:** code and portable validations only. No fresh 516000+ physics episode
has been run by this change. This file is stacked *after* independently
reviewed hybrid source draft PR #209; it does not change that frozen policy.

`prospective_train.py` delegates actual physics/option stepping to the
unaltered original V8 `rollout_train.py:run_real_episode` and imports the real
original MuJoCo 3.3.7 `MovingContactEnv`, v7 contact/terminal verifiers, frozen
V5 policy and SHA-pinned V8 hierarchical policy. It refuses incorrect Git
HEAD, trainer/physics lineage, foreign generic `run` cache, mismatched frozen
model/receipt, private artifact paths inside checkout, unavailable real
MuJoCo, incomplete world cohort, malformed original observation and timeouts.

## Frozen prospective plan

| Dimension | Contract |
| --- | --- |
| Result schema | `junction.rokoko.mujoco-v10-hybrid-prospective.v1` |
| Evidence packer plan schema | `junction.rokoko.mujoco-v10-hybrid-evidence-parts.v1` |
| Seed range allowed | `516000` through `516511` TRAIN only |
| Selected paired worlds | `128` near + `32` clear; ascending selection solely on original public first-observation obstacle Y |
| Four arms on each *identical* world | `frozen_v5`, `v8_hierarchical`, `near-early-side-mask-rescue`, `rescue_off_v5` |
| Full real trials | 640, 60 original maximum option actions per trial |
| Physics/shield | original unchanged MuJoCo 3.3.7, 18D public obs, seven legal masks |
| Raw physical evidence | `full_transitions.jsonl.gz`: each option, pre-observation/mask, action, reward, cost, contact cumulative, current/cumulative dwell, original success/done, next observation |
| Distinct artifacts | compact lossless `training.json` (≤19 MiB), `paired-readout.json`, `manifest.json`, `evidence-parts-plan.json`, full original raw gzip |
| Placebo negative control | Every `rescue_off_v5` trace **must** SHA-match its separate `frozen_v5` real trace on same seed; otherwise FAIL experiment |
| Scientific readout | real 250-tick dwell goal, unsafe, abstain, timeout, forward reopening; novel/lost/shared hybrid-v5 safe goals and new unsafe seeds |
| Follow-up authority | external CRACI harness shim and evidence ZIP packer are separately controlled by integrator; **this PR does not dispatch or spend** |

Do not silently swap model weights or use 513000/514000/515000 previously
examined training worlds. The 516000+ physics results remain untouched until
the candidate and harness source HEAD are frozen and qualified.

## Host shim invocation (after source review, not yet executed)

The integrator must provide actual new prospective **product head SHA** and
**harness head SHA** and restore exact reviewed frozen V8 files *outside*
checkout. File names below are representative paths, not existing claims.

```bash
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_hybrid/prospective_train.py \
  --mode prospective-train --require-git \
  --expected-head "$PINNED_PRODUCT_HEAD" \
  --expected-harness-head "$PINNED_HARNESS_HEAD" \
  --reviewed-weights-sha256 9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea \
  --frozen-weights /private/source-verified-v8/weights.json \
  --frozen-training-receipt /private/source-verified-v8/training-receipt.json \
  --output-dir /private/new-unique-v10-hybrid-prospective-output \
  --time-budget-seconds 3600
```

The packer should use `evidence-parts-plan.json` exact per-file hashes and
byte lengths to build a separate original, downloadable full ZIP. Never
recreate raw evidence from a summarized result, guess timeouts, or claim the
plan itself is an archive. The independent qualifier must re-hash and fully
replay all raw options and seven-mask legality, independently recompute
goal/unsafe/outcomes, compare all four policies per-world, verify original
product/harness identity from hosted run receipt, and reject partial capture.

**Science gates remain STOP.** Model promotion, release, merge, development,
calibration, test or OOD evaluation cannot follow from this source PR or a
successful host exit alone. If the hybrid loses V5 goals or creates new unsafe
paths, preserve the result as negative learning data instead of changing the
already-frozen candidate in place.
