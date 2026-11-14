#!/usr/bin/env python3
"""Pinned Aalto M320 offline imitation study, with no robot/Isaac interface.

Reads the *public* sponsor's LeRobot v3 Parquet state/action vectors only. The
videos are not downloaded or decoded. Episode-level splits prevent adjacent
frames in the same demonstration from leaking into holdout evaluation.

This is an action-prediction experiment, never evidence of sorting or safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from datetime import datetime, timezone

import numpy as np

DATASET_REPO = "zupermiez/g1_pick_cube"
DATASET_COMMIT = "04046a85586feb5727f991adee3367176015cab0"
INFO_SHA256 = "cc93b965d0a4d975e43749f1f408c693774d7da90d132924740ba0a494c98c70"
README_SHA256 = "43b571d3b957bde4b3b307a3d2ac732c9ba6f5e906b6a49a5b8eac6b68efd8b0"
UPSTREAM_COMMIT = "36daf5b44dad46b8f448a5124ded7faa9947be1e"
SPLIT_SEED = 20261114
FEATURES = ("observation.state", "action")
N_EPISODES, N_FRAMES, DIM, FPS = 20, 11720, 28, 30


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_preflight(root: Path) -> dict:
    """Require the exact sponsor metadata, feature order and public card bytes."""
    root = root.resolve(strict=True)
    info_path, card_path = root / "meta/info.json", root / "README.md"
    if not info_path.is_file() or not card_path.is_file():
        raise ValueError("missing LeRobot v3 metadata or public sponsor dataset card")
    if digest_file(info_path) != INFO_SHA256 or digest_file(card_path) != README_SHA256:
        raise ValueError("dataset metadata/card differs from sponsor's pinned revision")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    required = {"codebase_version": "v3.0", "total_episodes": N_EPISODES,
                "total_frames": N_FRAMES, "fps": FPS}
    if any(info.get(key) != value for key, value in required.items()):
        raise ValueError("unexpected LeRobot metadata episode/frame/fps/version")
    schema = info.get("features", {})
    for name in FEATURES:
        item = schema.get(name, {})
        if item.get("dtype") != "float32" or item.get("shape") != [DIM]:
            raise ValueError(f"unexpected {name} feature shape or dtype")
    state_names = schema[FEATURES[0]].get("names")
    action_names = schema[FEATURES[1]].get("names")
    if (not isinstance(state_names, list) or len(state_names) != 1
            or not isinstance(state_names[0], list) or len(state_names[0]) != DIM
            or len(set(state_names[0])) != DIM or state_names != action_names):
        raise ValueError("action/state joint order cannot be matched exactly")
    paths = sorted((root / "data").glob("chunk-*/*.parquet"))
    if not paths or any(path.is_symlink() for path in paths):
        raise ValueError("missing or symlinked data Parquet files")
    hashes = {str(path.relative_to(root)): digest_file(path) for path in paths}
    return {"repo_id": DATASET_REPO, "revision": DATASET_COMMIT,
            "info_sha256": INFO_SHA256, "card_sha256": README_SHA256,
            "parquet_sha256": hashes, "joint_names": state_names[0],
            "source_attestation": "metadata bytes verified; Parquet bytes hashed; HF revision must be pinned at download"}


def episode_split(n: int = N_EPISODES, seed: int = SPLIT_SEED) -> dict[str, list[int]]:
    if n < 10 or isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("need >=10 episodes and integer split seed")
    ids = list(range(n))
    random.Random(seed).shuffle(ids)
    n_holdout = max(2, n // 5)
    return {"train": sorted(ids[2 * n_holdout:]),
            "validation": sorted(ids[n_holdout:2 * n_holdout]),
            "test": sorted(ids[:n_holdout])}


def read_parquet_vectors(root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required: pip install pyarrow") from exc
    fields = ["episode_index", "frame_index", *FEATURES]
    episodes, frames, states, actions = [], [], [], []
    for path in sorted((root / "data").glob("chunk-*/*.parquet")):
        table = pq.read_table(path, columns=fields)
        episodes.extend(table["episode_index"].to_pylist())
        frames.extend(table["frame_index"].to_pylist())
        states.extend(table[FEATURES[0]].to_pylist())
        actions.extend(table[FEATURES[1]].to_pylist())
    episode = np.asarray(episodes, dtype=np.int64)
    frame = np.asarray(frames, dtype=np.int64)
    state = np.asarray(states, dtype=np.float32)
    action = np.asarray(actions, dtype=np.float32)
    validate_vectors(episode, frame, state, action)
    return episode, frame, state, action


def validate_vectors(episode, frame, state, action) -> None:
    if (episode.shape != (N_FRAMES,) or frame.shape != (N_FRAMES,)
            or state.shape != (N_FRAMES, DIM) or action.shape != (N_FRAMES, DIM)):
        raise ValueError("unexpected frame count or state/action dimensions")
    if not np.isfinite(state).all() or not np.isfinite(action).all():
        raise ValueError("nonfinite state/action values")
    if (set(np.unique(episode).tolist()) != set(range(N_EPISODES))
            or np.any(frame < 0)):
        raise ValueError("unexpected episode identities or frame indices")
    for ep in range(N_EPISODES):
        within = frame[episode == ep]
        if not len(within) or not np.array_equal(np.sort(within), np.arange(len(within))):
            raise ValueError(f"episode {ep}: duplicate/missing frame index")
    if len(set(zip(episode.tolist(), frame.tolist()))) != N_FRAMES:
        raise ValueError("duplicate (episode, frame) keys")


def grouped_metrics(pred: np.ndarray, truth: np.ndarray, episode: np.ndarray) -> dict:
    if pred.shape != truth.shape or pred.ndim != 2 or pred.shape[1] != DIM:
        raise ValueError("prediction/truth shape mismatch")
    if not np.isfinite(pred).all():
        raise ValueError("nonfinite predictions")
    diffs = np.abs(pred.astype(np.float64) - truth.astype(np.float64))
    per_episode = {str(int(ep)): float(diffs[episode == ep].mean())
                   for ep in np.unique(episode)}
    return {"mae_rad": float(diffs.mean()),
            "rmse_rad": float(np.sqrt(np.mean(diffs ** 2))),
            "episode_macro_mae_rad": float(np.mean(list(per_episode.values()))),
            "per_episode_mae_rad": per_episode}


def previous_action_oracle(action: np.ndarray, episode: np.ndarray,
                           frame: np.ndarray, default: np.ndarray) -> np.ndarray:
    """Teacher-forced action(t-1) is an *oracle* diagnostic, not a deployable policy."""
    indexed = {(int(e), int(f)): i for i, (e, f) in enumerate(zip(episode, frame))}
    result = np.repeat(default[None, :], len(action), axis=0)
    for i, (e, f) in enumerate(zip(episode, frame)):
        prior = indexed.get((int(e), int(f) - 1))
        if prior is not None:
            result[i] = action[prior]
    return result


def nearest_state_actions(train_x, train_y, eval_x, batch_size=128) -> np.ndarray:
    """Deterministic 1-NN using only training states; ties use stable input order."""
    if len(train_x) == 0:
        raise ValueError("empty training set")
    centre = train_x.mean(axis=0, dtype=np.float64)
    scale = train_x.std(axis=0, dtype=np.float64) + 1e-6
    source = (train_x.astype(np.float64) - centre) / scale
    queries = (eval_x.astype(np.float64) - centre) / scale
    source_sq = np.square(source).sum(axis=1)
    out = []
    for offset in range(0, len(queries), batch_size):
        q = queries[offset:offset + batch_size]
        distances = np.square(q).sum(axis=1)[:, None] + source_sq[None, :] - 2 * q @ source.T
        out.append(train_y[np.argmin(distances, axis=1)])
    return np.concatenate(out, axis=0)


def ridge_fit(train_x, train_y, alpha: float):
    """Train-only normalization, L2 regularization and an unpenalized intercept."""
    if not math.isfinite(alpha) or alpha <= 0:
        raise ValueError("alpha must be finite/positive")
    xm = train_x.mean(axis=0, dtype=np.float64)
    xs = train_x.std(axis=0, dtype=np.float64) + 1e-6
    ym = train_y.mean(axis=0, dtype=np.float64)
    x = (train_x.astype(np.float64) - xm) / xs
    y = train_y.astype(np.float64) - ym
    matrix = x.T @ x + alpha * np.eye(x.shape[1])
    weights = np.linalg.solve(matrix, x.T @ y)
    return weights, xm, xs, ym


def ridge_predict(model, features):
    w, xm, xs, ym = model
    return ((features.astype(np.float64) - xm) / xs @ w + ym).astype(np.float32)


def run_study(root: Path, output: Path, split_seed: int = SPLIT_SEED) -> dict:
    provenance = dataset_preflight(root)
    episode, frame, state, action = read_parquet_vectors(root)
    split = episode_split(seed=split_seed)
    masks = {name: np.isin(episode, ids) for name, ids in split.items()}
    if any(not mask.any() for mask in masks.values()):
        raise ValueError("empty episode partition")
    train_x, train_y = state[masks["train"]], action[masks["train"]]
    val_x, val_y, val_ep = state[masks["validation"]], action[masks["validation"]], episode[masks["validation"]]
    test_x, test_y, test_ep, test_frame = (state[masks["test"]], action[masks["test"]],
                                          episode[masks["test"]], frame[masks["test"]])
    mean_action = train_y.mean(axis=0)
    validation = {}
    models = {}
    for alpha in (0.1, 1.0, 10.0, 100.0, 1000.0):
        model = ridge_fit(train_x, train_y, alpha)
        score = grouped_metrics(ridge_predict(model, val_x), val_y, val_ep)["episode_macro_mae_rad"]
        validation[str(alpha)] = score
        models[alpha] = model
    selected = min(models, key=lambda a: (validation[str(a)], a))
    candidate_predictions = {
        "train_mean": np.repeat(mean_action[None, :], len(test_y), axis=0),
        "state_identity": test_x,
        "nearest_state_1nn": nearest_state_actions(train_x, train_y, test_x),
        "ridge": ridge_predict(models[selected], test_x),
        "oracle_previous_action_NOT_DEPLOYABLE": previous_action_oracle(test_y, test_ep, test_frame, mean_action),
    }
    metrics = {name: grouped_metrics(prediction, test_y, test_ep)
               for name, prediction in candidate_predictions.items()}
    best_reference = min(metrics[x]["episode_macro_mae_rad"]
                         for x in ("train_mean", "state_identity", "nearest_state_1nn"))
    ridge_score = metrics["ridge"]["episode_macro_mae_rad"]
    rel_gain = (best_reference - ridge_score) / best_reference if best_reference > 0 else 0.0
    report = {"work_id": "VERDA-AALTO-ROKOKO-20261114",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "dataset": provenance, "upstream_commit": UPSTREAM_COMMIT,
              "code_sha256": digest_file(Path(__file__).resolve()),
              "split_seed": split_seed, "split": split,
              "frame_counts": {name: int(mask.sum()) for name, mask in masks.items()},
              "train_only_normalization": True,
              "selection": {"ridge_alpha": selected, "validation_macro_mae_by_alpha": validation},
              "metrics": metrics, "ridge_relative_gain_over_best_deployable_baseline": rel_gain,
              "limitations": ["Offline open-loop joint-action prediction only; no 3D perception or robot/simulator success.",
                              "Four heldout demonstration episodes; suboptimal actions; per-episode uncertainty is substantial.",
                              "Oracle previous-action uses heldout ground truth and is NOT deployable.",
                              "Source metadata hashes and Parquet hashes are not a signature or physical custody proof."]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    np.savez_compressed(output / "ridge_weights.npz", weights=models[selected][0],
                        state_mean=models[selected][1], state_scale=models[selected][2],
                        action_mean=models[selected][3])
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-root", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path, help="new, non-existing output directory")
    p.add_argument("--split-seed", type=int, default=SPLIT_SEED)
    args = p.parse_args(argv)
    try:
        report = run_study(args.dataset_root, args.output, args.split_seed)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "offline_evaluation_only", "output": str(args.output),
                      "test_episode_ids": report["split"]["test"],
                      "macro_mae": {k: v["episode_macro_mae_rad"] for k, v in report["metrics"].items()},
                      "ridge_relative_gain": report["ridge_relative_gain_over_best_deployable_baseline"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
