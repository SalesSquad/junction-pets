# junction.aiven objective tournament, three arms — 14 November 2026

Source `0829bc6`. 2026-11-14T14:15:47.066Z – 2026-11-14T14:24:07.004Z; 378 answers, 0 errors, 0 unparsed. 14 code-scored tasks (9 basic, 5 hard), 3 seeds, identical seeds across models and arms. Arms: **pet** = full AGENTS.md context (19.8k chars), **compact** = AGENTS.compact.md (3.3k chars), **bare** = generic assistant. No LLM judge. Unqualified developer measurement, as in earlier rounds.

Cells show the share of perfect answers and the mean score.

| Model | Tier | pet | compact | bare |
|---|---|---|---|---|
| haiku | basic (27) | 78 % (0.923) | 96 % (0.988) | 85 % (0.941) |
| haiku | hard (15) | 100 % (1.000) | 100 % (1.000) | 100 % (1.000) |
| sonnet | basic (27) | 93 % (0.975) | 100 % (1.000) | 81 % (0.926) |
| sonnet | hard (15) | 100 % (1.000) | 100 % (1.000) | 100 % (1.000) |
| opus | basic (27) | 93 % (0.975) | 100 % (1.000) | 81 % (0.926) |
| opus | hard (15) | 100 % (1.000) | 100 % (1.000) | 100 % (1.000) |

| Model | Cost per answer: pet | compact | bare |
|---|---|---|---|
| haiku | 0.0010 | 0.0008 | 0.0007 |
| sonnet | 0.0152 | 0.0131 | 0.0103 |
| opus | 0.0316 | 0.0287 | 0.0221 |

## Findings

- **The compact guidance is the best arm for every model on basic tasks:** haiku 96 %, sonnet 100 %, opus 100 %. The full guidance scores 78 / 93 / 93 % and bare 85 / 81 / 81 %. For Haiku the long guidance hurts and the short one helps.
- **Caveat:** the compact edition's decision rules cover the same topics as the basic tasks, which were written earlier. On basic tasks this is partly teaching to the test.
- **The five "hard" tasks did not discriminate.** Every model and arm scored 100 %, bare Haiku included. Well-specified tasks with structured answers sit inside all three models' capability, even with long noisy input, conflicting evidence, replay ordering, multi-turn pressure and distractors at this size.
- **Where differences appear:** judgement and policy defaults, such as not echoing a pasted token or choosing a minimal service set. This is what guidance changes, not model size.
- **Practical routing:** Haiku with the compact guidance reaches 98 % overall at about 0.0008 USD per answer, roughly 1/20 of Sonnet with the full guidance (95 %).

## Next

1. Validate the compact edition on cases it was **not** written for: rerun the 8 held-out judged cases (`evals-heldout.json`) with the compact arm, and add new policy cases authored by someone else.
2. Make "hard" actually hard: logs of thousands of lines with several near-anomalies, under-specified designs scored against executed simulations (for example, feed the model's key and commit choices into `solutions/aiven-flight-recorder` and count duplicates and order violations), and real read-only tool use.
3. Promote the compact edition to the Chibi export only after step 1, through the integrator (manifest and plugin generation are integrator-owned).
