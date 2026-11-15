# aiven-flight-recorder continuation

Stage: building. Rescued on 15 November 2026 from the laptop branch `rescue/mbp-20261115/Developer/aiven-flight-recorder-demo-20261114` and filed here. The in-memory test suite (`node --test tests/core.test.mjs`, 3 tests) passes on this checkout. A live Aiven run was not repeated at filing time; the README's measured numbers come from the original author and are not re-verified here.

## Next task

- Work ID: junction.solution.aiven-flight-recorder.live-verify
- Base SHA: 4f56b644e5ffac3420295000316ea198243b22c2
- Owner and task/PR URL: unassigned (the Aiven pet owner; related branch `agent/junction-aiven-stack-capabilities-20261114`)
- Owned paths: solutions/aiven-flight-recorder/
- Objective: re-run the live comparison against real Aiven services and record the evidence
- Acceptance command and expected result: `cd solutions/aiven-flight-recorder && npm ci && npm test` passes; `./run-live.sh` output matches the README claims
- Blocker: needs Aiven credentials held by the operator
- Next action: run live, record SHA and output under Evidence

## Evidence

- Offline comparison (author, `node solutions/aiven-flight-recorder/cli.mjs`): baseline 120/200 executed, 10 duplicates, 90 lost; flight recorder 200/200, 0 duplicates, 0 lost, 1 redelivery after the crash, 0 effects on full replay. Shared with every pet as `replayable-event-log` (`services/aiven-platform`).

- Offline: `node --test solutions/aiven-flight-recorder/tests/core.test.mjs` → 3 passed (filing checkout).
