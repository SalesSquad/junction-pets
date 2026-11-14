# Rokoko Action-Necessity — Reward-Driven Multi-Action RL

**Work ID:** `J26-ROKOKO-MULTIACTION-RL-20261114`

This is an independently trained **Expected SARSA** learner for the existing
synthetic 2D `action_necessity/arena.py`; it is **not behavioral cloning**.
Neither the original `RouteTeacher` nor any imitation labels are called during
training. The training objective is actual simulator episodic return: forward
progress and goal alignment, with per-step/refusal/reobservation costs, positive
terminal success reward, and penalties for unsafe, aborted or timed-out runs.
Actions are actual discrete `Arena.step()` commands. A shared geometric shield
remains in the original environment. The learned agent additionally follows
predeclared deadman/stale-sensor fallback; an **independent constant FORWARD
controller with exactly the same fallback** is included alongside the original
shielded constant null to expose any advantage from that fallback.

## Frozen experiment protocol

| Purpose | Split | Seed range | May guide algorithm? |
| --- | --- | --- | --- |
| Reward training | `dev` | `122000..127999` | Yes, by return only |
| Development sanity | `dev` | `120000..120199` | Yes |
| Calibration | `cal` | `220000..220199` | Yes |
| **Fresh locked test** | `test` | `325000..325299` | **No** |
| **Fresh locked OOD** | `ood` | `425000..425199` | **No** |

The previous behavior-clone test `320000..320299` and OOD
`420000..420199` were already exposed by CRACI run `43625995894` and **must
not** be used to fit or choose this RL policy. No locked worlds above were run
by this implementation author. Development, calibration and training are
disjoint. The fresh locked ranges are valid within the unchanged arena's
10,000-seed split contracts.

The fixed default is **6,000 training worlds**, seed `20261114`, TD discount
`0.976`, initial step-size `0.24`, initial epsilon `0.36` annealing toward
`0.035`, with a sparse observable tile-coded action-value model. These choices
were selected using only development/calibration results. The code serializes
learned weights, their SHA-256 digest, per-world paired outcomes and source
file digests for independent reproduction; its self-hashes do not replace
GitHub commit/source attestation.

```bash
# Uses Python standard library only; no GPU, provider key, real robot or SDK.
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/rl/td_agent.py \
  --train-episodes 6000 --eval-split dev --eval-episodes 200 \
  --output /tmp/rokoko-td-dev.json

python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/rl/td_agent.py \
  --train-episodes 6000 --eval-split cal --eval-episodes 200 \
  --output /tmp/rokoko-td-cal.json

python3 -m unittest discover \
  -s solutions/rokoko-teleoperation-gym/learning/action_necessity/rl \
  -p 'test_*.py' -v
```

### Author-observed development and calibration only

On the same frozen policy (6k training worlds) and 200 paired worlds per split:

| Split | Learned successes | Original constant | Same-guard constant | Learned unsafe | Null unsafe | Paired improvement |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Development | 157/200 | 92/200 | 92/200 | 8 | 20 | +32.5 pp, 95% CI [23.5,41.0] |
| Calibration | 154/200 | 97/200 | 97/200 | 11 | 18 | +28.5 pp, 95% CI [19.5,37.0] |

These are **local Python synthetic observations**, not independent CRACI,
MuJoCo, physical actuator or real robot evidence. The paired percentile
bootstrap is descriptive and not a safety certificate.

### Only the independent CRACI qualifier may open lockboxes

After source SHA and model hyperparameters are frozen, run each once on an
authorized existing CRACI runner with the exact product source SHA:

```bash
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/rl/td_agent.py \
  --train-episodes 6000 --eval-split test --eval-episodes 300 \
  --confirm-locked --output /tmp/rokoko-td-locked-test.json
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/rl/td_agent.py \
  --train-episodes 6000 --eval-split ood --eval-episodes 200 \
  --confirm-locked --output /tmp/rokoko-td-locked-ood.json
```

Both results must have the **same model-weights SHA**. Predeclared acceptance:
at least **+15 percentage points** learned over both constants on the test
set, positive paired 95% lower confidence limit, and observed unsafe counts
no greater than either constant on test **and** OOD. A failed outcome is
preserved as a valid negative result; no threshold loosening, same-source
repeat or model tuning against exposed lockbox seeds.

To reach physical robot claims a separate phase still needs independent
MuJoCo CPU parity, contact/friction and actuator models, sensor dropouts,
recovery, safety-system engineering, vendor permission and physical validation.
This toy simulator and RL score do not license hardware deployment.
