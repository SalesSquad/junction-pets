# Junction 2026 — CRACI maximum useful campaign, 14 November 2026

Private SalesSquad/junction-pets; draft integration PR [#138](https://github.com/SalesSquad/junction-pets/pull/138). Manual-only workflow 417767938 and credit flag. Existing stop remains 15 Nov 2026 at 17:00 UTC (19:00 Helsinki). No new credit purchase, no keys moved. Actual billed euros/remaining credit unknown.

## New source-bound CRACI evidence

| Product | Exact source SHA | Run | Qualified scope |
|---|---|---|---|
| Valio existing browsers, new source | d45f450a38ec6c8fb2f73b96d181454458ae3928 | [43599103132](https://github.com/SalesSquad/junction-pets/actions/runs/43599103132) | Existing browser journeys, 3/3 browsers |
| Rokoko scripted heldout physics | 0390b87a54ad5cbc98fd5d781f828be0cfa8fbe8 | [43600904482](https://github.com/SalesSquad/junction-pets/actions/runs/43600904482) | 10,000 new synthetic worlds, 8 CPU shards, 40,000 MuJoCo episodes, 120,000,000 physics steps, 20,000 R bootstrap resamples (NOT extra episodes) |
| Arduino Green Edge | eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4 | [43600941134](https://github.com/SalesSquad/junction-pets/actions/runs/43600941134) | 384 synthetic days, 40 risk rows, 48 unexecuted switchback pairs; no physical watts/savings |
| Valio V4 settlement browser | d45f450a38ec6c8fb2f73b96d181454458ae3928 | [43601423703](https://github.com/SalesSquad/junction-pets/actions/runs/43601423703) | 3 engines × 2 viewports: signed demo handshake, quote/payment approvals, forbidden requests, balanced fictional ledger, idempotent replay, refund; zero JS errors/outbound connections/overflow |
| BAHN offline safety calibration | a4396d5ead2acc3d3db5e9a456af7f48058bb358 | [43602287400](https://github.com/SalesSquad/junction-pets/actions/runs/43602287400) | 8/8 shards of 10,000 fresh toy seeds: 80,000 pairs, 6.4 million request opportunities, clustered R confidence intervals |
| Rokoko CPU DQN optimizer smoke | 59479b42b177c1829a2e6678adfff1fb68aef09c | [43602577178](https://github.com/SalesSquad/junction-pets/actions/runs/43602577178) | 96 train episodes, 1,581 transitions, 380 gradient steps, weights changed; 20-option success horizon impossible for 250-tick dwell, so no quality claim |
| Rokoko full Double-DQN | 59479b42b177c1829a2e6678adfff1fb68aef09c | [43603057519](https://github.com/SalesSquad/junction-pets/actions/runs/43603057519) | 1000 train / 100 cal / 200 test / 100 OOD, 48,800 transitions and 12,185 gradient steps, 8,290,938 physics steps |
| Aalto Recovery Compass | 1a02a0bb650598571b63554312c7b5e82b323c7f | [43603674333](https://github.com/SalesSquad/junction-pets/actions/runs/43603674333) | 3 engines × 2 viewports: consent gate, unsent local-only draft, revoke/erase/reload, recipient safety and zero external requests |
| AstraZeneca Care Equity | ebff750c176838123311affed06082e8144001f5 | [43603679763](https://github.com/SalesSquad/junction-pets/actions/runs/43603679763) | 3 engines × 2 viewports: small-cohort suppression, overlapping uncertainty, invalid comparison denial, synthetic source digest, draft-only export |
| Rokoko fresh-world six-policy ablation | 59479b42b177c1829a2e6678adfff1fb68aef09c | [43605259084](https://github.com/SalesSquad/junction-pets/actions/runs/43605259084) | **2/2 independent training seeds PASS**, each 1,000 train + 300 fresh test / 200 fresh OOD worlds with frozen trained vs untrained Q, conservative constant PUSH_MEDIUM, heuristic, masked random and abstain; 5,000 paired world bootstraps per comparison. DQN did NOT beat constant PUSH_MEDIUM. |
| Valio single-order signed HTTP races | d45f450a38ec6c8fb2f73b96d181454458ae3928 | [43606499899](https://github.com/SalesSquad/junction-pets/actions/runs/43606499899) (initial [43605929449](https://github.com/SalesSquad/junction-pets/actions/runs/43605929449)) | 1,000 independent HTTP services/fixtures, 334 same-key storms, 333 distinct-key storms, 333 cancel races, 26,672 parallel settles +5,328 parallel cancellations; zero double charges/invalid ledgers/stock imbalance. |
| Valio two-order overfunding contention | d45f450a38ec6c8fb2f73b96d181454458ae3928 | [43606504880](https://github.com/SalesSquad/junction-pets/actions/runs/43606504880) (initial [43606237094](https://github.com/SalesSquad/junction-pets/actions/runs/43606237094)) | 500 independently signed two-order races, 1,000 signed orders, 16,000 concurrent payment posts, 8,000 insufficient-funds denials, 7,500 safe replays; each order could win; zero overdraft/duplicate-transfer/invalid ledger. |

Learner-seed stability study: [SUCCESS 43603928047](https://github.com/SalesSquad/junction-pets/actions/runs/43603928047), eight pre-registered learners 17/23/31/43/59/67/73/89; **8/8 jobs successful**. Each: 1,000 train +100 calibration/200 fixed-world test/100 fixed-world OOD episodes. Source 59479b42; distinct trained weights, total 97,167 gradient updates and 65,746,692 MuJoCo physics steps. Exact outcome by learner:

| Learner seed | Test successes / 200 | Test unsafe | OOD successes / 100 | OOD unsafe |
|---:|---:|---:|---:|---:|
| 17 | 110 | 0 | 7 | 1 |
| 23 | 110 | 0 | 7 | 1 |
| 31 | 110 | 0 | 7 | 1 |
| 43 | 110 | 0 | 7 | 1 |
| 59 | 109 | 0 | 5 | 1 |
| 67 | 110 | 0 | 7 | 1 |
| 73 | 110 | 0 | 6 | 1 |
| 89 | 88 | 0 | 3 | 0 |

Aggregate 857/1,600 *repeated paired learner/world* test successes, 49/800 repeated OOD successes, seven OOD unsafe events. **These are the SAME 200 test and 100 OOD world IDs for each learner, not independent worlds.** The seven unsafe events include repeated failure of world 420030 (near peak impulse 0.00608 > 0.006 threshold). Distinct weight hashes and per-world actions/trajectories confirm the evaluator really executes learned Q-networks; near-identical terminal results suggest a saturated nearly constant PUSH_MEDIUM strategy, not a strong learning uplift.

To test that alternative directly, a *separate* two-learner fresh-world ablation [SUCCESS 43605259084](https://github.com/SalesSquad/junction-pets/actions/runs/43605259084) completed: train 1,000 then compare frozen trained and untrained Q, conservative constant PUSH_MEDIUM, heuristic, masked random and abstain on **300 completely new test world IDs** 321000..321299 and **200 new OOD IDs** 421000..421199. Paired world-level bootstrap 95% CI; pre-registered learners 17/43. This will test added value of learning, not rely on a weak heuristic baseline. Record success/unsafe against *all* baselines including any negative result.

## Measured conclusions (all synthetic)

- **BAHN**: optimizer 1,823,772 on-time out of 1,865,084 won (97.785%); simple baseline 240,973 / 2,919,203 (8.255%). The >=90% threshold held in 78,366/80,000 individual seed runs; order acceptance and total toy gross margin were LOWER than baseline. No live Spread or calibrated real-world delivery guarantee.
- **Rokoko trained RL, single-seed exploration**: test Double-DQN 110 successes / 200 and 0 unsafe; same-world heuristic 2/200 and 0 unsafe. OOD Double-DQN 7 successes / 100 with 2 unsafe, heuristic 0 successes / 100 and 0 unsafe. The OOD risk is a blocker to hardware-safety claims. The 200-test-prefix partially overlaps an earlier exploratory run. Do not cherry-pick after inspecting it.
- **Rokoko decisive fresh-world ablation**: both learner seeds 17 and 43 achieved DQN **154/300 fresh standard worlds** and **14/200 fresh OOD worlds**; a deterministic mask-respecting constant PUSH_MEDIUM achieved **exactly the same 154/300 and 14/200**. Difference in success 0.0 percentage points with paired 95% test-world bootstrap interval **[-1.0, +1.0] pp**; OOD paired interval [0,0]. Both policies had **2/200 unsafe OOD worlds**, exact IDs 421121 and 421169, and zero unsafe standard worlds. Untrained Q and masked random each 0/300 standard and 0/200 OOD; heuristic 3/300 standard. Therefore the prior 110/200 versus weak heuristic alone was not evidence that RL outperforms the simple constant strategy. No trained-learning advantage demonstrated; do not promote this policy to real robot control.
- **Valio signed HTTP parallel financial invariants**: 1,000 sessions of original signed seller-offer/buyer-mandate flows under 32 simultaneous requests per fixture tested same-key replay, different-key duplicate prevention, and cancel/settle races. A separate 500 two-order benchmark with combined purchase value exceeding 250,000 synthetic cents confirmed one transfer only before funds ran out, clean denial of the competing order, exact refund before subsequent transfer and balanced double-entry hash chain after every phase. In-memory one-process transport evidence only; NOT distributed exactly-once, persistence, real settlements or authenticated buyer identity.
- **Rokoko scripted MegaSim** did not train any policy: it measures four scripted controllers under synthetic MuJoCo stress, separate from the actual Double-DQN lane.
- **Arduino, Aalto, Astra, Valio** remain demonstrators only: no patient data, clinical efficacy, physical energy measurement, payments, bank access, real robot commands or real recipient connection.

## Procedure / blockers / handoff

- No live BAHN SPREAD_KEY was read/exported. All business proof uses pinned source commits, fresh inputs, no external production service, source-bound CRACI receipt and bounded evidence archive (7-day retention).
- First Rokoko and Arduino scientific runs failed before qualification: the CRACI image's unused Microsoft apt feed returned HTTP 403. Fixed both by targeting signed Ubuntu OS package sources under the existing ubuntu network preset; both reruns passed. First Valio V4 browser implementation checked UI before the asynchronous state rendered; added explicit waits, all engines passed. Scientific thresholds were preserved.
- Repo green-source/seed tuples are not blindly replayed to consume credits. PR #138 remains draft: Portfolio PR Recovery is the sole integrator. No direct main push, release or uncoordinated merge.
- Credit balance and actual invoice are NOT verified; public per-vCPU tariff only supports rough budgeting. The existing timed CRACI cutoff and variable gate are authoritative.
- A read-only independent source/evidence reviewer identified two narrow Valio proof gaps and both were tightened without relaxing assertions: exact **403/400** for missing approval/tampered payment terms, and repeating the **same originally insufficient-funds idempotency key** after the competing winner's refund (must first create exactly one new transfer, then replay without duplicating). Both updated runs passed: [43606499899](https://github.com/SalesSquad/junction-pets/actions/runs/43606499899), [43606504880](https://github.com/SalesSquad/junction-pets/actions/runs/43606504880). Predecessor receipts are preserved above.

## Scientific next actions — do not spend credits on duplicate passing cells

1. **Rokoko product owner, PR #137:** current DQN is not better than shielded constant PUSH_MEDIUM. Redesign the test environment so stopping, realignment, safe retargeting, multi-obstacle transitions and vision-dropout recovery require policy switching. Pre-register entirely new world distributions and compare against this exact constant baseline, masked random, untrained Q and constrained MPC; seek a positive paired CI and zero unsafe OOD before any hardware claim. First reproduce OOD collision IDs **420030, 421121 and 421169**.
2. **Valio product owner, PR #130:** accept the positive one-process signed demo money race evidence, but next add authenticated buyer delegation, durable database transactions, actual independent process races and bank/PSP permissions in a separate authorized product scope. These current fixtures are not financial transfers.
3. **BAHN product owner:** offline 97.785% among won requests hides substantially lower order acceptance and toy margin. Define a multiobjective objective of on-time, acceptance, margin and constraint breach, with real sponsor-heldout calibration if separately authorized; additional identical toy sweeps do not repair economics.

