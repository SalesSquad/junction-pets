# Junction CRACI portfolio campaign — 14 November 2026

Work ID: `J26-CRACI-SCALE-20261114`. Implementation: [PR92](https://github.com/SalesSquad/junction-pets/pull/92), stacked on [PR91](https://github.com/SalesSquad/junction-pets/pull/91). Product corrections: [S-Pankki PR96](https://github.com/SalesSquad/junction-pets/pull/96) and [Espoo PR95](https://github.com/SalesSquad/junction-pets/pull/95). The existing Portfolio PR Recovery remains the sole integrator.

The owner explicitly requested substantially broader testing using existing CRACI credits. This campaign closes missing browser, arithmetic, database, model robustness and real sponsor build evidence. It does not qualify a production deployment or turn research-only products into working products.

## Delivered evidence

| Lane | Actual result | Evidence |
| --- | --- | --- |
| S-Pankki independent BigInt properties | 80,000 distinct generated scenarios, 880,008 passed checks, zero failures across four disjoint seeds. Includes money parsing, refunds/transfers, two-month baskets, multi-account chronology, contradictory ties, clipping, all 7/14/30-day plans and exact citations. | [43553076054](https://github.com/SalesSquad/junction-pets/actions/runs/43553076054) |
| S-Pankki browser | Repaired source passed Chromium, Firefox and WebKit at1440/390 px. Exact balance/reserves/runway, file import, refund, provenance, mixed-customer refusal and shortfall UI. | [43553080603](https://github.com/SalesSquad/junction-pets/actions/runs/43553080603) |
| Hostinger browser | All six engine/viewport journeys passed: evidence ledger, timing ablation, disposition persistence, downloaded report, sparse/syndicated cases and actual benchmark UI. Known held-out synthetic FP/FN remain disclosed. | Successful Hostinger jobs in [43552207056](https://github.com/SalesSquad/junction-pets/actions/runs/43552207056); overall run failed on Espoo. |
| Espoo browser | Repaired source passed all six journeys: citation focus, URL fragment, keyboard disclosure toggling, proposal/accept/decline/cancel, shared-employer time conflicts and reset. | [43552928227](https://github.com/SalesSquad/junction-pets/actions/runs/43552928227) |
| Council Python + PostgreSQL | 148 Python tests passed; unchanged real PostgreSQL gate passed8 simultaneous connections and independent new-process replay against a fresh UTF8 local database. | [43553078274](https://github.com/SalesSquad/junction-pets/actions/runs/43553078274) |
| Meta model robustness |12 predeclared training seeds;3,000 train examples×180 epochs each, fixed 1,500-example holdout plus10,000 additional distinct shifted examples per seed. Independent probability/confusion counts and no-authority assertions passed. | [43552620643](https://github.com/SalesSquad/junction-pets/actions/runs/43552620643) |
| Tieto actual sponsor C# | Official base and four sponsor heads built and tested in 4 actual suites each, with a disclosed SDK 9.0.100 compatibility overlay and original net8.0 target/runtime. Original SDK 8 failure retained. Across all 20 suite executions, 5,960 tests passed and 30 upstream tests were not executed (six per revision). | Base [43552925753](https://github.com/SalesSquad/junction-pets/actions/runs/43552925753); heads [43553313157](https://github.com/SalesSquad/junction-pets/actions/runs/43553313157) |
| Exa browser | Newly delivered PR94 entered the campaign during this work. All six engine/viewport journeys passed, including source hashes, exact reviewed download, consent-gated local requests, missing-key refusal and recovery. Only source replay, local review/export and missing-connection refusal; no live Exa API claim. | [43553596162](https://github.com/SalesSquad/junction-pets/actions/runs/43553596162), source 2ce520f55a97f2491d34fb4582de728e7f379c1b |

Machine-readable exact job/source/harness bindings and sanitized receipts: [portfolio-20261114.json](craci/portfolio-20261114.json). The earlier Stoa/Valio 12 browser journeys and official 363 MB S-Pankki importer qualification remain in [CRACI.md](CRACI.md); they were not replayed merely to spend credits.

### Defects found and repaired

1. **S-Pankki arithmetic:** Original 2,000-scenario run passed 22,000 checks and failed two aggregate overflow checks. Focused regressions additionally demonstrated intermediate cancellation losing one cent even when the final Number was safe. The fix accumulates with BigInt internally and checks every exposed Number result; source citations and API types remain. Same 8 focused regressions: original 3 pass / 5 fail, repaired 8 pass. Full original failing cloud receipt [43552618249](https://github.com/SalesSquad/junction-pets/actions/runs/43552618249) remains.
2. **Espoo accessibility:** Clicking a citation opened its disclosure but native fragment navigation overrode intended summary focus. The narrow handler correction preserves URL/hash, focus and normal modified-click behavior. Actual original failures [43552207056](https://github.com/SalesSquad/junction-pets/actions/runs/43552207056) and diagnostic continuation [43552624927](https://github.com/SalesSquad/junction-pets/actions/runs/43552624927) remain. The test was strengthened with actual keyboard Enter toggling.
3. **Council test environment:** `initdb --no-locale` without encoding created SQL_ASCII, making psycopg text values bytes and causing a misleading replay conflict. The harness now requests UTF8 and verifies both server/client encodings and text adaptation before the unchanged gate. Production Council code was not changed. Original [43552622899](https://github.com/SalesSquad/junction-pets/actions/runs/43552622899) remains.
4. **Tieto toolchain/data:** The sponsor pins SDK 8.0.402 / compiler 4.11 while its generator requires Roslyn 4.12. Ubuntu also lacked the legacy Cuba timezone alias. The original [43552204763](https://github.com/SalesSquad/junction-pets/actions/runs/43552204763) reports 167 generator-unit passes,984 core passes / 1 fail / 6 skips and two compilation failures. The compatibility experiment installs 9.0.100, keeps the .NET 8 runtime, records original / modified global.json hashes and diff, and installs Ubuntu tzdata-legacy. No sponsor application/test/package-source changes. Passing compatibility tests do not establish that the original SDK 8 contract works, or demonstrate a same-test fail→pass fix for each sponsor change.

### Meta result is a quality finding

All 12 experiments executed correctly, but additional shifted-data false-candidate rates were **12.4702–15.2428%**, compared with **4.6512–4.8301%** on calibration validation. Recall was approximately41–46%. This is a synthetic five-score model, not visual recognition, real glasses or an authorized action. No seed was selected for deployment; preserve every result rather than choosing the best holdout result. Model robustness remains a product limitation.

## Fixed workload menu

Existing workflow ID 417767938; no new provider or GitHub-hosted fallback. Harness checkout and each product checkout are separately pinned. The fixed menu accepts no arbitrary shell commands or user-supplied matrix JSON.

| Workload | Cells at full selection | Resources / timeout per cell | New purpose |
| --- | ---: | --- | --- |
| portfolio-browser |4 products × 3 engines = 12 |4 vCPU / 20 min | Real local source/approval/financial/meeting journeys; two viewports each |
| sbank-properties |4 seed shards |2 vCPU / 15 min |20,000 distinct scenarios and220,002 checks per shard |
| meta-seeds |4 shards, 3 seeds each |2 vCPU / 20 min | Predeclared training variability and independent shifted holdout |
| council-postgres |1 |4 vCPU / 25 min | Actual existing Python and durable PostgreSQL behavior |
| tieto-sponsor |5 pinned revisions |8 vCPU / 30 min | Actual four-suite C#build and regression results |
| portable, product-browser, sbank-sponsor |Preserved |See workflow | Prior useful source/browser/import lanes |

New matrices allow up to 8 parallel jobs each; this is **not a provider-wide concurrency cap**. Same-lane/cell concurrency groups serialize duplicates, but the coordinator must avoid duplicate unchanged successful tuples. A complete 26-cell new campaign has a **EUR 4.318 maximum list-price estimate** at configured vCPU×timeouts; actual billed cost is unknown and can differ. This estimate does not justify rerunning unchanged green cells.

Use a single selected product/engine/shard for a genuine repair. An optional full 40-character source override applies to a selected product or the arithmetic lane. The source pin is checked again in the harness. Tieto's `tieto_toolchain=compatible` is always explicitly labelled. Default pinned mode preserves the sponsor's original SDK contract.

Example administration through the existing authorized GitHub connection:

```sh
gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-portfolio-20261114 \
  -f workload=portfolio-browser -f product=exa -f browser=chromium
```

Read actual current branch/PRhead and run history first. Dispatch acceptance is not execution proof. Do not replay the example if the same source/case already passed.

## Whole-portfolio coverage and next useful work

The initial audit found 8 products with executable product/reference code; ExaPR94 arrived during the campaign, bringing that count to 9. The other 10 still need actual product implementations. Company helper tests do not count as product E2E acceptance. These are source snapshots, not claims of live workers or providers.

| # | Product | Current executable scope and next qualifying dependency |
| --- | --- | --- |
|1 |AfterQuery |Existing reference/taskPR83; prior safety-blocked Harbor authoring remains excluded. Existing owner retains container qualification gap; no retry or workaround. |
|2 |Valio |PR87 synthetic trade service and previously passed browsers. Next: independent inventory/order-state/property oracle and loopback concurrency; real buyer/provider qualification is separate. |
|3 |Bahn |Research/helper only. Implement the actual Spread simulator round/gig decision loop before large evaluations. |
|4 |Tieto |PR78 reference ledger plus this five-revision official sponsor study. Next: same frozen discriminating tests against base/head, with explicit compiler contract; current own-suite passes are not differential proof. |
|5 |Hostinger |PR89 actual synthetic detector/UI/benchmark. Next: licensed labelled held-out corpus and event-count/local-load study. Existing 12 held-out cases have 1 FP / 1 FN. |
|6 |Exa |New PR94 replay-backed product and explicit missing-provider state. Next: authorized real dated search→source→task artifact; local review never executes a real external task. |
|7 |Cala |Research/helper only. Implement sourced entity/introspection/retrieval contract and labelled identity-conflict cases. |
|8 |S-Pankki |PR85 plus correctionPR96, sponsor importer and this large independent arithmetic/browser study. Next: stratified sponsor-customer cohort and independent 30-question expected answers. |
|9 |AstraZeneca |Research/helper only. Needs cleared aggregate regional dataset and evidence/owner/outcome decision contract. |
|10 |Stoa |PR88 and previously qualified real sponsor DXF/browser. Next: held-out drawing/question set, independent geometry/citation cases beyond one known sample. |
|11 |MariaDB |Research/helper only. Needs actual revision-history ingestion and local MariaDB temporal answer benchmark. |
|12 |Context.dev |Research/helper only. Needs verified endpoint adapter whose output changes a visible decision; immutable snapshot/change contract. |
|13 |Espoo |PR90 plus correctionPR95; actual simulated event flows and browser evidence. Next: real event-scoped actor/visibility/consent contract; private Workbase IP remains private. |
|14 |Meta |PR70 synthetic score model; real hardware/DAT qualification remains separate. Next: robustness improvements assessed on a new predeclared holdout, plus actual authorized device flow. |
|15 |Rokoko |Research/helper only. Needs actual motion/action/stop contract and measured robot latency. |
|16 |Aalto Humanoid |Research/helper only. Needs separate placement/input/outcome contract and held-out episodes. |
|17 |Aalto Home Care |Research/helper only. Needs its own simulator/stop-rule response contract; do not double-count the humanoid helper. |
|18 |Arduino |Research/helper only. Needs actual UNO Q/Modulino inference/actuation proof. |
|19 |Intel |Research/helper only. Needs real-station action/safety contract; Intel+Ignite companions are one main challenge. |

## Continuous admission, budget and closure

Existing Product Factory and Portfolio PR Recovery prompts were updated and independently read back; their schedules, owners and other project safeguards were preserved. The latest instruction supersedes the previous 3-job limit: useful campaigns may contain up to 64 distinct jobs, normally 2–8 vCPU and at most 30 min each, with 8 concurrent portfolio jobs coordinated against actual capacity. Reserve worst-case queued/running cost before admission and subtract account-wide known usage. At8vCPU×30min×64jobs, the ceiling is EUR 26.112 at public list price. No top-up, cash spending, new provider, provider-model API credit or production traffic is authorized.

Billing showed EUR 1,009.89 at start andEUR 1,009.65 at 03:47 UTC. These are account credit observations, not an allocation of charges to this campaign; billing can lag and other existing jobs ran. The authorized incremental ceiling remains EUR 1,000. Provider credit expiry was not displayed.

The existing flag `CRACI_CREDIT_WINDOW_OPEN`, job-start UTC check and scheduled stop remain. Stop new admissions by **15 November 2026 19:00 Europe/Helsinki / 17:00 UTC**, close the flag, disable only workflow 417767938 and cancel this window's unfinished jobs. The one-time stop automation was read back as enabled at that time; future execution is not already verified and this is not a provider hard monetary cap.

Preserve source/harness/seed/runtime/job bindings. Avoid unchanged successful repeats, docs-only test churn, artificial resource inflation and unnecessary data downloads. New failures go to the existing source owner; no weakened assertions or rewritten historical receipts. Screenshots/traces remain temporary runner diagnostics; sanitized counts/hashes/receipts are retained here. Direct TLSbrowser/NuGet downloads do not establish complete SBOM coverage.

## Primary implementation references

- [CRACI pricing](https://craci.com/pricing):EUR 0.0017 per vCPU-minute, metered per second.
- [Runner configuration](https://docs.craci.com/reference/runner-configuration/):1–32 units, 1 vCPU / 3 GB per unit, input/network semantics.
- [CRACI network guide](https://docs.craci.com/guides/setup-action-network/): no NuGet preset; exact TLS/package sources used.
- [dotnet SDK 9.0.100 versions](https://github.com/dotnet/sdk/blob/v9.0.100/eng/Versions.props): Roslyn 4.12 toolset.
- [Ubuntu tzdata-legacy](https://packages.ubuntu.com/noble/all/tzdata-legacy/filelist): includes /usr/share/zoneinfo/Cuba.
- [PostgreSQL initdb](https://www.postgresql.org/docs/16/app-initdb.html) and [psycopg text adaptation](https://www.psycopg.org/psycopg3/docs/basic/adapt.html): explicit UTF8 test setup.

## Final source review and handoff

Independent read-only review found no blocking findings in the final executable workflow and harness bytes. The exact repaired product commits passed their hosted PR CI: Espoo PR95 run43553194455 and S-Pankki PR96 run43553198016. The latest executable harness commit is 63b01d5d489c89075deb04d1f187c656fd5029ff; later documentation records these completed outcomes without replaying the unchanged campaign. All task-owned source writing is complete and released to the existing sole integrator after final remote readback. No merge, deployment, external task sending or provider credential transfer was performed.
