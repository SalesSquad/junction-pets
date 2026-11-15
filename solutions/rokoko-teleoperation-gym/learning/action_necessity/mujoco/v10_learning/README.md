# V10 — real V8 failure informed TRAIN learner

This version is **not** a physics run or a claim of control improvement. It
compares two original, immutable and independently replayed source-bound MuJoCo
TRAIN cohorts. V7 used seeds 512000+; V8 ran 640 paired trials on 513000+.
The V8 source (`87c91de…`), harness (`251f003…`), CRACI run
`craci.43645486985.1.0627c4e23e4a1296`, receipt SHA (`59e200ce…`), full
training SHA (`af84ec8c…`), compressed 29,923-option archive SHA
(`cbaeacd5…`), qualification SHA (`1215cbba…`) and independent positive replay
SHA (`af11a65a…`) are literal, reviewed constants in `run.py`. The original
CRACI ZIP SHA is also pinned. No self-rehashed manifest or caller-supplied SHA
can authorize an experiment. The source-reported CRACI evidence remains
TRAIN-only; it is not provider-attested model superiority.

## Learning from an actual failure

- V8 fresh near-world safe goals: **0/128**. Frozen V5: **9/128** on precisely
  the same V8 worlds. Other V8 successes (including clear worlds) are reported
  separately, never blended into the near-world claim.
- Nine observed V5 successes in V8 fresh TRAIN and two original V7 safe-goal
  world witnesses supply actual positive trajectory actions. **Seven** new V8
  worlds and both old V7 worlds fit; two fresh V8 goal worlds form a world-
  disjoint TRAIN-only diagnostic with no action-label leakage. Other motor
  teacher worlds have separate fit, inner-TRAIN validation, and held TRAIN sets.
- Failures are used to **select and weight real teacher demonstrations**, not
  invent counterfactual labels for actions no policy ever took.
- Four 41-feature, seven-option heads inherit V8's public-observation and
  history-only feature ABI. This learning fits a masked softmax for 80 fixed
  epochs using action-replay imitation, time-discounted stage credit, KL to the
  immutable V8 prior and L2 to its weights. Held TRAIN diagnostics are read
  only *after* fixed training; no dev/cal/test/OOD data is opened.
- The candidate remains unpromoted even if TRAIN diagnostic losses improve:
  a new source-bound real MuJoCo cohort and independent replay are required.

## Offline entry point

```bash
python -m unittest discover \
  -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_learning \
  -p 'test_*.py'

python solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_learning/run.py \
  --v7-restored /evidence/v7-restored \
  --v7-retained /evidence/v7-retained \
  --v7-artifact-zip /evidence/craci-v7-retained.zip \
  --v8-restored /evidence/v8-restored \
  --v8-retained /evidence/v8-retained \
  --v8-artifact-zip /evidence/craci-v8-succeeded.zip \
  --v8-frozen-weights /source/v8_learning/checkpoints/weights.json \
  --output-dir /evidence/new-v10-offline-run
```

The output directory must be new and outside the Git checkout. The original
V9 checkpoint/readout and frozen 514000+ cohort remain untouched. The next
separate TRAIN-only proposal begins at **515000** and pairs five strategies
across 160 worlds (800 episodes). **Nothing dispatches these experiments.**

## Frozen, shield-only candidate inference

`policy_factory(path)` checks the **literal committed candidate file SHA**;
it yields fresh per-episode `FrozenV10LegalPolicy` instances. Each call takes
only `(observation[18], legal_mask[7])`, uses public option history and returns
an integer present in the original seven-option legal mask. It cannot request
an environment, seed, success, contact, reward or privileged simulator state.
Tests replay every singleton legal-action mask, floating masks, empty masks,
shape violations, fake weights and deterministic resets. This is a testable
controller interface for a *future separately approved TRAIN-only physics run*,
not deployment authorization.
