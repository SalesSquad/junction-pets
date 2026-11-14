# Aalto M320: genuine public-data imitation baseline (offline)

Work `VERDA-AALTO-ROKOKO-20261114`; this builds on [M320 baseline PR #121](https://github.com/SalesSquad/junction-pets/pull/121) and [official replay PR #139](https://github.com/SalesSquad/junction-pets/pull/139). The result is **not** a robot policy server, a simulator run, training on private data, or a Junction submission.

## Pinned inputs

- Sponsor dataset: [`zupermiez/g1_pick_cube`](https://huggingface.co/datasets/zupermiez/g1_pick_cube) at revision `04046a85586feb5727f991adee3367176015cab0`.
- Verified public `meta/info.json` SHA-256: `cc93b965d0a4d975e43749f1f408c693774d7da90d132924740ba0a494c98c70`.
- Verified public `README.md` SHA-256: `43b571d3b957bde4b3b307a3d2ac732c9ba6f5e906b6a49a5b8eac6b68efd8b0`.
- Verified public `data/chunk-000/file-000.parquet` SHA-256: `49a03ab14237467f27b5656d78103b8a716062e21e106c0f5650c566be25ded3` (3,533,626 bytes); enforced before parsing. Newer `hf-xet` cache clients symlink the snapshot to the shared `hub/blobs` directory; older clients use repository-local `blobs`.
- Exactly 20 episodes / 11,720 frames / 30 fps; `observation.state` and `action` are float32[28] with matching ordered joint names. Three AV1 camera streams are available, but this baseline **does not decode or download** them.
- Pinned sponsor runner source: `zupermiez/aaltonomous-humanoid@36daf5b44dad46b8f448a5124ded7faa9947be1e`.

The sponsor explicitly describes much of the data as **suboptimal**. Its public dataset card does not declare a general redistribution/training license, so this workflow is limited to the sponsored Junction challenge; do not republish footage, data or derived model weights without resolving rights.

## Actual CPU baseline run (no GPU needed)

Use an isolated venv and a scratch volume **outside iCloud and the repository**. No video download is required. The installed Hugging Face Hub client resolves the exact pinned revision; the study verifies metadata/card bytes and **rejects Parquet content that differs from the exact pinned SHA-256**, but local hashes are not a signature.

```bash
python3 -m pip install numpy pyarrow huggingface-hub
python3 -c 'from huggingface_hub import snapshot_download; print(snapshot_download(repo_id="zupermiez/g1_pick_cube", repo_type="dataset", revision="04046a85586feb5727f991adee3367176015cab0", allow_patterns=["README.md", "meta/**", "data/**"]))'

# Paste the snapshot directory returned above. Choose a NEW output path per run.
python3 offline_study.py --dataset-root /path/to/pinned/snapshot \
  --output /scratch/aalto-m320-state-baseline-001
```

The default split seed `20261114` fixes **12 complete training episodes, four validation episodes and four untouched test episodes**. No adjacent frame from the same episode crosses the partitions. Validation selects ridge regularization; test results are calculated once. Metrics are MAE/RMSE in joint radians with per-episode macro averages. Baselines are train-mean, current-state identity, 1-nearest-training-state action, and a clearly labeled **non-deployable teacher-forced previous-action oracle**. The report includes source, data-file and script SHA-256s, episode IDs/counts, model selection and limitations; a `.npz` stores only ridge weights with no executable pickle.

Because four episodes may strongly favor one model, run the deterministic five-seed sensitivity study. This tests the **fixed seeds 20261114 through 20261118 without cherry-picking**, with complete episode partitions preserved in every fold; the heldout groups overlap between seeds and are not independent datasets:

```bash
python3 sensitivity_suite.py --dataset-root /path/to/pinned/snapshot \
  --output /scratch/aalto-m320-five-seed-001
```

The new output contains all five seed receipts, their model weight arrays and `summary.json`, including source hashes, each held-out episode's error/exposure, median and worst gain. A robust improvement is accepted only if the validation-selected ridge improves at least **5% on each of the five fixed test splits**. Negative results are mandatory evidence, not grounds to choose a more favorable seed. No GPU/AV1 or robot simulator is used by this sensitivity suite.

Use the shortest affected-path test:

```bash
python3 -m unittest -q test_offline_study.py
```

## What warrants Verda GPU spend next

The state-only regression is tiny, so it does **not** merit an A100. `vision_probe.py` adds a **frozen, source-attributed visual encoder** over a sampled subset of the three public AV1 streams. It uses Meta's `facebook/dinov2-base` at exact revision `f9e44c814b77203eaa57a6bdbbd535f21ede1415` (Apache-2.0), and requires official LeRobot installed from exact source commit `fe1c54594f6ba275fccf210b9f7b11f0e2324b89`. The decoder/weights are checked before attempting the pinned public clips. PyAV is explicitly selected for stable AV1 decode across torch/CUDA stacks. The baseline and vision probes use the same split and compare on **identical sampled test rows**. The vision feature cache is source-fingerprinted (including SHA-256 of **each public AV1 shard**) and checkpointed every 32 frames; `--resume` reuses only an exact-match prefix. It refuses a non-CUDA environment.

Suggested authorized isolated GPU environment (run only after current Verda spend/availability preflight and with a task-owned instance):

```bash
python3 -m pip install numpy pyarrow torch torchvision transformers safetensors huggingface-hub \
  'lerobot[dataset] @ git+https://github.com/huggingface/lerobot.git@fe1c54594f6ba275fccf210b9f7b11f0e2324b89'

# Unlike the tiny CPU baseline, this explicitly needs all three public AV1 streams.
python3 -c 'from huggingface_hub import snapshot_download; print(snapshot_download(repo_id="zupermiez/g1_pick_cube", repo_type="dataset", revision="04046a85586feb5727f991adee3367176015cab0", allow_patterns=["README.md", "meta/**", "data/**", "videos/**"]))'

python3 vision_probe.py --dataset-root /path/to/pinned/snapshot \
  --output /scratch/aalto-m320-dinov2-probe-001 --max-seconds 6600 \
  --stride 6 --max-per-episode 80 --checkpoint-every 32
# After spot interruption, ONLY if source and dataset are unchanged:
python3 vision_probe.py --dataset-root /path/to/pinned/snapshot \
  --output /scratch/aalto-m320-dinov2-probe-001 --resume --max-seconds 6600 \
  --stride 6 --max-per-episode 80 --checkpoint-every 32
```

The source-only tests use no GPU, model download, or video input. The GPU path has **not been executed**; pinned LeRobot dependency resolution, AV1 decoding, DINOv2 inference, heldout vision gain and GPU runtime remain unverified. Keep the host-side GPU billing ceiling at two hours including setup/checkpoint handling. If frozen vision does not improve heldout episode-macro MAE by at least 5% over the same-row state-only ridge, stop without a larger ACT finetune.

If visual features improve, a subsequent task can train an image-conditioned ACT policy and attempt the official simulator on a separate **RTX-rendering** environment.

Important distinction: sponsor's Isaac RTX simulator is **not qualified** on an A100 spot card. Official simulation/real-robot success must not be inferred from low open-loop action error, synthetic replay rate or an AV1 embedding run. No physical commands or policy-server endpoints are exposed by this study.
