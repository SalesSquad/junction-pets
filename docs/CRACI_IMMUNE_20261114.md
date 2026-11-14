# CRACI Immune — three-hour bounded counterfactual campaign

Work ID: `CRACI-IMMUNE-20261114`. Owner request: 14 November 2026, up to **EUR 300 from existing CRACI credits** over three hours. **Do not** spend cash, top up, install new credentials, publish a site, run malware, or alter another repository. The existing Junction-wide credit window and its separate 15 November shutdown remain unchanged.

## New contribution

CRACI Immune combines two distinct evidence layers:

1. **Actual CRACI execution:** immutable source/harness checkout; `npm ci --ignore-scripts` using CRACI's package-aware npm preset; default-deny network policy; a neutral `example.com` outbound probe that is expected to fail; provider-side SBOM/network traces; bounded GitHub source receipts and artifacts. A failed curl alone is **not** a verified CRACI policy block — review the provider's network trace.
2. **Synthetic decision tournament:** 250,000 distinct adversarial dependency graph cases per cell (four cells per epoch), using real package names from the checked-out lockfile. Cases include legitimate updates, altered integrity/registry, undeclared lifecycle scripts, unapproved egress, transitive drift and deliberately unreachable decoys. Independently labelled fixture truth is compared to a provenance-reachability detector and a naive any-anomaly detector. A bounded cost-minimal counterfactual repair search proposes rollback, egress denial or optional-dependency quarantine. It **abstains** when there is no safe proven patch.

This is not proof of malicious package detection in the wild, signed artifact integrity, an AI model making production code changes, or real CVE remediation. In particular, a compromised original signed pin evades this simulated oracle. The existing CRACI dashboard must supply independently inspected real SBOM and egress claims.

## Timing and quota

- Only workflow `417767938` in `SalesSquad/junction-pets`, manually dispatched on the task branch; ordinary PR/main changes remain non-fan-out.
- Begin with the source SHA pinned in the new task branch, stacked on PR #138's finished MegaSim HEAD `b42253685625d6f1bb6d1927319a35beafd612b2`.
- At most twelve **distinct** 15-minute epochs; each epoch selects four new immutable seeds. Epochs 1–4 use a baseline distribution, 5–8 deeper transitive cases, 9–12 a shifted distribution with fewer safe rollback options. No successful identical tuple repeats.
- At most one active CRACI workflow dispatch from this coordinator, four matrix runners. Other active CRACI workflows defer the next epoch. No GitHub-hosted fallback.
- Strict local campaign deadline **14 November 2026, 18:00 UTC / 20:00 Helsinki**. Admission stops when less than sixteen minutes remain; the workflow also checks its own start deadline. Cancel only this campaign's own late runs.
- Conservative per-dispatch reservation: `(2 vCPU × 5 min + 4 × 4 vCPU × 15 min) × EUR 0.0025 = EUR 0.625`. Maximum twelve dispatches = **EUR 7.50 reserved list-price estimate**, far below the owner-authorized EUR 300. This is **not** a provider-billed cost or enforceable account cap; provider balance and actual charges remain unverified until billing readback. Never add enough load to chase the cap.
- The existing `CRACI_CREDIT_WINDOW_OPEN` variable and Junction's 15 November shutdown are additional admission gates, not a replacement for this campaign cutoff.

## Source- and experiment-bound receipts

The authenticated Mac Mini holds the named durable controller session `craci-immune-three-hour-20261114` and append-only journal `/private/tmp/craci-immune-controller-20261114.jsonl`. The script refuses an unknown GitHub delivery instead of dispatching twice. Workflow artifacts contain source hashes, bounded metrics, and a non-attesting egress probe outcome. GitHub run links and actual outcomes belong in the task PR. No keys, personal data or real company telemetry enter synthetic fixtures.

Success: all four cells finish their executable tests and source-bound receipts, then an independent read of actual provider network/SBOM evidence and a concise false-positive/abstention scorecard. Any failed cell is retained as RED, not silently skipped. Portfolio PR Recovery owns the later integration/merge, not this experimental controller.
