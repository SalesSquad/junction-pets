# Nine guidance lanes with Codex (second profile): no measurable gain, not landed (18 Nov 2026)

**Question.** Do general behaviour sections written by Codex lanes raise the pass rate of nine
lower-scoring pets (Exa, Featherless, Google DeepMind, Ignite Next, Intel, Modal, Tieto,
Valio Aimo, Wendy) on fresh cases?

**Method.**
- `scripts/lanes/run.mjs` on the Mac mini with `LANES_CODEX_BIN=codex-plus` (second Codex
  profile, owner-approved), 4 lanes at a time, one per pet, editing only `pets/<slug>/AGENTS.md`;
  the coordinator regenerated plugin files and ran `validate` and `plugins:check`.
  Wall time about 6 minutes for nine lanes. Context packs held the failed cases' prompts and
  rubrics, without model answers.
- Five lanes reported "blocked" only because they ran `plugins:check` before the coordinator's
  generator; their edits passed the coordinator gate afterwards. The runner now decides such
  self-reported blocks from the coordinator's own checks.
- Held-out set: 10 new cases per pet written by Sonnet from `pet.json`, rubrics audited by Opus
  (`fleet-20261118-heldout2/`). Haiku answers, both arms, 2 repeats; Opus and Sonnet must both
  pass. Baseline `main` at 320d032 and the candidate ran in parallel on the same cases.

| | Baseline | Candidate |
| --- | --- | --- |
| Total | 248/353 = 70.3 % [65.3–74.8] | 248/354 = 70.1 % [65.1–74.6] |
| Paired (349 runs) | baseline alone passed 41 | candidate alone passed 40 (sign test p = 1) |

Largest per-pet moves (20 runs each, mostly noise at this size): Modal +5 across arms,
Featherless own +4 / shared −3, Google DeepMind own −6, Valio Aimo own −3.

**Decision.** Not landed: no net effect and one possible regression (Google DeepMind own).
The candidate stays recorded as commit `ebf4998` (branch removed). Together with the earlier
three-pet run (+4.5 points, not significant), guidance text alone appears to have plateaued
near 70 % on held-out cases; the next lever is elsewhere (proposal handling and completeness
in the answer itself, measured per rubric item).

**Receipts.** `receipts/fleet-20261118-heldout2/`: scores and output hashes only.
