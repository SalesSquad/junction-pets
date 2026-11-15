# Chronicle Studio — M307 product UX milestone

**Source-bound synthetic demonstration, not a live MariaDB or Wikipedia integration.**
This is a product-only extension of the existing Chronicle Witness chronological core.
Official M307 sponsor brief: Wikipedia Through Time, snapshot 2026-11-14;
partner evidence key mariadb, owned brief M307, latestClarification=null.

## What works

Run: node solutions/mariadb-wikipedia-time/studio/server.mjs
Open http://127.0.0.1:4177 on the same Mac. No package install, API key,
daemon or external server is required. To stop, press Ctrl-C.

A reader chooses one of two fictional articles, an exact historical UTC revision,
and an earlier comparison. The source-bound engine shows the corresponding
snapshot, SHA-256 body fingerprint, lexical added/removed words, revision
timeline, and human-review-only short A–B–A revert candidates. An as-of view
cannot include a future revert candidate. Missing or same-time ambiguous
records produce refusals, not arbitrary answers. The demo has keyboard-operable
controls, screen-reader status, a responsive 390px layout and reduced-motion
support. All text is inserted via DOM text nodes, not unsanitized HTML.

Focused check: node --test solutions/mariadb-wikipedia-time/studio/studio.test.mjs

## Truth and safety boundaries

- Explicit SYNTHETIC_REPLAY_NO_MARIADB on every response; no provider call or
  purchased API, no Wikipedia source/license verification, no vector search,
  no human intent/factual accuracy inference, no production hosting.
- Server binds 127.0.0.1 only, validates Host/Origin, serves an exact
  allowlist of assets, uses restrictive CSP and no-store, accepts a 2048-byte
  bounded JSON query with exact key set, and makes no state changes.
- The timeline intentionally displays all fixture history; historical
  as-of findings and revert flags are restricted to the selected UTC cutoff.
  Cryptographic body digests authenticate only local bytes, not Wikipedia.
- This studio does not change the database schema, Core M1/SQL tests,
  sponsor corpus or independent MariaDB 11.8 qualification receipts.

## Next single dependency

To progress from polished local replay to an actual sponsor-connected product:
use a licensed and revision-pinned Wikipedia dataset, execute import plus
prepared as-of queries against a real isolated MariaDB SVT instance, compare
held-out timestamp-boundary/identity cases to an independent oracle, then bind
the verified results to this studio. The previously reported MariaDB 11.8
identity-collation failure and fix are separate historical evidence. Don't
treat a passing local UI test as fresh MariaDB or Wikipedia qualification.

Integration and merges belong solely to Portfolio PR Recovery; this branch
owns only solutions/mariadb-wikipedia-time/studio/**.
