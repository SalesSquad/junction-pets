# MuJoCo CPU physics — moving-obstacle action necessity

Work ID `J26-ROKOKO-MUJOCO-PHYSICS-20261114`. **Separate experimental
scenario; not a replacement for the original MuJoCo DQN, the standard-library
action-necessity toy, or any locked evaluation receipt.** Never call this Isaac,
MJWarp, a live robot, SDK teleoperation, a safety proof, or RL model training.

## Model and experiment

- Exact ancestor: draft PR #153 at `312130c9f0b63b9623e4cc9401ace74539296733`.
- A fresh MuJoCo XML derives from the existing `sim/scene.xml` with a **mocap
  moving obstacle**. Before each physical integration the obstacle advances via
  `MjData.mocap_pos`, then `mujoco.mj_step(model, data)` integrates contacts at
  2 ms. An unsupported mocap API fails rather than downgrading to 2D geometry.
- Existing source `learning/env.py` is imported unchanged. Original object mass,
  friction/grip distribution, contact-force threshold, success dwell, servo,
  sensor dropout, unreliable acknowledgement, held/deadman and out-of-bounds
  rules remain. The side-approach target is tightened to shallow oblique contact
  (the inherited side target is outside combined object/pusher radii), enabling
  an actual multi-action detour on this variant for either policy. Dynamic map
  comes from *noisy observed* world geometry and can
  become stale during dropout. Hold/abort remains a **simulation response**.
- Controller **constant** proposes `PUSH_MEDIUM` every option; **teacher** is a
  frozen deterministic observation-only alignment/side-approach/slow-push
  controller. Both go through the *identical* environment-level action shield
  and physics contact hazard detection. Optional trusted `module:function`
  policy receives only `(observation.copy(), mask.copy())`.
- Each policy resets the exact same seeded model/sensor/motion world, verified
  by hidden initial-state hash. Distinct actions, successes, unsafe incidents,
  actual engine physics-step counts and paired seed outcomes are recorded.
  Seedwise bootstrap CI is **descriptive**, not evidence of causal robot safety.

## Installation and bounded commands (CPU, no GPU)

From an exact, trusted checkout of this branch with Python 3.11+:

```bash
python -m pip install 'numpy>=1.26,<3' 'mujoco==3.3.7'
python -m unittest discover -v -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco -p 'test_contract.py'
python solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/run.py \
  --split dev --episodes 8 --max-options 60 --require-git \
  --expected-head FULL_TASK_BRANCH_COMMIT_SHA --output /tmp/rokoko-mujoco-dev.json
```

Evaluate first on dev `129000..129999`, then optional calibration `229000..229999`
without changing test/ood distributions. After reviewing and freezing the code,
pin `--expected-head` to the exact reviewed commit and run the **untouched**
test `329000..329199` and OOD `429000..429199` with explicit
`--permit-holdout`. The evaluator accepts at most 200 episodes and 60 options
per episode. Each completed option is at most 100 real MuJoCo physics steps;
its receipt contains actual counters, not a fabricated estimate. Do not treat a
zero or negative gain as positive evidence: the historical DQN-vs-constant
result was neutral and remains so.

**Decision gates** on the frozen heldout: engine `mujoco==3.3.7`, pinned Git
ancestor+HEAD, matched hidden world hash, positive physical steps for every
policy, source-file SHA256 manifest, no unsafe-count increase, and independently
reported teacher/constant success difference and paired interval. We do not
claim a threshold win if any of these are absent. A score-only gain with unsafe
regression is a fail. Target thresholds must be declared before holdout and not
retrofit to the data; no physics/safety guarantees beyond this toy environment.

### Known limits

CPU MuJoCo scene is a small planar pushing simulation with virtual contact
force and deadman events. It is not an industrial dynamic-obstacle controller,
not a Rokoko device or verified perception pipeline. The optional policy adapter
imports code you trust and is not a sandbox. No network calls, credentials,
paid runners, new daemon, or GPU are required. If `mujoco` isn't installed,
the real-physics test explicitly skips and CLI fails closed—never substitutes a
synthetic 2D rollout.
