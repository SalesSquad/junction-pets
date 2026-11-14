# Lumo architecture

```
Local sponsor CSV (synthetic only)
  └─ src/import-sponsor.mjs — streaming 1-customer subset → gitignored JSON
       └─ Browser session, in-memory only
            ├─ web/app.mjs — questions, reserves, what-if runway, source explorer
            ├─ src/coach.mjs — schema, exact cents, three baskets, 7/14/30 what-if math
            └─ web/styles.css — responsive iPhone-first visual system
```

`node server.mjs` serves localhost static files. No HTTP POST, network fetch, accounts, database, secrets, model tokens, analytics, Chibi runtime or provider calls. Input text is parsed via a declared finite set of intents and does not execute instructions. `answerQuestion` has no side effects. Source row numbers refer to synthetic fixture lines or the sponsor CSV's original lines, and reflect only user-provided data, not external provenance attestation.

Latest account balance selection compares validated `tx_timestamp` values (UTC fallback if timezone absent). A later CSV row does not imply a later transaction. Conflicting balances at the same latest timestamp cause a deliberate refusal; the UI budgeting formula is visibly clamped with `max(0, ...)` and labels any reserve shortfall. These choices prevent a plausible but false budget answer when input order or reserve size is adversarial.

The core is portable ES Modules and can be composed with a consented model intent adapter later. Trust invariant: the model may propose an intent but cannot supply the answer amount, rewrite a source row, classify an unknown merchant without a reviewed mapping, or authorize any financial action. Sponsor data stays outside version control.

## M2 educational planner contract

`planSpendingWindow` consumes an existing **source-cited, timestamp-checked** reserve-adjusted illustration and exactly three user inputs (`days` among 7/14/30, `dailyFlex` in euro cents, `oneTime` in euro cents). `remaining = max(0, illustrative_start - days × daily_flex - one_time)`; if the raw result is negative, report the exact gap and show 0 remaining. For an alternative daily spending envelope, `floor(max(0, illustrative_start - one_time)/days)` performs exact-cent conservative rounding. Intermediate multiplication/total must stay within JS safe integer cents. This is a deterministic *what-if*, not a future model or advice. Source references point only to historical latest account balances.

The benchmark `tests/synthetic-acceptance.test.mjs` pins 30 independent exact-cent Q&As against authored fictional rows, with explicit expected source CSV line IDs. It is not sponsor production qualification: `SPONSOR_SOURCE.md` records the official Git LFS pointer SHA and unavailability of actual object bytes.

## Ownership

- Solution owner: one S-Pankki solution developer, `solutions/s-pankki-economic-trainer/**`.
- Reuse/peer, non-runtime: `junction.s-pankki`, `junction.afterquery` (adversarial review), `junction.mariadb` (future temporal reconciliation), `junction.aiven` (future managed-data seam).
- Root scaffolding: [pending PR #64](https://github.com/SalesSquad/junction-pets/pull/64), not duplicated here. Files `solution.json`, README, architecture, progress and AGENTS are compatible with its schema but cannot claim the PR merged.
- Shared registries, generated plugins, private Chibi, banking identities and all other companies are outside this task.

