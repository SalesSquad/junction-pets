# Swept-lane v4 — experiment only

The immutable MuJoCo v3 source at `466c4264468b35c954242d8c3409a47c5ba3b4b8`
achieved 13/20 vs 12/20 on development data, but **failed independent
100-world calibration**: 48/100 vs 43/100, with **13 unsafe outcomes vs zero**.
The negative CRACI receipts are [development #43630195101](https://github.com/SalesSquad/junction-pets/actions/runs/43630195101)
and [calibration #43630816368](https://github.com/SalesSquad/junction-pets/actions/runs/43630816368).

V4 is a physical *hypothesis*, not a promoted controller. The observed failure
cluster has a moving obstacle near the path and late contact; v3 observes a
short horizon and can continue with an unsafe ALIGN or RETREAT. V4 uses only
the existing observation/mask, tries to establish an opposite-side lane before
the swept corridor, widens the obstacle drift envelope, and explicitly
ABSTAINS when a passage cannot be screened. The scene, dynamics, world RNG,
deadman, guard mask, failure thresholds and prior receipts are unchanged.
Unbounded Gaussian sensor noise means no formal collision-free guarantee.

## Reserved independent qualification

- Fresh development: seed offset `30`, `70` worlds → 129030–129099.
- Earlier v3 calibration 229000–229099 is **exposed**; it is not a holdout for v4.
- Future untouched calibration: offset `100`, `100` worlds → 229100–229199.
- Sealed physics tests 329000+ and OOD 429000+ must remain untouched until
  an independently justified source and safety gate exist.
- Primary gate is unconditional paired success gain, positive paired CI lower
  bound, and **no increase in any unsafe episodes** versus the same-world
  constant. Optional post-outcome obstacle/bounds diagnostics never reach the
  policy and must not filter the primary score.

The actual simulation requires `mujoco==3.3.7`, `numpy==2.3.4`, full
source checkout with exact `--expected-head`, and a fresh unique output:

```bash
python solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v4/run.py \
  --split dev --seed-offset 30 --episodes 70 --max-options 60 \
  --require-git --expected-head FULL_NEW_V4_COMMIT \
  --output /tmp/unique-real-v4-dev.json
```

An exit code 2 is an authentic science failure and still produces an immutable
JSON receipt. Nothing here certifies a physical robot.
