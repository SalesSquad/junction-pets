# Lumo — your money, in focus

An independent, **event-created, mobile-first working prototype** for Junction 2026's S-Pankki **Personal Economic Trainer** challenge. It is not S-Pankki software and is not endorsed by the bank.

The problem: people can see transactions but struggle to explain spending, distinguish obligations from choices and estimate how much of a historical balance remains after planned reserves. **Lumo gives one answer with its arithmetic and its source rows.** An unsupported question receives an honest refusal, not a plausible fabricated figure.

## Run locally, no dependencies

Requires Node.js 22+.

```sh
cd solutions/s-pankki-economic-trainer
node server.mjs
# Open http://127.0.0.1:4173 in a browser (desktop or mobile viewport).
node --test tests/coach.test.mjs
```

In the browser, ask **“Where did my money go this month?”**, **“How much did I spend on taxis?”**, **“Where did my money go last month?”**, and **“What can I safely spend this week?”**. Also ask about **rent, electricity, repairs, recurring essentials, irregular bills or discretionary spending** in English or Finnish. Follow the CSV row badges into the evidence explorer. Edit the three reserve figures to watch the illustrative spending room update. Unknown categories remain visible. The source file is internally consistent **fictional demonstration data** written for this prototype; it is not copied from the sponsor CSV.

### Try the what-if money runway

Open **What if I spend this much?** below the reserve controls. Select **7, 14 or 30 days**, enter a hypothetical daily discretionary amount and one extra purchase, and press **Run my scenario**. The exercise shows the remaining illustrated room, an alternative maximum daily amount rounded **down** to cents, the exact overrun if the planned expense exceeds room, a 7/14/30-step visual, and links to the account-balance source rows. Alter your three reserved buffers and run again to see the implications. This is **not a prediction**: it assumes fixed historical balances, no incoming or unexpected transactions and the exact user-entered choices. A historical snapshot cannot tell a real person what they may safely spend.

## Import the sponsor's real synthetic dataset

The sponsor's [official dataset repository](https://github.com/hackjunction/Junction-2026-S-pankki) documents `tx_junction_transactions.csv`, `tx_customers_junction.csv` and mortgage tables. The transactions file is about 346 MB stored with **Git LFS**. This prototype reads only the transaction fields, not mortgages. Read that repository's download instructions and verify that you have CSV bytes, not a small Git LFS pointer.

```sh
# CUSTOMER_ID must exist in the sponsor's synthetic data, not a real bank customer.
node src/import-sponsor.mjs /absolute/path/to/tx_junction_transactions.csv CUSTOMER_ID ./data/customer.json
```

Open the locally served browser demo and select `data/customer.json` under **Open local export**. The loader streams the input CSV, selects one synthetic customer, preserves original CSV row numbers, exports a maximum of 10,000 rows and refuses to overwrite an existing output. `data/` is gitignored. The app reads the selected JSON only into browser memory; it has no upload endpoint, storage, remote model invocation or telemetry.

The source schema has `customer_id`, `bank_account_id`, `tx_date`, `tx_timestamp`, `category`, `tx_amount_eur`, `balance_after_eur`, `transaction_type`, `merchant_id`, `mcc_code`. Inputs have a UTF-8 BOM and amounts must have no more than two fractional digits. Ambiguous categories are deliberately **unclassified** until an explicit reviewed rule is added. Other customer IDs in a multi-customer JSON trigger a refusal.

**M2 sponsor-source status (2026-11-14):** Checked official repo at `fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f`. Its LFS pointer Git blob is `a9e792b4004c0e54a96857dd72d91539124ba0be`; the referenced real CSV is 362,796,501 bytes with SHA-256 `49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63`. The authorized GitHub fetch returned only that pointer, and outbound GitHub raw HTTP timed out. The actual CSV contents were **not** retrieved or run. `tests/synthetic-acceptance.test.mjs` therefore contains **30 cent-exact, source-row-asserted question/answer cases on a clearly fictional sponsor-schema fixture**—useful offline product regression evidence, *not sponsor-dataset qualification*. See [SPONSOR_SOURCE.md](SPONSOR_SOURCE.md) for evidence and a reproducible sponsor check when real bytes become available.

