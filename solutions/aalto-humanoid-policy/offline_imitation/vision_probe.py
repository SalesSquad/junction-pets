#!/usr/bin/env python3
"""A100-eligible, resumable DINOv2 vs state-only Aalto offline vision probe.

Read-only public sponsor footage; no simulator/robot action, external upload,
foundation-model finetuning, or model promotion. Run *after* offline_study.py.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import distribution
import json
import math
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

import numpy as np

import offline_study as base

MODEL_ID = "facebook/dinov2-base"
MODEL_COMMIT = "f9e44c814b77203eaa57a6bdbbd535f21ede1415"
LEROBOT_COMMIT = "fe1c54594f6ba275fccf210b9f7b11f0e2324b89"
CAMERAS = ("observation.images.cam_high", "observation.images.cam_left_wrist",
           "observation.images.cam_right_wrist")
EMBED_DIM = 768


def balanced_indices(episode: np.ndarray, frame: np.ndarray, stride: int,
                     max_per_episode: int) -> np.ndarray:
    """Episode-uniform temporal subsampling, fixed before model evaluation."""
    if stride < 1 or not 1 <= max_per_episode <= 256:
        raise ValueError("invalid stride/max_per_episode")
    picked = []
    for ep in range(base.N_EPISODES):
        candidates = np.nonzero((episode == ep) & (frame % stride == 0))[0]
        chosen = candidates[np.argsort(frame[candidates], kind="stable")[:max_per_episode]]
        if len(chosen) < 8:
            raise ValueError(f"episode {ep} has too few decodable sampled frames")
        picked.extend(chosen.tolist())
    return np.asarray(sorted(picked), dtype=np.int64)


def dual_ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float):
    """Primal/dual ridge use only TRAIN moments; dual supports wide vision vectors."""
    if not math.isfinite(alpha) or alpha <= 0:
        raise ValueError("invalid alpha")
    xm = x.mean(axis=0, dtype=np.float64)
    xs = x.std(axis=0, dtype=np.float64) + 1e-6
    ym = y.mean(axis=0, dtype=np.float64)
    xn = (x.astype(np.float64) - xm) / xs
    yn = y.astype(np.float64) - ym
    # Kernel scales with sample count to make alphas comparable for feature sets.
    gram = (xn @ xn.T) / len(xn)
    coefficients = np.linalg.solve(gram + alpha * np.eye(len(xn)), yn)
    return xn, coefficients, xm, xs, ym


def dual_ridge_predict(model, x: np.ndarray):
    train, coeffs, xm, xs, ym = model
    query = (x.astype(np.float64) - xm) / xs
    return ((query @ train.T) / len(train) @ coeffs + ym).astype(np.float32)


def evaluate_features(features: np.ndarray, state: np.ndarray, action: np.ndarray,
                      episode: np.ndarray, split: dict) -> dict:
    """Validation chooses alpha, test queried once per fixed feature family."""
    if (features.ndim != 2 or features.shape[0] != len(state)
            or features.shape[1] != EMBED_DIM * len(CAMERAS)
            or not np.isfinite(features).all()):
        raise ValueError("vision embedding dimensions/finiteness mismatch")
    if not np.isfinite(state).all() or not np.isfinite(action).all():
        raise ValueError("nonfinite source labels")
    masks = {name: np.isin(episode, ids) for name, ids in split.items()}
    result = {}
    for label, x in (("state_only", state), ("state_plus_frozen_vision", np.concatenate([state, features], axis=1))):
        validation, trained = {}, {}
        for alpha in (0.1, 1.0, 10.0, 100.0, 1000.0):
            model = dual_ridge_fit(x[masks["train"]], action[masks["train"]], alpha)
            prediction = dual_ridge_predict(model, x[masks["validation"]])
            validation[str(alpha)] = base.grouped_metrics(
                prediction, action[masks["validation"]], episode[masks["validation"]]
            )["episode_macro_mae_rad"]
            trained[alpha] = model
        selected = min(trained, key=lambda a: (validation[str(a)], a))
        result[label] = {
            "ridge_alpha": selected,
            "validation_macro_mae": validation,
            "test": base.grouped_metrics(dual_ridge_predict(trained[selected], x[masks["test"]]),
                                         action[masks["test"]], episode[masks["test"]]),
        }
    reference = result["state_only"]["test"]["episode_macro_mae_rad"]
    candidate = result["state_plus_frozen_vision"]["test"]["episode_macro_mae_rad"]
    result["vision_gain_vs_same_rows_state_ridge"] = (reference - candidate) / reference if reference > 0 else 0.0
    return result


def progress_fingerprint(source: dict, indices: np.ndarray, stride: int, max_per_episode: int) -> dict:
    h = hashlib.sha256(indices.tobytes()).hexdigest()
    return {"source_data": source["parquet_sha256"], "info_sha256": source["info_sha256"],
            "dataset_revision": base.DATASET_COMMIT, "model_commit": MODEL_COMMIT,
            "lerobot_commit_expected": LEROBOT_COMMIT,
            "code_sha256": base.digest_file(Path(__file__).resolve()),
            "indices_sha256": h, "stride": stride, "max_per_episode": max_per_episode,
            "split_seed": base.SPLIT_SEED}


def save_progress(out: Path, indexes: list[int], embeddings: list[np.ndarray]):
    tmp = out / "embeddings.partial.npz.tmp"
    with tmp.open("wb") as f:
        np.savez_compressed(f, rows=np.asarray(indexes, dtype=np.int64),
                            embeddings=np.asarray(embeddings, dtype=np.float32))
    tmp.replace(out / "embeddings.partial.npz")


def recover_progress(out: Path, samples: np.ndarray) -> tuple[list[int], list[np.ndarray]]:
    cached = out / "embeddings.partial.npz"
    if not cached.is_file():
        return [], []
    with np.load(cached, allow_pickle=False) as d:
        rows = d["rows"]
        embeds = d["embeddings"]
        if (rows.ndim != 1 or embeds.shape != (len(rows), EMBED_DIM * len(CAMERAS))
                or not np.isfinite(embeds).all() or len(rows) > len(samples)
                or not np.array_equal(rows, samples[:len(rows)])):
            raise ValueError("corrupt or mismatched resume embedding cache")
        return rows.tolist(), [e.copy() for e in embeds]


def run(root: Path, out: Path, *, resume: bool, stride: int,
        max_per_episode: int, max_seconds: int, checkpoint_every: int) -> dict:
    start = time.monotonic()
    import torch
    from huggingface_hub import hf_hub_download
    from transformers import AutoImageProcessor, AutoModel
    from lerobot.datasets import LeRobotDataset

    if not torch.cuda.is_available():
        raise RuntimeError("real GPU vision stage requires CUDA; CPU fallback is offline_study.py")
    if not 60 <= max_seconds <= 7200 or not 1 <= checkpoint_every <= 64:
        raise ValueError("invalid time/checkpoint bounds")
    direct_url = distribution("lerobot").read_text("direct_url.json")
    pinned_install = json.loads(direct_url) if direct_url else {}
    installed_commit = pinned_install.get("vcs_info", {}).get("commit_id")
    if installed_commit != LEROBOT_COMMIT:
        raise RuntimeError("LeRobot must be installed from pinned official Git commit")
    data_source = base.dataset_preflight(root)
    for key in CAMERAS:
        if not (root / "videos" / key).is_dir():
            raise ValueError(f"missing public AV1 footage for camera {key}")
    episode, frame, states, actions = base.read_parquet_vectors(root)
    indices = balanced_indices(episode, frame, stride, max_per_episode)
    fingerprint = progress_fingerprint(data_source, indices, stride, max_per_episode)
    if resume:
        if not out.is_dir() or not (out / "fingerprint.json").is_file():
            raise ValueError("resume requires existing checkpoint/fingerprint directory")
        existing = json.loads((out / "fingerprint.json").read_text())
        if existing != fingerprint:
            raise ValueError("source/weights/selection changed; refusing stale resume")
    else:
        out.mkdir(parents=True, exist_ok=False)
        (out / "fingerprint.json").write_text(json.dumps(fingerprint, sort_keys=True, indent=2) + "\n")

    completed, embedding_vectors = recover_progress(out, indices)
    processor = AutoImageProcessor.from_pretrained(MODEL_ID, revision=MODEL_COMMIT, trust_remote_code=False)
    model = AutoModel.from_pretrained(MODEL_ID, revision=MODEL_COMMIT,
                                      trust_remote_code=False, use_safetensors=True)
    weights = hf_hub_download(MODEL_ID, "model.safetensors", revision=MODEL_COMMIT)
    weights_sha = base.digest_file(Path(weights))
    model.to("cuda").eval()
    for param in model.parameters():
        param.requires_grad_(False)

    # Dataset is read with its source SHA and local root; no unpinned Hub update.
    dataset = LeRobotDataset(base.DATASET_REPO, root=root, revision=base.DATASET_COMMIT)
    if len(dataset) != base.N_FRAMES:
        raise ValueError("LeRobot decoder changed dataset row count")
    for offset, i in enumerate(indices[len(completed):], start=len(completed)):
        if time.monotonic() - start >= max_seconds:
            save_progress(out, completed, embedding_vectors)
            raise RuntimeError("GPU time cap reached; progress saved for exact-source resume")
        sample = dataset[int(i)]
        if (int(sample["episode_index"]) != int(episode[i])
                or int(sample["frame_index"]) != int(frame[i])):
            raise ValueError("LeRobot row order mismatch with pinned Parquet labels")
        frames = [sample[key] for key in CAMERAS]
        if any(x.shape != (3, 480, 640) for x in frames):
            raise ValueError("unexpected camera frame shape")
        # LeRobot yields float images in [0,1]; avoid the common 1/255 double rescale.
        inputs = processor(images=frames, return_tensors="pt",
                           do_rescale=frames[0].dtype == torch.uint8)["pixel_values"].to("cuda")
        with torch.inference_mode():
            vectors = model(pixel_values=inputs).last_hidden_state[:, 0, :]
        if tuple(vectors.shape) != (len(CAMERAS), EMBED_DIM):
            raise ValueError("DINOv2 embedding contract changed")
        embedding_vectors.append(vectors.float().cpu().numpy().reshape(-1))
        completed.append(int(i))
        if (offset + 1) % checkpoint_every == 0:
            save_progress(out, completed, embedding_vectors)
    save_progress(out, completed, embedding_vectors)

    # Compare the *same* heldout sampled frames, not a mismatched full-frame run.
    selected_features = np.asarray(embedding_vectors, dtype=np.float32)
    chosen = indices
    split = base.episode_split()
    comparison = evaluate_features(selected_features, states[chosen], actions[chosen],
                                   episode[chosen], split)
    report = {"result": "frozen_vision_offline_eval_only",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "source": fingerprint, "model": {"id": MODEL_ID, "revision": MODEL_COMMIT,
                                               "safetensors_sha256": weights_sha,
                                               "license": "Apache-2.0, official Meta DINOv2 model card"},
              "data_source": data_source, "samples": len(chosen),
              "split": split, "frame_counts": {name: int(np.isin(episode[chosen], ids).sum())
                                                 for name, ids in split.items()},
              "torch_version": torch.__version__,
              "cuda_device": torch.cuda.get_device_name(0),
              "wall_seconds": time.monotonic() - start,
              "comparison": comparison,
              "limitations": ["Vision encoder frozen; training labels from suboptimal teleoperation.",
                              "No inference safety validation, Isaac simulation, task success or physical robot result.",
                              "Four heldout episodes; test was not used for hyperparameter selection.",
                              "Model license verified Apache-2.0; sponsor dataset card does not state broad redistribution rights."]}
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--stride", type=int, default=6)
    p.add_argument("--max-per-episode", type=int, default=80)
    p.add_argument("--max-seconds", type=int, default=6600)
    p.add_argument("--checkpoint-every", type=int, default=32)
    a = p.parse_args(argv)
    try:
        report = run(a.dataset_root, a.output, resume=a.resume, stride=a.stride,
                     max_per_episode=a.max_per_episode, max_seconds=a.max_seconds,
                     checkpoint_every=a.checkpoint_every)
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": report["result"], "output": str(a.output),
                      "samples": report["samples"], "vision_gain":
                      report["comparison"]["vision_gain_vs_same_rows_state_ridge"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
