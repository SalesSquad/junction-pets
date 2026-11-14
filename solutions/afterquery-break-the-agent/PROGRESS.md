# AfterQuery product development record

Status: **building**. Work ID `J26-AQ-HARBOR-001`.

## First implemented increment

- Source base: `7b80fee6aad03e145a8197be4482842e07a09e40`, private `SalesSquad/junction-pets`.
- Product code head initially authored on task branch `codex/j26-afterquery-harbor-task-20261114`; link to [draft PR #83](https://github.com/SalesSquad/junction-pets/pull/83) and read its **current** head before continuing. This file is not a live branch watcher.
- Paths: only `solutions/afterquery-break-the-agent/**`; previous AfterQuery [PR #13](https://github.com/SalesSquad/junction-pets/pull/13) remains merged and untouched.
- Implemented: Harbor 1.4 separate-verifier benchmark of a 38-order synthetic ledger, static `decisions.json` answer artifact, immutable source SHA guard, private golden key, a deterministic reference solver, 37 independent offline cases and four adversarial policies plus do-nothing baseline.
- P0 fixed in working source: independent reviewer exploited prior verifier executing untrusted solver with hidden answer key in `/tests` (reward 1.0 without reasoning). Current verifier never invokes agent code and uses fresh `tests/Dockerfile` verifier; exploit regression now scores 0.0. **This fix still needs Harbor/Docker integration verification**, not a claim of hosted success.
- Local check: `python3 solutions/afterquery-break-the-agent/harbor/settlement-reconciliation/tests/local_regression.py` → `PASS_LOCAL_ONLY`; 37/37 oracle cases; actual 38-order artifact oracle 1.0; do-nothing 0, stop early 0, fabricated PAID 0, input tampering 0, hidden-test exfil 0, blanket escalation 0.115044.
- Not verified: Harbor/Docker qualification, three frontier-agent runs, real reward gap or organizer reproduction, Chibi host or external payment execution, demo/FINAL submission.

## Next actionable task

- Work ID: `J26-AQ-HARBOR-002`.
- Exclusive owner: one assigned product developer; no automatic Cloud task assumed from environment settings.
- Objective: reproduce the **separate verifier artifact transfer** on an authorized executor with Docker and the Harbor CLI, run the Oracle at pinned PR-HEAD, preserve the actual `/logs/verifier/reward.txt` and full run metadata. Verify that the verifier cannot execute/read hidden tests from the agent context.
- Acceptance: one real Harbor Oracle run with source SHA, run ID, verifier details, reward 0–1, input/task source digest and explicit environment; rerun the exploit attack and no-op/blanket policies on the actual Harbor runner before frontier agent runs.
- Blocker: author executor has neither Docker nor Harbor CLI. Check existing authorized Codex Cloud or Mac toolchain; no new spending, credential changes or policy bypass.
- Integration: generic product-workspace [PR #82](https://github.com/SalesSquad/junction-pets/pull/82) is still a draft at authorship; avoid duplicating its root script/validator.

Only a verified hosted result or owner-authorized submission can change the model-run/FINAL status.
