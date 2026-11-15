# Public legal benchmarks: what we found and what beat the baseline (2026-11-14)

## Data and numbers to beat

- **Benchmarks used:**
  - LegalBench `sara_entailment`: 272 rows, US tax statute + facts → assertion, MIT.
  - LegalBench `contract_nli_*`: 14 clause types, 1,927 rows, NDA excerpt → fixed hypothesis, CC BY 4.0. Hypothesis texts come from the official ContractNLI release.
  - Loaders: `fetch_legalbench.mjs`.
- **Context:**
  - LLM-AggreFact grounding leaderboard: Jev 1.13 at 78.7, the top at 79.5.
  - An independent Vals AI evaluation ranked Jev last of 12 on its LegalBench slice (0.730 against 0.932 for the leader). That slice is different from ours, so the numbers are not directly comparable.
  - Stanford RegLab measured hallucination in legal research AI at 17–33 %.
  - Notes are in the session scratchpad (`datasets_notes.md` and `sota_notes.md`); they are not in the repo.
- **Point-in-time legal text exists and works:**
  - legislation.gov.uk `/{type}/{year}/{n}/section/{s}/{YYYY-MM-DD}/data.xml`
  - eCFR versioner `/api/versioner/v1/full/{date}/title-N.xml`, e.g. 14 CFR 250.5 has 7 versions and 29 CFR 541.600 has 6.
  - No time-aware legal claim benchmark was found.

## Results (balanced accuracy; every call recorded in `cassettes/*.jsonl.gz`)

| Verifier | SARA (272) | ContractNLI (1,927) |
|---|---|---|
| Code only: numbers verbatim | 51 % | 50 % |
| Jev, one question "is every part of the claim supported?" | 77 % | 83 % |
| Luna, one question | 65 % | 87 % |
| Our hand-written truth table (built against forgeries), Jev | 62 % | 71 % (558-row sample) |
| Learned combination of judge probabilities, Jev (grouped CV, 558-row sample for ContractNLI) | 82 % | 85 % |
| Learned combination, Luna (grouped CV, 558-row sample) | 68 % | 87 % |
| **Compiled clause programs, Jev** | — | **90 %** |
| **Compiled clause programs, Luna** | — | **93 %** |

The two learned-combination rows give SARA when trained on Jev's table rows and ContractNLI when trained on its single question. Its baseline on the 558-row sample is Jev 80 %, Luna 83 %.

1. **The anti-forgery truth table costs accuracy on natural data.** It is a precision filter. A claim that is a paraphrase or an inference trips the "adds" and "numbers" rows. Use it where an attacker writes the passages, not as a general entailment judge.
2. **Learning how to weight the judgments helps.** It is cross-validated so that no clause type or case is in both training and test. It adds 2–5 points with no new calls, which shows the rows carry signal and the hand-written AND rule was the problem.
3. **"Haiku compiles, Jev executes, code decides" is the clear win.**
   - Haiku turned each of the 14 hypothesis texts, once and without seeing any excerpt or label, into 2–3 positive yes/no element questions and a boolean formula (`cnli_programs.json`, $0.003).
   - The judge answers the elements; code evaluates the formula (AND = min, OR = max, NOT = 1 − p).
   - Gains on all 1,927 rows: Jev 83 → 90 %, Luna 87 → 93 %. Exact McNemar p ≈ 1e-13 (Jev 156 rows gained, 51 lost). The gain is +6 points, 95 % CI 2–11 by cluster bootstrap over clause types.
   - Abstaining in the 0.3–0.7 band, Jev answers 88 % of rows at 94 % balanced accuracy.
   - Biggest lifts: confidentiality of the agreement 65 → 94 %, return of confidential information 60 → 90 % (on the 558-row sample).
4. **Cost.** Jev runs about 2.5 element questions per row, at about $0.04 per 1,000 judgments and p50 under 200 ms. Compiling costs one Haiku call per hypothesis, reused for every document.

## Why it works

A single question asks the model to hold a whole hypothesis in mind, including its quantifiers ("some", "all"), the parties involved, and negation. Those are exactly Jev's documented weak spots: negation and first-option bias. The compiled program splits the hypothesis into small positive questions: is the topic addressed, what is the direction, is there a guard against the usual confusion. Code then does the logic. This is the TypeSafe guidance ("judgments from Jev, decisions in code") applied automatically, with the program written by a cheap generator.

## SARA with compiled statute programs (`sara_compile.mjs`)

- **How it works.** Haiku sees only the statute excerpt and the assertion. It writes:
  - `fact` questions, which the judge answers over the facts;
  - `given` conditions, decided at compile time from the statute and the assertion alone, e.g. whether the tax year falls in the period the excerpt names, so date logic stays out of the model;
  - a formula combining them.

  It marks an assertion unhandled when deciding it needs arithmetic or law outside the excerpt: 111 of 272.
- **Results:**

  | Judge | Rows | One question | Compiled program | Exact McNemar |
  |---|---|---|---|---|
  | Jev | all 272 | 77 % | 79 % | p = 0.46, not significant |
  | Jev | 161 handled | 83 % | 86 % | — |
  | Luna | all 272 | 65 % | 70 % | p = 0.10 |
  | Luna | 161 handled | 72 % | 81 % | — |

- **What it shows.** Applying a statute to dated, numeric facts gains less from compilation than classifying contract clauses. The next step is arithmetic in code: SARA facts are templated sentences, so amounts can be extracted by code, with the program computing.

## TimeLaw (see `bench/timelaw/FINDINGS.md`)

A new time-aware benchmark: 620 claims from official point-in-time texts.

| Method | Result |
|---|---|
| Date-blind checking | 61 % accurate; accepts 9 % of historically true claims |
| Point-in-time checking | 620/620 |
| Haiku from memory | 93 %; never wrong at confidence ≥ 90 |

## Next

- **SARA:** compile statute + question into programs, with date arithmetic in code. SARA is where a single question is weakest (Luna 65 %).
- **A time-aware legal claim benchmark** from the point-in-time APIs: claims true on one date and false on another, gold from the official text.
- **The same compile step for Warrant premises,** so each verified premise carries its element answers as replayable receipts.
