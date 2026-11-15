# MuJoCo risk-v3 — real-contact experiment, not a claimed breakthrough

Work ID `J26-ROKOKO-MUJOCO-RISK-V3-20261114`. New additive `mujoco/v3/`
subtree, stacked on immutable MuJoCo v2 PR #167 SHA
`b8f35db5e88eb0eb55157790618a52e73ca60220`. Earlier source, receipts,
benchmark seed ranges, physics thresholds and original action semantics remain
unchanged. This uses **real `mujoco.mj_step` CPU physics**, not 2D kinematics.

## Evidence forcing this iteration

- Real negative v1 dev run [#43627944236](https://github.com/SalesSquad/junction-pets/actions/runs/43627944236):
  original teacher **0/8** vs shielded medium constant **5/8**; unsafe0/0.
- Real negative v2 dev run [#43628857595](https://github.com/SalesSquad/junction-pets/actions/runs/43628857595),
  exact source `b8f35d...`, artifact `14127535149`: adaptive-v2 **5/8** vs
  constant **5/8**, success delta 0pp CI[0,0], but **unsafe1 vs constant0**.
  This is scientifically worse, despite infrastructure/physics success.
- Detailed v2 option trace: world `129004` hit an unsafe event on its **53rd**
  option, an `APPROACH_RIGHT` immediately after earlier left-side steering;
  `peak_impulse=.0039878` was below the `.006` threshold. The v2 receipt did
  not expose whether the hazard was obstacle contact or bounds; do not invent
  the cause. The late side flip plus moving obstacle is a plausible risk source.
- Reconstructing the public `env.py`'s independent seeded world RNG shows
  `release=160` for worlds `129003` and `129006`. After that simulated deadman
  release, hold is permanent; both v2 and constant failed. These two worlds
  cannot realistically be rescued by changing a controller after release.
  The policy does **not** receive or condition on this hidden true value;
  it is reported only as a diagnostic for the entire unfiltered sample.

## Preregistered, observation-only v3 hypothesis

1. Continue proven medium/slow contact when the common shield and an additional
   **short swept obstacle-clearance** estimate both allow it.
2. Predict one 200 ms option from *observable* object/map positions plus a
   smoothed bounded obstacle velocity estimated across sensor observations.
   Compare predicted motion to geometric clearance from the public XML with a
   fixed 55 mm simulation-only center separation; this is not a formal control
   barrier or certified safe margin.
3. Detour laterally only if both forward options are masked and swept
   clearance permits. Preserve the original safe side choice through later
   medium-push intervals; refuse late reversals near the moving obstacle.
4. Otherwise align/retreat to wait for a safer observed phase. Deadman and
   dropout masks always override, and the controller never sees true motion
   phase, contacts, or simulator internals.

This may avoid one unsafe pattern but could reduce goal success. A positive
result cannot be assumed. The original scenario has a genuine finite-horizon
reachability limitation for certain permanent-deadman worlds. If every safe
action fails on those, the correct conclusion is to improve the **action
semantics/safety contract** in a separately declared new environment, not
weaken success thresholds or relabel a failed experiment.

## CPU dev/cal run — fresh seeds only

From a pinned full-history checkout with Python 3.11+:

```bash
python -m pip install 'numpy>=1.26,<3' 'mujoco==3.3.7'
python -m unittest discover -v \
  -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v3 \
  -p test_contract.py
python solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v3/run.py \
  --split dev --seed-offset 10 --episodes 20 --max-options 60 \
  --require-git --expected-head EXACT_V3_HEAD_SHA \
  --output /tmp/rokoko-mujoco-v3-fresh-dev-UNIQUE.json
```

Fresh contiguous dev seeds `129010..129029` are mandatory; the runner rejects
`129000..129009` development qualification after v1/v2's negative evidence.
Independent calibration can use `--split cal --seed-offset 0 --episodes 20`
(`229000..229019`) without changing the controller or threshold. No test/ood
seed has been opened.

One paired world includes unchanged constant, unchanged v2 and new v3 with
identical real MuJoCo physics and shields. Receipts report SHA256 of source,
exact Git head, per-seed world hash, actual physics steps, success, unsafe,
action counts, sensor holds, shield vetoes, contact counts, per-option trace,
final dwell and hidden deadman-release *post-hoc diagnostics only*.

The runner **creates** the receipt exclusively (`open('x')`) and never silently
overwrites failed evidence. It fails closed if `mujoco==3.3.7` is absent. A
scientific qualification requires positive paired success gain over constant,
no unsafe regression and bootstrap95 lower bound greater than zero. On failure
it preserves the receipt and returns exit code 2; this is a scientific FAIL
even when hardware/CI steps are green. For locked `test`/`ood`, the runner
requires `--permit-holdout --require-git --expected-head EXACT_SHA`; do not
invoke until the algorithm is frozen and independently calibrated.
