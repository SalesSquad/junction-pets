# Bahn reliability study — 15 November 2026

Work ID: `bahn-reliability-20261115`. Stacked on PR #161 at
`957f0c3e2f0e77aef4c9ad045c0b9a9234fecc55`. All executed worlds in this
study are official level-8 **unranked practice** worlds. The simulator's
`score.ranked` flag means the score clears the eligibility rule; it does not
mean that a leaderboard attempt was used.

## Decision and completed confirmation

The frozen learned risk gate at threshold **0.02** delivered **564/567 = 99.47%**
on five fresh confirmation seeds. The paired frozen 139% / +240-minute baseline
delivered **995/1,033 = 96.32%**. This meets the requested aggregate percentage
in the observed sample, with a substantial commercial cost: **45.11% fewer won
orders and 51.28% less gross margin**. There were also 431 fewer on-time
deliveries in absolute terms. The candidate improved the percentage in every
pair and reduced margin in every pair.

| Fresh confirmation, five paired seeds | Frozen baseline | Learned risk ≤0.02 |
| --- | ---: | ---: |
| On time / won | 995 / 1,033 | 564 / 567 |
| Aggregate service | 96.32% | **99.47%** |
| Late orders | 38 | 3 |
| Worst world | 94.38% | **97.87%** |
| Worlds at least 98% | 0 / 5 | 4 / 5 |
| Worlds at least 99% | 0 / 5 | 4 / 5 |
| Gross margin | €28,278.68 | **€13,778.23** |

**Recommendation:** keep the strict policy as an explicit service-priority
option. Do not automatically replace the competition default: the sponsor
maximizes gross margin subject to at least 90% service in each scored world,
and both policies cleared that rule in all five confirmation worlds. Losing
€14,500.45 of margin to raise the percentage is a poor trade for that objective
on these observations. The strict policy does not establish 98–99% in every
world, or a guarantee for the secret final world. No leaderboard/final entry
was made and no policy was automatically promoted.

The model was trained once on six development seed groups. No blind or
confirmation outcomes were added to training. Threshold 0.02 is a decision
score cutoff, not a certified 2% per-order risk bound.

### Version history and the failed first qualification

The first primary candidate used threshold **0.05**, after achieving
986/1,001 = 98.50% on the six development seeds, with €25,234.52 margin versus
€33,560.29 baseline and a 95.88% worst world. Those were training scenarios,
so an untouched comparison was required.

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

### Version 2: fresh paired confirmation

The second version was frozen at source
`fa2c3b7fe3f6a9bbb4ba834b2902ad861e6af1ab`, using the original model and threshold
0.02, before creating any confirmation world. The seed prefix below is
`bahn-reliability-confirm-20261115-`; all five seeds are disjoint from the six
training seeds and the five version-1 blind seeds.

| Seed suffix | Baseline on time / won | Candidate on time / won | Baseline margin | Candidate margin |
| --- | ---: | ---: | ---: | ---: |
| 01 | 211 / 217 (97.24%) | 125 / 125 (100%) | €7,194.47 | €3,437.02 |
| 02 | 249 / 255 (97.65%) | 125 / 126 (99.21%) | €7,219.59 | €3,092.20 |
| 03 | 80 / 84 (95.24%) | 38 / 38 (100%) | €2,883.77 | €1,202.20 |
| 04 | 304 / 317 (95.90%) | 184 / 184 (100%) | €6,984.29 | €4,182.88 |
| 05 | 151 / 160 (94.38%) | 92 / 94 (97.87%) | €3,996.56 | €1,863.93 |

The 20,000-draw paired-seed bootstrap gives a descriptive 95% interval of
**98.65–100%** for candidate aggregate service and **+2.09 to +4.10 percentage
points** for the service improvement. The point improvement is +3.15 points.
The candidate's one-sided 95% lower bound is 98.74%. The corresponding total
margin difference interval is **−€18,571.09 to −€10,429.81**.

Only five scenarios and three candidate late outcomes underpin those intervals.
They describe resampling of this limited sample. They do not establish 99%
population service, 98% in every world, or a global prespecified 95% claim across
the adaptive versions. The fifth candidate world itself falls below 98%.

Original binary CSV, exact R output, dataset reconciliation, effective freeze
and ten selected run receipts are retained in
`evidence/reliability-20261115/confirm_v2/`. The effective freeze SHA-256 is
`34458043449b978e644c29e2a0d06ef33e908aea8ee7d40beb1af4189b88987d`.
Each receipt binds its configuration, source, model and raw bundle digest.
Independent R review reconciled all counts, input hashes and disjoint splits.
The coordinator additionally rehashed the raw bundles on the execution host.

### Same-future fork experiment

One additional parent practice world, `w9c80405de6143e9eac90`, was paused at
minute 1,440 of 14,280. Its public snapshot and history were hashed before two
children were created. Both children started from the same public state and
the sponsor's documented same-future contract, and both completed before any
reveal was inspected.

| Child | On time / won | Service | Gross margin |
| --- | ---: | ---: | ---: |
| Baseline, `w7e9544e09e16e271cf82` | 182 / 187 | 97.33% | €5,877.25 |
| Learned ≤0.02, `w5824febe43379fa67fda` | 147 / 150 | 98.00% | €4,160.38 |

