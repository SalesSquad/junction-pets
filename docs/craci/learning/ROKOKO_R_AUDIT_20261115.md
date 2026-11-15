# Rokoko CRACI — independent R statistics of original TRAIN physics

2026-11-15. NO-GO for model promotion. No new training, physics runs, or hidden holdouts.

## Exact input provenance

- V10: run 43649224059, original ZIP SHA256 c9bd2ae587d16111213ae7f3e142976d39575850605c312d66cc63ce5e125ccb; source 9cc583d3f0f24484b79c1929ba875c7a3b667806; harness a64e6fcc73a1d47485fe052990e31c9d9e45100f; 800 original TRAIN trials, 38,569 option transitions.
- Hybrid: run 43650587631, original ZIP SHA256 286f83c729303a7fe159d68ca494b94f51f685370ffff3e8578cefe62eaf5e0c; source 39f48031f7bff3970516a3c055efe47603e78be5; harness e977ee1eb9c64a3be75b9967e8153f89a7772d76; 640 original TRAIN trials, 24,167 option transitions. Hosted run overall FAILED in post-physics Python/NumPy check; original raw is forensic evidence, not green qualification.
- Python verifies both outer ZIP SHA256 values, original raw pieces and full originals, pinned source/harness, 18-D observation and seven-option mask declarations, 160 complete paired worlds per run, and TRAIN-only/no-test flags.
- No original CRACI source receipt is provider-signed. Cost is unknown. R analysis does not replay physics.

## Same-world V5 comparisons

| Run | World group | N | V5 goals | Candidate goals | New | Lost | Difference pp | Exploratory paired bootstrap 95% pp | Exact McNemar p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v10 | all | 160 | 37 | 26 | 0 | 11 | -6.88 | [-11.25, -3.12] | 0.0009766 |
| v10 | near | 128 | 12 | 10 | 0 |  2 | -1.56 | [-3.91, 0.00] | 0.5 |
| v10 | clear |  32 | 25 | 16 | 0 |  9 | -28.12 | [-43.75, -12.50] | 0.003906 |
| hybrid | all | 160 | 30 | 30 | 0 |  0 | 0.00 | [0.00, 0.00] | N/A (zero discordance) |
| hybrid | near | 128 | 15 | 15 | 0 |  0 | 0.00 | [0.00, 0.00] | N/A (zero discordance) |
| hybrid | clear |  32 | 15 | 15 | 0 |  0 | 0.00 | [0.00, 0.00] | N/A (zero discordance) |

- V10 near/clear exploratory Holm-adjusted p-values: 0.5 / 0.007813. Post-hoc difference in lost V5 wins between clear/near: Fisher exact p < 1e-04. This is hypothesis-generating.
- Hybrid and V10 use DIFFERENT 160-world TRAIN cohorts and are not statistically pooled. Hybrid zero discordance does not establish equivalence on new worlds.
- Bootstrap intervals resample source-selected TRAIN worlds, not robots, deployment scenes or locked dev/test/OOD. P-values are conditional and repeated selection weakens inference.

## Engineering consequence

- V10 loses 11 V5 safe goals and recovers zero: 9 losses in 32 clear worlds and 2 losses in 128 near worlds. Protect V5 goal wins and 250-tick terminal dwell before optimising proxy reopening.
- Hybrid has zero gained and zero lost safe goals against frozen V5. Forward reopening as a proxy cannot establish terminal goal success.
- Do not promote V10, hybrid or V8 or repeat known-negative cohorts. Distinct preregistered fresh TRAIN source and independent physics review would be needed for a new qualification.

Recompute: python3 scripts/craci/rokoko_r_audit_extract.py --v10-zip V10.zip --hybrid-zip HYBRID.zip --output-dir NEW_DIR; Rscript scripts/craci/rokoko_r_science_audit.R NEW_DIR.
