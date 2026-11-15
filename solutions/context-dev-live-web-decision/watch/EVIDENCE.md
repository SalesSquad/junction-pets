# Product watch qualification — 15 November 2026

## Source and focused checks

Implementation `41d84220d3462f560740d0d06397d54e04c12949` was developed from
main `262e328bf43b97b17bff02c2011f8e3d027cfe80` in an isolated checkout.
On the authorized MacBook Pro, Node's test runner passed **50/50, zero skipped**:

```sh
node --test solutions/context-dev-live-web-decision/watch/watch.test.mjs \
  solutions/context-dev-live-web-decision/live/live.test.mjs \
  solutions/context-dev-live-web-decision/engine.test.mjs
```

Coverage includes calendar/time-zone/DST behavior, exact product identity,
ordinary/member prices, unknown costs, cancellation and late-result fencing,
SQLite idempotency/CAS/reopen, concurrent reservations, UTC rollover, orphaned
run isolation, run limits, provider failure and same-origin HTTP controls.
Synthetic provider responses in these checks are not live-provider evidence.

Follow-up `22f4a517297a3972634d8dfe4a5e947090820899` adds an atomic persisted
provider-block check before both new claims and subsequent submissions. The
focused `search auth/credits` regression passed, including negative manual
search/research and positive explicit-resume cases. Source-only UI refinements
clarify key configuration, historical evidence and advisory research. The
unchanged earlier suite was not rerun for these presentation changes.

## Executed Context.dev and browser flow

The local server used the owner's previously authorized restricted host-side
Context connection. No credential or account metadata is in this record.
Private qualification state was separate from normal application state.

Safari created a manual watch for Logitech MX Master 3S Bluetooth Edition,
EAN **5099206129382**, ordinary unit-price ceiling EUR120, one unit, new and
in stock, Gigantti/Proshop, catalogue expansion enabled. Save made no provider
call. Explicit Run now submitted six bounded requests:

| Operation | Context request ID |
| --- | --- |
| Search | `e35918d3-9a21-4c3c-9ef2-1b672130d4a9` |
| Map | `908bcebb-b7cd-4e0c-b5a5-b2f402ac0cef` |
| Scrape | `1da168bb-382b-478a-a498-1dbd49a86173` |
| Scrape | `b36828c2-a546-4b6b-aff7-6edcf5e6c595` |
| Scrape | `2d5920aa-fcaa-4924-82f8-d35494520489` |
| Scrape | `95c7e77b-db2b-4637-9c6e-68e83044ac05` |

At 03:39 UTC it retained two exact-EAN offers: Proshop EUR109.99, shipping
starting EUR6.99; Gigantti ordinary EUR109.00, member EUR69.99, shipping unknown.
Both reported new/in-stock. Two additional discovered pages were rejected,
without substituting variants or turning missing prices into zero. These are
historical public retailer observations, not stock reservations or delivery
quotes. The UI showed separate prices, exact identities and first-observation
events; no price-drop claim was invented.

Explicit Answers research succeeded. The initial task lacked the exact EAN and
returned a similar variant; the final task now includes EAN, quantity, stock,
condition and membership controls within the documented 2,000-character limit.
The final task's actual request `673bbf6e-dff7-406a-bc97-b9ecf733f877` returned
the correct product URLs but confused Gigantti's member price with an ordinary
public price. This contradiction is preserved: research stays **unverified
advice**, cannot replace verified offers, and now has an explicit UI label.
A successful model response does not prove its price or matching claims.

A separate finite watch was saved through the same HTTP API with a one-off
03:47 UTC schedule and **maxRuns: 1**. Without Run now, the normal server
scheduler claimed it at **03:47:04.106 UTC**. It completed at approximately
03:47:35 UTC, returned the same two exact-EAN offers, then paused with no next
slot. Requests:

| Operation | Context request ID |
| --- | --- |
| Search | `91c2003c-eec3-4f0b-9b2b-755b2c67afed` |
| Scrape | `4965935c-085d-4b33-abcc-f2de5c93e624` |
| Scrape | `804c8897-6f27-4f81-9f04-6931c8d15151` |

An isolated in-app browser then rendered the completed scheduled watch,
1/1 run limit, paused state, historical retrieval times, separate prices,
source history and readable advisory research. Safari's original live watch
flow and this later rendered check are distinct observations. The finite
qualification watches exhausted their limits; no recurring owner watch or
provider monitor was activated.

## Independent risk review

The existing Verda Nemotron route reviewed git-object source at `41d84220` in
four parallel focuses (money, auth, concurrency, data), all completed. Its 14
advisory items were checked against the implementation:

- **Fixed:** direct manual API requests could bypass persisted provider pause.
  Claims and individual submissions now check the block transactionally;
  regression checks above passed. Key-configured wording was also clarified.
- **Refuted accounting claims:** `runs.reserved` is immutable; only
  `budgets.reserved` decrements. `reserved - requests_used` is therefore the
  correct release amount. Edit/pause/archive call `cancelRunning` before
  revision changes, so late completion neither locks nor releases twice.
- **Intentional conservative limits:** failed and map submissions count before
  transport because they can consume provider capacity. Refunding failures or
  waiting until success would weaken the submission cap.
- **Documented recovery boundary:** automatic deletion/reclamation of another
  process's unknown running work is not safe. Pause/resume explicitly recovers
  an orphan; due jobs skip it. SQLite state is single-owner local data, not a
  multi-tenant service. Loopback Host validation plus browser same-origin
  isolation protect reads; mutation requests add the origin/header gate.
- **Privacy/design scope:** product descriptions are explicitly submitted to
  Context, with an in-form warning and common credential-pattern refusal.
  Archive is explicitly recoverable and retains history. User-requested memo
  export is local plaintext. No child/private dataset, automatic hard deletion,
  encryption service or inferred PII classifier was introduced. Total saved
  watches/runs are bounded (30 watches × 30 runs); returned history is capped.
  Provider key presence is configuration, never a validity attestation.

A separate read-only repair reviewer exercised interleaved reservation,
partial usage, edits/cancel, duplicate finish, block/resume and midnight
sequences without provider calls; no material findings remained. Reviewed
SHA256: store `aa09967293fc4e5ec840afa8bf388d5e3383c362f9f0eb7b9e7c183ce11d2c81`,
service `98f7e330d13b6b66060ffb64c0614b0b60293c358c294bd091cef2a02d1d5123`.

This qualifies the stated local workflow. It does not establish cloud/24-hour
execution, OS wake-up, external notifications, a hosted release, an official
challenge submission, every retailer/product, or the factual reliability of
Context Answers. The server must run for scheduled work.
