# Spread offline dispatch director

**SYNTHETIC_OFFLINE · maturity=2/6 · no sponsor connection · unsigned audit JSON.**
Work-ID J26-PF-BAHN-M2-20261114. This runnable local decision laboratory maximizes reserved gross margin subject to a >=90% **heuristic synthetic lower safety score**. It does not guarantee 90% delivery in Spread, reproduce the sponsor simulator, or dispatch cars. No key, HTTP client, team creation, board, final or submission code exists.

## Run

Python 3.10+ standard library (arbitrary precision integer arithmetic); Node 22 for the optional UI smoke. No install or root manifest changes.

```sh
cd solutions/bahn-freight-optimizer
python3 optimizer.py demo --seed 11 --level 8 --output demo.json
python3 optimizer.py compare --output comparison.json
python3 optimizer.py recommend --input snapshot.json --output audit.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
node test_ui.cjs
```

Open `index.html` locally in a browser, then select demo.json or comparison.json. The responsive English operator desk exposes recommendations, abstentions, all fee alternatives, timed stops and comparison ledgers, and downloads unsigned JSON. Scenario changes use CLI `--seed` / `--level`; no server required. Browser rendering uses textContent only, including hostile imported strings. This is a DOM smoke-tested UI, not visually qualified on desktop/mobile.

## Source contract

Repository base: `a33f525171b6424d39dfc4c889b63e0fc5cb459e`. Partner `bahn-express`, owned brief M349, latestClarification=null; previous guidance 13 November. Local public read-only kit supplied on this MBP, hashes verified before implementation:

| Source | SHA256 |
| --- | --- |
| RULES.md (13 November, authoritative over handbook) | `657c44f88e36d2dab3e0b0ea28d552bdfb9796cfd61ce49634a9e3a6dd10cdbc` |
| HANDBOOK.md | `afd234e526c5dd72d82709ee87a94c2d4e90e56013dce7f89b06f56dca57f7f9` |
| API.md v0 | `6e5b460752b39562f0b2c8107e214ddad62cc696623feb6428239852f8c8a377` |

Public source: https://spread.bahnexpress.com/kit/ (RULES.md, HANDBOOK.md, API.md). No sponsor endpoint was called in this implementation. Final Sunday 15 November 08:00 Helsinki; registration closes 07:30. These dates convey no authority to participate. Live GitHub main verification was blocked by DNS; checkout origin is SalesSquad/junction-pets, clean starting HEAD was the requested base.

### Explicit validated mapping, not a raw DeskSnapshot parser

The kit docs describe semantic entities but do not include the complete OpenAPI/kit types. Therefore **raw sponsor snapshots are refused**. `format=spread-offline-mapping-v1` requires an explicit local mapping, with exact keys, bounded arrays, unique IDs, integer validation (bool/fraction rejected), and no unknown fields. Use `scenario(11)` in optimizer.py as an executable fixture. A future connector must pin/validate official OpenAPI before converting data; this adapter is not live compatibility proof.

| Local field | Sponsor concept / mapping requirement |
| --- | --- |
| now, level | Whole world minutes, level 1–8 |
| requests[].id/respondBy/referenceFeeCents/note | Price request identifier, response cutoff, typical driver fee and untrusted dealer note |
| options.{same_day,next_day,within_3_days} | Explicit deadline and listPriceCents from the accepted options; never infer business-day dates |
| legs[].pickup/delivery | placeId, window [from,to], open [from,to], private; mapper must resolve the relevant day's real/stated hours and choose conservative intersection |
| roadMinutes/km | Published map road metrics, not straight-line estimates |
| premium/manualGearbox/electric/chargePercent/needsPlates | Explicit car facts; unknown facts must not be silently defaulted |
| releasedAt, snow | Known readiness/payment release, null means unknown; snow blocks quoting pending tyre/forecast resolution |
| drivers[].id/rating100/completedGigs/manualLicence | Driver profile; rating scaled to integer hundredths |
| availableAt/reliabilityBps | **Synthetic operator evidence**, not published roster truth: availability buffer and uncalibrated reliability basis points |
| status/revision | Local pending/cancelled lifecycle and immutable revision number |

No secrets should be supplied: unknown fields such as API keys are rejected. Money is integer cents, input bounded below interoperable JSON safe-integer limits with ample multiplication/sum headroom; Python arithmetic never overflows. Output is JSON numbers. No monetary floating point is used. Files are bounded to 2 MB; no eval, shell interpolation, external dependencies or network access.

## Decisions and recovery

At levels 1–3 every quote wins the first offered option at list price, so unsafe requests get no quote. At 4–6 candidate quotes use 96% list; at 7–8 120% list, explicitly a frozen synthetic policy, not learned competitor pricing. Evaluate low opening fee (80% reference) versus high (110%, or 150% in shortage), reserving the highest scheduled fee plus 10% quote contingency. Level 1 has one step; later levels have monotone opening/30-minute steps. These are illustrative policies, not an empirically optimized price model. Declines are abstentions; the level >=4 goodwill cost of silence is acknowledged, not simulated or bypassed with an unsafe high-price quote.

