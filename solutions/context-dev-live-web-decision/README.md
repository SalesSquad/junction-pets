# SupplyPulse / Live Web Decision Room

**SYNTHETIC_REPLAY · maturity 2/6 · local functional prototype.** No live Context.dev session, key, credits, supplier fact or provider execution is claimed. No orders, monitors, webhooks or outbound actions exist. Work ID J26-PF-CONTEXT-M1-20261114; base `98d5a524d61e431ca36acd62b268ede343fc7fe2`. Only this directory is owned. Coordinator handles source integration.

A small retailer procurement operator needs 40 ivory desk lamps within five days for at most EUR600. Investigate two supplier observations, compare eligibility and total cost, inspect provenance, review a human-only memo and download it. The fixed replay clock avoids presenting historical fixtures as fresh live data.

## Run (Node 22+; no dependencies)

```sh
node solutions/context-dev-live-web-decision/server.mjs
# Open http://127.0.0.1:4173 in a browser on that host.
node solutions/context-dev-live-web-decision/cli.mjs after
node solutions/context-dev-live-web-decision/cli.mjs failed
node --test solutions/context-dev-live-web-decision/engine.test.mjs
node solutions/context-dev-live-web-decision/comparator.mjs
```

The four replay controls show North at EUR480 before the change; Coast at EUR540 after North's inventory falls from 80 to 12; a cosmetic banner that preserves North's recommendation; and failed JSON under HTTP200 that refuses the comparison. No raw page text enters HTML: UI data uses `textContent`. The evidence inspector binds complete snapshots and fixed policy via SHA-256. Refusal is separate from an ineligible candidate: incomplete trust evidence halts the entire comparison.

## Evidence contract

`decide` accepts a bounded JSON string (32 KiB UTF-8), exactly shaped envelope and snapshots, a supplied canonical UTC clock, two exact source-ID/URL bindings and at most eight snapshot entries. Identical duplicate snapshots deduplicate; conflicting duplicates refuse. Unknown, absent and null values never become zero. EUR cents must be positive safe integers; multiplication must remain safe. Stock, days and confidence have explicit bounds. Observations and cache origins must be valid, not future or older than five minutes. Both outputs require HTTP200, explicit JSON success, and explicit non-partial status.

Eligibility: at least 40 units, at most five days, confidence at least 90, and total at most EUR600. Lowest eligible total wins; then lead time, then ID. Every result has `actionAuthorized:false`. Cosmetic text changes alter full evidence hashes but never ranking. Field changes are semantic, even if they do not cross a decision threshold. Canonical hashing sorts object keys; array order remains provenance. This is reproducibility, not a signed receipt, freshness attestation, event ledger or authentication. JSON follows standard last-member-wins parsing for duplicate object keys: do not use this format as authorization or ingest arbitrary raw provider JSON as an authenticated record.

The existing `pets/context-dev/extract-snapshot.mjs` was read and left unchanged. It extracts title/version/summary from fictional line text, with span provenance and TTL checks. SupplyPulse adds domain-specific typed procurement comparison rather than pretending those strings are live price evidence. The two `.invalid` URLs are identifiers only and are never fetched. Every fixture carries `SYNTHETIC_REPLAY`; adversarial variants derive from those labeled fixtures.

## Context.dev integration seam — deliberately dormant

`live-adapter.mjs` has no SDK import, installation or native fetch. A trusted operator must supply an SDK client and explicitly choose `LIVE` with an environment key, then add a reviewed exact HTTPS URL mapping in source. The preconfigured mapping is **empty**: there is no caller-provided URL and no live target callable in this delivery. Host, path and URL must match exactly; there is no arbitrary URL proxy.

Planned SDK shape: `client.web.scrape({url, formats:{json:true}, jsonParams:{schema}, sharedParams:{maxAgeMs:0}})` and check `page.json.success` before reading `page.json.data`. The source validator rejects failed and partial fields. Mock SDK-shaped output demonstrably changes the core decision. Returned live fields remain `LIVE_UNVERIFIED` and cannot enter this synthetic-only engine: do not relabel them synthetic to bypass admission.

The [official scrape reference](https://docs.context.dev/api-reference/web-scraping/scrape) was read during implementation. It confirms per-format success and structured JSON, but currently displays HTTP `maxAgeMs` at the top level and the JSON result at the response root. The requested sharedParams/page SDK shape is an **unverified SDK mapping**, not a tested provider contract. Before activation pin the SDK version and verify its actual request/response mapping, freshness field placement, public-only DNS/redirect enforcement, timeout/byte limits before parsing, source/final URL equivalence, request ID and trusted cache/observation metadata. An injected trusted client is a trust boundary; this module does not implement a network sandbox. No arbitrary private/unknown URLs or browser actions may be enabled.

## Junction source fit and milestones

Source: `docs/challenge-research/current-source-catalog.json`, snapshot 14 Nov 2026, partner `context-dev`, `latestClarification:null`; dated 13 Nov guidance reviewed. M332 asks for a product that reacts to live-web changes, with impact, creative use, completeness, technical execution and real-timeness weighted equally. T44 requires at least one Context.dev endpoint in the **core flow**, with its data visibly driving the demo; creative use 40%, centrality 30%, execution 30%. This prototype demonstrates decision centrality synthetically; **partner challenge integration is currently unverified and T44 endpoint execution is not satisfied**. Historical credit offers do not prove account credit.

Future A–E milestones:

- A: Coordinator integrates this bounded source; run local browser/keyboard/mobile review on a host that permits loopback.
- B: Operator verifies an authorized Context.dev account, pinned SDK schema and two public supplier URLs with terms permission; configure provider-side public-only/redirect policy and bounded transport.
- C: Implement separate trusted live evidence admission, using provider request/cache metadata and output success; record an authorized live before/after input that changes a decision, without actions.
- D: Retailer evaluates held-out real procurement cases, shipping/tax/MOQ/currency semantics, extraction accuracy, latency and refusal recovery. Keep missing costs unknown.
- E: Independently qualify host/privacy/accessibility and submission evidence. Human-only memo remains the boundary; purchases need a separate product and authority decision.

What would change the decision: a cheaper eligible offer, insufficient stock, late delivery, poor confidence, budget breach or stale evidence. Shipping and tax are excluded from this invented unit-price scenario; production totals must not silently omit them. Confidence is a supplied synthetic number, not calibrated extraction certainty.
