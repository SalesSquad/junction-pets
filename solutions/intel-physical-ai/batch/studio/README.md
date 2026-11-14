# Inspect / Action — Batch Operations Studio (M3)

Work: `J26-PF-INTEL-M330-M3-20261114`. Read-only local software experience,
Node **22+**, no dependencies or installation. From the repository root:

```sh
node solutions/intel-physical-ai/batch/studio/server.mjs 3300
```

Open **http://127.0.0.1:3300** (use the IP exactly, not `localhost`). A second
argument is not needed; the sole optional argument is a port, with `0` selecting
an available port printed at startup. Stop with Ctrl-C. No remote services,
credentials, hardware or provider calls exist. Do not expose this development
server through a proxy, public tunnel or network interface.

## Operator workflow

1. Enter an integer seed from 0 through 4294967295 and generate eight bricks.
   Seeds change feed slots, not fault difficulty. The queue contains simulated
   handling/camera states and operator decisions; no evaluation ground truth.
2. Review each brick's Continue or explicit STOP and required reason. M2's
   original reasons are preserved until edited; edits use a non-empty fixed
   reason list. STOP affects that episode only, never a persistent emergency stop.
3. Run the synthetic batch. The browser calls imported `runBatch`, then
   `replayBatch`, including its nested M1 verification. It displays good,
   defect, hold and stop counts and the existing M2 naive comparator. Drill
   into any episode's inspection interval, operator decision, software bowl,
   coreReceipt and chained steps. Scene truth appears only after replay, under
   **SIMULATED SCENE TRUTH**; it never enters the request or policy.
4. Download the entire immutable receipt. Import a local M2 receipt up to
   **2 MiB (2,097,152 bytes)**; its original outcomes are displayed only after
   complete `replayBatch` verification. A failed import clears the previous
   verified receipt and export eligibility. No corrupt input is repaired.
   Imported M2 batches can contain 1–64 episodes; this studio generates eight.
5. A seed/input edit, regenerated plan or changed operator decision invalidates
   the receipt and download. Export before changing anything to keep a result.
   Nothing uses localStorage/sessionStorage or an app database. Browser-chosen
   downloads persist outside the app and may contain operator reasons.

M2 decides everything: an uncertain fixture may route to its software hold
bowl; lost grip, disagreement or stale capture retains HOLD with **no placement**.
The UI never converts those retained faults into a bowl action. The M1/M2 code
is imported, unchanged; no policy copy or alternate route exists here.

Coverage is sorted / all episodes, including holds and stops. Conditional
correctness is correct / sorted only, undefined with zero sorted. Unsafe sorted
is the existing M2 hazard count among sorted episodes. The naive comparator
ignores interlocks and STOP. These are synthetic fixture counts, not calibrated
accuracy, cycle time, throughput or hardware measurements. Holds correctly
preserve faults and uncertainty; reduced coverage is not itself a defect.

## Source and boundary

Prepared clean source / coordinator-authenticated main:
`633523f2cc007fae2d3b8a912e3ac3eaa12b934e`.
Task branch: `codex/j26-intel-batch-studio-m3-20261114`.
M2 contract: `../cell.mjs` exports `plan`, `runBatch`, `replayBatch`;
it indirectly imports M1 `../../core.mjs`. M2 receipt provenance retains its
own historical M1 source pin `ee2ce767ed779cafa0f048c6b087ce5c84831a7f` and
`synthetic-batch/1` version. The studio does not rewrite that provenance to its
new source pin. Coordinator owns eventual commit and integration.

Read the 14 November `ignite-next-and-intel` latest clarification before its
previous guidance and M330 brief. The GitHub 25/25/20/20/10 and PDF
25/20/20/20/10/5 rubrics remain unresolved. No claim of sponsor acceptance,
challenge eligibility or real autonomous execution follows from this milestone.
No real camera, SO-101, Anomalib, VLA, Physical AI Studio, OpenVINO or Intel
CPU/GPU/NPU execution has been qualified.

`server.mjs` binds only 127.0.0.1, compares Host against its actual port, refuses
foreign Origin / cross-site Fetch Metadata, methods beyond GET/HEAD and bodies.
Only `/`, `/index.html`, `/style.css`, `/app.mjs`, `/model.mjs`, `/cell.mjs` and
`/core.mjs` are served. The last two map exactly to existing M2 and M1; the
browser's relative module imports resolve to those routes. Raw path matching
rejects traversal/encoding/query variants before URL normalization. No directory
serving, backend data API, POST, upload, logs of input, or filesystem writes.
CSP denies connections, forms, frames, external scripts/styles and images;
modules/styles use same-origin assets. Camera/microphone permissions are denied.
JSON is rendered using DOM text nodes, never HTML interpolation. Hashes are
unsigned and reproducible by anyone: integrity is not identity or authorization.

## Focused verification

```sh
node --test solutions/intel-physical-ai/batch/studio/studio.test.mjs
node --check solutions/intel-physical-ai/batch/studio/app.mjs
node solutions/intel-physical-ai/batch/studio/server.mjs 0
```

Two execution contexts, Node v26.13.0, 14 November 2026:

- **Codex CLI sandbox:** five pure module/state tests passed, but three actual
  HTTP tests were blocked at `listen EPERM: operation not permitted 127.0.0.1`.
  Those failures are preserved as environment evidence, not hidden or skipped.
- **Coordinator's authorized Mac Mini terminal (Remote Desktop Commander):**
  the same eight tests **8/8 PASS**, including actual loopback HTTP/CSP/MIME,
  hostile Host/Origin/Fetch Metadata, body/path refusals, direct M2 and nested
  M1 replay, tampering and invalidation. JavaScript syntax checks passed.
  No unrelated full suite was run.

**Actual browser journey (coordinator, 14 November 2026):** Headless Chrome
157.0.8103.80, using the installed, existing Puppeteer runtime, exercised the
real loopback studio at both **1440px desktop** and **390px mobile**. Generated
eight bricks, selected per-brick STOP/reason, executed the imported M2 gates,
inspected the STOP/no-software-placement episode and naive comparison, downloaded
the actual JSON receipt, imported and fully replay-verified it, and deliberately
altered its root to verify import refusal and disabled export. Both widths had
**zero document overflow** and **zero browser JavaScript exceptions**.
The bounded smoke closed its HTTP server and headless browser after completion.
The observed synthetic edited-run count was good 0, defect 2, hold 4, stop 2;
its exported root was
`026134c577a901dec121b192f3b505e9fe0002fb1063b01f15f7985c7511ebe0`.
This is a functional Chrome path, not an independent accessibility audit,
cross-browser qualification, licensed user cohort or real-device run.

**Still outstanding:** VoiceOver/screen-reader assessment, real SO-101
robot/camera/Anomalib/VLA/OpenVINO and comparable physical station timing,
sponsor clarification of conflicting judging criteria, and source-bound
external approval. No new paid provider was called and no production deployment
or Junction submission occurred. Portfolio PR Recovery alone owns integration.
