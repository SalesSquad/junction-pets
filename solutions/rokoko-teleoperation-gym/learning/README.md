# Original option Double-DQN research lane

Independent implementation; reads `../sim/scene.xml` without modifying the historic
Mega experiment or its results. Native MuJoCo contacts run on CPU at 500 Hz;
position target updates run at 50 Hz and options last up to 200 ms (5 Hz).
The neural network and gradient optimizer use the requested torch device.
No hardware commands, real human interventions, smartglove joint support,
Isaac Lab, MuJoCo Playground integration or safety certification is provided.
HOLD keeps the last position servo target: it is **not a physical E-stop** and
residual forces may cause an unsafe termination even while held.

## Coordinator setup and execution

Use the existing approved V100 and existing Python with torch 2.9.1+cu128;
this code provisions nothing and performs no API consultation. Install only the
missing pinned wheel into the task-owned layer (NumPy must already be present):

```sh
/root/savi-lite-venv/bin/python -m pip install --no-deps --target /root/rokoko-rl-20261114/deps mujoco==3.3.7
PYTHONPATH=/root/rokoko-rl-20261114/deps /root/savi-lite-venv/bin/python solutions/rokoko-teleoperation-gym/learning/train.py --train-episodes 1000 --cal-episodes 100 --test-episodes 200 --ood-episodes 100 --out /root/rokoko-rl-20261114/run-01 --device cuda --max-seconds 3600
```

The headless MuJoCo wheel also requires its normal import dependencies to already
exist in the host environment; if imports fail, report the dependency gap to the
coordinator rather than installing into the shared host or changing physics.
Use a fresh empty output directory. `--only-smoke --device cpu` caps training to
two short episodes and heldout splits to one world each; it does not qualify a
learner and usually cannot reach the 64-transition replay warmup. For a trainer
optimizer smoke use `--train-episodes 12 --cal-episodes 0 --test-episodes 0
--ood-episodes 0 --max-options 10 --device cuda` in a distinct output directory.
Check actual gradient steps and changed parameter hashes, not just process exit.
A deadline stops between options; one option and final serialization can exceed
it. No new rollouts are admitted after expiry; partial episodes are excluded from
completed counts. Outputs are incremental JSONL, CSV, frozen configuration,
`weights.pt` and `receipt.json`. Preserve failed receipts too.

## Data and evaluation contract

World groups are fixed: train 120000+, calibration 220000+, sealed test 320000+,
OOD 420000+, at most 10000 worlds per group. Learner `--seed` changes network and
exploration only. Separate world, sensor and independent synthetic ACK RNGs avoid
policy-dependent world generation; all paired methods reset the same seeds.
Historic Mega worlds 800000+ are rejected. Calibration is report-only: no automated
hyperparameter tuning. The optimizer freezes before calibration/test/OOD. Do not
retune this code after inspecting sealed results; a changed experiment needs new
sealed groups. Repeat learner seeds in separate runs if budget permits; the
current receipt deliberately makes no multi-seed statistical claim.

The 18 allowlisted features are noisy puck XY, pusher XY and velocity XY,
noisy mapped obstacle XY, observation age/quality, deadman/inside flags,
remaining synthetic ACK budget, elapsed fraction, last option, HOLD flag and
fixed goal XY. Hidden mass, friction, true obstacle, forces, seed, reward and
future observations never enter the network. Dense training reward uses hidden
true progress, with a terminal bonus only after true 0.5 s goal dwell and contact;
unsafe cost is separate in episode labels and an unsafe event stops immediately.
The reward is training feedback, never a policy input. All seven options use the
same visible proposal generator for learned and heuristic policies. A fixed mask
and actuator candidate filter operate independently of Q confidence. Occlusion,
staleness, deadman and observed workspace failures latch HOLD. Only a separate
synthetic random ACK while healthy and with budget remaining can release it.
This ACK model and geometric margins are research assumptions, not human consent
or a proven collision avoidance guarantee.

Unsafe means object damage proxy above 0.006 Ns per 2 ms contact step,
object/obstacle or pusher/obstacle collision, or either body's workspace excursion.
Success uses hidden true final geometry and 250 consecutive physics steps inside
20 mm, requires object contact, and excludes unsafe cases. Terminal safe abstain
is distinct from success. The heuristic aligns, pushes slowly, retreats near goal
and abstains on mapped corridor risk. Always-abstain is paired on the same worlds.
No change to the original scientific thresholds or old benchmark is made.

The learner uses a 64x64 MLP, replay, epsilon-greedy exploration, masked Double-DQN
bootstrap, Huber loss, gradient clipping and target synchronization. The fixed
shield provides conservative masking instead of a learned safety guarantee.
Training may learn to abstain or fail to improve. `FAILED_OR_UNQUALIFIED` is emitted
unless a non-smoke completed paired test has zero learned unsafe episodes, more
safe successes than both baselines, actual gradient updates and changed weights.
Even a passing label supports only those sampled synthetic worlds. It is not
hardware safety or statistical significance. OOD outcomes remain separate.

Receipts record execution HEAD **and dirty source state**, SHA256 of every Python
producer and the XML, frozen input hash, torch/MuJoCo versions, CUDA identity,
gradient and transition counts, actual physics steps, wall time, initial/final
parameter hashes and serialized weights hash. The receipt does not hash itself.
Execute from the coordinator's transferred exact committed source; inspect dirty
state as well as HEAD. No trained artifact exists merely because source is ready.

## Local focused check

```sh
/tmp/rokoko-m3-venv/bin/python solutions/rokoko-teleoperation-gym/learning/test_env.py
```

Two tiny real physics episodes plus seed, shape, forbidden historic seed,
deadman/model override and non-auto-rearming checks. This does not test PyTorch
or demonstrate usefulness. No broad historic suite is required for this isolated
research lane.
