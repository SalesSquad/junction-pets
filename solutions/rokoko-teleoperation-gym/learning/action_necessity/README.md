# Action-Necessity Arena — bounded research experiment

Work ID `J26-ROKOKO-ACTION-NECESSITY-20261114`. Exact parent source:
`59479b42b177c1829a2e6678adfff1fb68aef09c` (Rokoko PR #137).
Isolated new experiment; do not rewrite PR #137 training or M6 PR #148 evidence.

## Why

The earlier Double-DQN and shielded constant PUSH_MEDIUM produced **identical**
test success (154/300) and OOD success (14/200), with no measured DQN gain.
More training on that version alone is not evidence of learning. This separate
diagnostic checks whether varying movement choices matter on predeclared worlds.

The task intentionally includes both **straight-through controls** (`clear`,
`side_blocked`) and **action-dependent challenges** (`center_blocked`,
`crossing`). Static geometry, randomized friction and drift, moving obstacles,
sensor lag/dropout and deadman loss vary by seed and OOD distribution. The
teacher receives *only delayed observations and an explicit static map*, not
hidden friction, phase, seed or future object states. Every candidate motion
passes the **same independent true-geometry simulation shield** for teacher
and constant-forward null; refused motions are counted. Operators must still
retain independent physical safety functions if this work is ever ported.

## Local commands

Python 3.10+ standard library only; no network, cloud, torch or device required:

```bash
cd solutions/rokoko-teleoperation-gym/learning/action_necessity
python -m unittest -v test_arena.py
python run.py --split dev --episodes 120 --output /tmp/rokoko-action-dev.json
```

For a future **single locked evaluation after algorithm/world freeze**:

```bash
python run.py --split test --episodes 300 --output /tmp/rokoko-action-test.json
python run.py --split ood --episodes 200 --output /tmp/rokoko-action-ood.json
```

The CLI refuses overwriting a receipt. It writes policy-separated seed rows,
source-file SHA256, exact run settings, unsafe/abstention/refusal counts and a
world-paired 4,000-resample bootstrap confidence interval. The predeclared
toy **action-necessity demonstration criterion**, evaluated only with at least
100 worlds, is teacher > constant by 15 percentage points, bootstrap lower
95% > 0 and teacher unsafe no higher than constant. This is **not** a claim
about learned weights, MuJoCo, an actual robot, or physical safety. Failures
are retained; never rework worlds or tests after reading holdout scores.

## Next genuine MuJoCo/learning gate

Implement the approved scenario distribution on an **independently tested
MuJoCo dynamics model** (and optionally MJWarp / Isaac Lab with CPU parity),
freeze its exact source and heldout seeds before training, then compare a
newly trained policy with the **identical shielded action baseline**. Keep
physics/learning, sensor provenance, safety and the synthetic kinematic
diagnostic separate. Sponsor SDK/robot and licensed recording access remain
missing, so none of this authorizes actuation or device data collection.
