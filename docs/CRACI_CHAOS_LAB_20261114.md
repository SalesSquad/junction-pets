# CRACI Chaos Lab — 14 November 2026

Work ID: `CRACI-CHAOS-20261114`. Scope: private `SalesSquad/junction-pets`; manual CRACI `chaos-lab` workload stacked on the already-running `CRACI Immune` draft PR. Only synthetic source/dependency data and ephemeral runner fixtures. No production service interruption.

## Why these tests and hooks

The useful invariant is **an unsafe or unverifiable step can never become a green release claim**, including when a worker crashes between dispatch and acknowledgement. An append-only dispatch intent is recorded first. All hooks fail closed and every work unit produces a source-pinned receipt or an explicit incomplete/failure receipt. A SHA-256 digest detects byte corruption but **is not a signature or a CRACI service attestation**.

There are six fault-hook boundaries in `scripts/craci/chaos-lab.mjs`:

1. `before-admit`: credit flag, €300 task cap, source job reservation, no duplicate/ambiguous dispatch, 16-minute deadline headroom.
2. `after-checkout`: harness/source/lockfile SHA pinning.
3. `after-install`: cache ancestry, installation scripts disabled, forbidden egress and network reset handling.
4. `after-execute`: nonzero exit, hung/cancelled task and time limit.
5. `after-receipt`: receipt digest, exact source identity, completed stage/runner outcome, no synthetic secret marker.
6. `after-artifact`: missing/truncated/swapped evidence and checksum match.

In the **synthetic** test loop, 20 adversarial faults plus four benign controls are combined into four boundary-focused profiles. Each 25,000-case CRACI cell includes cross-profile pairwise combinations, deterministic seed/replay, negative controls and a deliberately weak comparator. The independent fixture oracle checks injected fault labels against the modeled hook verdict, and reports missed injections, rejected benign controls, pair coverage and unverified cost. A zero miss count here is **not** proof of real-world malware prevention.

Separately, `scripts/craci/chaos-probes.mjs` performs six **real isolated runner tests**:

- `npm ci --ignore-scripts --offline` prevents a benign fixture `postinstall`; control fixture confirms the script otherwise executes.
- An inconsistent package manifest/lockfile is rejected by npm offline.
- A loopback-only HTTP server injects TCP reset and timeout; a clean request then succeeds.
- Child process exits with code 71; a hung child is timed out; next child succeeds. Never kill the runner host.
- Atomically committed local receipt detects a truncated payload and accepts its restored digest.
- 32 concurrent file-create attempts produce one winner, and unknown dispatch ACK is treated as non-retriable.

The workflow's network-profile cell additionally performs an **actual CRACI runner** `npm ci --ignore-scripts` with CRACI `default: deny`, `presets: [github, npm]`, and a neutral `example.com` transport-denial probe. A failed `curl` only proves transport failed; **CRACI's provider network trace/SBOM must be inspected separately** to attribute enforcement. Neither npm script execution nor any hostile package is allowed in the real checkout.

## Campaign and safeguards

- **Owner hard stop:** `2026-11-14T18:00:00Z` = 20:00 Finland; runner admission requires 16 minutes to drain, even though the broader approved CRACI credit flag lasts longer.
- **Owner spend cap:** €300 shared task ceiling. The independent Chaos Lab 4×2-vCPU×15-minute + 2-vCPU×5-minute reservation estimate is at most **€0.325 per dispatch**, based on the reported planning rate €0.0025 per vCPU-minute; actual CRACI account bill remains unknown without provider billing access. Other CRACI campaign reservations must be counted before recurring waves.
- Manual `workflow_dispatch` only. No PR/main cron fan-out, production security token changes, remote host kill, disk fill or live internet attack.
- 4 matrix jobs, `fail-fast:false`, 15-minute timeout, `contents:read`, pinned marketplace actions, credentials not persisted by checkout, 7-day artifacts.
- Existing CRACI Immune controller remains pinned to its original HEAD and own branch; never mutate its checkout or restart it as a side effect.
- `run-receipt.mjs` wraps the qualification and finalizes on error. Artifacts contain case digest, profile, real-probe verdict, source SHA, work ID and limitations; do not put tokens or private data into artifacts.

## Local preflight and CI handoff

Local scratch preflight (Node v24.22.1) on 14 Nov 2026:

- `node --test craci/chaos-tests.test.mjs`: **7/7 pass**.
- `node craci/chaos-probes.mjs --output /tmp/craci-chaos-probes-check-20261114.json`: **6/6 pass**, real local fixtures.
- Four `chaosCampaign({seed:12345,cases:20000,profile})` calls: **80,000 synthetic cases**, no modeled unsafe misses or benign-control false positives. These runs are not yet CRACI/cloud receipts.

For cloud qualification: dispatch existing `.github/workflows/craci-pilot.yml` with `workload=chaos-lab`, explicit `epoch`, `source_sha=<exact chaos-lab task HEAD>` and `ref=codex/craci-chaos-lab-20261114`, only while the hard-stop guard can pass. Verify 4/4 CRACI jobs, source pins, 4 artifact receipts and real test evidence; report any CRACI billing uncertainty. Later waves must use a unique epoch and source, check the shared capacity, consume an explicit reservation, and stop at the same campaign cutoff. Retain failed runs; never greenwash or turn a failed probe into a synthetic pass.

External patterns: [GitHub workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency), [GitHub artifact checksums](https://docs.github.com/en/actions/tutorials/store-and-share-data), [CRACI network policy](https://docs.craci.com/guides/setup-action-network/), and [Shopify Toxiproxy](https://github.com/Shopify/toxiproxy) informed the design. This task uses dependency-free local network fixtures, not a deployed Toxiproxy or Chaos Mesh service.
