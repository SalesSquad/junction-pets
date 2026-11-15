# Valio Aimo browser-local App

This is an executable, English-language browser-only companion App. It uses the
original `src/core.mjs`, portfolio planner, purchase-unit arithmetic, diagnostics,
settlement and trust-envelope modules unchanged. It does not call a backend,
localhost service, sponsor API, model service or Chibi account/session API.

All catalogs, prices, policies, reviews, identities, orders and wallet transfers
are **invented local simulation**. Real signatures do not establish legal
identity, human presence, supplier authority, external consent, AP2/Kättely
conformance or real payment. Valio has not endorsed this independent prototype.

## Build and export

From this directory:

```sh
npm ci --ignore-scripts
npm run build
```

The declared producer generates `dist/index.html`, `dist/app.js`, `dist/app.css`,
`dist/NOTICE.txt` and `dist/export.json`. These are static App assets. Runtime
libraries are pinned `@noble/curves` and `@noble/hashes` (MIT); their versions and
license text are included in `NOTICE.txt`. esbuild and Playwright are build/test
dependencies, not runtime dependencies. No CDN, remote font or network data is
needed by the exported App. A secure browser context is required for WebCrypto,
IndexedDB and Web Locks; unsupported or denied capabilities fail closed.

The manifest records source-input SHA-256 hashes relative to the solution root
and output hashes relative to `dist`. `browser/verify.mjs` uses only Node builtins
and exports `await verifyBrowserBuild()` so the shared exporter can reject stale
source or modified assets without installing this package. It does not require
a Git commit, remote branch check or a new build when all verified bytes match.

## Original domain, narrow browser boundaries

- One typed milk/oat mission yields the original three cost/resilience/footprint
  choices. The portfolio requires both families; identical allocations are
  honestly labelled equivalent. The original portfolio budget gate is retained.
- A single-family need uses the original `requestReview` path. For example,
  1,000 L milk with a 140000-cent budget produces the real fixture's 37300-cent
  quote-only exception. It is one exact basket, not three invented alternatives.
- Human review in this App is an explicitly unauthenticated local decision.
  Only the displayed quote/snapshot can be acted on; edits require a fresh need.
- The buyer independently verifies its original typed need, packs, totals,
  budget exception and quote body before signing. Its WebCrypto Ed25519 private
  key is non-extractable and structured-cloned into IndexedDB.
- The original synchronous fixture supplier/trust module uses a narrow
  `node:crypto` adapter: noble Ed25519, SHA-256, secure random UUIDs and exact
  Ed25519 key serialization. Startup checks verify noble/native WebCrypto
  interoperability, SHA-256 equivalence and signature tamper refusal.
- `node:assert/strict` is adapted only for the original buyer verifier's `ok`,
  Object.is-based `equal` and strict plain-JSON `deepEqual`. Mismatches, differing
  prototypes, array order changes and unsupported shapes refuse; assertions
  are never replaced with no-ops. The signing canonicalizer is unchanged.
- Only the optional `node:child_process.spawn` OCR boundary is disabled. It throws
  `SERVER_OCR_UNAVAILABLE`; the original scanning parsers remain unchanged.

## Persistence and two tabs

Each operation takes a named Web Lock, reads the latest IndexedDB checkpoint,
rehydrates the actual domain and cryptographic registry, computes the candidate,
then writes through a revision-checked IndexedDB transaction. The UI receives a
success result only after the transaction completes. A failed storage ACK
preserves the previous checkpoint and blocks further purchasing until reload;
there is no memory-only fallback or silent identity/state reset.

Checkpoint integrity uses SHA-256 over JSON, allowing the original portfolio's
fractional advisory metrics. The original strict, integer-only signing digest
continues to cover the exact quote body. Saved state is bounded to 8 MiB and
incompatible/corrupted state is preserved and refused. Web Lock queueing is
bounded; BroadcastChannel is only an optional display-refresh notification.

The fixture supplier seed and synthetic evidence are origin-local data; this is
not an encrypted vault or a multi-tenant account store. Any same-origin script
has the origin's browser privileges. The App neither reads nor stores real Chibi
credentials, personal buyer records, provider secrets or production identity.
Use the private host/server architecture for those boundaries.

## Focused checks

```sh
npm run check
```

Playwright needs a configured Chromium installation. On an authorized Mac,
`PLAYWRIGHT_CHROMIUM_PATH` may point to the installed browser executable; no
browser is downloaded or installed by the producer. `PLAYWRIGHT_MODULE` is an
optional existing runner module override. The test creates only a short-lived
loopback **static asset server**; the App itself makes no backend requests.

Checks cover the strict assertion adapter, three actual portfolio choices, the
quote-only exception, real browser proof, non-extractable restored buyer key,
quota failure before storage ACK, two queued tab commitments behind the same
Web Lock, one order, one replay-safe transfer, full refund, reload recovery,
corrupt/denied storage refusal and 390px layout. The static requests are checked
for external provider traffic and non-GET/backend operations.

Six App scenarios execute fresh, isolated browser workspaces: purchase/refund,
recorded rejection, stale source, persisted retry, exact shortage and expiry.
Results arise from live domain calls and tested expected refusals, not canned
PASS labels. Their temporary records are removed after each run. Browser retry
means rehydrating and retrying a persisted domain action; it is not a Node
server/socket-loss, SIGKILL or machine-restart claim. The existing separate
seven-scenario Node laboratory remains the source of its own evidence.

## The full system remains available

The App links to the [original runtime and source](https://github.com/SalesSquad/junction-pets/tree/main/solutions/valio-trusted-trade).
The Node/SQLite service, external host JWT identity, signed host decisions,
MCP tools, server OCR, optional pgvector seam and provider-read integration are
preserved there. They are deliberately not represented as connected browser
features. Real Valio order integration still requires an approved contract,
sandbox, customer/branch authority and provider-qualified semantics.
