# Rokoko V11 — source-trained, goal-preserving rescue (prospective draft)

WorkID `CRACI-V11-LEARNING-20261114`. **No new V11 physics has run. No autonomous
CRACI dispatch, new spending, promotion, merge or deployment is authorized by
this code.** Source-only scientific selection and unit checks are not safety or
physical-gain qualification.

## Source: what actually failed

Genuine V10 CRACI run [43649224059](https://github.com/SalesSquad/junction-pets/actions/runs/43649224059), original source SHA
`9cc583d3f0f24484b79c1929ba875c7a3b667806`, executed harness SHA
`a64e6fcc73a1d47485fe052990e31c9d9e45100f`, source-reported receipt
`craci.43649224059.1.49e1693ab133a3e9`. Exact immutable original
`training.json` SHA256 `103091f37e1b7d46937ea002845dda05f08391f4580f0aa7c181722d78b118af`,
full options `full_transitions.jsonl.gz` SHA256
`739c30a13ecacdecd404774fc9dadd887944f32df5cef14cfd2758a639460419`.

Independent V10 proof, original source manifest/retention SHA and 800 complete
real MuJoCo 3.3.7 TRAIN trials with 38,569 genuine original option transitions
are source-verified by `evidence.py`. Frozen V5 safely reached 250-tick goal
dwell on **37/160** worlds (12/128 near,25/32 clear); V10 only **26/160**
(10 near,16 clear), **lost eleven V5 goals and gained zero**, with zero unsafe.
V10's forward reopening is not an acceptable proxy for a physical dwell goal.

## What this loop actually learns

1. `learn_gate.py` derives a public-state rescue predicate from actual original
   V5 masks/actions on 160 genuine paired TRAIN worlds, inspecting 96 finite
   configurations. The fixed 4/5 FIT and 1/5 disjoint TRAIN diagnostic split
   is by seed modulo5, never world outcome.
2. The frozen gate is `blocked_or_abstain_side`, public distance >.035,
   observed obstacle |y| <.1 and >=1 consecutive blocked/abstain option with
   legal lateral. It fired on **zero of 29 FIT and zero of eight held TRAIN
   original V5 successful trajectories**; it found 80 FIT +22 held *failed*
   V5 worlds where independently executed V10 saw a same-world forward reopen.
   Those are **102 navigation opportunities, not 102 improvements or any
   counterfactual action labels**.
3. Source-trained bounded rescue budget = **eight** V10 option choices: actual
   original V10 blocked-side→first legal forward gap <=8 in 79/81 FIT TRAIN
   and22/22 held TRAIN traces with such a gap. Two FIT cases required18; the
   guard knowingly sacrifices those possibilities to limit oversteer. No claim
   that a V10 action from a changed V5 state will succeed.
4. `policy.py` leaves original frozen V5 intact except at an early, public
   legal-mask escape point: at most **one V10 rescue round, <=8 options**, then
   fresh V5 state. It returns to V5 immediately on observed legal forward,
   goal-distance<=.035, or budget. Every option remains behind the original
   seven-action shield; illegal original policy output fails closed.
5. Re-run frozen original evidence only through `train.py` with explicit
   SHA-verified V10 archive. Output checkpoint is immutable SHA-pinned
   `frozen-v10-train-approved/gate.json` SHA256
   `b115fc329b50f2557e8c6074734990dbcf6d1c5046516fbbda6158c5c513eaa8`.

## Next fresh TRAIN physics qualification, not yet dispatched

**Run only after independent source review and separate existing CRACI credit/
workload authorization.** Register a new source-pinned workload in the **existing**
`craci-pilot.yml` workflow. Do not start a second daemon or duplicate CRACI
controller. Original V10 runner blob is pinned
`64dc947d5dbf09e305a6034c4c5d146f14db820b` and immutable ancestor
`9cc583d3f0f24484b79c1929ba875c7a3b667806`.

The next cohort is **all 512 public-initial observations** at seed
`517000..517511`, independently selecting exactly first128 near(|y|<.122)
and32 clear; no successes, reward, hidden state or after-policy observations
enter selection. Run all five frozen arms `V5/V6/V8/V10/V11` on identical
160 worlds = **800 full MuJoCo episodes**, max60 original shielded options and
original physics250-tick dwell. This is a **new distinct TRAIN cohort**:
no V8, V10, V10-hybrid, DEV/CAL/TEST/OOD old/hidden seeds reused.

Expected original harness command after checking out a *reviewed exact new
V11 branch HEAD*, with restored SHA-verified frozen V8 and V10 checkpoint
files **outside source checkout** and a fresh private output directory:

```bash
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v11_learning/prospective_train.py \
  --mode prospective-train --require-git --expected-head "$V11_REVIEWED_HEAD" \
  --v10-weights "$V10_UNPROMOTED_WEIGHTS" \
  --v8-weights "$V8_FROZEN_WEIGHTS" \
  --v8-training-receipt "$V8_FROZEN_RECEIPT" \
  --output-dir "$NEW_PRIVATE_ORIGINALS" --time-budget-seconds 1800
```

After actual run, independently verify complete SHA-pinned originals:

```bash
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v11_learning/qualification_inputs.py \
  --original-dir "$NEW_PRIVATE_ORIGINALS" \
  --expected-head "$V11_REVIEWED_HEAD" \
  --out "$NEW_PRIVATE_QUALIFIER_REPORT"
```

**Required existing CRACI integrator work before hosted admission** (owned by
the sole integrator, deliberately not changed by this stacked PR):

- `.github/workflows/craci-pilot.yml`: register V11 name and exact source,
  separate harness HEAD, explicit finite credit budget; preserve other jobs.
- `scripts/craci/rokoko-mujoco-v11-qualify.py`: independent full original
  physics/contact/dwell replay and all 800 masks/worlds, re-derive **all 512
  public starts**, frozen V5 pairs and every unsafe/lost/novel outcome.
  `qualification_inputs.py` is a **source integrity precheck**, *not* that
  physics verifier.
- `scripts/craci/rokoko-mujoco-v11-retain-evidence.py`: byte-verifiable,
  **lossless ZIP parts** of the original complete training+full-options streams
  using the reviewed V10 source-pinned packer contract. Enforce capture
  per-file and total caps and verify reassembled original SHA; no truncation,
  redaction of losses, samples masquerading as full results or stdout dumps.

**Promotion conditions:** physical V11 goal250 dwell beats frozen V5 on at
least one **new** paired world, loses **zero** previously winning V5 worlds,
adds **zero** unsafe worlds, and passes independent source+physics replay and
human model review. If any one fails, **NO-GO**. Nothing here authorizes model
promotion even if these numerical predicates happen to pass; DEV/TEST/OOD
remain unopened and held TRAIN diagnostics are not disguised holdouts.

## Reproducible tests and historical fit

```bash
python3 -m unittest discover -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v11_learning -p test_learning.py -v
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v11_learning/train.py \
  --retained CRACI_PRIVATE_RETAINED/artifacts/rokoko-mujoco-v10-prospective \
  --receipt CRACI_PRIVATE_RETAINED/receipt.json \
  --source-root . --out NEW_UNUSED_PRIVATE_CHECKPOINT_DIRECTORY
```

Original CRACI receipt is **source-reported, not a signed bill or robot safety
attestation**. No GPU, new model-weight training, hidden observations, sealed
evaluation or cloud spend occurred in V11 source-only training. This is an
explicitly falsifiable goal-first control hypothesis awaiting real physics.
