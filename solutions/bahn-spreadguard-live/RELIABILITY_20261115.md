# Bahn reliability study — 15 November 2026

Work ID: `bahn-reliability-20261115`. Stacked on PR #161 at
`957f0c3e2f0e77aef4c9ad045c0b9a9234fecc55`. All executed worlds in this
study are official level-8 **unranked practice** worlds. The simulator's
`score.ranked` flag means the score clears the eligibility rule; it does not
mean that a leaderboard attempt was used.

## Decision and current evidence

The learned risk gate achieved **986/1,001 = 98.50%** on six development
seeds at a 0.05 late-risk threshold. Its gross margin was **€25,234.52**, versus
**€33,560.29** for the frozen 139% / +240-minute baseline. That is a material
service/volume/margin tradeoff, not a free improvement. The worst learned-policy
world was **95.88%**. Development results cannot establish a 98–99% guarantee
on a new world.

The first primary candidate for the untouched five-seed comparison was the learned
policy with threshold **0.05**, chosen to retain a cushion above the requested
98% aggregate service target. The fitted model is frozen; the blind worlds are
not used for fitting, threshold selection, or parser changes.

**Version 1 missed the target on five untouched paired seeds.** It delivered
1,082/1,108 = **97.65%**, versus baseline 1,326/1,401 = **94.65%**. Gross margin
fell from **€33,397.43 to €26,070.09** (−21.94%), with 293 fewer won orders.
Worst-world service improved from 90.87% to 96.08%, but only one of five candidate
worlds reached 98%. Its paired-seed descriptive 95% interval for aggregate
service is **96.98–98.31%**. Improvement is supported; 98–99% qualification is not.

After that failure, a separate safety version at threshold **0.02** was evaluated
on the original six development seeds, without refitting the model. It produced
696/702 = **99.15%**, worst world 97.27%, with **€15,716.68** margin. That rejects
45.20% of baseline won volume and loses 53.17% of baseline margin on development.
Its five fresh confirmation seeds are declared in
`reliability_plan_20261115_safety.json`; version 1's blind results remain intact
and are not reused as fresh confirmation. This is an adaptive second version,
not one prespecified experiment with a global 95% guarantee.

**Version 2 confirmation and the conditional fork experiment: pending at this
checkpoint.**

## Official development experiments

All rows use the same six development seed groups declared in
`reliability_plan_20261115.json`. They are six scenarios, not six independent
scenarios per policy. The learned policies are evaluated on their training seed
groups here, so their figures are explicitly developmental.

| Policy | On time / won | Service | Worst world | Gross margin |
| --- | ---: | ---: | ---: | ---: |
| Frozen baseline | 1,236 / 1,281 | 96.49% | 95.00% | €33,560.29 |
| Deadline option choice | 1,237 / 1,282 | 96.49% | 95.00% | €33,703.81 |
| Observable capacity | 1,168 / 1,203 | 97.09% | 96.34% | €32,165.84 |
| Notes, pre-fix v2 experiment | 1,240 / 1,283 | 96.65% | 94.88% | €34,092.77 |
| Trust pricing | 1,240 / 1,288 | 96.27% | 94.62% | €34,457.01 |
| Learned risk ≤0.05 | 986 / 1,001 | 98.50% | 95.88% | €25,234.52 |
| Learned risk ≤0.075 | 1,078 / 1,100 | 98.00% | 96.46% | €28,972.32 |
| Safety version, learned risk ≤0.02 | 696 / 702 | 99.15% | 97.27% | €15,716.68 |

The 0.075 threshold was an additional, adaptive **development** experiment
after the large margin cost of 0.05 became visible. It is not a blind result.
The 0.05 candidate sacrifices 280 won orders (21.86%) and €8,325.77 margin
(24.81%) against baseline on these seeds. A competition decision must consider
that cost: the sponsor's objective is gross margin subject to at least 90%
on-time service in each scored world. The owner's 98–99% target is stricter.

