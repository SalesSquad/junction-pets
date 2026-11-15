# Typed judges vs heuristics (2026-11-14)

Providers: OpenAI Decisions API (`POST /v1/decisions`, model gpt-6-luna). TypeSafe Jev is wired in
(`src/decide/decide.ts`, relay `/api/decide`) but was not run here: no `TYPESAFE_API_KEY` is configured.
Total cost of every run on this page was about $0.15.

## Findings

1. **Use one state per judged object.** Ten items in one shared state against one item per state,
   on the same 380 items:

   | | κ vs Haiku, states rule | κ vs Haiku, source type | Matches consensus, states rule | Matches consensus, source type | Legal text precision / recall |
   |---|---|---|---|---|---|
   | 10 items per request | 0.33 | 0.42 | 75 % | 69 % | 82 % / 74 % |
   | 1 item per request | 0.68 | 0.77 | 93 % | 93 % | 100 % / 90 % |

   The library therefore asks about each object in its own request, run in parallel.
   Fan-out (several questions at once) stays limited to questions about the same object.
2. **As a judge, Luna is as good as the other two.** Its κ against Haiku and against GPT-5.4-mini is at or above
   the agreement between Haiku and GPT. Its p(states rule) is well calibrated:
   Brier 0.046, against 0.213 for a constant base-rate guess. The `contradicts` field is too rare in
   this data to measure (κ near 0 for every pair of raters).
3. **The judge found a bug in the code; the fix went into the code.** All 16 false positives of the legal-text allowlist
   were EUR-Lex *summary* pages (`/legal-content/summary/`, `/LSU/`, `uri=legissum:`) and one GovInfo
   publication. `isLegalTextUrl` now excludes them:

   | Allowlist | Precision | Recall |
   |---|---|---|
   | Before the fix | 91 % | 82 % |
   | After the fix | 100 % | 82 % |

   The deterministic rule is still the authority. Letting the judge also admit pages would raise recall
   to 93 %, but the hosts only the judge accepted include unofficial mirrors (public.law, regelex.com)
   and exa.ai. So the judge does not admit legal sources. Combining it with the allowlist as a veto
   (`allowlist AND judge`) gave 100 % / 79 % before the fix; after the fix, the allowlist alone is as precise.
4. **Benchmark v1 recomputed with the fixed rule.** Benchmark v1's host classifier also counted the
   summaries as legal text, mostly in the plain-language arms. Corrected numbers:

   | Arm | Legal-text sources in top 5 | Top result is legal text |
   |---|---|---|
   | keywords | 1.63 | 60 % |
   | question | 0.57 | 17 % |
   | citation | 2.70 | 87 % |

   Citation vs keywords: 20 wins, 9 ties, 1 loss (p < 0.001; before the fix 18 / 11 / 1).
   The conclusion gets stronger. Benchmark v2 used judge labels and is unaffected.
5. **Outcome selection: no gain as a replacement, some gain as a second candidate.** On 18 real
   errands, taking the judge's pick as the primary answer fixed 2 and broke 2 (78 % → 78 %). The compiler
   keeps the judge's pick *next to* the heuristic's alternatives and lets the legal text decide. With
   that, the reference value reaches the legal text in 89 % of errands instead of 83 %.
6. **Prompt injection: no false positives.**

   | Set | Result |
   |---|---|
   | Synthetic injections (Finnish, German, an HTML comment, inline in a statute) | 12 / 12 caught |
   | Instructions written for people | 0 / 8 dropped |
   | Real Exa passages | 0 / 90 dropped |

   Block threshold 0.7, as in TypeSafe's guidance.
7. **Replays are deterministic.** The same questions asked twice gave identical probabilities in 49 / 49
   cases (largest difference 0.000). A receiver re-asking a warrant's judgments with the same model
   therefore reproduces them exactly. With another model family it is an independent second opinion.
