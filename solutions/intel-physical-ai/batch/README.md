# Synthetic batch inspection cell — M2

Work `J26-PF-INTEL-M330-M2-20261114`. Node 22+, no dependencies. From repository root:

```sh
node --test solutions/intel-physical-ai/batch/*.test.mjs
node solutions/intel-physical-ai/batch/cli.mjs demo /tmp/intel-m2-receipt.json 330
node solutions/intel-physical-ai/batch/cli.mjs verify /tmp/intel-m2-receipt.json
```

Output uses exclusive file creation; choose a new filename on repeat runs. Omit
filename to print the full receipt. No server, hardware, inference or credentials.
The source main pin is `ee2ce767ed779cafa0f048c6b087ce5c84831a7f`;
M2 source version is `synthetic-batch/1`. This pin identifies the imported M1
baseline, not a future M2 commit. Coordinator must bind the eventual commit to
these new files. Receipts are unsigned deterministic corruption checks, not
identity attestations or authorization. Anyone can create another valid trace.

Operator journey: run seed 330 to feed eight simulated bricks in order. Each
records feed position, grip retention, unchanged M1 Anomalib-style fixture
score/uncertainty/camera evidence, and an explicit operator decision and reason.
The first two clear gates route good/defect; the uncertain third requires M1
review and routes to the third (hold) bowl. Gripper loss, camera disagreement
and stale evidence retain HOLD without simulated placement. Their embedded M1
sessions stop, with no bowl. Brick seven demonstrates explicit operator stop
for that episode; the next independent episode may start. This is not a
persistent emergency stop or a real batch controller. Missing camera and low
confidence also retain HOLD. No fault can be overridden into placement.

For a custom operator script, import `plan`, change an episode's
`operator: {decision: 'stop' | 'continue', reason: '...'}`, then call `runBatch`.
Every run is a complete, immutable snapshot, not a mutable device session.
Episode IDs must be unique within the run. Replay is idempotent and has no side
effects; duplicate IDs fail rather than count twice. There is no cross-process
registry, persistent queue or exactly-once physical execution claim.

`cell.mjs` imports M1 createSession/apply/receipt/replayReceipt rather than
copying or modifying its gate. Seeded feed positions and fixed fault scenarios
are versioned synthetic fixtures. Independent labelled simulator truth is joined
only after routing, for evaluation; routing never reads truth or M1 fixture
labels. Changing seeds changes positions, not difficulty or measurement quality.
The always-sort comparator uses only the score threshold, ignoring all gates
and operator stop. Counts report sorted/held/stopped, correct/wrong among sorted,
unsafe sorted and coverage. Conditional correctness excludes holds/stops and is
null with no sorted items. All numbers are synthetic fixture arithmetic, never
robot accuracy, measured throughput or calibrated model performance.

Each step hashes version, sequence, episode, stage, data and previous SHA-256;
the initial digest binds the complete request and provenance. Final evaluation
is chained too. Verification regenerates every event and metric and independently
replays nested M1 receipts, comparing the complete result. Altered hash, state,
provenance, reason, truth or arithmetic fails. Full valid regeneration is possible
because this is an offline simulator, not authenticated real-world evidence.

Source fit: catalog `docs/challenge-research/current-source-catalog.json`,
14 November snapshot, partner `ignite-next-and-intel`, owned brief M330, shared
by junction.intel and junction.ignite-next. Latest clarification preserves the
unresolved GitHub 25/25/20/20/10 versus PDF 25/20/20/20/10/5 judging rubrics;
this milestone does not reconcile them. Three-bowl guidance supports the
conservative hold demonstration, not sponsor acceptance of simulated completion.

Single next acceptance dependency: coordinator obtains sponsor-confirmed
acceptance criteria (including the unresolved rubric) and an authorized real
station qualification plan. Actual SO-101 grip/cameras/emergency stop, Physical
AI Studio VLA, trained Anomalib, OpenVINO CPU/GPU/NPU, hardware performance and
sponsor acceptance are unverified. This synthetic executable does not satisfy
real autonomous robot requirements. No real action authorization is issued.