## Trust contract

- **Exact arithmetic:** all monetary sums are integer euro cents, never float additions. Negative `tx_amount_eur` means outgoing. Recognized refunds offset spending, salary/income and internal transfers are excluded from spending. Transfers *are* included in the last account balance as recorded by the sponsor. An unknown type remains separately inspectable.
- **Three baskets:** mandatory regular (rent, bills, groceries), mandatory irregular (repairs/health), everyday choices (coffee, taxi, dining, shopping). Classification is a small **declared mapping** in `src/coach.mjs`, not an AI guess. Some real-world categories may require human approval.
- **Provenance:** each answer contains original source row numbers. Dataset chronology uses the actual `tx_timestamp` per account, not a later CSV line as a proxy for time. Absent timezone is interpreted as UTC for deterministic comparison; the sponsor's actual timezone semantics require confirmation. Equal latest timestamps with conflicting balances are refused; equal timestamps with equal balances cite the higher row solely as a deterministic reference. Browser-rendered source labels are plain text, never executed as HTML or prompts.
- **Spending room:** sum the latest observed `balance_after_eur` **once per account**, selected by transaction timestamp; subtract the user's upcoming regular bills, irregular buffer and emergency buffer, and use **max(0, observed balance − all reserves)**. If reserves exceed balances, show the shortfall instead of implying the un-clamped equation equals zero. It is an **illustration, not a safe-to-spend guarantee**: holds, overdrafts, liability schedules, unsettled transactions, future income and true pending bills are not available in the CSV. The UI intentionally highlights this.
- **Runway:** user-chosen `daily flexible spend × days + one-time purchase` is subtracted from the *clamped* reserve-based room. Negative outcomes appear as an explicit shortfall, never a claimed negative account balance. Alternative daily ceiling is floored to an exact cent and is **not** personalized advice or a forecast.
- **No permissions:** no account login, banking SDK, transfers, payments, advice, credit scoring or external agent execution. No PII or private customer data in the included fixture.
- **Source boundaries:** this independent product is distinct from the existing `pets/s-pankki` companion, fictional SMS helper and private Chibi runtime. It does not copy pre-event commercial code. All project-owned code here is newly authored for the event.

## Product roadmap beyond this first working slice

1. Retrieve and verify sponsor's actual LFS CSV hash, validate official categories and balance semantics against one real **sponsor synthetic** customer sample, and add official-data-bound Q&A. Current 30 verified Q&As are on locally invented sponsor-schema rows only.
2. Extend through a code-validated natural-language *intent proposal*, with model output unable to invent figures or action authority; add Finnish language and ambiguity follow-ups.
3. Expand the current 7/14/30-day educational scenario into richer goal and recurring-commitment explorations, while continuing to separate user assumptions from actual historical evidence.
4. Commission UX/usability tests with actual target users and mobile Safari; refine dynamic type, accessibility and visuals. Current browser visuals and local server are not a deployed S-mobiili integration.
5. Keep a future bank/Open Banking integration **separate and consent-gated**; no real user financial data or regulated advice in this hackathon submission.

## Evidence to collect for judging

Sponsor criteria (each 20%): financial literacy and pedagogy, originality of AI use, clarity of mobile UX, feasibility, and credible S-mobiili integration potential. This prototype demonstrates **deterministic calculations and interactive UX**, not model AI integration or actual bank adoption. The **30 named synthetic Q&A pairs** and 7/14/30 what-if checks are local acceptance evidence; future qualification additionally needs the real sponsor CSV, mobile visual inspection and real AI-model interpretation tests if a model adapter is added.

Sources: [Official challenge](https://hackjunction.app/participate/45/challenges/311), [sponsor data](https://github.com/hackjunction/Junction-2026-S-pankki), [Junction source research](../../pets/s-pankki/CHALLENGE_RESEARCH.md).

