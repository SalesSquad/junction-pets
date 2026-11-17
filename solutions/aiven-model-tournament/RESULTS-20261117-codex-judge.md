# junction.aiven: third, non-Claude judge (Codex CLI) — 17 November 2026

Codex CLI 0.169.0, running on the owner's Mac mini with a ChatGPT login, re-judged every stored answer of the unseen v3 run (`unseen-v3-haiku-sonnet.json`). It used the same `challenge-judge.mjs` prompt as the Claude judges. `--output-schema` enforces a typed verdict: boolean arrays whose length equals each case's rubric. It produced 133 of 138 verdicts; 5 runs returned no valid output. Runner: `codex-judge/run.mjs`. Receipt: `receipts/injection-20261116/codex-judge-unseen-v3.json` (booleans only).

| Answers by | n | Codex agrees with opus | Codex agrees with sonnet | All three agree | Pass: opus+sonnet | Pass: Codex alone | Pass: all three | Pass: majority of 3 |
|---|---|---|---|---|---|---|---|---|
| Haiku | 63 | 90.5 % | 84.1 % | 82.5 % | 87.3 % | 81.0 % | 79.4 % [67.8–87.5] | 88.9 % [78.8–94.5] |
| Sonnet | 70 | 95.7 % | 84.3 % | 84.3 % | 81.4 % | 80.0 % | 78.6 % [67.6–86.6] | 81.4 % [70.8–88.8] |

## Reading
- **The ranking holds across judge families.** A non-Claude judge also scores Haiku at least as high as Sonnet on unseen cases, so Haiku's lead is not a Claude self-preference artifact.
- Codex is closest to Opus (90–96 % agreement) and slightly stricter: 80–81 % pass when judging alone.
- A three-judge majority gives Haiku 88.9 %; strict three-judge consensus gives 79.4 %. The 95 % goal is not met under any aggregation. This closes the long-open third-judge item without Aiven AI Gateway access.
