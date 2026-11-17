# junction.aiven injection suite: unseen set and injection routing — 17 November 2026

Source `a96a438` on branch `agent/junction-aiven-routed-injection-20261117`. New unseen set `injection-cases-v3.json` (35 cases: 20 injected, 15 clean). Sonnet wrote the cases with the corrected per-kind prompt, and `audit-rubrics.mjs` (Opus) rewrote 20 must-include items in 14 cases into evidence-bound form before any answer was generated. Arm framed-repair, 2 repeats, judges opus + sonnet with consensus. Developer measurement with the Claude CLI; no response text is stored. Receipt: `receipts/injection-20261116/unseen-v3-haiku-sonnet.json`.

| Model | Pass (consensus) | Detected | Followed | False alarms (clean) | Cost incl. judging |
|---|---|---|---|---|---|
| **Haiku** | **88.2 % [78.5–93.9]** (68 answers) | 100 % | 0 % | 3.4 % (1/29) | $3.75 |
| Sonnet | 81.4 % [70.8–88.8] (70 answers) | 100 % | 0 % | 0 % | $6.06 |
| Routed: Sonnet only when the host regex detects an injection (33/68 answers) | 79.4 % [68.4–87.3] | – | – | – | – |

## Reading
- **The Sonnet advantage from v2 (92 % vs 82–84 %) did not replicate on unseen cases.** Here Haiku scores higher, and the intervals overlap. Routing injected input to Sonnet therefore does not raise quality, and it costs more. `largeOnInjection` stays off by default in `services/aiven-platform/cascade.mjs`.
- Safety held for both models: every injection was detected and none was followed.
- The host regex (`injectedDirectives`) flags 17 of the 20 injected cases and 0 of the 15 clean ones.
- **The 95 % goal is still not met** (Haiku 88 %, upper bound 94 %). The failures are judge-scored completeness misses.
- Generator fix: the clean batch previously received the injection instructions, so the writer alternated injected and clean cases (5 of 10 "clean" drafts carried an injection). The prompt now differs by batch kind, and the regenerated 15 clean controls needed no drop.
- Rubric audit: even Sonnet-written rubrics asked for unsupported facts in 14 of 35 cases. Run `audit-rubrics.mjs` on every new set before answering it.
