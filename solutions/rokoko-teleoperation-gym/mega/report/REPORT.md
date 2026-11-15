# Rokoko MotionBridge — large, actual MuJoCo physics campaign

Frozen executed source SHA: ec5dce6d21cd64b4d7d647bce124fb6b5c2543b0
Actual independent world/scenario seeds: 1500
Actual completed MuJoCo physics episodes: 6000
Actual 2 ms physics solver steps: 18,000,000
R paired-bootstrap replicates (NOT physics episodes): 20000
Raw CSV shards / SHA256 matched: 3

## Verified controller outcomes

aligned_replay: 5/1500 strict safe (0.3%, Wilson 95% 0.1–0.8%), 183 unsafe, 70 damaged, 87 object-obstacle, 124 pusher-obstacle episodes.
contact_feedback: 318/1500 strict safe (21.2%, Wilson 95% 19.2–23.3%), 90 unsafe, 8 damaged, 89 object-obstacle, 0 pusher-obstacle episodes.
guarded_feedback: 318/1500 strict safe (21.2%, Wilson 95% 19.2–23.3%), 1 unsafe, 1 damaged, 0 object-obstacle, 0 pusher-obstacle episodes.
safe_abstain: 0/1500 strict safe (0.0%, Wilson 95% 0.0–0.3%), 0 unsafe, 0 damaged, 0 object-obstacle, 0 pusher-obstacle episodes.

Contact feedback minus aligned replay: 20.87 percentage points (stratified paired bootstrap 95% CI 20.07 to 21.67 pp); exact two-sided paired p=3.3768e-87.

## Boundaries

- The four controllers are scripted, NOT trained reinforcement learning.
- The inputs are invented glove-derived progress and synthetic noisy camera observations.
- Object and pusher dynamics, forces, collisions, failure flags and dwell are actual MuJoCo calculations.
- Strict analysis additionally penalizes pusher-only obstacle collisions.
- Fragility impulse thresholds are deliberately toy physics, not hardware calibration.
- Paired bootstrap samples scenario IDs in predeclared strata; draws are R resamples, not robot trials.
- No claim of real Rokoko SDK, physical robot safety, NVIDIA GPU, Google DeepMind Playground or actual human intervention.
- API/model calls: NONE; no new paid compute. All raw failures remain in the source-pinned CSVs.

## Artifacts

Raw campaign-shard CSVs plus exact data/source SHA256 manifests in results/.
policy_summary.csv, paired_bootstrap.csv, regime_summary.csv,
impulse_sensitivity.csv, success_by_regime.png, unsafe_by_regime.png.


## Shift robustness: object-centred feedback

nominal: 293/300 strict successes (97.7%); 0.0% unsafe episodes.
lateral_shift: 11/300 strict successes (3.7%); 0.0% unsafe episodes.
friction_mass: 12/300 strict successes (4.0%); 0.3% unsafe episodes.
sensor_dropout: 2/300 strict successes (0.7%); 0.0% unsafe episodes.
adversarial: 0/300 strict successes (0.0%); 29.7% unsafe episodes.

Each of five regimes is equally weighted by benchmark design.
Strong nominal success must not disguise near-zero shifted-world robustness.
The replay baseline is a single fixed demonstration, not an optimal policy.
No comparison here demonstrates trained RL or real robotics generalization.
Next: a learned CPU option-value baseline and pre-registered new OOD cases.
