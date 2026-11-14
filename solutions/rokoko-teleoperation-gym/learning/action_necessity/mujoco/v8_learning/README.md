# V8 — train-only hierarchical shield-masked imitation learner

This is **real gradient-trained model code**, not a claim of a model that beats
V5/V6. It is staged separately from the original contact physics, safety
mask, seven-action ABI, fixed V7 policies, and immutable V7 train receipt.

## Why

Verified CRACI V7 real MuJoCo 3.3.7 completed 1,280 paired episodes and
68,568 option transitions on 128 observed near and 32 clear **TRAIN** worlds.
The two near-world safe wins came only from the old V5/V6 policies. The
`repeat_left` macro obtained at least 25 mm **safe lateral progress in 74/128
near worlds**, but no new goal wins; rightward macros had safety failures.
Positive traces were independently replayed, including every initial world
selection. Real training therefore needs the safe lateral *subskill* and the
scarce V5/V6 successful *goal* suffix—not more threshold tuning.

The first V7 run `43639519781` lost the raw evidence at artifact collection.
The separately corrected run `43640728389` succeeded and retained exact raw
bytes, with source SHA `127ceb9be4374ba46908cd398ced6b740275a434` and
training-trials digest `d1ad3e8de866e38a15e86d76f16205d7ff1830289de151af78014edb03c36320`.
These are source-bound source-reported CI records, not robot-device certificates.

## Frozen input contract

Take the **retained** CRACI archive from run `43640728389`. Its
`artifacts/rokoko-mujoco-v7-feasibility/` folder contains source-pinned
`manifest.json`, `independent-qualification.json`,
`independent-positive-replay.json`, and split ZIPs. Reconstruct exact raw data
with the separately reviewed harness utility:

```sh
python3 scripts/craci/rokoko-mujoco-v7-retain-evidence.py \
  --mode restore \
  --evidence-root /approved/private/unpacked/artifacts/rokoko-mujoco-v7-feasibility \
  --restore-output /approved/private/restored-v7
```

Place byte-identical copies of the 3 small independent qualification files in
the **private** restored folder. `run.py` refuses to train if any expected
original SHA, exact source, physics version, all 1,280 trial identities,
sample-pairing, independent replay, train-only flag, or full raw trace digest
is missing or contradictory. The verifier does not authorize deployment.

## Training recipe

Pin a clean Git checkout of this V8 task branch and run:

```sh
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v8_learning/run.py \
  --mode offline-train --require-git \
  --expected-head <exact-reviewed-v8-full-commit-sha> \
  --v7-evidence /approved/private/restored-v7 \
  --output-dir /approved/private/new-empty-v8-output
```

Requires NumPy (tested with 2.3.x). No GPU/API key/internet, simulator
installation or fresh world sampling is required for the **offline** fit.
Runs should occur in a verified executor. Outputs, created exclusively in a
new directory, are:

- `weights.json`: learned **four separate masked linear-softmax heads**;
  immutable source, full training data SHA and weight digest.
- `training-receipt.json`: actual raw option count, safe episode teachers,
  gradient epochs, train-only diagnostic losses, and limitations.

Inputs to the policy are strictly the **public 18D observation, current
seven-option safety mask, and its own action history**. No world seed, true
contact impulse, hidden mover dynamics or simulator state enters inference.
The underlying `MovingContactEnv.mask` enforces safety; the learned policy
filters forbidden actions again before every option. Zero unsafe output from
the training set is **not** a general safety certificate.

Training selects full near-world goal witnesses from frozen V5/V6 and
`repeat_left` episodes that safely achieved ≥25 mm obstacle-away movement.
All unsafe/abstained/rightward failed episodes are excluded as positive
imitation teachers (but still checked for raw integrity). Gradient training
uses 55 epochs, 0.055 step, 0.003 L2, deterministic NumPy seed 20261114.
The train diagnostic reserves 20% of safe-lateral worlds by world seed,
but **never** removes the two scarce successful goal witnesses from fitting.
This is not an independent heldout; goal-stage diagnostic can be absent.

## Advancement gate

No automatic CRACI dispatch, model promotion, test opening, main push or
robot actuation is included. The next scientifically meaningful step is a
separate source-reviewed, budget-bounded **TRAIN-only** MuJoCo v8 exploration
on fresh seeds starting `513000`, paired against frozen V5, V6 and the
`repeat_left` mechanism. If it learns a promising safe success sequence,
freeze weights *before* a new prospective development run on unopened
`129330..129409` with strict zero new unsafe, no lost-baseline-success and
positive novel safe wins. Scientific failure is retained, not retrained away.

This deliberately reuses the existing experiment registry's
`failure → case → review → plan-next → run` chain; this product code does not
start another registry service or duplicate the operational CRACI receipt.
