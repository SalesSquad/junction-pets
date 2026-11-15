# Verification — J26-PF-CONTEXT-M1-20261114

Date: 2026-11-14. Executor: local restricted Codex workspace, Node v26.13.0. Source base: `98d5a524d61e431ca36acd62b268ede343fc7fe2`; branch `codex/j26-context-live-web-decision-20261114`. Dirty baseline was clean. Product bytes are uncommitted intentionally; coordinator alone commits/pushes/opens PR. No Issue #77 changes.

## Observed execution

`node --test solutions/context-dev-live-web-decision/engine.test.mjs`: **18 cases, 17 passed, 0 failed, 1 skipped** in final run. Tests cover material/cosmetic decision behavior, HTTP200 failed output, partial output, unknown fields, fractional/overflow cents, exact TTL boundary, stale cache, invalid/future dates, exact URL bindings, conflicting/identical duplicates, bounded input, ineligible candidates, deterministic hashes, inert injected text, disabled live seam, mock SDK output validation and comparator outcomes.

The server test initially failed with actual `listen EPERM: operation not permitted 127.0.0.1`. It now reports an explicit skip only on EPERM; other errors still fail. This is an environment limitation, not a server pass. Loopback HTTP, CSP enforcement in-browser, responsive rendering, keyboard navigation, download behavior and visual accessibility remain **not verified**. UI source includes semantic tables, labeled replay buttons with pressed state, live result announcement, focus indication, skip link, reduced motion handling and text-only DOM insertion; these are implementation observations, not an accessibility audit.

`node solutions/context-dev-live-web-decision/cli.mjs after` executed: Coast recommended for human review at EUR540, North excluded for insufficient stock; input and policy hashes printed, no action authorized. `node solutions/context-dev-live-web-decision/comparator.mjs` executed with eight labeled synthetic results.

An initial comparator assertion incorrectly expected two baseline successes; observed baseline correctly chose Coast in the cheaper-Coast case, giving three successes. The expected count was corrected to match the enumerated comparator outcomes; the decision thresholds and scenario expectations were not changed.

## Synthetic comparator

| Set | Expected decisions | Policy result | Price-only baseline |
| --- | --- | --- | --- |
| Three baseline cases: original, stock drop, banner | North, Coast, North | 3/3 | 2/3 |
| Five held-out variants: failed JSON, delivery slip, over budget, cheaper Coast, expired evidence | Refuse, Coast, Refuse, Coast, Refuse | 5/5 | 1/5 |

Overall 8/8 versus 3/8. “Held-out” means separate scenario variants outside the primary UI replay, **not blinded or independent evaluation**. All were authored by the implementer and are small deterministic policy examples. No significance, calibrated confidence, extraction accuracy or supplier performance is established. A raw text-diff alarm incorrectly treats the banner as important and misses structured delivery/price changes when supplied text stays identical. Semantic comparison uses typed fields; safety admission separately checks output success and time.

## Provenance and boundaries

Read local START_HERE, AGENTS, AGENT_SOURCE_INDEX, CURRENT_SOURCES, current-source-catalog partner `context-dev` and M332/T44, company research, existing extraction helper and contract. Latest clarification is null; previous dated guidance was reviewed. Fixtures are authored fictional content under SYNTHETIC_REPLAY, not copied supplier pages or licensed provider output. SHA-256 binds supplied bytes and policy but proves no remote fact. No SDK was installed and no Context.dev request, secret, credits, production account, hardware or CI execution was used.

The official scrape documentation was read without provider execution. SDK field placement must be verified before any live use; see README. The live target map is empty, outbound browser connections are denied by CSP, and the server only serves five literal assets via GET/HEAD on IPv4 loopback. There is no POST API, URL fetch route or runtime target configuration.

Maturity **2/6**: functional synthetic decision prototype and source-only adapter; not live-integrated or browser-qualified. Next dependency: coordinator runs the local UI on an authorized loopback-capable host, then operator verifies pinned SDK contract and exact public source policies before implementing live admission. Partner challenge integration remains unverified.


## Independent coordinator follow-up — authorized MacBook Pro (14 Nov 2026)

A second execution outside the Codex workspace sandbox used MacBook Pro Node v24.12.0 with the same source tree. Its read-only IPv4 loopback HTTP/CSP/method/path security test **passed**, establishing that the earlier EPERM was a worker sandbox limitation, not an observed server defect. Before committing, the coordinator added one strict unknown/missing-source-field negative regression matching the already-implemented exact schema guard; the final Node built-in test command returned **19 passed, 0 failed, 0 skipped**. The unchanged eight authored deterministic scenarios returned 8/8 expected decisions vs 3/8 for the price-only baseline. The Git whitespace check returned clean. No provider access, customer data, real supplier observation, software signing, hosted browser, public deploy or FINAL approval was involved. CRACI CI, if triggered by the eventual PR, is separate and must be source-HEAD-verified before reporting green.
