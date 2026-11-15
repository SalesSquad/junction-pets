# Rokoko v5 — reward/cost learning on real MuJoCo CPU

This is a **bounded learning pilot**, not another hand-written controller
evaluation and not a physical safety certificate. The v4 policy is an
observation-only heuristic; v5 performs a deterministic two-generation
reward/cost optimization of four bounded policy parameters using **actual
`mujoco==3.3.7` simulation**, then freezes the learned parameters *before*
opening any new development-validation worlds. The original simulator,
observation/action ABI, deadman, action mask, contact thresholds and all v1–v4
scientific-negative receipts remain unchanged.

## Exact-source CRACI command

Use one existing authorized source-pinned, manual CRACI task on an immutable
checkout. All runnable evidence must come from the *same* executed source SHA.

```sh
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v5_learning/run.py \
  --mode train-dev --require-git --expected-head FULL_40_CHAR_GIT_SHA \
  --train-episodes 48 --dev-episodes 80 \
  --output-dir "$CRACI_RECEIPT_DIR/artifacts/mujoco-v5-learning"
```

The output directory may exist but must be **empty**; files are opened
exclusively. Required `python3`, `numpy`, `mujoco==3.3.7`, clean Git checkout.
No CUDA, provider API key, account scope or credential transfer is involved.
The source has a per-invocation 1,200-second (20-minute) ceiling, and a CRACI
workflow must independently enforce its own timeout and credit cutoff. If
the science gate fails, the process writes receipts then returns **exit 2**;
an infrastructure/source/timeout failure must not be called scientific RED.

## Separation and data provenance

- Training-only seeds: **510,000…510,047** by default, in an independent
  reservation **inside frozen `ContactEnv.reset`'s valid `[120000,520000)`
  seed domain**, disjoint from all existing physics dev/cal/test/OOD bands.
  Six policy candidates (three
  each for two generations) see the same 48 training seeds, using only actual
  observed `observation[18]`, `mask[7]`, seven-option action, reward, cost and
  subsequent observation. A candidate's training success, unsafe/abstain and
  actual reward drive selection. No hidden obstacle phase, world seed or true
  contact geometry is available at policy inference.
- Fresh dev paired validation: **129,170…129,249** (80 worlds), one pass
  after training/model freeze. Run constant, the unchanged v4 controller and
  the learned v5 on the *same latent world hash* with the unchanged shield.
  Prior exposed v4 dev129030..169 and v3 cal229000..099 are excluded.
- Additional train-only future cohort: **511,000…511,999**, also inside the
  frozen valid environment seed domain. Failure
  taxonomy produces a *proposal*, never an automatic new experiment.
- **No** v3/v4 exposed calibration reuse, no physics test329000+ or
  OOD429000+, no privileged teacher supervision and no automatic model
  promotion. A later calibration needs a separately source-frozen candidate
  and independent review.

## Evidence contract

- `training.json`: actual per-option trajectories, reward/cost, repeated
  train-only seed provenance, selected optimizer generation, dataset SHA-256,
  weight SHA-256 and next-train-only curriculum suggestion based on failures.
- `model.json`: frozen bounded parameter vector and exact digest, no inference
  access to privileged state.
- `dev.json`: all 80 paired worlds, per-policy raw outcomes, v2 paired bootstrap
  confidence interval, exact weight/data digest, unsafe and science gates.
  A legitimate first-option ABSTAIN has **zero physics steps and scores as a
  failed/refused** episode; it is not a safety proof.
- `manifest.json`: SHA-256 of all three observed receipts plus local v5 source
  files. Provider invoices or actual Euro spend are never inferred from this.

The primary gate is **unchanged** from v2: candidate success gain strictly
positive, paired 95% lower bound strictly above zero and candidate unsafe
count no worse than constant. Additionally, v5 must have no unsafe regression
against the v4 same-world comparator. Any miss is scientific RED, not a
reason to loosen thresholds or retune against the observed development set.

## Local portable checks

```sh
python3 -m compileall -q solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v5_learning
python3 -m unittest discover -v -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v5_learning -p test_contract.py
```

These verify only source contracts and mocks. A real environment qualification
requires the pinned CRACI run and its unmodified original GitHub artifacts.
