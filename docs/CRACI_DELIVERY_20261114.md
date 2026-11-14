# CRACI delivery and retained evidence — 14 November 2026

Work ID: `J26-CRACI-DELIVERY-20261114`. Implementation base:
`1283d38c0352055fb487f0c2d7af06f86a915f9b`. Shared workflow/source ownership:
[issue 80 comment 6874318759](https://github.com/SalesSquad/junction-pets/issues/80#issuecomment-6874318759).

The owner approved implementing the reviewed source-selection, lightweight CI,
artifact-retention and experiment-registry improvements, plus one corrected
MariaDB runtime and the existing Meta browser acceptance journey. This task
reserves at most **EUR10 of the existing credit** within the already approved
EUR1,000 campaign. No top-up, new provider, production load or deployment.
The existing stop at **2026-11-15 17:00 UTC / 19:00 Helsinki** and repository
variable `CRACI_CREDIT_WINDOW_OPEN` remain effective. Portfolio PR Recovery is
the sole integrator.

**Delivered:** corrected MariaDB **80/80**, the existing Meta Chromium journey,
and native x64/ARM64 probes **9/9 each**. A collector timing-unit defect was
found, repaired and verified separately. Original evidence remains unchanged;
the two original duration fields require the explicit corrections below.

## What changed

- Qualifications are manual `workflow_dispatch` choices; ordinary PR/main
  commits no longer launch full suites. An admission job validates immutable
  sources and bounded matrices before allocation; invalid products cannot
  silently select the portfolio.
- Native/MariaDB and other portable lanes use the resolved source consistently.
  Tieto uses its official sponsor revision selector and rejects unrelated
  overrides. Historical fallback pins remain explicit.
- The wrapper preserves command failure, verifies source/harness, and records
  bounded evidence through the existing registry API. A pinned artifact action
  uploads only verified staging, retained for seven days.
- Meta executes its existing source verifier with locked Playwright/Chromium;
  product assertions are unchanged. Development guidance follows the lightweight
  rule; 34 environment manifests remain command menus, not mandatory full suites.

## Actual qualification and source binding

**Seven jobs executed across three runs: three admission jobs and four runtime
jobs.** Other workload cells were skipped. The original product qualifications
used harness `ea6670964176617bf45dda8a43e1671c48316fe0`; the native probes
verified the timing repair at `a6c0e4a3d3cf6ac6eabe7cbd81272e2331024474`.

| Qualification | Run / runtime job | Observed outcome |
| --- | --- | --- |
| Corrected MariaDB | [43575939909 / 132390122200](https://github.com/SalesSquad/junction-pets/actions/runs/43575939909/job/132390122200) | 80 passed, 0 failed, no execution error |
| Meta browser | [43575942647 / 132390130647](https://github.com/SalesSquad/junction-pets/actions/runs/43575942647/job/132390130647) | Existing synthetic Chromium journey passed |
| Native x64 / corrected collector | [43576465580 / 132391718451](https://github.com/SalesSquad/junction-pets/actions/runs/43576465580/job/132391718451) | 9 cases passed; corrected receipt 0.363 s |
| Native ARM64 / corrected collector | [43576465580 / 132391718495](https://github.com/SalesSquad/junction-pets/actions/runs/43576465580/job/132391718495) | 9 cases passed; corrected receipt 0.423 s |

MariaDB and both native cells used `83c45015f475471a861d663677d060e26b2692c3`,
the [PR111](https://github.com/SalesSquad/junction-pets/pull/111) correction
stacked on [PR103](https://github.com/SalesSquad/junction-pets/pull/103).
Meta used `01065ebcffb74ebbb801f126ae8b46dba15b3a80`, merged through
[PR108](https://github.com/SalesSquad/junction-pets/pull/108).
All four runtime receipts report verified source/harness, no unexpected tracked
changes, exit 0 and a recorded registry entry.

Retained admission records:
[MariaDB](craci/delivery-20261114/mariadb-43575939909-plan.json),
[Meta](craci/delivery-20261114/meta-43575942647-plan.json), and
[native](craci/delivery-20261114/native-43576465580-plan.json).
These are historical executions, not requests to repeat passing cells.

### MariaDB: five original failures resolved

The earlier [run 43564983185](https://github.com/SalesSquad/junction-pets/actions/runs/43564983185)
still records **72 passes / 5 failures** at `d0be3abf66c86d6817f82ca5ae5598ae003b5360`.
The unchanged runtime harness now passes all four case/diacritic page-identity
cases and the case-distinct dataset insertion. That insertion enables three
additional checks, giving the expected total of **80**.

Actual MariaDB was **11.8.9-MariaDB-ubu2404**, native amd64, with the pinned image
digest verified. All three identifier columns used `utf8mb4_nopad_bin`.
Revision boundaries, ambiguity, Unicode parameters, duplicate rollback and
import-time history passed. Restart preserved **16 current/history rows**;
source bytes were unchanged and owned containers/volumes were removed.
The [captured JSONL](craci/delivery-20261114/mariadb-43575939909/command.stdout.log)
retains every check. Harness SHA-256 remained
`26c50dd67281c2af4a6532a8e37805d22f3ed0944cfa5e2656e123bb3a75ed92`.

This proves the corrected DDL/query on a fresh disposable database and synthetic
fixtures. Migration of a populated table, sponsor Wikipedia data and an external
database service remain unverified. The offline product CLI itself still
reports `NO_MARIADB_CONNECTION`.

### Meta: actual local browser acceptance

The [browser receipt](craci/delivery-20261114/meta-43575942647/artifacts/meta-browser/browser-receipt.json)
records **Linux Node v22.23.3 / Chromium 158.0.8127.18**, a **15.126 s**
journey and no page errors. Keyboard confirmation, interruption, rejected visual
evidence, refresh persistence, correction, capture revocation and offline resume
passed. The compact surface measured **600 × 600**, action bottom **556 px**,
with no document overflow.

Screenshots: [desktop](craci/delivery-20261114/meta-43575942647/artifacts/meta-browser/resume-desktop.png)
and [600 × 600](craci/delivery-20261114/meta-43575942647/artifacts/meta-browser/resume-display-600.png).
[Setup timing](craci/delivery-20261114/meta-43575942647/artifacts/setup-timing.json)
measured **1 s dependencies / 30 s Chromium installation**. Browser setup was
the larger installation cost in time in this sample; no cache speedup or universal
runner-sizing claim follows.

Physical glasses, the Display Simulator extension, native WebMCP execution,
live camera/microphone, authenticated Chibi host identity/persistence,
cross-device synchronization and production deployment were not verified.

## Receipt and registry contract

`run-receipt.mjs run -- <fixed command>` wraps one qualification command per
cell; `finalize` runs with `if: always()`. Missing command/log evidence or an
unverified checkout remains incomplete. Source/harness HEADs and tracked changes
are checked before and after execution; explicit Tieto `global.json` overlays
carry file/diff digests. Receipts bind identity, outcome, provenance, hashes,
next owner and nullable cost. Original failing exits/signals are preserved.

The unchanged `recordRun` API creates an immutable registry record in safe
staging. The coordinator verifies/downloads artifacts and submits sanitized
imports through the task PR; CI retains `contents: read` and never pushes Git.
Uploads require `upload_ready`. Only bounded regular logs, JSON/JSONL, PNG, ZIP,
TRX and SHA-256 files are admitted; links/unknown/oversized files are excluded.
If harness checkout fails, the infrastructure-only fallback explicitly lacks
verified product/registry evidence. A runner that never starts or cannot upload
has no proven retained receipt. Hashes are integrity evidence, not attestations.

## Timing correction and implementation verification

Artifact inspection found that `performance.now()` milliseconds had been labeled
`wallSeconds`. Both the outer receipt and its original registry metric were
affected. Functional results remain valid; the original numbers below are
**not valid durations in seconds**.

| Original run | Invalid raw field | Derived seconds, rounded to six decimals | UTC endpoint duration |
| --- | ---: | ---: | ---: |
| MariaDB 43575939909 | 29230.547 | 29.230547 | 29.231 s |
| Meta 43575942647 | 15674.918 | 15.674918 | 15.675 s |

The original archives, receipts and embedded registry records are unchanged.
[timing-corrections.json](craci/delivery-20261114/timing-corrections.json)
binds their hashes and timestamps to the divide-by-1,000 derivation and distinct
corrected record IDs. Meta's wrapper duration includes command overhead;
the inner browser journey independently measured 15.126 s. Neither includes
runner queueing or installation.

The fixed conversion is `Math.round(elapsedMilliseconds) / 1000`.
An independent UTC-endpoint regression failed on old code
(234.371 reported versus 0.234 s) and passed after repair (0.244 versus 0.245 s).
Final collector SHA-256:
`bbd777749eff8df18f5ff42dfd511615808992db8eafca6eaf3cd036bc45f35b`.
The published fix was verified through the existing native probe, without
rerunning MariaDB or Meta. x64 measured **0.363 s** versus **0.364 s** UTC;
ARM64 measured **0.423 s** versus **0.423 s** UTC.
Both Node v22.23.5 probes produced canonical result digest
`6f323fd6052fa020c02de088673774a7373cbc07b5a55a8da5d9779bb0853a6e`.
These are offline CLI cases, not ARM64 database-container qualification.

Final combined targeted planner/receipt checks passed **16/16**. Coverage
includes source selection, invalid fan-out, deadlines, failing exits/signals,
missing or modified checkouts, explicit overlays, immutable publication,
unsafe files, bounded logs, missing-log integrity and timing units.
Independent review covered the implementation and final unit correction bound
to the collector hash above. No full repository suite or unchanged portfolio
matrix was run for this slice.

The MariaDB Docker image remains digest-pinned. Its exact documented
`production.cloudfront.docker.com:443` allowance remains outside package-aware
detection; this task does not claim complete container SBOM observation. No
existing workload network policy is broadened.

## Durable evidence and registry audit notes

Downloaded archives were hash-verified; expanded siblings retain commands,
logs, manifests, receipts and original registry records:

The [machine-readable index](craci/delivery-20261114/index.json) binds the
workflow/job/artifact IDs, final code hashes, registry additions and budget observations.

| Evidence | Original ZIP | Expanded receipt | ZIP SHA-256 |
| --- | --- | --- | --- |
| MariaDB | [archive](craci/delivery-20261114/mariadb-43575939909.zip) | [receipt; invalid duration field](craci/delivery-20261114/mariadb-43575939909/receipt.json) | `83228d2ed80b4d11ccdda608afafd5346703d0a93a81fd26d277875ac0f7cb4b` |
| Meta | [archive](craci/delivery-20261114/meta-43575942647.zip) | [receipt; invalid duration field](craci/delivery-20261114/meta-43575942647/receipt.json) | `fcb3736c6964f4fc6a58b1aef5e5dbefb1b0e26c6109908ce3b091731616a201` |
| Native x64 | [archive](craci/delivery-20261114/native-x64-43576465580.zip) | [receipt](craci/delivery-20261114/native-x64-43576465580/receipt.json) | `33cd006944b2a0e0eca69e9e0f9b457eb783c7f458cd9cf0444a2eae323c49c5` |
| Native ARM64 | [archive](craci/delivery-20261114/native-arm64-43576465580.zip) | [receipt](craci/delivery-20261114/native-arm64-43576465580/receipt.json) | `863f9ccb9d2ecb2466c8bb017b34439bb4634f9480ae0ac55a33d196e647496a` |

Five sanitized records enter the existing registry:

- [Failed MariaDB baseline](../ops/experiments/runs/craci.baseline.mariadb.43564983185.json):
  `historical-result`, still failed 72/5; `capturedAt` denotes import time,
  not the original runtime.
- [MariaDB timing correction](../ops/experiments/runs/craci.43575939909.1.7fee397ca276abbc.timing-corrected.json)
  and [Meta timing correction](../ops/experiments/runs/craci.43575942647.1.29e976e45d79a5ae.timing-corrected.json):
  distinct `historical-result` records with explicit derivation and original
  receipt hashes. These do not replace originals or represent new executions.
- [Native x64](../ops/experiments/runs/craci.43576465580.1.8fa10b8e8667336f.json)
  and [native ARM64](../ops/experiments/runs/craci.43576465580.1.3f6b02c38640b6df.json):
  `synthetic-test` records from the fixed collector.

All five remain `source-reported`; normalized historical metadata is not a
provider attestation or model-promotion decision. Original evidence identities,
hashes, limitations and failed baseline are retained.

## Budget observations and handoff

The **EUR10 reservation** remains within the owner's existing **EUR1,000-credit**
authority. Actual job and task costs remain **unknown**, with null receipt cost
fields. The fresh billing UI was blank at **2026-11-14 08:24:42 UTC**.
The earlier **EUR1,009.48 at 06:13:19.588 UTC** is a historical observation,
not a current balance or task cost calculation.

`CRACI_CREDIT_WINDOW_OPEN` was read true at **08:27 and 08:34 UTC**.
The existing **15 November 17:00 UTC / 19:00 Helsinki** stop is unchanged.
No top-up, new provider, production load, merge or deployment was performed.

[PR115](https://github.com/SalesSquad/junction-pets/pull/115) carries this
implementation and evidence; its last executed code commit is `a6c0e4a…`.
This task's coordinator commits the final evidence; Portfolio PR Recovery owns integration.
The MariaDB owner can carry the 80-check receipt into PR111/PR103 and update
product readiness while retaining the migration/sponsor-data limits.
The existing Meta/private-Chibi line owns the next authorized host/device
integration. Further work should close those gaps rather than repeat these
successful cells.
