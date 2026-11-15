# Read-only procurement diagnostics

This independent client explains why the invented procurement request cannot be
filled and identifies the smallest budget change **only when complete compatible
stock exists**. It creates no session, quote, approval, reservation or order.
All product facts and amounts are synthetic, noncommercial fixture data.

## Run

In the solution directory, start the existing supplier with `npm start`.
In another terminal:

```sh
node src/diagnose-agent.mjs --milk-litres=1000 --budget-cents=140000
node src/diagnose-agent.mjs --milk-litres=2000 --budget-cents=250000
node src/diagnose-agent.mjs --milk-litres=1000 --oat-litres=1000 --budget-cents=140000
```

With the unchanged invented catalog these report, respectively:

- **BUDGET_REVIEW_NEEDED:** minimum 177300 EUR cents, additional 37300 cents.
  This asks for budget review; it is neither a quote nor approval.
- **STOCK_SHORTFALL:** 320 L of compatible milk missing. Complete-basket cost
  and additional budget are `null`; increasing budget cannot fix this stock snapshot.
- **POLICY_LIMIT_EXCEEDED:** complete two-family minimum 339300 cents exceeds
  the existing server-owned 250000-cent ceiling. Refer to the policy owner;
  this client does not raise the ceiling.

Omitted product quantities default to 1000 L milk only when neither product
option is supplied. `--oat-litres=240` requests oat only. All requirements remain
lactose-free with the fixture delivery date, 16 November 2026. Duplicate,
unknown, fractional, negative and exponential options are refused.

## Integration seam

`diagnoseProcurement` in `src/procurement-diagnostics.mjs` is a pure function.
Provide the bounded structured catalog, one or two distinct typed requirements,
the request budget and the existing server-owned policy budget. It returns
per-family shortages, excluded product reasons, exact-cent cheapest compatible
allocations and the stock/price versions used. Missing structured facts and
duplicate SKUs are rejected; product description prose is not interpreted.

The CLI discovers and checks the synthetic API contract, then makes exactly four
public **GET** requests: discovery, OpenAPI, policy and catalog. It sends no
authorization header. Only plain localhost HTTP is accepted; redirects, external
discovery origins and unlabelled catalogs are refused. Reads are individually
bounded by a five-second timeout and a 1 MiB response limit.

The standalone CLI remains read-only. The existing browser now uses the
server-owned review flow below. Portfolio PR Recovery retains integration and
merge ownership; the pending Frontier/settlement branches need to retain these
new core, server, contract and browser changes during reconciliation.

## Snapshot-bound quote and exception card

Open the existing local browser workspace and select the EUR 1400 budget.
The server diagnoses the exact need and builds any viable quote in the same
synchronous source read. Only the requested product family is inspected.
The immutable source identifier covers those product facts, the constraints,
the server policy and an ephemeral service-instance namespace. It is a revision
identifier, not a supplier signature or authenticated commercial identity.

- `POST /api/reviews` uses the existing synthetic buyer capability and accepts
  the same bounded request as `POST /api/quotes`. It returns a diagnosis, a
  coherent source snapshot and either a fixed quote or `quote: null`.
- Missing exact stock or a minimum exceeding the existing policy ceiling has
  no approvable quote. These constraints cannot be waived by the card.
- A budget exception retains the **original** requested budget and records
  the exact additional cents with scope `THIS_QUOTE_ONLY`. Even below the
  normal automatic threshold it requires an explicit simulated decision.
  Without a budget exception, the existing low-value auto-commit rule remains.
- `POST /api/reviews/{id}/decision` requires `buyerId`, `decision`,
  `snapshotId` and `quoteId`. The session must own both review and quote.
  Altered, missing, foreign or expired bindings are refused; the legacy
  approval endpoint cannot approve a review-backed quote.
- The card shows original budget, exact basket total, extra budget, unchanged
  product/diet/date/quantity constraints, validity and the no-reservation limit.
  Editing form inputs disables consent to the previous displayed terms.
- Approval covers that one quote and does not raise the buyer policy ceiling.
  Current relevant source facts, policy, expiry and decision bindings are
  rechecked before commitment. New quotes never inherit old approval.
- Same-key order replay still returns the existing receipt without another
  stock deduction. A new request is disabled while an active simulated order
  still needs cancellation, preserving its visible receipt and cancel action.

The browser may automatically request a fresh proposal, but cannot approve
it. All actors and decisions remain explicitly unauthenticated synthetic demo
data; no real procurement authority is introduced.

## Limits

The exact minimum applies to the complete **invented snapshot**, whole litres
and linear net unit prices. There is no freight, VAT, package rounding, supplier
minimum order, reservation, stock forecast or authentic supplier assertion.
Policy and catalog are separate reads, not one atomic database snapshot.
Changed stock/prices require new diagnostics and a fresh server-owned quote;
all existing approval and commitment checks still apply. A feasible diagnostic
never grants purchase authority. No sponsor API or real order is contacted.

Focused verification:

```sh
node --test tests/procurement-diagnostics.test.mjs
```

The checks include an exhaustive small-inventory minimum-cost oracle, hard
diet/date exclusions, unknown-source refusals and a separate real Node buyer
process proving only GETs occur while catalog, policy and audit remain unchanged.
No browser, deployment, real buyer identity or sponsor integration is qualified.

Snapshot/consent boundary verification:

```sh
node --test tests/snapshot-review.test.mjs tests/core.test.mjs tests/http.test.mjs tests/agent-boundaries.test.mjs tests/procurement-diagnostics.test.mjs
node tests/approval-card.browser.mjs
```

The optional browser check uses the repository's Playwright dependency; an
existing isolated module and Chromium executable can instead be selected with
`PLAYWRIGHT_MODULE` and `PLAYWRIGHT_CHROMIUM_PATH`. It runs only against its
own ephemeral localhost server, closes its own browser/server, and can write
temporary card captures to `VALIO_REVIEW_SCREENSHOT_DIR`.