Drivers must satisfy premium experience (>=4.8, >=50 completed gigs) and manual licence. Earliest available eligible driver is reserved sequentially, preventing simultaneous claims on one driver. Home/transit, market acceptance, hidden workdays and drops remain unknown; a 60-minute access buffer, 20% road duration cushion and 60-minute deadline reserve are conservative synthetic assumptions. EV <30% and >200 km adds a 40-minute charging stop; plates add 30 minutes. Actual opening intervals, payment release and private slots constrain stops. All nonempty dealer notes fail closed for manual review; multilingual/correction interpretation is deliberately unimplemented.

A two-leg trade-in is sequenced new-car delivery then old-car pickup. Connected place IDs are required; unknown inter-leg roads abstain. >720 road minutes across two cars abstains with a split-required reason: automatic split needs independent second-driver evidence and is not implemented. This intentionally sacrifices profitable work rather than inventing deliverability. Per-leg safety uses a union bound for two-leg orders, not an independence assumption. Only positive reserved margin and lower score >=9000 bps qualify. Projection is **not statistical confidence**: no official data calibration, confidence interval or real reliability claim exists.

`Book` is a separate replay helper, not a complete sponsor event decoder. Explicit mapped event keys seq/kind/orderId/revision support JSON checkpoints and duplicate-sequence suppression; cancellation is terminal, changed orders invalidate plans for review, expiry/drop/no-show requires replan/repost, release (payment/readiness event) permits replan. No repost executes. Started gigs cannot be released through `release_fee`; fees are rounded conservatively at 25/50/100%, with free driver_late release before start. Cancellation settlement and cross-order shortened/continues gigs need official ledger ingestion and are not simulated here. The planner uses one order per gig, so cross-order gig cancellation is absent. Snapshot resumption requires a fresh authoritative mapping; local idempotency hashes are audit identities, never exactly-once server guarantees.

Direct offer helper enforces level>=3, 07:00–23:00 reading hours, <=3 per driver/day, <=3 concurrently open per gig and ten-minute expiration. It reserves counters only; does not send offers, infer acceptance or claim live cap compatibility. Production must rebuild actual offer state from sponsor events.

## Seeded comparison and limitations

`comparison.json` contains actual deterministic offline runs and per-order revenue/fee/on-time ledgers. Fixed seeds 11/29/47 and held-out 101/211/307 are declared in code; the 9000-bps threshold and pricing/safety constants were not tuned against holdout. The simulation model was corrected during implementation to give both policies the same per-request hidden draws and fee-dependent booking costs; no claim of a blind independent experiment is made.

Baseline quotes list price, posts at 80% reference, and ignores constraints. Both policies face the same synthetic per-request demand, cancellation, fee requirement, booking and delay draws. The outcome model is intentionally small: revenue less driver fee, with 25% late refunds, not the official full ledger, price war, trust, business-day refund tiers, undelivered penalties or dynamic multi-gig driver economy. Gross margin below means **this toy model's actual integer ledger sum**, not official performance. It favors funded gigs by construction; it establishes runnable decision mechanics, not competitive advantage.

| Split / seed | Baseline won / on-time / GM cents | Optimizer won / on-time / GM cents | Optimizer >=90% |
| --- | --- | --- | --- |
| fixed 11 | 32 / 1 / 679022 | 19 / 19 / 550611 | yes |
| fixed 29 | 35 / 4 / 768656 | 26 / 25 / 768397 | yes |
| fixed 47 | 31 / 2 / 659427 | 25 / 25 / 725784 | yes |
| held-out 101 | 37 / 1 / 776606 | 22 / 22 / 637429 | yes |
| held-out 211 | 34 / 3 / 727793 | 21 / 21 / 576330 | yes |
| held-out 307 | 33 / 2 / 737687 | 19 / 16 / 568791 | **NO (84.21%)** |

All baseline runs miss the delivery minimum. Optimizer seed 307 fails despite every admitted plan meeting its heuristic safety threshold: a concrete warning that the guard is uncalibrated. Failure counters in JSON identify toy delay/drop versus baseline underfunding/unread constraints. No-order runs are not ranked; cancelled orders are excluded. The benchmark does not execute actual sponsor dispatch, so cancellations/reposts/release correctness is tested separately rather than claimed as end-to-end sponsor behavior.

13 targeted Python tests cover cents/bounds, unsafe exclusion, cancellation/cutoff, release costs/started refusal, notes, licence/experience, EV, levels/schedule, 12h, replay restart/idempotency, offer caps and strict serialization. UI DOM smoke checks inert malicious strings and oversized input. No browser/device visual acceptance, real key, practice round, team registration or external integration was verified.

**Exact next external dependency:** a legitimately registered Spread team API key plus an official practice-world held-out round and >=90% minimum. Coordinator first reviews this exact commit and the held-out failure; separately authorize official mapping/key handling and a practice run. Do not create a team, spend credit, dispatch a runner or enter final/board from this artifact. Tiger Data T53 time-series market/driver reliability telemetry is **proposed/unconnected**; nothing installed. Local files are source artifacts for GitHub integration, not a claim of iCloud persistence.
