# Rokoko V8/V9 Quality Recovery — immutable TRAIN-only regression

This source-only tool catches a specific confirmed **model-quality failure** before
someone schedules another model-training batch. It is a **read-only diagnostic**,
not a trainer, model optimizer, safety shield, simulator evaluation, CRACI workflow,
runtime integration, or permission to release a model.

## Frozen evidence and reproduction

- Original hosted V8 prospective CRACI run: [43645486985](https://github.com/SalesSquad/junction-pets/actions/runs/43645486985).
  Harness SHA: 251f003b56b9eea1aff79568ad351f615acaee20;
  product SHA: 87c91de52cef5c3e745115f737abc4ab8d654a32.
- Original GitHub artifact ID 14134391158, outer ZIP SHA-256:
  8e33c0b87a8e98cf3be2d4116a8bc4eca2e45efc3707e9fc8d385566319febb8.
- Frozen V8 model file SHA-256:
  07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1.
  Canonical model SHA: 9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea.
- Optional unpromoted V9 weights: PR #202, candidate-file SHA-256
  81734631d41428e029b3b308ca2e0d5cdf2485dd9ef3dae70794d69f4f5939ba.
  V9 decisions are projections onto **V8's old states and action history** only.

The original archives and model weights are inputs from authorized, verified
private storage. They are deliberately **not copied into this PR**. The hosted
run receipts and historical negative result remain unchanged.

From this folder, execute the focused, synthetic contract tests:

    python3 -m unittest -v test_audit.py

With exact source files already downloaded to a **private** folder:

    python3 audit.py \
      --artifact /private/evidence/original-gh-artifact.zip \
      --v8-weights /private/evidence/v8-frozen-weights.json \
      --v9-weights /private/evidence/v9-unpromoted-weights.json \
      --output /private/evidence/quality-recovery-v1.json

The utility validates each retained ZIP part, full historical raw-file hashes,
every trial's trace digest, the exact 640-trial/160-world paired cohort, 29,923
option records and all 9,580 frozen V8 policy actions. It does **not** run new
physics. The original engine was MuJoCo 3.3.7. All file SHA-256 expectations are
hard-pinned, not supplied through trust-override flags.

## Measured result on original frozen source

| Diagnostic | Source-bound result |
| --- | ---: |
| Actual frozen V8 action decisions reproduced | 9,580/9,580 |
| Stage 2, forward allowed by original seven-action mask | 3,745 |
| Frozen V8 stage-2 forward actions | **0** |
| Frozen V8 stage-2 leftward actions | **3,745** |
| V9 candidate, off-policy projection on old V8 states: forward | **0** |
| V5 near-world safe goals | 9/128 |
| V8 near-world safe goals | **0/128** |

A diagnostic flags a model as degenerate when at least 100 forward-legal
stage-2 decisions all avoid forward. **This is not a safety threshold** or
a deployment qualification. The original action shield is never bypassed.
A model that chooses forward here could still fail in real physics.

Original V7 teacher audit exposed the likely mechanism: all stage-2 imitation
labels came from the incomplete repeat_left lateral macro (1,816 left vs 576
forward; the 1.5× weighted left labels give 2,724 left versus 576 forward).
Complete V5/V6 goal teachers never entered stage 2. Only two distinct goal
worlds contributed stage-3 teachers. See [owner handoff on PR #202](https://github.com/SalesSquad/junction-pets/pull/202#issuecomment-6885151942).

## Repair contract for existing V9/V10 owner

1. Separate *safe obstacle-away lateral progress* from *goal-completion*
   demonstrations. Do not reward endless side movement as terminal progress.
2. Preserve direct safe-goal approaches from frozen V5/V6; avoid requiring a
   four-stage detour for every valid completion.
3. Make public-observation side-to-forward transitions depend on verified
   progress, without forcing masked or unsafe options.
4. Run a deterministic offline action-distribution diagnostic before any
   prospective physics; then qualify on **new**, preregistered disjoint TRAIN
   worlds. Historical V8/V9 states are diagnosis, not fresh quality evidence.
5. Do not promote without sufficient completion teachers, risk gates,
   independent heldout physics, and separate deployment authority.

**Status:** SCIENCE_RED_DIAGNOSTIC_ONLY. No qualified model, new CRACI job,
provider expense, secrets, merged V8/V9 historical branches, dev/test/OOD,
robot action, or release is authorized. The global 2026-11-15T17:00:00Z
CRACI cutoff and 31-minute no-admission window remain unchanged. Provider
billing and provider-signed attestation are unknown.
