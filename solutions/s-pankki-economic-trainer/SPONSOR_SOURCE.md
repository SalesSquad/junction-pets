# S-Pankki synthetic sponsor source — pinned acquisition record

## Current authenticated OFFLINE source qualification — 15 November 2026

The official public organizer repository's **Git LFS Batch API** returned a
download action for the exact object referenced by the historic pointer.
The entire file was acquired on the already-authorized MacBook Pro without
installing new tools or using paid providers. Verified locally:

- Repository: `hackjunction/Junction-2026-S-pankki`, public challenge data
  (no general redistribution license was shown; raw data stays private).
- Real LFS object: **362,796,501 bytes**, SHA-256
  **`49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63`**.
- Actual official sponsor-provided **SYNTHETIC** transactions: **3,626,755
  rows**, dates 2024-10-01 through 2026-09-30, with the declared 10 fields,
  no observed multiline rows, no rejected cent-precision amounts in the
  private whole-file scan.
- Sponsor `tx_timestamp` is **`DDMONYY:HH:MM:SS`** (e.g. a month written in
  three English letters), **not ISO 8601**. The original prototype refused
  actual rows. This branch binds the timestamp's two-digit year, day and
  month to the separate full-year `tx_date`, rejects any conflict/invalid
  clock time, and interprets missing timezone as UTC **only for deterministic
  ordering**, never as bank-provided timezone proof.
- Official transaction types contain **35,668 `investment_deposit`** and
  **6,189 `salary_sweep`** negative-account movements. Previously these
  were incorrectly included as consumer spending. Their signed values
  represent **€36,445,997.76** across this *synthetic* file. They are now
  source-confirmed non-consumption movements: still included in the
  sponsor's historical account balances but excluded from spending totals.
  No real customer loss, money movement or bank error is asserted.
- The private reproducible check preselected the first synthetic customer
  *by file order* before viewing outcomes: 581 source rows, 24 distinct
  months, **24/24 independent exact-cent monthly totals and 533/533
  originating source-row citations match**, and all 24 sampled
  savings/sweep movements are excluded. One representative question answer
  and budget source provenance matched. This is **offline sponsor-synthetic
  qualification**, not an independent bank balance, a held-out sponsor
  grading set, a live API, or real-user accuracy.
- The sponsor's broad `Transportation`, `Lifestyle`, `Home & Tech`,
  `Health`, `Travel` categories remain explicitly *unclassified*
  pending more precise merchant/necessity semantics. A missing
  classification is never silently renamed `Taxi` or guessed essential.
- Private evidence remains in an access-limited task scratch directory
  outside the repository; no raw CSV, customer IDs or transaction excerpts
  are committed or posted to GitHub. Actual provider cost not measured.
  This proves a synthetic dataset import and two concrete accounting
  corrections, **not sponsor API authentication or financial advice**.

**Next single data dependency:** one independent, disjoint official-synthetic
customer cohort with externally specified expense-class semantics and
labelled expected questions; then a consented mobile usability study.
Keep live bank/Open Banking permission, payment and real customer data entirely
out of this offline challenge experiment.

**Observed at:** 2026-11-14, using the authorized GitHub repository connector. This is a **source record**, not a claim that the sponsor's CSV was imported or analyzed.

| Source | Verified value |
| --- | --- |
| Public official repository | `hackjunction/Junction-2026-S-pankki` |
| `main` at inspection | `fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f` |
| Sponsor README Git blob | `8498dcfe7745befa019cd9984ca39d6b02fcff63` |
| `tx_junction_transactions.csv` committed Git blob | `a9e792b4004c0e54a96857dd72d91539124ba0be` |
| Git LFS pointer (`134` bytes) | `version https://git-lfs.github.com/spec/v1` |
| Referenced LFS object SHA-256 | `49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63` |
| Referenced full CSV size | `362796501` bytes (~346 MiB) |
| Customer metadata source Git blob | `9638bb4e556e6e748a417e3317f9af11bdf58409` |

Official schema confirmed by README and customer-file header: `customer_id`, `bank_account_id`, `tx_date`, `tx_timestamp`, `category`, `tx_amount_eur`, `balance_after_eur`, `transaction_type`, `merchant_id`, `mcc_code`. CSV may begin with UTF-8 BOM. Monetary signs and balance semantics **remain to be verified on actual transactions**.

## Historical 14 November blocker — resolved locally on 15 November

- On 14 November, the GitHub connector returned the 134-byte Git LFS pointer, **not** real CSV rows. The source includes README instructions to download real bytes through the browser or Git LFS.
- On 14 November, direct HTTP HEAD to GitHub raw timed out after 8 seconds from the executor network. No available authentic full CSV could be located in the current scratch workspace.
- The 30 source-linked Q&A cases in `tests/synthetic-acceptance.test.mjs` use our *own clearly fictional fixture* conforming to the documented sponsor schema. Every amount and claimed row ID is independently asserted. They do **not** validate sponsor classifications, distribution, model quality, balance ordering or transaction-type semantics on true sponsor data.
- No sponsor transaction contents, customer identifiers, raw uploads or credentials were committed. The Git blob SHA above is a pointer digest, **not** a hash of the 362 MB CSV.

## Historical source-qualification checklist (acquisition now completed)

1. Obtain `tx_junction_transactions.csv` through the official source README's download/Git LFS steps in an authorized environment; do not substitute ZIP pointers or third-party copies.
2. Verify file size **362796501 bytes** and SHA-256 **49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63** before classifying any row as sponsor-grounded.
3. Inspect header/BOM, chronological `tx_timestamp` formats and category/transaction-type values; explicitly audit cents sign and balance consistency.
4. Select one **synthetic** customer ID with `node src/import-sponsor.mjs INPUT.csv CUSTOMER_ID ./data/customer.json`, keeping the export untracked and under the 10,000-row cap.
5. Run `node --test tests/*.test.mjs` and browser import; add a dedicated ≥30-case sponsor-grounded expected-value benchmark with original CSV line IDs and a recorded source SHA. Do not relabel the existing synthetic benchmark as sponsor-grounded.

## Source URLs

- Repository: https://github.com/hackjunction/Junction-2026-S-pankki
- README: https://github.com/hackjunction/Junction-2026-S-pankki/blob/fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f/README.md
- LFS pointer: https://github.com/hackjunction/Junction-2026-S-pankki/blob/fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f/tx_junction_transactions.csv
