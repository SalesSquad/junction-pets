# Aalto Humanoid M320: offline hold milestone

Work: `J26-PF-AALTO-M320-20261114`. This is a runnable deterministic safety/contract baseline, **not a sorting policy, camera perception system, hardware result or submission**. M343 wellbeing is unrelated.

## Frozen sources

Official public upstream: [`zupermiez/aaltonomous-humanoid`](https://github.com/zupermiez/aaltonomous-humanoid/tree/36daf5b44dad46b8f448a5124ded7faa9947be1e), commit `36daf5b44dad46b8f448a5124ded7faa9947be1e`:

- [`INTERFACE.md`](https://github.com/zupermiez/aaltonomous-humanoid/blob/36daf5b44dad46b8f448a5124ded7faa9947be1e/aaltonomous/docs/participants/INTERFACE.md)
- [`SUBMISSION.md`](https://github.com/zupermiez/aaltonomous-humanoid/blob/36daf5b44dad46b8f448a5124ded7faa9947be1e/aaltonomous/docs/participants/SUBMISSION.md)
- `aaltonomous/deploy/protocol.py`, `aaltonomous/deploy/policy_server.py`, `aaltonomous/interface/joint_spec.yaml` at that same commit.

Sponsor clarification M320 (14 November): dataset revision `04046a85586feb5727f991adee3367176015cab0`, 20 episodes, 11,720 frames, 30 fps, LeRobot v3, 28-dimensional state/action; demonstrations are suboptimal. No dataset was downloaded or replayed here. Source main at intake and authenticated remote readback: `00dcaca26d46eed196fa2e6c770cbc808901acbd`.

## Run locally, no dependencies or GPU

From this directory:

```sh
python3 -m unittest -v test_policy.py
python3 replay.py
python3 replay.py --trace /tmp/aalto-m320-new-trace.jsonl
```

The final command creates a new file exclusively; it never overwrites evidence. CLI output is bounded JSON with states, failures, abstentions, coverage arithmetic and a trace digest. The in-memory trace is a tuple of frozen records, with input hashes, exact upstream/dataset revisions and a hash chain. JSONL exports are ordinary mutable files, not signed receipts; their chain supports comparison against a separately retained digest. They contain synthetic inputs' hashes and results, no camera pixels. This local output is not an iCloud archive.

`policy.py` accepts decoded scalar vectors as 14-element lists/tuples and images as exact-sized bytes. The adapter enforces numpy wire dtype/shape before conversion: RGB uint8[480,640,3], depth uint16[480,640], arm_q/arm_dq/hand_q float32[14], instruction string, t seconds. Zero depth is invalid. All three RGB shapes match the pinned INTERFACE §2.

READY means valid input with an understood narrow instruction, not permission to move. HOLD covers blank camera frames, zero valid depth and gaps >=0.2s; ABSTAIN covers unseen/ambiguous instructions. FAULT latches for bad numeric shape/type/finiteness, malformed sensors, nonmonotonic time, or gaps >=1s; reset clears it. When possible all states return the initial validated measured pose as absolute arm/hand targets. With no valid initial pose FAULT emits no target and raises an explicit error. Reset must be performed at episode boundaries. The local gap checks do not replace the staff runner's wall-clock watchdog (0.2s hold, 1s safe stop).

Parsing deliberately recognizes only `put/place/move/sort [the] COLOR object/item/block/cube in/into/to [the] [SIDE] bin`, optional please, case and terminal punctuation. Red maps left, yellow center, blue right; conflicting sides, negation, multiple instructions and unfamiliar phrasing abstain. Images are checked for format and nonzero depth only: **no perception is performed**. All targets remain fixed even when measured joints change. No trajectory, synthetic grasp, or non-hold command is generated. No robot connection exists in the core/replay.

Dex3 left/right have different joint ordering: left thumb 0–2, middle 0–1, index 0–1; right thumb 0–2, index 0–1, middle 0–1. Left fingers close with negative angles, right with positive; thumb_0 is mirrored too. Preserve all 14 hand slots exactly as delivered by the pinned joint specification; do not reverse, swap, rename or mirror them. The sentinel test verifies preservation, not anatomical mapping or hardware calibration. The core validates initial and subsequent 14 arm + 14 mirrored Dex3 targets against the pinned official URDF bounds in joint_limits.py, failing closed before emitting a new initial target. These bounds are not the staff safety filter's position margins, velocity checks, wrist/palm workspace and collision constraints. It never bypasses the official filter or executes an actuating trajectory. No local clipping is performed.

## Optional official server and next dependency

`adapter.py` subclasses the official `Policy`, implements `reset(instruction, task, seed)` and `act(obs)`, and delegates binary msgpack metadata/reset/reset_ok/act/action handling to upstream `serve(..., port=8000)`. It imports rather than copies upstream code. On missing numpy/upstream it exits with a dependency error; an invalid initial observation raises through upstream's error response. Later faults retain the previous hold. No custom protocol or background controller is introduced.

**One next dependency:** a source-verified local installation of the pinned upstream package and its declared numpy/websocket/msgpack dependencies. Use an isolated environment and follow that checkout's installation instructions, then expose its root via PYTHONPATH. For example, with that checkout already at the exact SHA:

```sh
# Terminal 1, with the official dependencies installed; local testing only
PYTHONPATH=/path/to/aaltonomous-humanoid python3 adapter.py
# Terminal 2, from that pinned upstream checkout, same environment
python -m aaltonomous.deploy.replay --synthetic 100 --policy ws://localhost:8000
python -m aaltonomous.deploy.runner --backend mock --policy ws://localhost:8000 --team m320-hold --episodes 2
```

These are the official SUBMISSION §5 next checks, **not executed here**. Blank synthetic images produce holds. Official replay measures actual returned command throughput; runner mock checks safety plumbing. Neither establishes sorting success or Isaac safety qualification.

Only after separate authorization and access to an RTX Isaac environment, the official next gate is:

```sh
python -m aaltonomous.sim.evaluate --policy ws://localhost:8000 --team m320-hold --task sort_fixed --trials 20
```

Keep defaults: >=27 commands/s, zero clips, arm command delta <=1 rad/s and hand <=3 rad/s at 30Hz. Simulation requires an RTX rendering GPU; none was provisioned or authorized. Real robot execution remains exclusively staff-run after simulation admission; no deployment, submission or physical execution is part of this work.

## Acceptance observed locally

14 November 2026, isolated clone, Python stdlib unittest: 8 tests passed. Covers numeric invalidity, shape, stale time, watchdog gap boundaries, absent depth, instruction abstention, fault/reset, safe-command reuse, hand slot preservation and trace immutability/determinism. Local synthetic replay: 90 scheduled frames at 30Hz, 90 target responses, 30 abstentions, zero failures, zero arm/hand target deltas and zero clipping operations. `30 * emitted / scheduled_frames = 30` is **coverage arithmetic only**, not a wall-clock measurement or a >=27Hz official pass. No timed scheduling is claimed. The replay prints its content-dependent SHA-256 digest; re-run after any fixture or policy change. No previous digest is represented as evidence for this revision.

Upstream server and SUBMISSION source were read at the pinned commit; adapter import/runtime, official replay, runner mock, dataset replay, RTX/Isaac, container startup, staff filter margins, workspace, physical safety and task success remain unverified. No third-party code was copied.