The capacity change's paired-seed 95% descriptive bootstrap interval for its
service difference is −0.36 to +1.72 percentage points. Its margin difference
interval is entirely negative (−€2,333.31 to −€430.63 across six worlds).
Deadline's small margin gain comes from one pair; the other five pairs have
identical scalar outcomes. Neither establishes the requested service target.

## What was implemented

### Observable state and admission

`reliability_experiment.py` preserves an explicit frozen baseline and adds
isolated deadline, capacity, learned-risk, and trust-pricing ablations.
The capacity lane fixes a concrete SDK integration defect: completed orders
can retain an old status in the starter's local book, so outstanding work must
be determined from `deliveredAt`, not status alone. It also filters observable
driver eligibility, accounts for pending quote reservations, and includes the
age of currently unbooked work. A booking drop starts a new unbooked interval;
time already spent booked is not treated as booking wait.

These are public-state decisions. Driver home positions remain an imperfect
fallback when observed positions become stale. A pending quote reservation is
planning capacity, not an actual driver assignment. The current waiting-time
feature is an observed lower bound, not a fitted survival quantile.

### Typed note constraints

`typed_notes.py` returns nullable facts, supporting text, unknown clauses and
ambiguities. It handles a bounded FI/SV/EN grammar for readiness, payment release,
opening hours, deadlines, manual transmission, plates and tyres. It abstains
on unscoped multi-leg notes and preserves recurring hours as structured data.
`evaluate_notes.py` measures field precision and coverage against completed
official reveals; unknowns are not counted correct.

The whole historical cohort contains 2,748 revealed won orders including
subsequent cancellations, of which 1,125 have notes. Parser v2 produced 373
correct evaluated field assertions, 32 nonbinding deadline assertions and zero
false assertions in that development cohort. Coverage is limited, and the
grammar was repaired using errors from these same worlds; this is not unseen
parser accuracy or delivery success.

Independent review subsequently found a separate downstream safety defect:
`Manual gearbox, not before 16:00.` could recognize the gearbox while silently
leaving the clock unconsumed. Clearing the original note then removed the
baseline pickup bound. The v2 live notes trial is retained as **pre-fix
experimental evidence and is not promoted**. The repaired parser v3 retains
baseline behavior for unconsumed timing. A dedicated regression checks
both the actual posted window and quote slack.

The opt-in `NotesDesk` initially applies only fully supported readiness,
release, manual and plates facts. Unknown or unsupported notes fall back to
baseline. It emits narrower stop windows relative to the original official
order, so a locally changed copy cannot accidentally hide the constraint from
the actual API action. It keeps separate counts for eligible notes, added
constraints and genuinely changed wire actions.

### A fitted R risk model

`fit_reliability.R` fits ridge logistic regression using base R. This is a real
trained model, not a neural network. Its 16 features are recorded **before
quoting**; completed-world reveals and ledger data supply outcome labels only.
No end-of-world snapshot is used to reconstruct predictive state.

The initial model uses 3,766 rows, 125 late/undelivered outcomes, 18 policy
worlds and six seed groups. Every label total reconciles with the official
score. All worlds from a seed stay together in cross-validation; centering and
scaling are fitted separately within each training fold. The selected ridge
penalty is 10. Grouped out-of-fold AUC is **0.7308**. Equal-world log loss is
**0.134925**, versus **0.148058** for an intercept-only control; Brier score is
**0.030971**, versus **0.032671**.

Model SHA-256:
`33115ca3e7ca4d4520785955e0be92b9aecdc68f9f78fb4bcaa347541f971675`.
Training source: `31f7ae2098f3cee1800d1dec772b6836f46e4e34`.
The original CSV bytes, model, source identities and SHA-256 manifest are in
`evidence/reliability-20261115/development_initial/` and its parent folder.

The model estimates risk conditional on the source policies winning an order.
It does not identify outcomes for all previously rejected requests. Selecting
the penalty on cross-validation makes the selected CV score developmental;
the six later learned-policy runs use the same seed groups. Their service
figures therefore require the separate untouched comparison below.

### Reproducible official experiments

