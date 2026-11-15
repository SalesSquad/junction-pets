# Open 3D and video: source-pinned CPU research campaign

This is a research workload, not a robot controller, physical safety
qualification, new MuJoCo result, or model release. It is independent of the
existing V13 causal unsafe STOP and does not alter its admission gates.

## Sources and bounded selection

All selected files are public, ungated, individually pinned by immutable
Hugging Face repository revision, byte length and SHA-256 in
`scripts/craci/fixtures/hf-open3d-manifest.json`. Credits and license notices
must accompany downstream use. The raw 884 MB selection is fetched from the
original hosts into ephemeral scratch, not committed to Git.

- [NVIDIA Video to Data, Track 3](https://huggingface.co/datasets/nvidia/video_to_data_challenge/blob/5f68335f3acc802033d1e80728c1633197521de8/track_3/v2d-challenge-track3.md):
  CC BY 4.0, 20 public human-manipulation episodes, 5,246 frames, 10 tasks,
  frame-aligned ego video and 3D object trajectories. Use only the public train
  paths, not its separate evaluation videos. The dataset reports that x/y
  origins are episode-centred and no camera-to-world extrinsic is supplied.
- [Experiential Technologies G1 Moves](https://huggingface.co/datasets/exptech/g1-moves/tree/895d064b2385725e6aabf540461c219afc3e0916):
  CC BY 4.0, select the first 15 sorted dance and 15 sorted karate NPZ clips.
  These are processed/retargeted 29-joint G1 motions; the additional MP4 is a
  rendered training preview, not a real camera recording.
- [BitRobot RoboMoCap](https://huggingface.co/datasets/BitRobot/robomocap/tree/20adb80c474c163fe451b5c4f994b665b3234024):
  CC BY 4.0, select 20 skeleton recordings balanced across 10 participants
  from the first 50 dynamic-recovery session metadata entries. Exclude source
  structure/timing FAIL; remaining source WARN flags are retained in the
  manifest. One original third-person video is also fetched and decoded as a
  source-integrity check. The full dataset is over 5 TB and is not downloaded.

The preparation process verifies all 112 selected original/metadata files and
decodes all 20 paired NVIDIA videos plus the two auxiliary previews. It checks
per-frame video/pose counts, finite coordinates, joint layouts and recorded
participant identity against the frozen manifest. It outputs bounded derived
features and their SHA-256 hashes, not the full videos, raw recordings or
participant names. The video features contain downsampled frame information
and should still be treated as derived public data.

## Fixed comparison

Each of the three lines has **15 distinct cells**: five group-disjoint folds
times Ridge, ExtraTrees and a fixed MLP. Three fold-0 Ridge pilots must all
complete before the other 42 cells run. This tests execution and data
contracts; an inferior pilot score does not erase valid negative science.

| Line | Task | Held-out grouping | Forecast / units |
| --- | --- | --- | --- |
| V2D | Downsampled current and previous ego frames predict displacement of the first tracked object while visible | Original task, 10 groups | 4 frames, approximately 0.2 s / metres |
| G1 | Current joint angles and observed change predict the next 29-joint change | Motion clip, 30 groups | 6 frames at 60 Hz / radians |
| RoboMoCap | Root-relative skeleton positions and observed change predict the next 22-joint change | Participant, 10 groups | 12 frames at 120 Hz / metres |

Only the training fold determines scaling. Each cell reports persistence and
constant-velocity baselines, moving-only and overall errors, and errors by
held-out group. The V2D baseline for both is zero displacement because its
model inputs contain video rather than motion history. The summary reports
both frame-pooled error and group-weighted error; frames are not independent
people, tasks or clips. The G1 grouping is by clip, so a performer may appear
on both sides. Cross-validation here is exploratory and is not an untouched
external test or proof of generalization.

The models are stored as hash-verified small ZIP parts inside the existing
collector caps. Reassembly yields a `joblib`/pickle file; loading it executes
Python deserialization and must be restricted to trusted artifacts. Models
remain research-only and no rollout or promotion is automated. Data and
actual job receipts must be inspected before making an outcome claim.

## Admission and costs

The existing manual CRACI workflow is extended with one bounded workload.
There are 45 training cells, one data-preparation cell and one summary cell,
plus the existing 2-vCPU planner. Training and preparation request CRACI's
documented maximum 32 vCPU; no GPU is claimed. At most six remaining training
cells are scheduled concurrently, leaving room for other work. Each has a
30-minute timeout; preparation and pilot completion gate the remaining work.
The original credit flag, deadline and no-repeat rules remain in place.

At the earlier public EUR 0.0017/vCPU-minute figure, the upper estimate for
46 cells at 32 vCPU × 30 minutes, a 2-vCPU/20-minute summary and a
2-vCPU/5-minute planner is approximately **EUR 75.16**. This is a planning
estimate, not a bill or a hard provider spending cap; it excludes concurrent
account activity and prices may differ. No top-up, new provider or automatic
deployment is authorized.

## Local preflight

On the local Linux executor, the exact pinned files were fetched and
SHA-verified: 2,577 V2D examples/10 task groups, 12,825 G1 examples/30 clip
groups and 11,765 RoboMoCap examples/10 participant groups. One actual local
model per line ran with group-disjoint splits. The V2D Ridge pilot produced
0.0251 m RMSE versus 0.0128 m for persistence on one held-out task; this is
a negative developmental observation, not a CRACI result. The other two
smoke runs establish that their code paths execute, not that any model
generalizes. Local preflight is not a CRACI receipt.

The first hosted attempt [#43672290377](https://github.com/SalesSquad/junction-pets/actions/runs/43672290377)
failed during system dependency installation before any dataset download or
training. The runner's default APT configuration also queried a Microsoft
repository blocked by the network policy. The source now uses only the
existing Ubuntu APT sources when installing FFmpeg. The failed attempt's
incomplete receipt remains in artifact 14144387856.
