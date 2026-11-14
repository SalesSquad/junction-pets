# Rokoko v6 — learned contact-setup corridor planner

**Experimental, not robot-safe or scientifically qualified.** This is a new
stateful observed-contact strategy, not another tuning of v5's four thresholds.
On real MuJoCo 3.3.7, the frozen v5 [CRACI #43635488617](https://github.com/SalesSquad/junction-pets/actions/runs/43635488617)
observed 8,900 option transitions. Its 48-world training best was 20 wins vs
17 default; its **fresh 80-world dev result was 35/80 for v5 and 35/80 for
constant, 33/80 for v4, zero unsafe, SCIENCE RED**. In particular, previously
exposed center-obstacle worlds (local y=.065) had **0/27 wins** for all three
and v5 aborted 23/27; the 53 clear worlds accounted for all 35 wins. Those
worlds and the 129170–249 dev seed range are **never used for v6 training or
evaluation**.

## Novel mechanism

The v6 policy is a bounded macro driven *only* by `observation[18]`,
`mask[7]` and its own past decisions/observed displacement:

1. Select route mode from the **first visible obstacle map**. For clearly
   offset obstacles, delegate the whole episode unchanged to frozen v5.
2. For observed corridor obstacles, **ALIGN (option 0)** the pusher behind
   the object, **APPROACH_LEFT/RIGHT (3/4)** from the far side of the mapped
   obstacle, and periodically probe contact with **PUSH_SLOW (1)**. Persist
   across failed shallow contact attempts rather than automatically aborting.
3. React to observed lateral displacement and allow bounded physical
   **RETREAT (5)** or ALIGN for re-planning if the unchanged mask allows it.
   RETREAT is a real servo motion, **not HOLD, a no-op or an emergency stop**.
4. Move forward via **PUSH_SLOW/PUSH_MEDIUM (1/2)** only when the original
   independent mask and conservative observation-only swept clearance permit.
   ABSTAIN (6) remains a counted failed/refused episode. The original
   environment, contact thresholds, deadman release, collision physics,
   moving-obstacle phase and action ABI are untouched.

Eight policy parameters control macro budgets, observed progress threshold,
probe timing, desired lateral lane, pusher clearance and recovery threshold.
Six candidates across **two generations** are optimized against actual
MuJoCo per-option rewards/costs; this is small-policy return optimization,
**not** training an LLM or claiming proven robot safety.
The optimizer deliberately gives extra weight to successful, unsafe-free
**observed corridor training** worlds, identified solely from their first
noisy public observation. This avoids easy clear training worlds drowning out
the contact-failure hypothesis. It never uses development/calibration/test
outcomes for candidate selection.

## Exact manual CRACI command

Use an immutable exact-source checkout under the authorized existing CRACI
window. The output directory may already exist but must be **empty**.

```sh
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v6_learning/run.py \
  --mode train-dev --require-git --expected-head FULL_40_CHAR_GIT_SHA \
  --train-episodes 48 --dev-episodes 80 \
  --output-dir "$CRACI_RECEIPT_DIR/artifacts/mujoco-v6-learning"
```

- Train-only 511000..511047, valid in the immutable ContactEnv seed range
  `[120000,520000)`, completely separate from all frozen physics bands.
  Bounded training reuses these seeds **only within** candidate optimization.
- Fresh dev only 129250..129329, 80 paired identical-world seeds for
  `constant`, immutable `learned_v5`, and `learned_v6`.
- Next proposal-only train cohort 512000..512999. No automatic rerun; no
  calibration229100+, test329000+, OOD429000+ access.
- V5 observed model weights are pinned:
  `COLLISION_CLEARANCE=.0597963`, `CORRIDOR_ENTRY_X=.0586112`,
  `LANE_DISTANCE=.0265924`, `POSSIBLE_SWEEP_Y=.0903199`, digest
  `fc3504f64c7e283cb53fbb8801c99e3bd9065e1fb0bc19ae73a66b8f7e4b5875`.

## Honest evidence and science gate

- `training.json`: six × 48 real train-only episode rollouts, all observed
  option-level inputs/masks/actions/reward/cost, exact transition count,
  canonical SHA-256, chosen weights and failure/side-contact taxonomy.
- `model.json`: frozen contact-macro weights, canonical SHA-256 over sorted,
  compact JSON, model source and immutable v5 baseline digest.
- `dev.json`: all 80 raw paired-world outcomes, observed (nonprivileged)
  initial corridor labels, per-policy side-action traces, risk/ABSTAIN counts
  and 2,000-resample paired CI from unchanged v1 logic.
- `manifest.json`: source and full evidence SHA-256s, no provider billing claim.

Qualification strictly requires **positive v6-vs-constant success gain,
paired 95% lower CI > 0, zero *new unsafe worlds* relative to either constant
or v5 (even if aggregate counts tie), no loss of even one previously
successful **constant or v5 world**, at least five genuinely new success worlds
which both baselines failed, and at least v5's total successful worlds**.
Observed center-corridor new wins are reported separately; a no-contact
physical primitive could still make this hypothesis SCIENCE RED. No baseline
relaxation or post-hoc tuning on the opened dev cohort is allowed. A science
red writes all four receipts and exits **2**; an incomplete training run or
timeout is infrastructure failure, not a scientific result.

Portable unit tests and syntax checks can run without MuJoCo. They do **not**
establish any physics improvement; only source-pinned CRACI actual `mj_step`
jobs can do that. Every action and scenario is fictional research, not
production equipment control.
