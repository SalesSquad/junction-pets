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

## Source-verified V8 offline checkpoint (training already completed)

The exact reviewed, **TRAIN-only** Mac Mini offline fit completed on Git HEAD
`4b91c64bc1a79bf630b1da6d12bea28e87c2990a`, using all retained V7 raw
traces. The frozen model and original untouched receipt are preserved byte for
byte under [`checkpoints/`](checkpoints/):

| Checkpoint | Immutable SHA-256 |
| --- | --- |
| `weights.json` original file | `07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1` |
| `training-receipt.json` original file | `dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73` |
| Frozen model canonical JSON | `9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea` |

The independent code audit of this trainer had no remaining P0/P1 after
evidence-pin hardening and 8/8 contract tests. The actual source-verified
offline fit used 4,339 safe teacher actions; all four stages lowered their
**fit** cross-entropy. This is not evidence of novel safe near-world goals.
The historical HEAD in these immutable files is intentionally not rewritten
when the later prospective rollout runner is committed. It must remain an
ancestor of the experiment source, with `v8_learning/run.py` unchanged.

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

Place byte-identical copies of the 3 small independent qualification files,
the original CRACI `receipt.json`, and the **outer downloaded GitHub artifact**
as `artifact.zip` in the **private** restored folder. `run.py` requires all
seven files (including the 11 MB outer artifact). It checks **independently
pinned** corrected-run SHA-256 hashes, rather than trusting the input manifest:

| Immutable input | Exact SHA-256 |
| --- | --- |
| `training.json` | `06ffeb5f4d5a639eba15f0bd2c260b6d0c046ea13665a8f5e884848bb1a236d8` |
| `full_transitions.jsonl.gz` | `3888fd350c66f3a1ca6a2bebb7731097c86181b5644d921b0bb580855bae4d64` |
| `receipt.json` | `546249d8ccc2929a58429c0c767e58b92eb9deaabb2d3f39c36761b4e27ae9a6` |
| `artifact.zip` | `612a7770ded0466e00ec45e1b0073cb03a0cf4758d0e17d354f32e0639749e3c` |

It also pins manifest and independent qualification/replay SHA bytes and the
CRACI `craci.43640728389.1.ebec06d6f3461523` success receipt. It aborts if
the original V7 source and fixed harness HEAD, physics version, any of 1,280
trial identities, sample pairing, independent replay, train-only flag, or
full raw trace digest is missing or contradictory. The verifier does not
authorize deployment.

## Training recipe

Pin an entirely clean Git checkout of this V8 task branch (including no
untracked files) and run:

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
robot actuation is included. The next step is a separately reviewed and
budget-bounded prospective **TRAIN-only** MuJoCo v8 experiment on fresh
`513000..513511` candidates, comparing the immutable V8 weights against
original frozen V5, V6 and `repeat_left` in exactly paired worlds.

The source-bound command (run only after integrator independently approves
the final experiment HEAD and immutable model hashes) is:

```sh
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v8_learning/rollout_train.py \
  --mode prospective-train --require-git \
  --expected-head <full-reviewed-v8-experiment-HEAD> \
  --reviewed-weights-sha256 9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea \
  --frozen-weights /approved/private/model/weights.json \
  --frozen-training-receipt /approved/private/model/training-receipt.json \
  --output-dir /approved/private/new-empty-v8-prospective \
  --time-budget-seconds 1200
```

Copy the two exact `checkpoints/` files into the private model directory before
running; the rollout refuses checkout-local artifact inputs/outputs. Both
file hashes, the model canonical SHA, historical trainer source and full
unaltered original receipt are checked **before** importing MuJoCo or stepping
any environment. The prospective runner additionally verifies the new clean
HEAD descends from the historical trainer and the trainer's code bytes stayed
unchanged. Requires exact MuJoCo **3.3.7** and the original V7 physics and
seven-action mask, not an emulator. No new model fitting occurs in this step.

The selection is pre-registered and cannot be changed through CLI flags:

- Ascending candidate seeds `513000..513511` (**TRAIN only**, `ood=False`).
- First 128 near and 32 clear worlds solely from **initial public** observed
  obstacle y (`abs(y) < .122`); no outcome-based selection.
- Every chosen world executes **all four policies** on its identical hidden
  world hash, yielding exactly 640 real MuJoCo episodes.
- Reports signed obstacle-away movement >=25 mm, first contacts, stage-order
  milestones, forward reopening, final goal+dwell, unsafe/abstention,
  lost old safe goals, and novel V8 safe near goals, per paired world.

Output: `full_transitions.jsonl.gz` with full original per-option records,
`training.json` with every trial and dataset SHA, `paired-readout.json`
including per-strategy counts and lost/novel/unsafe paired seeds, and
`manifest.json` pinning their byte hashes. The two JSON summary files have
explicit <19 MiB guards; the CRACI-specific artifact collector must retain
the complete gzipped raw traces using independently verified bounded ZIP
parts if needed, without weakening its 20 MiB/file capture cap. This code
does not assert independent physics replay or operational qualification;
that is a separate evidence review after a real CRACI result.

Only if fresh TRAIN worlds show genuinely promising safe completion should
an independent reviewer preregister a future development-world comparison
on still-unopened `129330..129409`. No success-loss or safety failures may
be hidden by retraining, seed changes or selective reporting. Scientific
failure is retained, not retrained away.

This deliberately reuses the existing experiment registry's
`failure → case → review → plan-next → run` chain; this product code does not
start another registry service or duplicate the operational CRACI receipt.
