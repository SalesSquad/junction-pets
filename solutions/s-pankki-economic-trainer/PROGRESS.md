# Working vertical slice — J26-SBANK-PRODUCT-001

**Stage:** `building`, source-only local interactive demo; not a production/qualified bank application or a Junction FINAL submission.

**Task owner:** S-Pankki product slice writer, exclusive ownership `solutions/s-pankki-economic-trainer/**`. Repo task admission base was `7b80fee6aad03e145a8197be4482842e07a09e40`; refreshed commit after docs-only #79 main merge: `bb1f50908e05ada32e947abff86ac5e31e82e22d`; re-resolve current main/PR state before continuing.

**Implemented:** deterministic transaction/cents engine, named three-basket classification, refund/transfer treatment, explicit reserves and shortfall, timestamp-ranked account balances with tied-latest ambiguity refusal, evidence rows, adversarial refusals; sponsor CSV BOM/LFS-aware per-customer streaming importer; mobile-first local browser UI. Fictional demonstration dataset is clearly labeled.

**Acceptance commands:** `node --test tests/coach.test.mjs`, `node server.mjs` and browser `http://127.0.0.1:4173` with 3 sample questions, one reserve adjustment and one refused unsupported instruction.

**Highest-priority next task:** pin an actual *sponsor synthetic* customer subset file SHA without committing the private/local export, measure ≥30 cent-exact question/answer pairs and verify category mappings. Add browser viewport QA and model proposal adapter only after data mapping is true.

**Limits:** no 346 MB sponsor LFS data bundled; no executed AI provider/model run; no official S-Pankki API, live balance, user sign-in, financial guarantee, actual recipient or public deployment. Do not treat authored frontend as a deployed S-mobiili product. Validate final PR HEAD/readback, not just these dated statements.