This conditional comparison improves service by 0.67 percentage points and
reduces margin by €1,716.87, with 37 fewer orders. It is one shared-prefix
scenario, not two new independent validation scenarios. Both children retain
orders accepted in the common prefix. The parent was subsequently completed;
its baseline score exactly matches the baseline child. No unfinished
task-created practice world remains. Bounded receipts and bundle digests are
retained under `evidence/reliability-20261115/fork_safety/`.

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

Parser v3 was checked again against the same historical cohort with zero false
field assertions; this remains a development check. The delivered learned
policy does not enable the experimental notes adapter, so its confirmation
score is not a qualification of that adapter.

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
Run the commands from `solutions/bahn-spreadguard-live/`. The following starts
one new unranked practice world with the strict service-priority option:

```bash
python official_study.py run \
  --seed YOUR_NEW_DEVELOPMENT_SEED --policy learned --partition development \
  --model evidence/reliability-20261115/development_initial/model.json \
  --late-threshold 0.02 --output /absolute/new-run-directory

python evidence_dataset.py --input /absolute/completed-runs \
  --output /absolute/new-analysis-directory

Rscript evaluate_reliability.R --input /absolute/paired-results.csv \
  --output /absolute/comparison.json --baseline baseline --candidate learned \
  --draws 20000
```

To reproduce the reported confirmation analysis without creating any world:

```bash
Rscript evaluate_reliability.R \
  --input evidence/reliability-20261115/confirm_v2/results.csv \
  --output /absolute/confirmation-recheck.json \
  --baseline baseline --candidate learned --draws 20000 --seed 20261115 \
  --source-sha fa2c3b7fe3f6a9bbb4ba834b2902ad861e6af1ab
```

Existing campaign receipts are bound to the actual execution commit, not a
later documentation commit. Reproducing that exact campaign requires source
`fa2c3b7fe3f6a9bbb4ba834b2902ad861e6af1ab`. For a new experiment, use new output
and seed names and a new explicit freeze; do not edit an old receipt to make a
different source appear equivalent. A later evidence-only delivery commit
leaves the decision code and model bytes unchanged.

Historical worlds without live feature records remain a separate failure
inventory. The R training/evaluation tools accept development/blind partitions;
do not relabel historical data blind. The fork world is also kept separate from
the fresh-seed comparison.

## Operational record and handoff

Initial development source: `31f7ae2098f3cee1800d1dec772b6836f46e4e34`.
Second development source: `4fe55abc5d607dbf530e4865093b3c16cd5ecacb`.
First blind source: `74c551ede77caa613c1a5166f0a4f293318a9c89`.
Safety confirmation and fork source:
`fa2c3b7fe3f6a9bbb4ba834b2902ad861e6af1ab`.
Portable checks ran against the pinned SDK in the cloud. The final executable
source passed **114 targeted Python tests** on the Mac; the real R fitting and
evaluation also completed with R 4.6.2. The source/model/threshold freeze was
checked in every confirmation child before and after its run. Independent
review verified the freeze fixes and all ten confirmation receipts. Tests
establish implementation contracts, not delivery performance. The delivery
PR records final-HEAD checks separately from hosted CI status.

The owned run inventory contains **73 unique new official practice world IDs,
all completed**: one baseline parity run, 18 initial development runs, one
preserved interrupted/resumed run, 18 additional policy runs, six 0.075 runs,
ten version-1 blind runs, six 0.02 development runs, ten fresh confirmation
runs, and the fork parent plus two children. The ten historical exports are
pre-existing and are not counted as newly created worlds. Repeated policies,
repeated seeds and fork children do not multiply the number of independent
scenarios.

In the confirmation campaign the simulator rejected 16 baseline actions and
zero candidate actions; both policies nevertheless completed all five worlds.
The runner records rejection counts, not all rejected-response reasons. Do not
describe these as error-free runs or infer a cause without the missing response
detail. Each fork child had one rejected action. The maximum observed event
handler time was approximately 556 ms across confirmation; that measurement
can include synchronous SDK network calls and is not a final-environment
latency guarantee.

The sponsor returned HTTP 502 during one baseline development run. Its receipt
and world were preserved, then the same world was resumed to completion. A
fresh uninterrupted control on the same seed replaced it in the paired
analysis; the interrupted/resumed evidence remains outside the training input.
No failed evidence was rewritten to appear as an uninterrupted run.

This study is delivered through [draft PR #233](https://github.com/SalesSquad/junction-pets/pull/233),
stacked on #161. The Portfolio PR Recovery owner remains the integrator. The
task worktree and raw evidence are retained for imminent reproduction; pushed
commits preserve the implementation and bounded evidence. No unrelated work
or failed receipt was discarded. External call costs were not metered and
remain unknown. A leaderboard/final entry and merging/releasing are separate
decisions. No final-world result is claimed.

Sponsor sources: [rules](https://spread.bahnexpress.com/kit/RULES.md),
[handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md),
[API](https://spread.bahnexpress.com/kit/API.md).
