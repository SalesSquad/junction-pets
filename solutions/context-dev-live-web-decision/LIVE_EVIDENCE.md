# SupplyPulse actual live comparison — 15 November 2026

Implementation base: `7e460f8c5bbcdd3b921ea81780cdf5799e28a6b4`.
Initial live source: `4c25a15815dc0d36b4ed112d576ef14a1d694c12`.
Risk fixes / 30 focused passes: `f315bb5e0b5937b85f8858fab7f2cf7defbb466b`.
Only `solutions/context-dev-live-web-decision/**` is changed. Existing PR204's
branch/source is retained; no shared-service or Chibi production changes.

## Actual provider and browser execution

On the authorized MacBook Pro, Safari rendered the real product comparison.
Clicking **Refresh both sources** made the same-origin POST, then the server's
actual Context.dev REST client requested both pinned public product pages with
root `maxAgeMs:0`. The response flowed through `capturePublic → normalize →
compare → JSON API → rendered cards` without manual price entry.

| Source | Request ID | Received (UTC) | Measured duration | Ordinary item price | Member price | Starting shipping |
|---|---|---|---:|---:|---:|---:|
| Gigantti | `06731ac2-8c80-46e2-b1ea-0c82d640537a` | 2026-11-15 02:38:11.079 | 6.147 s | EUR 109.00 | EUR 69.99, excluded | unknown |
| Proshop | `d9fa6b5c-6b3f-4dc3-a6fd-09c13547d6b6` | 2026-11-15 02:38:08.016 | 2.878 s | EUR 109.99 | not supplied | EUR 6.99 |

Both responses reported cache age 0 and matching EAN `5099206129382` / part
`910-007501`. Both retailer offers reported InStock. **Gigantti is shortlisted
for ordinary item price only.** Its delivered total is unknown, not EUR109.
No retailer stock, tax treatment, destination-specific shipping or arrival was
independently verified. No actual market price/stock change was observed;
unchanged data is reported unchanged. Synthetic change controls are separate.

Safari's actual accessibility state showed both cards, normal/member prices,
starting/unknown shipping, request IDs, EET timestamps, refresh control,
"No material change detected" and the human-review limitation. There was no
horizontal document overflow in the observed desktop viewport. This is a local
Safari flow, not mobile-device, screen-reader or production qualification.

The owner explicitly approved restricted API-key setup in the current chat.
The new key has **Data APIs: Use** only; other permissions remain None. It is
stored in a mode-0600 host-only environment file outside Git; no credential
value, raw private session data or account logs enter source or evidence.
An earlier broad authenticated-page text read was rejected by automatic
approval review; the task continued only after the owner's explicit narrowed
approval. The rejected read was not worked around.

## Portable and HTTP checks

`node --test solutions/context-dev-live-web-decision/live/live.test.mjs
solutions/context-dev-live-web-decision/engine.test.mjs`: **30 passed, 0 failed,
0 skipped** on the fixed source above, Node 26.13.0 on MBP. Covers original
synthetic behavior plus real-response-shape transport, identity, ordinary vs
member prices, failed/partial/truncated output, cache, expiry, unknown shipping,
conflicting data, tie/requalification, bounded JSON-LD, timeout/body-size,
credential non-disclosure, concurrent refresh, exhausted credits, and actual
loopback HTTP origin/method/body/path checks. The first restricted-sandbox run
failed to bind a localhost socket (EPERM); the authorized unsandboxed run
executed that check successfully, without removing assertions or skipping it.
No broad suite or new GitHub Actions configuration was used.

Before final integration the existing repository-owned CRACI automatic workflow
started on the ready PR. It was not manually dispatched or reconfigured; its
actual result is tracked separately on PR279. A final source read also found
and fixed a cold-start race in capture initialization: all concurrent readers
and refreshes now await one initialization promise. The concurrency regression
now starts both refreshes immediately, without a timing-dependent sleep.

The generated `live/capture.json` independently retains two selected public
MCP retrievals at 02:29:32 UTC (request IDs in that file), useful as **saved
historical captures**, not a substitute for the REST/browser execution above.
No customer reviews or account-credit metadata are retained. Local hashes
support reproducibility, not provider authenticity or signed execution.

## Independent Nemotron review and disposition

Four parallel source-only reviewers (auth, money, errors, state) completed on
`4c25a15815dc0d36b4ed112d576ef14a1d694c12`; all processes exited 0. Their
findings are advisory, not a blanket approval or runtime test.

Accepted and repaired in `f315bb5`:

