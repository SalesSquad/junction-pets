# junction.aiven — compact-edition validation and extreme tier — 14 November 2026

Sources: runner `8aa1444` (held-out), `239717c` (extreme). Unqualified developer measurements through the authorized Claude CLI (no tools, no MCP); not the Aiven AI gateway, not a Chibi host run. No response text is stored here.

## 1. Held-out judged cases: does the compact edition generalise?

8 held-out cases (`pets/aiven/evals-heldout.json`, written before the compact edition and not used to write it) × 2 repeats. Judge: **opus**, which is not a contestant, plus the deterministic regex checks. 2026-11-14T14:35:28.130Z – 2026-11-14T14:45:12.217Z.

| Model | full guidance | compact | bare |
|---|---|---|---|
| haiku | 50 % pass, score 0.771 | 25 %, 0.625 | 12 %, 0.458 |
| sonnet | 69 % pass, score 0.854 | 25 %, 0.729 | 14 %, 0.333 |

Two sonnet/bare answers timed out (exit 143) and are excluded.

- **The compact edition does not generalise.** On cases it was not written for it falls from the full guidance's 50 % (haiku) and 69 % (sonnet) to 25 %. Its basic-task lead in the previous round was teaching to the test.
- **The full guidance adds the most:** +37 to +55 percentage points over bare. It contains the knowledge the held-out cases need: AI gateway early availability and billing, pricing honesty, Kafka ordering and per-partition semantics, metering reconciliation.
- **The compact edition wins only on `ho-operator-secrets`,** through its explicit rule "never repeat a pasted secret, even while refusing". The full guidance should adopt that sentence.
- **A non-contestant opus judge is stricter** than the earlier sonnet judge and gives a much larger spread between arms.

## 2. Extreme tier: code-scored, long and executed tasks

4 tasks × 3 seeds × 3 models × 3 arms = 108 answers, 0 errors. 2026-11-14T14:36:57.825Z – 2026-11-14T14:41:35.459Z.

Tasks:
- 1,450-line metrics log with a permanent stall, an offset regression and a decoy pause
- a five-choice pipeline design executed in a fault simulator
- exact minimum-partition bin packing with infeasible cases
- usage reconciliation across first-delivery timestamps, redeliveries, renames and the Europe/Helsinki billing day.

**Every model and arm scored 100 %, bare Haiku included.** A manual spot check on fresh seeds confirmed it: Haiku without guidance returned the exact ground truth for all four tasks. The scoring is not lenient.

## Conclusion

- Precisely specified computational and long-context tasks no longer discriminate between Haiku, Sonnet and Opus 5.5.
- What separates a useful Aiven companion from a bare model is **domain knowledge and default judgement**: what to refuse, what not to invent, which Aiven limits apply and what to verify. Only the open-ended held-out cases measure this, and there the full guidance wins clearly.
- **Route:** Sonnet with the full guidance (69 % held-out). Keep the compact edition as a research artifact only.
- **Next:**
  1. Add the secret-handling sentence to the full guidance (trim elsewhere to stay under the 20,000-character manifest limit).
  2. Have someone other than the guidance author write more held-out cases.
  3. Rerun with the opus judge.
