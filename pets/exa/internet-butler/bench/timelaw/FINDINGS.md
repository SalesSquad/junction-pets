# TimeLaw: a time-aware legal claim benchmark from official point-in-time texts (2026-11-14)

**Question:** is this clause the law on this date?

**Data.**
- 620 claims from 10 official provisions: 4 from the eCFR versioner (US) and 6 from legislation.gov.uk point-in-time (UK).
  - US: denied boarding compensation, credit-card penalty fees, FTC civil penalties, child-labour penalties.
  - UK: national minimum wage, statutory sick, maternity and paternity pay, the week's-pay cap.
- 234 claims are true, 191 stale (an earlier amount) and 195 premature (a later amount).
- **Gold comes only from the official text on that date.** A clause is true on D exactly when D's text has the same sentence template with the same numbers. No model labels anything.
- `build.mjs` rebuilds the set (texts are cached in `data/`, which is not committed); `eval.mjs` scores it.
- We found no published time-aware legal claim benchmark.

| Method | Accuracy | Historically true claims accepted |
|---|---|---|
| Date-blind: today's official text, Jev and/or code | 61 % (balanced 51 %) | 9 % |
| **Point-in-time: the official text on the claim's date, Jev** | **620/620** | **100 %** |
| Point-in-time, code only (numbers verbatim) | 619/620 | 100 % |
| Jev with no document | 50 % (chance) | — |
| Claude Haiku from memory | 575/620 = 93 % (CI 90–95) | — |

**What it shows.**
1. **The decisive component is retrieving the right version, not the judgment.** Given the right document, verification is essentially perfect. Given today's text, a date-blind verifier rejects 91 % of claims that were true on their date. That is what a "search and check today" agent does.
2. **Jev has no world knowledge.** It is a judge over what it is given, not a knowledge base; without a document it is at chance.
3. **Haiku's memory is good but not legal-grade.**
   - It is wrong on 7 % of claims, worst for the oldest year (2015: 75 %) and the newest (2025–26: 89 %).
   - Its self-reported confidence is informative. No wrong answer had confidence ≥ 90. At ≥ 90 it answers 21 % of claims, 128/128 correctly.
   - So a cascade works: memory at confidence ≥ 90, otherwise point-in-time retrieval. The official APIs are free.
4. **Point-in-time URLs make a warrant re-checkable exactly.** The text of a past date never changes, so a quote pinned to such a URL is verified by the receiver against the identical version. Live pages and best-effort snapshots cannot guarantee that.
   - `src/warrant/pointInTime.ts`: `pointInTimeUrl`, `officialFetch` and `lawOn(ref, date)`.

**Limits.**
- The claims are clauses from the provisions themselves, so this measures temporal retrieval and reading, not paraphrase.
- UK probes are 1 April and 1 October (plus today); eCFR probes are its version dates. Transitions between probes are not tested.
- 29 CFR 541.600 contributed no claims: its salary-level clause was not picked up by the clause splitter.
