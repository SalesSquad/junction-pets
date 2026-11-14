# CRACI Meta R — 2x hard-shift study (14 Nov 2026)

Work ID CRACI-META-R-HARDSHIFT-2X-20261114; stacked on PR #163. Other CRACI qualification PR #157 has a separate source writer. Sole integrator: Portfolio PR Recovery. No merge/deploy.

Existing hosted baseline: run 43627971042 completed 8 cohorts, 240k synthetic numeric feature observations, 32 R fits; run 43628887582 completed 12 cohorts, 420k observations, 48 fits, with only two unadjusted exploratory positive signals. Neither was promoted.

New independent question: Does training/calibration on a mixture of normal and shifted numeric examples survive deliberately *harder, previously unobserved synthetic feature-score shift*?

- 24 new cohorts, each 4 vCPU, max six concurrently (leaves two slots against the eight-job coordination limit), 20 min/job.
- Per cohort: 10,000 normal + 10,000 shifted train; 5,000 shifted calibration; 5,000 hidden synthetic hard-shift holdout; 5,000 normal-domain holdout. TOTAL 840,000 independent synthetic observations; 96 fitted R model variants if 24 jobs complete.
- Each cohort gets five separate source seeds between 2.1M and 3.0M; none overlaps earlier 8+12 R cohorts or original model. Exact model source pinned at 634f1e0e6cb2de46bcf0a783532d46c23f513d11.
- Four fixed hidden stress variants rotate by cohort modulo four. Synthetic negative score pairs become more confusable; true positives lose one score dimension. Labels influence TEST stress synthesis only and are NEVER used for learning, threshold selection or calibration. This is an adversarial *synthetic* comparison, not a real camera distribution.
- Fit main/interaction binomial GLMs and rpart depth-3/depth-5. Select ONLY on shifted calibration with FPR not exceeding calibrated baseline and improved recall.
- Heldout positive claim requires higher recall, no increase in overall or hard-negative false-candidate rate, normal FPR at most baseline +1 pp, AND positive Bonferroni familywise lower bootstrap bound across 24 comparisons (two-sided 5% familywise alpha; 12,000 resamples/cohort). Separate descriptive 95% CI remains.
- Do not rerun previous green or failed identical source/hypothesis/seed tuples. Preserve every failure as evidence; only repair concrete harness/source issues. No promotion, production use, model API calls or private camera data.

Existing manual workflow #417767938, CRACI credit flag and 15 Nov 2026 17:00 UTC stop are unchanged. The conservative maximum list-price estimate is 24*4*20*EUR0.0017 = EUR3.264, plus one 2-vCPU*5min planner EUR0.017, total EUR3.281. Actual provider billing and signed provider attestation are UNKNOWN; compare worst-case queue/inflight reservations and other known jobs against existing EUR1000 credit authority before admission. No new cash or top-up. Release claims require real licensed/consented visual/device acceptance.

Dispatch only once from verified current HEAD:

gh workflow run craci-pilot.yml -R SalesSquad/junction-pets --ref codex/craci-meta-r-hardshift-2x-20261114 -f workload=meta-r-hardshift-2x -f source_sha=634f1e0e6cb2de46bcf0a783532d46c23f513d11

Audit after artifacts arrive, without overwriting other evidence:

python3 scripts/craci/meta-r-hardshift-audit.py --root FRESH_DIR --out FRESH_SUMMARY --harness-sha FULL_HEAD --run-id RUN_ID

A run passing proves only source-bound synthetic scoring/training, not real-world safety, identity or consent.
