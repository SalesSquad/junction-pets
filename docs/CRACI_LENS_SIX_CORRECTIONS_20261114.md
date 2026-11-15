# CRACI Lens: six preregistered corrective ML rounds (14 Nov 2026)

Work ID: CRACI-LENS-SIX-ML-20261114. Uses the existing CRACI workflow #417767938, no new provider, webhook or daemon, and no main branch direct push. The user asked for six actual correction/learning rounds. These are SIX DISTINCT, PREDECLARED MODEL TRAINING ARMS evaluated without tuning to their shared test outcomes, **not** sequential automatic promotion or six replays of a previous passing job.

Source: MIT-licensed public BOP YCB-Video real RGB object crops transformed locally into 48 numeric-only features. Exact archive SHA256 c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d, fixture CSV SHA256 c2374f53bc510b6655623f5fa05bb23d08bd1531f24b0aa4e2bcdccab11899a6. No original RGB pixels, faces, private screenshots, OCR, family recordings, device metadata, API keys or private profiles are exported to the runner. Each job re-runs the existing fail-closed public-source gate. Four YCB object class IDs are labels, NOT unique physical identities or permissions.

All rounds use the unchanged **580 training / 375 separate calibration / 300 heldout** crops, split by distinct real video scenes. The heldout test has **75 independent frames**, so the paired bootstrap resamples FRAME groups, not correlated crops as if they were independent. Each arm calibrates its wrong accepted classification fraction using only calibration (5% cap; round 6 tightens to 2.5%). Test is evaluated once only after each model/threshold is frozen. There is no winner selected using shared heldout data. Every arm compares to a deterministic train-only nearest-centroid baseline with exactly the same calibration opportunity. Bonferroni familywise 95% paired bootstrap across all six variants is required for even a scoped exploratory positive. Unqualified results remain visible and are not reasons to weaken the gates.

Six algorithmic training hypotheses:
1. Class-balanced supervised softmax — reduce minority-class wrong acceptance without changing labels.
2. Occlusion/visibility weighted softmax — train with heavier weight on hard partly-occluded objects, without treating visibility as test-time authorization.
3. Lighting-normalized color descriptors — reduce illumination dependence through fixed per-channel normalization before fitting.
4. Combined spatial and gradient features plus one global color signal — avoid pure color dependence.
5. Cross-modal color/spatial interaction descriptors — test whether paired texture/geometry cues improve heldout discrimination.
6. Cost-sensitive label-smoothed softmax with conservative 2.5% wrong-accept calibration and stronger weight decay — prefer abstention to risky acceptance.

Each round uses its own fixed training shuffle seed and source-verified code, 115 SGD training epochs, weights/report JSON and immutable per-job CRACI receipt. No runtime integration, real Meta glasses recognition or external device control is claimed. This is a limited internal four-class single-scene experiment, not an official BOP metric or licensed production detector.

Resource admission: six distinct CPU2 CRACI jobs, at most six simultaneous; up to 18 minutes each. Conservative public list-price reservation: 6×2×18×EUR0.0017 = EUR0.3672, plus one 2vCPU×5min planner = EUR0.017, total **EUR0.3842**. Actual bill and provider-signed attestations are unknown. Check the already-approved EUR1000 existing-credit authority, current account load and CRACI_CREDIT_WINDOW_OPEN before dispatch. The established 15 Nov 2026 17:00 UTC cutoff and all hard-stop boundaries are unchanged; no cash/top-up is authorized.

The only dispatch is the existing fixed manual workflow with workload=lens-six-ml, at a newly verified exact source commit. No repeat on unchanged passing source/arm/split. Preserve all failed scientific receipts and training outputs. For actual generalization, next source owner needs independent rights-cleared devices/visual scenes; no result here suffices for real user authorization.
