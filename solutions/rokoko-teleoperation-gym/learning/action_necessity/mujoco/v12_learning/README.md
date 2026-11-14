# CRACI Rokoko V12 — real-action learning, unqualified physics candidate

This is a source-only experiment on frozen, independently qualified **original
MuJoCo TRAIN execution traces**. It is not a claim that V12 improves goal
completion, not a new runner/daemon/CI workflow, and never initiates CRACI
compute or promotes a policy. The independently maintained CRACI feedback
controller can consume this frozen readout; it alone owns any scheduling.

## Why V12 exists

- V10 original 800 trials / 38,569 actual options, source HEAD
  `9cc583d3f0f24484b79c1929ba875c7a3b667806`, harness
  `a64e6fcc73a1d47485fe052990e31c9d9e45100f`: frozen V5 **37** goals,
  V10 **26**, **zero novel**, 11 lost. V10 was a physical GOAL NO-GO.
- V11 original 800 trials / 34,992 actual options, source HEAD
  `ab6df4054ef6ed350b479469590a48046a0c0a68`, harness
  `b1938bee9dbca482f645b5dde3359de38e6c125e`: V5 and V11 **18** goals,
  zero novel, zero lost, zero candidate unsafe. V11 is a physical GOAL NO-GO.
- We recovered the exact 1,600 episodes/73,561 option transitions, verified
  both ZIP-part reassembly proofs and SHA-256 source receipts, original public
  18D state/seven legal-mask actions, positive/clear independent physical
  qualifications, then fit **only actually executed options**. Never impute an
  unchosen action's result from an alternate trajectory.

Actual source action support (V10+V11):

| Action | Legal masked opportunities | Executed | World-disjoint predictive model |
|---|---:|---:|---|
| ALIGN 0 | 48,800 | 947 | **NO-GO**: held-world maximum coverage 84.9%; below 90% gate |
| PUSH SLOW 1 | 37,342 | 2,848 | supported, 98.5% held-world coverage |
| PUSH MEDIUM 2 | 36,406 | 8,148 | supported, 95.5% held-world coverage |
| APPROACH LEFT 3 | 48,791 | 35,911 | supported, 95.7% held-world coverage |
| APPROACH RIGHT 4 | **48,800** | **3** | **UNTRAINED**; all 3 from one V10 world, 0 V11 worlds |
| RETREAT 5 | 48,800 | 487 | supported, 100% held-world coverage |
| ABSTAIN 6 | 73,561 | 25,217 | original safety hold, not a learned motor |

The original 320 distinct TRAIN worlds are split deterministically by `seed%5`:
185 FIT, 65 CAL and 70 untouched diagnostic worlds. Each world gets equalized
training weight across its long/short sequences. The CAL 95% bound uses the
**maximum prediction error per independent world**, not option count; the
held diagnostic reports both world-max and event-level coverage, effective
distinct world counts per action and a zero-motion baseline. Action 0 remains
unqualified even though 947 executed samples exist. Trained action models:
`[1, 2, 3, 5]`; unsupported `[0, 4, 6]`.

Frozen model `model.json` SHA-256:
`82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e`.

The files in `frozen-real-train-v10-v11-final/` are generated once from those
original bytes. `manifest.json` records the SHA of each output; `model.json`
pins both original SHA/run/harness pairs, exactly 73,561 executed records,
source-world split *seed lists* and their SHA-256 hashes, the 55 frozen V5
successes on which the V11 gate **never fired**, weights and held-world
calibration. `analysis.json` preserves measured negative science, not a
manufactured V12 score.

## Frozen policy hypotheses

- `policy.policy_factory(frozen_v5_factory, model_path)` yields one isolated
  baseline-V5-first policy per actual episode. The independently frozen V11
  public blocked/abstain gate may trigger **one** rescue of at most **eight**
  options, only from validated public 18D current/previous observations and
  original 7D action mask. It ranks **supported** actually-trained actions by
  conservative (95% calibrated world-max) object-to-goal distance plus a
  non-certifying dwell proxy; return to fresh V5 when forward becomes legal,
  the public object nears goal, time expires, or support is absent. The
  shield remains the final actuator authority. No hidden mover phase,
  frequency, seed, reward, success, post-step dwell or cost enters inference.
