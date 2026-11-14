# SO101 physical simulator / fail-closed replay bridge (M8)

Portable executable Python CLI, isolated from core, batch, host, vision and studio.
One cube and prescribed joint waypoints in real MuJoCo rigid-body dynamics, with
separate **SYNTHETIC_FAULT_INJECTION**. No model confidence, anomaly metric or
quality score is generated. Existing M4/M5 fixture receipts remain synthetic.
The bridge always REFUSES sorting: no real calibrated defect source exists.
It has no hardware adapter, network client, background service or rearm API.

## Run

Python 3.13+, existing authorized model directory, native CPU with a working
MuJoCo rendering context. Install only the pinned project-local environment:

```sh
uv venv --python 3.13 /absolute/work/.venv
uv pip install --python /absolute/work/.venv/bin/python -r solutions/intel-physical-ai/sim/requirements.txt
/absolute/work/.venv/bin/python solutions/intel-physical-ai/sim/run.py \
  --model-root /absolute/existing/robotstudio_so101 \
  --output-dir /absolute/work/new-run
/absolute/work/.venv/bin/python solutions/intel-physical-ai/sim/bridge.py \
  --model-root /absolute/existing/robotstudio_so101 \
  --episode-dir /absolute/work/new-run/nominal-23
```

Neither CLI downloads models or data. Output directory creation is exclusive;
existing directories fail, even empty ones. A failure preserves partial output
without a completed summary. Choose another directory for a retry. No binary
model, mesh or camera bytes are committed here. `model-pin.json` pins XML,
all available external mesh assets and LICENSE to Menagerie revision
`370c43965323c0944b433b202aac5058b5f907a9` (Apache-2.0). Supply the
`robotstudio_so101` directory from an independently obtained checkout; all pinned
files must match before loading XML. `LICENSE.model.txt` preserves the license.
No model files were modified. Waypoint functions were refactored from the owner's
14 November SO101 lab; the original script digest is in `historical.json`.

Defaults: nine named scenarios × unseen fixed seeds `[23,31]`, 180 frames each,
200 Hz physical integration and 30 Hz target opportunities. `--cases nominal
operator_global_stop --seeds 23` selects a smaller repeatable run. The legacy
case names `low_confidence` and `threshold_ambiguous` are fault identifiers only;
no confidence, interval or score is invented. All eight fault types conservatively
latch the same software global STOP at frame 70. This changes the old lab's
rearming local-hold behavior deliberately. Once latched, **no further target is
issued**, even if the next observation is healthy. The old servo target remains
energized in simulation; physical joints continue moving. This is virtual servo
hold, never power removal or a physical emergency stop.

Each step integrates the previous servo target, renders the real virtual wrist
camera, checks that observation and fault injection, then may issue the next
interval's demonstration target. These waypoints are permitted only as a
non-sorting demo; unknown defect evidence always yields HOLD. No scene truth
is used as a defect decision. Only a virtual wrist camera exists here; there
is no simulated top/inspection calibration or multi-camera inference.

## Replay and integrity

`run.json` records UTC, host, Python/dependency versions, actual source file
hashes and git base HEAD, model pin, seeds, rates and capture configuration.
Every episode has a manifest and complete JSONL trace: monotonic frame index,
physical time, full actual qpos/qvel, contacts (geometry IDs, positions, distances),
persistent servo target, explicit command emission, camera identity/timestamp,
saved PPM bytes SHA-256, separate injected fault and bridge decision. Trace and
manifest digests bind completed episodes to the summary. Source hashes describe
executed bytes even when the run predates the branch commit.

The verifier checks external model bytes against the trusted local pin, fixed
frame count, complete newline, trace hash, sequential frames/times/rates, finite
physics, camera file boundaries/hash/size, identity/freshness and decision replay.
Path traversal and escaping symlinks fail. Commands or target changes after STOP
fail. Missing/stale/wrong-identity camera evidence yields a latched STOP and
`sensor_replay_accepted:false`; the trace may still have valid physical/log
integrity. CLI malformed/corrupt input exits 2; sensor-refused replay exits 0 with
explicit refusal fields, **never approval to route**. Callers must check
`sensor_replay_accepted`, not process exit alone. There is no route-enabling
result, calibrated source input or automatic rearm in this milestone.

Hashes are unsigned corruption checks, not authenticated capture provenance.
A malicious author can fabricate an internally consistent log or reassign an
old image to a new identity. Passing replay is not independent attestation of
physics execution, image freshness, calibration or real command transmission.

When native rendering is unavailable, explicitly select `--capture disabled`.
This is a **missing-camera CPU diagnostic**, not a rendered simulation pass:
it still integrates physical state and records every frame, but camera path/hash
are null, every camera is absent, and STOP latches at frame zero. All scenarios
then share that initial missing-sensor boundary; their frame-70 fault behavior
is not independently exercised by such a run. Never treat it as the required
rendered 18-episode qualification.

## Targeted tests

Supply actual external run and historical camera locations. The expected
historical SHA should come from the evidence inventory, independently of a
potentially modified file.

```sh
export M8_MODEL_ROOT=/absolute/existing/robotstudio_so101
export M8_EPISODE=/absolute/work/diagnostic/nominal-23
export M8_HISTORICAL_CAMERA=/absolute/historical/runs/frames-camera_missing-7-gate/f0000.ppm
export M8_HISTORICAL_CAMERA_SHA256=<recorded-sha256>
PYTHONDONTWRITEBYTECODE=1 /absolute/work/.venv/bin/python -m unittest discover \
  -s solutions/intel-physical-ai/sim -p 'test_*.py' -v
```

Tests cover genuine historical saved-byte hashes and tampering, complete replay,
duplicate/missing/truncated/nonmonotonic/nonfinite rows, missing hash, traversal,
model pin failure, camera absence/staleness/identity, global latch without rearm,
post-stop target/emission rejection, unknown evidence HOLD without quality score,
and exclusive output integrity. The positive complete-replay fixture repeats
one genuine historical image with test-assigned identities: **protocol test only,
not 180 new captures or independently executed commands**.

## Evidence and remaining gate

See `evidence.json` for local execution/check outcomes and source/log digests.
Actual Mini CPU diagnostics run nine scenarios × `[23,31]`. Default native
capture failed with `mujoco.cgl.cgl.CGLError: invalid CoreGraphics connection` in
this restricted executor. A full newly rendered 18-episode run remains blocked
on an authorized working native graphics context. No OS permissions were changed.
All logs/artifacts stay in the task's Mini Operations directory, outside Git;
no iCloud persistence is claimed.

`historical.json` reuses existing `[7,11,19]` evidence without rerunning or
relabeling it: 1,962 baseline post-fault command changes versus zero while
latched, maximum recorded drift 0.001362 rad. Its injected anomaly/confidence
values are not model results; its motor-power absolute integral is a proxy,
not actual watts. New drift values use displacement from the first latched
frame and are not the old lab's distance-to-held-target metric.

This is no SO101 hardware or Intel CPU/GPU/NPU result. Still absent: allocated
station, real camera identity/calibration, real labeled defects and held-out
perception, Anomalib/OpenVINO execution, VLA/Physical AI Studio policy, autonomous
grasp/three bowls, live arm, physical E-stop, real power/thermal/cycle-time data.
The 14 November M330 judging conflict remains unresolved (GitHub
25/25/20/20/10 versus slides 25/20/20/20/10/5); older 13 November guidance and
the captured main brief are preserved as separate sources in the root catalog.
No challenge completion or sponsor endorsement is claimed.