`official_study.py` records source hashes, effective configuration, model
hash, decision-time feature rows and world IDs. It exposes practice and
read-only export commands. `reliability_campaign.py` bounds concurrency to
three workers and enforces the predeclared source/model/threshold freeze for
blind campaigns. Each child validates the campaign manifest before creating or
resuming a world, rechecks source at the end, and the campaign checks its returned
receipt. Effective model/threshold defaults become explicit child arguments;
conflicting environment overrides are removed. A world-creation intent is durable before the request;
uncertain creation requires reconciliation instead of silent recreation.

`evidence_dataset.py` reconciles labels with exact official won/on-time
counts, excludes canceled orders, validates the chosen option/last quote and
binds each dataset partition to its run receipt and bundle digest. Direct
order-specific failed visits are not attributed to every order in a shared
gig. Failure flags are overlapping associations, not causal attribution.

`evaluate_reliability.R` compares complete matched seed groups and bootstraps
whole pairs. It reports service, worst-world service, margin, volume and
eligibility together. It does not assume that thousands of orders are
independent trials and never automatically promotes a policy.

`fork_study.py` creates two children from an owned, paused unranked practice
world. Both child identities and equal public starting state are recorded
before either runs. It uses the sponsor's same-future contract, reconstructs
state from history, and deduplicates the history repeated on the first child
advance. Both policies finish before their reveals are inspected. This is one
conditional comparison, not two independent validation seeds. Prefix orders
without child decision-time features are not a complete training dataset.

## Historical failure inventory

The prior frozen candidate produced 2,596/2,711 on time, with 115 failures.
Forty failed orders had a failed visit: 19 not ready, 12 missing plates and
nine closed sites. Ninety-two had a deadline warning and 32 a driver drop;
these groups overlap. Nine orders remained undelivered. All ten historical
worlds reconcile exactly with official scores.

The newly instrumented baseline reproduced the first historical seed exactly:
319/333 on time and **793,697 cents** margin. This verifies that instrumentation
preserved the frozen strategy on that official comparison.

## Reproduction

Use the official `spread==0.1.0` SDK; the inspected wheel SHA-256 is
`74f93ba5acd17edc17e484bb5ad5a6a200689587461374eb2b13f8af5a214b1c`.
Supply credentials through the existing authorized host-side mechanism. No
credential value belongs in source, datasets, artifacts or command logs.

```bash
python official_study.py run \
  --seed YOUR_NEW_DEVELOPMENT_SEED --policy learned --partition development \
  --model evidence/reliability-20261115/development_initial/model.json \
  --late-threshold 0.05 --output /absolute/new-run-directory

python evidence_dataset.py --input /absolute/completed-runs \
  --output /absolute/new-analysis-directory

Rscript evaluate_reliability.R --input /absolute/paired-results.csv \
  --output /absolute/comparison.json --baseline baseline --candidate learned \
  --draws 20000
```

Historical worlds without live feature records remain a separate failure
inventory. The R training/evaluation tools accept development/blind partitions;
do not relabel historical data blind. The fork world is also kept separate from
the fresh-seed comparison.

## Operational record and handoff

Initial development source: `31f7ae2098f3cee1800d1dec772b6836f46e4e34`.
Second development source: `4fe55abc5d607dbf530e4865093b3c16cd5ecacb`.
Portable checks ran against the pinned SDK in the cloud, and the Mac execution
milestone passed 102 targeted checks. Actual fitting/evaluation used R 4.6.2 on
the authorized Mac. Tests establish implementation contracts, not delivery
performance. Final source verification is recorded with the delivered commit.

The sponsor returned HTTP 502 during one baseline development run. Its receipt
and world were preserved, then the same world was resumed to completion. A
fresh uninterrupted control on the same seed replaced it in the paired
analysis; the interrupted/resumed evidence remains outside the training input.
No failed evidence was rewritten to appear as an uninterrupted run.

This study is delivered through a task-owned draft PR stacked on #161. The
Portfolio PR Recovery owner remains the integrator. A leaderboard/final entry
and merging/releasing are separate decisions. No final-world result is claimed.

Sponsor sources: [rules](https://spread.bahnexpress.com/kit/RULES.md),
[handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md),
[API](https://spread.bahnexpress.com/kit/API.md).
