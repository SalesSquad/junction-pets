# Guidance fixes for three weak pets, made by parallel lanes (18 Nov 2026)

**Question.** Do short, general behaviour sections in the guidance of the three weakest pets that
no other agent holds (Context.dev, Hostinger, OpenAI Codex) raise their pass rate on fresh cases?
S-Pankki was left out because another agent holds an open PR on it.

**Method.**
- Three Opus lanes (`scripts/lanes/run.mjs`), one per pet, each editing only `pets/<slug>/AGENTS.md`;
  the coordinator regenerated plugin files and ran `validate` and `plugins:check`. Wall time 51 s.
- The lanes saw the failed cases of the 17 Nov fleet run. Their effect is judged only on a new
  held-out set: 10 cases per pet written by Sonnet from `pet.json` (not from the guidance), with
  rubrics audited by Opus (`fleet-20261118-heldout/`).
- Haiku answers, both arms, 2 repeats; Opus and Sonnet judges must both pass. The baseline
  (`main` at 4458e54) and the candidate ran in parallel on the same cases.

| Pet / arm | Baseline | Candidate |
| --- | --- | --- |
| context-dev / own | 9/20 | 10/20 |
| context-dev / shared | 12/20 | 11/20 |
| hostinger / own | 11/20 | 13/20 |
| hostinger / shared | 12/19 (1 error) | 15/20 |
| openai-codex / own | 15/20 | 15/20 |
| openai-codex / shared | 16/20 | 17/20 |
| **Total** | **75/119 = 63.0 % [54.1–71.2]** | **81/120 = 67.5 % [58.7–75.2]** |

**Result.** +4.5 points; paired on 119 runs the candidate alone passed 18 and the baseline alone
13. The direction is positive but not significant at this sample size (sign test p ≈ 0.47).
No pet/arm fell by more than one run. The change is landed as low-risk general guidance; a
larger held-out run would be needed to claim an effect.

**Receipts.** `receipts/fleet-20261118-heldout/{baseline-4458e54,candidate}.json`: scores and
output hashes only, no model text.
