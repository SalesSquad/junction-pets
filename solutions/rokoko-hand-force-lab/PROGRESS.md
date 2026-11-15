# Progress

Stage: building. Created 15 November 2026 from main `e0d397463f03adb92e106d46eacf89f94b10b592` on branch
`claude/rokoko-hand-force-lab-20261115`. Writer: Claude session for the owner. Checks actually run in that session:
`python3 rokoko_v3.py` (round trip passes), `python3 teleop_replay.py` (153.8 N peak grip from the simulated stream),
`tasks.cup_task()` (bottle placed upright), all five scenarios rendered, `exp.py feedback friction learn`.
No hosted CI run. `node scripts/solution-workspace.mjs check` result is recorded in the PR/branch report.

## Next tasks

1. Run `teleop_replay.py --udp` against a real Rokoko Studio stream; fix joint names/axes from real frames.
2. Damp the grip-force oscillation in the lift task without losing the grasp (one attempt at a slower loop dropped the bottle).
3. Replace the carriage with an arm model and inverse kinematics.
4. Decide with the Rokoko lane owner whether this lab or MotionBridge Studio leads the submission; root indexes
   (`solutions/README.md`, `docs/AGENT_SOURCE_INDEX.json`) were not edited here because the integrator owns them.