- `policy.right4_train_only_factory(frozen_v5_factory, model_path)` is **a
  separate TRAIN-only acquisition probe**. It can choose originally
  mask-legal RIGHT4 once at the source-frozen public gate. It has no learned
  `action4` weights, never scores action4, resets V5 state after deviation,
  and is explicitly ineligible for deployment or promotion. Future actual
  physics must first establish safe support in **many distinct worlds**.

These are **testable hypotheses**, not assertions that the next observed
world will be safe or finish the 250-tick CONTACT dwell. Safety cannot be
predicted from positional regression or an aggregate held diagnostic.

## Fresh disjoint prospective TRAIN (not executed)

The source-bound protocol in `next-train-plan.json` and `protocol.py` freezes:

1. First independently scan **all 512** original public starts for seeds
   **518000..518511**, never a provided subset; derive first 40 observed
   near-corridor and first 8 observed clear worlds using `abs(obs[7])<.122`,
   no outcome/privileged state; keep actual same-world signature. Run frozen
   V5, V12 supported-action hypothesis, and RIGHT4 TRAIN-only probe = **144
   real MuJoCo episodes**. Preserve full option streams and exact masks.
2. **HARD STOP** if any new unsafe or any lost original V5 250tick contact goal
   or **zero novel** candidate 250tick goals. `forward_reopened` alone gives
   **no GO**. RIGHT4 unsafe also triggers a STOP. Never unseal DEV/TEST/OOD.
3. Only if pilot positive and independent original physics/proof replay GO,
   scan disjoint **518512..519023**, first 128 near +32 clear, frozen V5 vs
   one explicitly preregistered nonexploratory V12 candidate = **320 more**
   real episodes. Repeat zero lost/unsafe and positive novel goal requirement.
4. Both stages require **original** physics 20mm contact goal sustained at
   least **250 real MuJoCo ticks**, full 7-action shield replay, raw lossless
   retention (e.g. <=6 MiB ZIP binary parts before the host's capture cap),
   manifest/proofs, independent positive and clear-goal replays, exact source
   HEAD and harness SHA receipts. A preliminary source readout is not an
   independently qualified promotion; **no automatic dispatch or spending**.

`protocol.derive_cohort()` independently derives/validates the 512 scan and
the precise paired world set; `paired_physical_goal_readout()` rejects any
missing/duplicated trial and calculates only actual physical goal results.
It does not execute MuJoCo or certify an output by itself. The existing
integrator/hosted qualifier owns runner and retention changes. No historical
CRACI workflow, safety limit or shared output is edited by this task branch.

## Reproduce frozen original-source training

From the original verified private checkout/retained evidence roots:

```bash
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v12_learning/train.py \
  --v10-archive craci-v10-retained-EKOQuR/artifacts/rokoko-mujoco-v10-prospective \
  --v10-receipt craci-v10-retained-EKOQuR/receipt.json \
  --v10-source-root . \
  --v11-archive craci-v11-retained-43653579339/artifacts/rokoko-mujoco-v11-prospective \
  --v11-receipt craci-v11-retained-43653579339/receipt.json \
  --v11-packer scripts/craci/rokoko-mujoco-v11-retain-evidence.py \
  --out /path/to/NEW-ABSENT-private-run-directory
```

`--v11-packer` must have Git blob SHA `5a7138a7467f05262ad76e9faa50c6b5f46c6c62`.
No original evidence is modified and output must not exist. The resulting
source-bound checkpoint is deterministic except its honest manifest timestamp.

Focused test, 10 tests / 10 pass at HEAD:

```bash
cd solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v12_learning
python3 -m unittest -q test_learning
```

**Verdict:** frozen TRAIN learning algorithm and contracts implemented; newly
hosted V12 physical GOAL qualification **not done**, V12 model **NOT
PROMOTED**. New cloud spend requires a separate authorized integrator and
independent source review first.