- Bound JSON-LD traversal by depth and total nodes.
- Put a five-second absolute deadline on incoming refresh bodies; guard a
  detached request socket and return 402 for the credit-blocked state.
- Distinguish unreadable capture files from invalid capture content.
- Make equal-price state `TIE`; label stale MCP evidence explicitly HISTORICAL.
- Refuse conditional main-price collisions and contradictory ordinary VAT-
  inclusive specifications; preserve the verified two-source normal-price path.
- Preserve the earlier fix: stale-to-fresh requalification is not a market
  winner-change claim. Regression assertions accompany the fixes.

Verified and retained boundaries (not defects in the stated product contract):

- This ranks **listed item price**, not delivered cost; neither a budget check
  nor purchase path exists. Unknown shipping never becomes zero. Converting
  the product to a delivered-cost winner would invent missing commercial data.
- A publisher can misstate its public offer; schema and EAN checks are retailer
  claims, not an independent price/membership audit. Conflicting advertised
  specs now refuse, and the UI still requires checking the retailer.
- Local processes/extensions are trusted in this single-user loopback tool.
  Same-origin/Host/header checks prevent cross-site browser calls, not arbitrary
  code already running on the Mac. This boundary is explicit in LIVE.md; a
  multi-user deployment needs separate authentication and is not included.
- Browser connection status is needed for first-run recovery and contains no
  key. A live API client necessarily holds its bearer credential in process
  memory; the key is scoped, never logged or returned, and not committed.
- Public-data request IDs are trace identifiers, not secrets. Imported captures
  are explicitly host assertions, never provider-authenticated receipts.
- Exported importer validation throws to its caller; its CLI masks errors.
  The real recursion issue was bounded instead of hiding invalid input.
- Generic unexpected failures deliberately avoid raw exception/credential
  leakage. No automatic retries occur, and exhaustion is sticky until operator
  restart so a refilled account cannot silently resume consumption.

## Scope still separate

No public deployment, unattended process, recurring monitor, supplier purchase,
reservation, message or official Junction submission. GitHub source integration
and the existing Portfolio PR Recovery ownership are recorded on PR279.

A bounded follow-up review of only the repair commit (errors/state, two parallel
reviewers, 180 seconds each) returned **timeouts with no findings text**. This
is an unavailable advisory follow-up, not an independent final-source pass.
The four completed original reviews and explicit dispositions above are retained;
the repaired source was author-read and its 30 focused checks passed.
Recorded real MCP captures also normalized successfully through the repaired
code at their actual historical observation time (not presented as a new fetch).

## Retailer news live run (15 November 2026)

Source: main `7f5cfde` plus the concurrency fix in this change, clean clone on
the owner's MacBook Pro, server on 127.0.0.1:4391 with the host-only key file.

1. First **Refresh both sources** (06:28 UTC): both scrapes succeeded
   (request IDs `d3a9a5f0-a9dc-43b6-bf0c-b07148498e00`,
   `1e4233f0-9f87-497e-9718-87ad7c624409`), but both news calls failed with
   `PROVIDER_RATE_LIMIT`. A single diagnostic call showed the key is limited to
   **2 concurrent requests** (`x-ratelimit-mode: concurrency`,
   `x-ratelimit-limit: 2`) and the service had fired four at once. Fixed in
   `live/service.mjs` (scrapes first, then news); `live/news.test.mjs` now
   asserts at most two requests in flight (fails with 4 on the old code).
2. Second refresh after the fix (06:29:49 UTC), no errors:

| Call | Request ID | Result |
|---|---|---|
| scrape Gigantti | `50409bc9-7cf1-4c90-921e-be54851c987c` | EUR 109.00, member EUR 69.99 (excluded), InStock, unchanged |
| scrape Proshop | `fb5f92f6-86d4-49ed-ab31-7bfe250ef259` | EUR 109.99, shipping from EUR 6.99, InStock, unchanged |
| news gigantti.fi | `03fb6bef-f1cb-4bba-822f-3ddd97c14e36` | `NO_RECENT_NEWS` (0 articles in 30 days) |
| news proshop.fi | none (404) | `NO_COVERAGE` (provider: no company found for domain) |

Shortlist: Gigantti on ordinary item price; no risk flags. Diagnostic calls
without the 30-day filter found only two loosely related Gigantti articles
(one secondary match from 2022), so the empty result reflects provider
coverage, not a bug. Credits remaining reported by the provider after the
diagnostics: 903. No key value was printed or stored.
