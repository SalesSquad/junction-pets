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

Learner seed stability study: [43603928047](https://github.com/SalesSquad/junction-pets/actions/runs/43603928047), pre-registered seeds 17,23,31,43,59,67,73,89 with the same source and fixed world-prefix/test sets; 1000+100/200/100 episodes per seed. This tests learner variability, NOT fresh independent heldout worlds. Report all seeds, including failures.

## Measured conclusions (all synthetic)

- **BAHN**: optimizer 1,823,772 on-time out of 1,865,084 won (97.785%); simple baseline 240,973 / 2,919,203 (8.255%). The >=90% threshold held in 78,366/80,000 individual seed runs; order acceptance and total toy gross margin were LOWER than baseline. No live Spread or calibrated real-world delivery guarantee.
- **Rokoko trained RL, single-seed exploration**: test Double-DQN 110 successes / 200 and 0 unsafe; same-world heuristic 2/200 and 0 unsafe. OOD Double-DQN 7 successes / 100 with 2 unsafe, heuristic 0 successes / 100 and 0 unsafe. The OOD risk is a blocker to hardware-safety claims. The 200-test-prefix partially overlaps an earlier exploratory run. Do not cherry-pick after inspecting it.
- **Rokoko scripted MegaSim** did not train any policy: it measures four scripted controllers under synthetic MuJoCo stress, separate from the actual Double-DQN lane.
- **Arduino, Aalto, Astra, Valio** remain demonstrators only: no patient data, clinical efficacy, physical energy measurement, payments, bank access, real robot commands or real recipient connection.

## Procedure / blockers / handoff

- No live BAHN SPREAD_KEY was read/exported. All business proof uses pinned source commits, fresh inputs, no external production service, source-bound CRACI receipt and bounded evidence archive (7-day retention).
- First Rokoko and Arduino scientific runs failed before qualification: the CRACI image's unused Microsoft apt feed returned HTTP 403. Fixed both by targeting signed Ubuntu OS package sources under the existing ubuntu network preset; both reruns passed. First Valio V4 browser implementation checked UI before the asynchronous state rendered; added explicit waits, all engines passed. Scientific thresholds were preserved.
- Repo green-source/seed tuples are not blindly replayed to consume credits. PR #138 remains draft: Portfolio PR Recovery is the sole integrator. No direct main push, release or uncoordinated merge.
- Credit balance and actual invoice are NOT verified; public per-vCPU tariff only supports rough budgeting. The existing timed CRACI cutoff and variable gate are authoritative.