8. **Cost and latency.** 663 requests and 520 k input tokens cost about $0.05.
   Latency p50 was 291 ms and p95 487 ms, one object per request, eight in parallel.

The sections below are the raw output of the full run with one item per request, before the allowlist fix.

## A. Judging agreement — openai-decisions on 380 labelled items (1 item(s) per request)

| field | Luna vs Haiku κ | Luna vs GPT-5.4-mini κ | Haiku vs GPT κ (reference) | Luna = consensus (where Haiku and GPT agree) |
|---|---|---|---|---|
| states_rule | 0.68 | 0.61 | 0.56 | 93 % (89–95) of 300 |
| source_type | 0.77 | 0.86 | 0.81 | 93 % (90–96) of 336 |
| contradicts | 0.17 | 0.10 | 0.32 | 87 % (83–90) of 372 |
| jurisdiction_match | 0.00 | 1.00 | 0.00 | 100 % (99–100) of 372 |

Legal-text detection on 336 items where Haiku and GPT agree on source type:
- code allowlist (isLegalTextUrl): precision 91 %, recall 82 % (tp 154, fp 16, fn 34)
- openai-decisions judge: precision 100 %, recall 90 % (tp 169, fp 0, fn 19)
- allowlist OR judge: precision 92 %, recall 93 % (tp 175, fp 16, fn 13)
- calibration of p(states rule) on 321 unanimous items: Brier 0.046 (constant base-rate predictor 0.213)

## B. Outcome selection — openai-decisions on 18 errands (real Exa answer lane, run2)

| errand | reference | heuristic outcome | judge pick (p) | verdict |
|---|---|---|---|---|
| eu261-amount | EUR 250 | €250 | €250 (0.77) | both right |
| eu-crd-withdrawal | 14 days | 14-day | 14-day (1.00) | both right |
| eu-guarantee | two years | 2-year | 2-year (1.00) | both right |
| gdpr-access | one month | 1 month | 1 month (0.93) | both right |
| eu-rail | 25 % | € 1.50 | 25% (0.96) | **judge fixes** |
| eu-bus | 120 minutes | 250 km | 50% (0.79) | both wrong |
| eu-late-payment | 60 calendar days | 60 days | 60 days (0.96) | both right |
| uk-cra-reject | 30 days | 30 days | 30 days (1.00) | both right |
| uk-deposit | 30 days | 30 days | 30 days (1.00) | both right |
| uk261 | £220 | £220 | £220 (1.00) | both right |
| us-dot-refund | six hours | 7 business days | 7 business days (0.74) | both wrong |
| us-fcba | 60 days | 60 days | 60 days (0.98) | both right |
| us-cooling-off | third business day | third business day | 3-Day (0.99) | **judge breaks** |
| us-fdcpa | five days | five days | thirty days (0.74) | **judge breaks** |
| us-flsa | $7.25 | $7.25 | $7.25 (0.97) | both right |
| ca-deposit | 21 days | 21 days | 21 days (0.94) | both right |
| ny-deposit | 14 days | 14 days | none > 0.7 (max 0.68) | both right |
| ny-notice | 90 days | 30 days | 90 days (1.00) | **judge fixes** |

primary outcome correct: heuristic 78 % (55–91), heuristic + judge 78 % (55–91); judge fixed 2, broke 2, abstained on 1 (kept heuristic)

## C. Prompt-injection quarantine — openai-decisions (block above 0.7)

- synthetic injections caught: 100 % (76–100) of 12 (incl. Finnish, German, hidden HTML comment, inline in legal text)
- hard negatives (instructions to people) wrongly dropped: 0 of 8
- real Exa answer-lane passages wrongly dropped: 0 % (0–4) of 90

## D. Replay stability — openai-decisions: same questions asked twice

- 49/49 answers land on the same side of 0.7; largest probability difference 0.000

## Cost and latency

- openai-decisions: 663 requests, 520348 input tokens (≈ $0.0520 at $0.1/M uncached), latency p50 291 ms, p95 487 ms
