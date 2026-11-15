# V15: source-bound world-disjoint learning tournament (TRAIN diagnostic)

**Work ID:** `CRACI-V15-ACTIVE-LEARNING-20261115`. This is a real offline
model-selection experiment on original, independently qualified MuJoCo physics
data; **not** a new physics run, deployment, safety certificate or release.

## Why this is additive to the existing learning controller

The repository already has `scripts/craci/learning_controller/`: its V8
640-episode paired evidence and immutable next-cycle advisory do the critical
`evidence → causal failure → next TRAIN hypothesis` bookkeeping. It does **not**
fit and cross-test a world-disjoint public-context rule on the **later V12
48-world/three-arm actual MuJoCo matrix**. This new module adds precisely that:

1. Independently pin **the outer original V12 artifact ZIP** and reconstruct
   its two lossless nested ZIP parts with raw SHA-256 checks. Recheck 144
   complete episodes, 4,228 original seven-mask-legal options, all 512 public
   world scans, 48 actually paired TRAIN worlds, receipt and qualification.
2. Learn a small, inspectable candidate from a frozen four-rule grammar using
   *only* the observed initial obstacle Y and the original public mask: V5,
   public-corridor, or one-sided Y threshold to select between the two **whole
   previously executed strategies** V5 and V12 phase. There is no model output
   for individual motor options and no unsupported counterfactual action label.
   Untrained RIGHT4 is separately reported, never selected.
3. Five world-disjoint folds (`seed % 5` for grouping only) fit the threshold
   and select the best rule on FIT worlds. Strict fitness order: **zero new
   unsafe / zero lost frozen-V5 goals**, observed efficiency benefit, at least
   two improving independent worlds, non-worse physics ticks and no fragile
   single-world rule. Report paired diagnostic results on excluded worlds,
   a world-bootstrap descriptive interval and hashes of FIT/held world sets.
4. Compile hard-negative counterexamples (no 250-tick goal, phase option
   overhead, possible narrow efficiency wins, untrained RIGHT4), with
   provenance hashes and preregistration questions for the **next** independently
   reviewed source. Do not re-run the identical source indefinitely.
5. Require the original V13 SHA-only unsafe packet. V13's **incomplete**
   394-option, one-unsafe experiment yields **zero** learning/efficacy rows,
   preserves `STOP_UNSAFE`, and cannot be automatically retried or promoted.

### Measured result on actual original source (not simulation of data)

Original run [#43657058944](https://github.com/SalesSquad/junction-pets/actions/runs/43657058944),
artifact `14139070947`, original outer ZIP SHA-256
`f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311`,
source HEAD `78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f` and harness
`4874d15dd68d3a809aaf7d769d6b5bef85d378bd`. The original sources are
private and **not** committed. This folder commits only code, synthetic tests
and the small deterministic source-derived aggregate receipt.

| Actual original TRAIN arm | Safe physical goals / 48 | Total actually executed options | Mean options/world |
| --- | ---: | ---: | ---: |
| Frozen V5 (champion) | **12** | **1,337** | **27.85** |
| V12 supported-action phase | **12** | 1,658 | 34.54 |
| RIGHT4 exploratory (untrained; ineligible) | **12** | 1,233 | 25.69 |

V12 phase added options in **22** paired worlds, matched in 24 and saved two
options in just **two**; it made **no** new safe 250-tick goals. Its extra
average six-plus options/world were not a learning breakthrough.

**Five-fold cross-fit:** 48 held-world diagnostic predictions, the trainer
chose V5 in **all five** FIT folds, observed paired option delta **zero**, goal
losses **zero**, unsafe **zero**, novel goals **zero**. World-bootstrap descriptive
95% interval for its *zero difference from itself* is `[0, 0]`; this does not
establish physical safety or improvement. The active learner **correctly
rejects** the unhelpful policy family rather than spending CRACI on a false
winner. The next engineering questions target the **36/48 failed goal** worlds
and the **22/48 phase-overhead** worlds, with a new preregistered candidate
required before any physical experiment.

### Important qualification boundaries

- All 48 worlds are **TRAIN**. Folded diagnostics are examined repeatedly;
  there is **no untouched DEV/CAL/TEST/OOD** evidence or external validity
  claim. Strict no-go is source policy, not a p-value or a safety guarantee.
- A paired whole-policy choice is observable here because all three original
  strategies **really ran** in every source world; an unchosen *motor action*
  in a trajectory is **not** observed and must never be assigned a label.
- `seed`/world hash select grouped folds and audit data only; they never enter
  the candidate inference rule. Future policy alternatives require new source
  review, restored independent replay, complete evidence, CRACI spending
  authority, a fresh cohort and separate safety admission.
- No auto scheduling, API calls, GPUs, jobs, deployment, model promotion,
  actuators or changed original physics/masks. The existing controller and
  CRACI Guardian continue owning scheduling/credits. This V15 product is a
  training/diagnostic **research layer**, not an alternative dispatcher.

## Reproduce and verify

From repository root, with the original retained archive in a private local
path and the SHA-only V13 packet from the reviewed integrator source:

```sh
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v15_evidence_tournament/tournament.py \
  --original-v12-artifact /private/exact-original-v12-artifact.zip \
  --v13-sha-only-manifest docs/craci/learning/rokoko-mujoco-v13-43660619725/unsafe-sha256.json \
  --out /private/NEW-ABSENT-v15-receipt.json
```

The CLI refuses replacement of an existing receipt and prints its SHA-256.
The committed `frozen-v12-source-bound-tournament-receipt.json` reproduces
from the same source ZIP and unsafe manifest; its SHA-256 is
`87d78d2870d72a0847fd7b45f807ccb550d3f311bddfeefdedbe5b52edb389e2`.

Targeted synthetic tests (no private evidence needed):

```sh
cd solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v15_evidence_tournament
python3 -m unittest -v test_tournament
```

**Decision:** `STOP_V13_UNSAFE_AND_V12_ZERO_NOVEL_GOAL`. Keep V5 champion;
do not auto-promote, auto-train on incomplete V13 or silently repeat the 48
TRAIN worlds. The scientifically meaningful next iteration must **change the
predeclared policy hypothesis**, then get independent source/safety review and
a new, disjoint, complete original physics evaluation.
