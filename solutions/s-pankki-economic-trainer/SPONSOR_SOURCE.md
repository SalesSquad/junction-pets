# S-Pankki synthetic sponsor source — pinned acquisition record

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

## Current blocker and honest acceptance status

- Official GitHub connector returned the 134-byte Git LFS pointer, **not** real CSV rows. The source includes README instructions to download real bytes through the browser or Git LFS.
- Direct HTTP HEAD to the same GitHub raw path timed out after 8 seconds from the executor network. No available authentic full CSV could be located in the current scratch workspace.
- The 30 source-linked Q&A cases in `tests/synthetic-acceptance.test.mjs` use our *own clearly fictional fixture* conforming to the documented sponsor schema. Every amount and claimed row ID is independently asserted. They do **not** validate sponsor classifications, distribution, model quality, balance ordering or transaction-type semantics on true sponsor data.
- No sponsor transaction contents, customer identifiers, raw uploads or credentials were committed. The Git blob SHA above is a pointer digest, **not** a hash of the 362 MB CSV.

## Exact source qualification when the LFS bytes become available

1. Obtain `tx_junction_transactions.csv` through the official source README's download/Git LFS steps in an authorized environment; do not substitute ZIP pointers or third-party copies.
2. Verify file size **362796501 bytes** and SHA-256 **49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63** before classifying any row as sponsor-grounded.
3. Inspect header/BOM, chronological `tx_timestamp` formats and category/transaction-type values; explicitly audit cents sign and balance consistency.
4. Select one **synthetic** customer ID with `node src/import-sponsor.mjs INPUT.csv CUSTOMER_ID ./data/customer.json`, keeping the export untracked and under the 10,000-row cap.
5. Run `node --test tests/*.test.mjs` and browser import; add a dedicated ≥30-case sponsor-grounded expected-value benchmark with original CSV line IDs and a recorded source SHA. Do not relabel the existing synthetic benchmark as sponsor-grounded.

## Source URLs

- Repository: https://github.com/hackjunction/Junction-2026-S-pankki
- README: https://github.com/hackjunction/Junction-2026-S-pankki/blob/fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f/README.md
- LFS pointer: https://github.com/hackjunction/Junction-2026-S-pankki/blob/fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f/tx_junction_transactions.csv
