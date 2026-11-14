# Working vertical slice — J26-SBANK-PRODUCT-001

**Stage:** `building`, source-only local interactive demo; not a production/qualified bank application or a Junction FINAL submission.

**Task owner:** S-Pankki product slice writer, exclusive ownership `solutions/s-pankki-economic-trainer/**`. Repo task admission base was `7b80fee6aad03e145a8197be4482842e07a09e40`; refreshed commit after docs-only #79 main merge: `bb1f50908e05ada32e947abff86ac5e31e82e22d`; re-resolve current main/PR state before continuing.

**Implemented:** deterministic transaction/cents engine, named three-basket classification, refund/transfer treatment, explicit reserves and shortfall, timestamp-ranked account balances with tied-latest ambiguity refusal, evidence rows, adversarial refusals; sponsor CSV BOM/LFS-aware per-customer streaming importer; mobile-first local browser UI. Fictional demonstration dataset is clearly labeled.

**M2 milestone (2026-11-14):** added a 7/14/30-day interactive planning-runway with daily flexible spending, one-time purchase, cent-exact remaining/shortfall and conservative daily ceiling, visual per-day timeline and original balance row citations. Added English/Finnish category/basket question coverage and **30 numbered source-linked, cent-exact synthetic Q&A acceptance cases**, plus financial-safety runway tests. Official sponsor repo `fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f` and 346 MiB LFS pointer digest are pinned in `SPONSOR_SOURCE.md`, but real transaction object was unavailable through connector/network. **No official sponsor CSV import or qualification has occurred.**

**Acceptance commands:** `node --test tests/*.test.mjs`, `node server.mjs` and browser `http://127.0.0.1:4173` with 3 sample questions, one reserve adjustment, a 7/14/30-day plan adjustment and one refused unsupported instruction.

**Highest-priority next task:** retrieve the actual *sponsor synthetic* LFS bytes, verify the real CSV size/SHA and category semantics, then run ≥30 **sponsor-grounded** expected-amount/source-row pairs. The current 30 Q&As are synthetic only. Add browser viewport QA and model proposal adapter only after data mapping is true.

**Limits:** no 346 MB sponsor LFS data bundled; no executed AI provider/model run; no official S-Pankki API, live balance, user sign-in, financial guarantee, actual recipient or public deployment. Do not treat authored frontend as a deployed S-mobiili product. Validate final PR HEAD/readback, not just these dated statements.

