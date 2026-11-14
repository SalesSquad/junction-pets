# Care Equity Navigator — first executable evidence-to-action milestone

**Junction 2026 M344 · AstraZeneca source key `astra-zeneca` · maturity 1/6.** The first runnable workflow is an offline policy-review **demonstration**, **not** an actual cancer-care outcome analysis. All observations, regions, intervals, counts and benchmarking values in `fixtures/regions.json` are **invented**. No live AstraZeneca, THL, Finnish Cancer Registry or clinical system is connected. This product makes no diagnosis, individualized recommendation, patient-level inference or causal impact claim.

## User journey

1. A regional pathway director chooses a referral, diagnosis or treatment-stage indicator and two fictional regions.
2. The engine checks strict source identity, comparable time period and standardization, small-cell suppression (minimum `n=30`) and confidence-interval overlap; unsupported regional rankings are refused.
3. Only for a nonoverlapping, illustrative worse-focus region does the interface prepare an accountable **human review proposal**, including an owner, measurable follow-up and noncausality caveat.
4. The operator may export a local **DRAFT_ONLY** evidence packet, with SHA-256 digest of the fixture, source kind, retrieval date and unresolved Goal 3 clause gate. No network write, real policy or patient action is performed.

## Run

```bash
npm test
npm run demo
npm start
# Open http://127.0.0.1:4179
```

No npm dependencies or external services are required. The static app loads only same-origin files and uses restrictive CSP. In a final demo, only the **synthetic** path is currently qualified; the official challenge requires a real cited aggregate indicator connected to Goal 3 of the national cancer strategy.

## Data ingestion contract and next real acceptance

`equity-fixture-v1` requires exact dataset and per-observation source references, explicit period, indicator standardization, intervals and cohort size. `CLEARED_AGGREGATE_INPUT` is rejected unless explicitly marked as observed public input; this flag alone is **not** proof of license, origin or clinical quality. Actual import must attach primary data URI, record-level source hash, Finnish region-year normalization, small-count suppression rules, uncertainty-method audit, explicit Goal 3 clause citation and scientific review before any non-demo claim.

**Exactly next dependency:** a legally reusable, date-pinned, **public aggregate regional cancer-care pathway** dataset with a verifiable national strategy Goal 3 clause, sufficient stage/period/region comparability, followed by a human-reviewed action card. This must not be guessed from the synthetic dataset or sponsor affiliation. Benchmark needs held-out comparable cohorts against naive raw regional rankings.

**Technical boundary:** No external API, PII, device, patient access, paid services, publication, deployment or sponsor endorsement. PR integrator owns eventual merge; FINAL event controller remains separate.
