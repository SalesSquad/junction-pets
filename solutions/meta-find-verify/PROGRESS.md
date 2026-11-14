# Chibi Lens continuation

Stage: idea; product workspace scaffold. Existing kernel evidence lives with PR60.

## Next task

- Work ID: junction.solution.meta-find-verify.native-adapter-plan
- Base SHA: 5852fa406a7ea38ed02f0f83ab9b904ad427bccc (re-resolve current source)
- Owner/task URL: unassigned; check existing Meta PR60 owner before taking a write scope
- Default owned paths: solutions/meta-find-verify/
- Objective: specify the smallest actual DAT frame + audio integration against the current kernel ports
- Acceptance: ARCHITECTURE.md records current PR60 head/base/owner, exact adapter input/output and error contract, fake-frame check command, native build/test command and verified executor or explicit blocker
- Workspace check: node scripts/solution-workspace.mjs check
- Portable tooling regression: node --test tests/solution-workspace.test.mjs
- Blocker: real native adapter, authorized Apple executor and hardware evidence have not been established by this scaffold
- Next action: read current PR60 agent ports, agree native path ownership, then replace the plan acceptance with an executable integration task

## Handoff evidence

Record actual tested SHA, commands, output, executor and PR/log links. A DAT adapter,
host-private append-only sightings and phone/glasses calibration are separate
work items. No product submission or live worker is established here.
