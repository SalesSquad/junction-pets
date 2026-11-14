# CRACI R ML Tournament — source-bound CPU experiment

Work ID: `CRACI-R-TOURNAMENT-20261114`.
Branch: `codex/craci-r-policy-tournament-20261114` (stacked on Chaos Lab PR #150).
**Not an extension of the CRACI Immune / Chaos Lab three-hour campaigns**, which close at 2026-11-14 18:00 UTC. This is a new owner-requested exploration using the still-authorized Junction CRACI credit window (separate shutdown 2026-11-15 17:00 UTC).

## Objective and scientific hypothesis

Rokoko CPU Double-DQN was previously trained on CRACI, but an independent held-out ablation found no improvement over PUSH_MEDIUM. This experiment trains alternatives rather than repeating passing suites. The goal is to see whether a **contextual selector** between two existing shielded policies outperforms constant PUSH_MEDIUM without increasing simulated unsafe episodes.

We use the pinned **actual MuJoCo simulator** SHA `59479b42b177c1829a2e6678adfff1fb68aef09c`, not an imitation environment. Each of four disjoint cohorts uses paired identical worlds for PUSH_MEDIUM and the pinned heuristic. Initial observation vectors only (18 state features; no outcomes, future events or world seed) are predictors. All code and model execution are pinned to the experiment harness Git commit and the simulator commit independently.

| Split | Worlds per cohort | Seed group (cohort offset 3000) | Purpose |
| --- | ---: | --- | --- |
| train | 80 | 270000 | Fit binomial GLM and rpart models for success and safety |
| cal | 40 | 370000 | Select a policy selector, or retain baseline if worse |
| test | 60 | 390000 | Fresh paired results and bootstrap 95% success difference |
| ood | 40 | 490000 | Shifted friction/mass/obstacles; safety regression check |

A cohort generates 440 actual simulator rollouts; four parallel cohorts cover **1,760 rollouts / 880 unique worlds** if all complete. This is deliberately small for a first live R compatibility test, not a claim of massive training throughput. Benchmark pairs share per-world dynamics but the four splits and cohorts do not overlap. Original simulated shield remains in force for every policy; selector cannot issue unmasked actions.

R runs both `glm(..., family=binomial())` and `rpart` classification for outcome likelihoods. The selector scores candidate policies as predicted success minus five times predicted unsafe probability. The calibration gate admits a learned selector only when simulated unsafe count is no greater than the PUSH_MEDIUM comparator and either success improves or unsafe count is lower. Fresh test and OOD are never used to choose the candidate. Report success, unsafe, 1,200 paired bootstrap draws and exact seed/range. **Negative results are retained.**

## Execution and bounds

- Existing manual `.github/workflows/craci-pilot.yml` gains opt-in `workload=rokoko-r-tournament`; no PR/main automatic execution.
- Matrix: 4 independent cells × 8 CRACI vCPU / 24 GB memory, 30-minute hard timeout; `max-parallel: 4`. CRACI's actual concurrent quota and credit remain subject to provider checks, not inferred from owner statement.
- Network: default deny; only `github, pypi, ubuntu` presets, needed for pinned MuJoCo/npm-free Python and `r-base-core, r-cran-rpart, r-cran-jsonlite`. No keys, no secrets, no production traffic.
- Immutable checkout and existing `run-receipt.mjs` command/manifest plus GitHub artifacts. No automated deployment or PR merge.
- If all jobs use 8 vCPU × 30 minutes (plus a 2-vCPU × 5-minute planner), **worst-case usage estimate ~$1.94** using CRACI's public $0.002/vCPU-minute. Actual price, promotional credits, metering and provider bills are unknown. No cash/top-up or new vendor agreement.
- Scientific limitations: synthetic physics, only 80 train worlds per cohort, broad confidence intervals, no robot hardware safety validation; frozen simulator may not reflect product source after subsequent PRs.

## Evidence to verify

1. Confirm exact PR/harness head and simulator SHA, R and MuJoCo package versions.
2. Four cohort jobs should end in success and each produce a source-bound, non-expired artifact plus a dataset digest, trained `.rds` weights and test/OOD report.
3. Summarize model selection and paired bootstrap intervals **per cohort**; do not average across all simulations without a hierarchical/statistical rationale.
4. If the runner lacks a permitted `apt` or PyPI route, classify it as an environment failure and repair only runner setup; never claim trained output.
5. Preserve actual failed receipts, do not repeat unchanged successful cohorts or assume the old campaign's spending limit has been extended.

Direct project owner: Portfolio PR Recovery for integration; task branch writer owns only `scripts/craci/rokoko-r-*`, `plan.mjs` additive workload, and this single CRACI workflow job.

## Hosted pilot #1 and correction

[CRACI run 43625113313](https://github.com/SalesSquad/junction-pets/actions/runs/43625113313), harness `b304793b8b2066bfc1f86cae0b0c49936ced22c7`, admitted four 8-vCPU cells with exact simulator SHA. All four **failed during R installation**, before simulation/training. The source is **not qualified**: the Ubuntu 24.04 image includes a Microsoft apt repository; under the approved `[github,pypi,ubuntu]` egress policy its InRelease fetch returned 403, making `apt-get update` fail. This was an environment dependency issue, NOT a trained model result or reason to open egress.

Correction restricts apt package lists to the image's existing `/etc/apt/sources.list.d/ubuntu.sources`, retaining CRACI's default-deny network policy. A new source-harness SHA and new cloud run are required; first run remains failed evidence and must not be overwritten.

## Hosted pilot #2 and R class-collapse fix

[CRACI run 43625356365](https://github.com/SalesSquad/junction-pets/actions/runs/43625356365) at harness `58c05be04e493475cadc195284c6cc16c4719fe1`: R **4.3.3** and `rpart`/`jsonlite` installed successfully using Ubuntu-only repositories. Four simulated cohorts each generated a source-pinned dataset of **220 worlds × two policies** (cohort 0 finished in 51.5 seconds). R then failed with `rpart(...): number of rows of matrices must match` because a classification target had only one observed class. This is scientifically meaningful (zero positives, or no class variation) and MUST NOT be fixed by inventing labels, changing seeds, or hiding data.

The next source revision explicitly uses a constant-probability model when a target contains only one class, records which GLM/rpart heads truly fitted versus were constant fallbacks, and records success/unsafe class counts. The synthetic dataset is also preserved as a ZIP plus SHA-256 to allow independent review; no private data is included. Script syntax is checked on the CRACI runner before costly physics rollouts. Old failed receipts are preserved.

## Hosted pilot #3 — modeling worked, evidence rejected

[CRACI run 43625929337](https://github.com/SalesSquad/junction-pets/actions/runs/43625929337), source harness `aaebb1f3b9bc7b21b783fd2d18b7152e526fa8c9`, generated actual paired MuJoCo datasets and executed R 4.3.3 models for all four cohorts. Cohort 0 selected fixed `push_medium` after calibration: fresh test **36/60 successes and 0 unsafe**, OOD **4/40 successes and 0 unsafe**; heuristic was weaker (test 2/60, OOD 1/40). Negative scientific result preserved; no deployment-worthy improvement. All four hosted jobs were marked **failure** at receipt finalization (`ARTIFACT_COLLECTION_INCOMPLETE`) despite stage training success, because the source-verified collector intentionally rejects raw `.csv` and `.rds` files under `artifacts/`. Receipt evidence level remains source-reported, not provider-attested.

Next fix moves unapproved raw files into a temporary private runner scratch directory, keeps only approved `dataset-receipt.json`, `training-report.json` and `training-evidence.zip` in `artifacts/`, and archives exact CSV + RDS + JSON inside the ZIP. The existing artifact extension allowlist, source checks, limits, and negative observations are preserved, not loosened. A new harness SHA and fresh source-bound run are required to qualify artifact completeness.
