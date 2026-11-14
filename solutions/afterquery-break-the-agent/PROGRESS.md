# AfterQuery product development record

Status: **building**. Work ID `J26-AQ-HARBOR-001`.

## First implemented increment

- Source base: `7b80fee6aad03e145a8197be4482842e07a09e40`, private `SalesSquad/junction-pets`.
- Product code head initially authored on task branch `codex/j26-afterquery-harbor-task-20261114`; link to [draft PR #83](https://github.com/SalesSquad/junction-pets/pull/83) and read its **current** head before continuing. This file is not a live branch watcher.
- Paths: only `solutions/afterquery-break-the-agent/**`; previous AfterQuery [PR #13](https://github.com/SalesSquad/junction-pets/pull/13) remains merged and untouched.
- Implemented: source-bound synthetic Harbor benchmark, reference solver, deterministic reward verifier, 37 cases and four adversarial policies plus do-nothing baseline.
- Local check: `python3 solutions/afterquery-break-the-agent/harbor/settlement-reconciliation/tests/local_regression.py` → `PASS_LOCAL_ONLY`; oracle reward 1.0, do-nothing 0, stop early 0, fabricated PAID 0, input tampering 0, blanket escalation 0.16.
- Not verified: Harbor/Docker qualification, three frontier-agent runs, real reward gap or organizer reproduction, Chibi host or external payment execution, demo/FINAL submission.

## Next actionable task

- Work ID: `J26-AQ-HARBOR-002`.
- Exclusive owner: one assigned product developer; no automatic Cloud task assumed from environment settings.
- Objective: reproduce the benchmark on an authorized executor with Docker and the Harbor CLI, run the Oracle at pinned PR-HEAD, preserve the actual `/logs/verifier/reward.txt` and full run metadata.
- Acceptance: one real Harbor Oracle run with source SHA, run ID, verifier details, reward 0–1, input/task source digest and explicit environment; re-evaluate local baseline score provenance. Then start repeated frontier/OpenCode model runs as separate work, not inferred.
- Blocker: author executor has neither Docker nor Harbor CLI. Check existing authorized Codex Cloud or Mac toolchain; no new spending, credential changes or policy bypass.
- Integration: generic product-workspace [PR #82](https://github.com/SalesSquad/junction-pets/pull/82) is still a draft at authorship; avoid duplicating its root script/validator.

Only a verified hosted result or owner-authorized submission can change the model-run/FINAL status.
