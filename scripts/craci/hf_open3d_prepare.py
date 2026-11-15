#!/usr/bin/env python3
"""Fetch pinned open 3D/video data and prepare bounded, group-labelled features."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.parse
import urllib.request

import numpy as np
import pyarrow.parquet as pq

HOSTS = {"huggingface.co", "us.aws.cdn.hf.co", "cas-bridge.xethub.hf.co"}
MAX_FEATURE_BYTES = 19 * 1024 * 1024


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS:
            raise ValueError("Unexpected data redirect host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirect)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def fetch(dataset, record, scratch, byte_limit=None):
    path = record["path"]
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("invalid source path")
    expected = record["sha256"]
    size = record.get("bytes")
    if len(expected) != 64 or (size is not None and not 0 < size < 100_000_000):
        raise ValueError("unbounded source")
    destination = scratch / (expected + Path(path).suffix)
    if destination.exists():
        if sha(destination) != expected or (size is not None and destination.stat().st_size != size):
            raise ValueError("cached source differs from pinned source")
        return destination
    repo, revision = dataset["repo"], dataset["revision"]
    url = ("https://huggingface.co/datasets/" + repo + "/resolve/" + revision + "/"
           + urllib.parse.quote(path, safe="/"))
    limit = size if size is not None else byte_limit
    if not limit:
        raise ValueError("source byte bound required")
    request = urllib.request.Request(url, headers={"User-Agent": "Junction-open3d-research/1.0"})
    fd, tmp_name = tempfile.mkstemp(prefix="open3d-", dir=scratch)
    tmp = Path(tmp_name)
    digest = hashlib.sha256()
    count = 0
    try:
        with os.fdopen(fd, "wb") as output, OPENER.open(request, timeout=120) as response:
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > limit:
                    raise ValueError("source exceeded byte bound")
                digest.update(block)
                output.write(block)
        if digest.hexdigest() != expected or (size is not None and count != size):
            raise ValueError("source hash or size mismatch")
        tmp.replace(destination)
    finally:
        tmp.unlink(missing_ok=True)
    return destination


def decode_video(path):
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "2",
        "-i", str(path), "-vf", "scale=32:32:flags=area", "-vsync", "0",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, check=True, timeout=240)
    if not result.stdout or len(result.stdout) % 1024:
        raise ValueError("invalid decoded video")
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape((-1, 32 * 32))


def validate_manifest(manifest):
    if manifest.get("version") != 1:
        raise ValueError("manifest version")
    expected = {
        "v2d": ("nvidia/video_to_data_challenge", "5f68335f3acc802033d1e80728c1633197521de8"),
        "g1": ("exptech/g1-moves", "895d064b2385725e6aabf540461c219afc3e0916"),
        "robo": ("BitRobot/robomocap", "20adb80c474c163fe451b5c4f994b665b3234024"),
    }
    for key, (repo, revision) in expected.items():
        entry = manifest["licenses"][key]
        if (entry["repo"], entry["revision"], entry["license"]) != (repo, revision, "CC-BY-4.0"):
            raise ValueError("unapproved source or license")
    if (len(manifest["v2d"]), len(manifest["g1"]), len(manifest["robo"])) != (20, 30, 20):
        raise ValueError("dataset selection changed")
    if len({row["participant_group"] for row in manifest["robo"]}) < 5:
        raise ValueError("insufficient participant groups")


def video_examples(row, files):
    table = pq.read_table(files[row["parquet"]["sha256"]])
    values = table.to_pylist()
    frames = decode_video(files[row["video"]["sha256"]])
    if len(frames) != len(values) or len(values) < 12:
        raise ValueError("video and physical data are not frame aligned")
    names = sorted(item["name"] for item in values[0]["observation.objects"])
    if not names:
        raise ValueError("no tracked object")
    name = names[0]
    X, Y, baseline = [], [], []
    for i in range(1, len(values) - 4, 2):
        current = {x["name"]: x for x in values[i]["observation.objects"]}.get(name)
        future = {x["name"]: x for x in values[i + 4]["observation.objects"]}.get(name)
        if not current or not future or not current["visible"] or not future["visible"]:
            continue
        target = np.asarray(future["pose"][:3], dtype=np.float32) - np.asarray(
            current["pose"][:3], dtype=np.float32)
        if not np.isfinite(target).all():
            raise ValueError("non-finite video target")
        now = frames[i].astype(np.float32) / 255.0
        previous = frames[i - 1].astype(np.float32) / 255.0
        X.append(np.concatenate((now, now - previous)))
        Y.append(target)
        baseline.append(np.zeros(3, dtype=np.float32))
    return X, Y, baseline, str(values[0]["task_index"])


def motion_examples(series, valid, lag, horizon, stride, max_samples):
    if series.ndim != 2 or not np.isfinite(series[valid]).all():
        raise ValueError("invalid motion data")
    indices = np.arange(lag, len(series) - horizon, stride)
    indices = indices[valid[indices] & valid[indices - lag] & valid[indices + horizon]]
    if len(indices) > max_samples:
        indices = indices[np.linspace(0, len(indices) - 1, max_samples, dtype=int)]
    current = series[indices]
    delta = current - series[indices - lag]
    return (np.concatenate((current, delta), axis=1), series[indices + horizon] - current,
            delta * (horizon / lag))


def prepare(manifest_path, output, scratch):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    scratch.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=False)
    requests = []
    for row in manifest["v2d"]:
        requests.extend(("v2d", row[key], None) for key in ("parquet", "video"))
    requests.extend(("g1", row, None) for row in manifest["g1"])
    requests.append(("g1", manifest["g1_preview"], None))
    for row in manifest["robo"]:
        requests.append(("robo", row["motion"], None))
        requests.append(("robo", {"path": row["meta_path"], "sha256": row["meta_sha256"]}, 100_000))
    requests.append(("robo", manifest["robo_preview"], None))

    def load(request):
        dataset, record, bound = request
        return record["sha256"], fetch(manifest["licenses"][dataset], record, scratch, bound)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        files = dict(executor.map(load, requests))
    # Explicitly verify the two auxiliary preview files can be decoded. They do
    # not enter the visual or motion model training data.
    for key in ("g1_preview", "robo_preview"):
        if len(decode_video(files[manifest[key]["sha256"]])) < 1:
            raise ValueError("preview video is empty")

    line_data = {"v2d": [], "g1": [], "robo": []}
    for row in manifest["v2d"]:
        X, Y, baseline, group = video_examples(row, files)
        line_data["v2d"].append((X, Y, baseline, group))
    for row in manifest["g1"]:
        with np.load(files[row["sha256"]], allow_pickle=False) as source:
            series = np.asarray(source["joint_pos"], dtype=np.float32)
            if series.ndim != 2 or series.shape[1] != 29 or float(source["fps"][0]) != 60.0:
                raise ValueError("unexpected G1 motion dimensions")
        X, Y, baseline = motion_examples(series, np.ones(len(series), dtype=bool), 3, 6, 4, 500)
        line_data["g1"].append((X, Y, baseline, row["group"]))
    joints = None
    for row in manifest["robo"]:
        meta = json.loads(files[row["meta_sha256"]].read_text(encoding="utf-8"))
        participant = hashlib.sha256(meta["participant"].encode()).hexdigest()[:16]
        if participant != row["participant_group"] or meta["sanity"]["status"] != row["quality"]:
            raise ValueError("participant or quality changed")
        with np.load(files[row["motion"]["sha256"]], allow_pickle=False) as source:
            positions = np.asarray(source["positions_m"], dtype=np.float32)
            valid = np.asarray(source["valid"], dtype=bool)
            names = source["joint_names"].tolist()
            if (positions.ndim != 3 or positions.shape[1:] != (23, 3)
                    or len(valid) != len(positions) or names[0] != "Hips"
                    or float(source["mocap_rate_hz"]) != 120.0):
                raise ValueError("unexpected human motion dimensions")
            if joints is not None and names != joints:
                raise ValueError("inconsistent joint layout")
            joints = names
            series = (positions[:, 1:, :] - positions[:, :1, :]).reshape(len(positions), -1)
        X, Y, baseline = motion_examples(series, valid, 6, 12, 15, 600)
        line_data["robo"].append((X, Y, baseline, row["participant_group"]))

    results = {}
    for line, groups in line_data.items():
        if any(len(X) < 10 for X, _, _, _ in groups):
            raise ValueError("too few valid examples in a group")
        group_names = sorted({group for _, _, _, group in groups})
        if len(group_names) < 5:
            raise ValueError("group split cannot have five folds")
        X = np.concatenate([np.asarray(item[0], dtype=np.float32) for item in groups])
        Y = np.concatenate([np.asarray(item[1], dtype=np.float32) for item in groups])
        baseline = np.concatenate([np.asarray(item[2], dtype=np.float32) for item in groups])
        G = np.concatenate([np.full(len(item[0]), group_names.index(item[3]), dtype=np.int32)
                            for item in groups])
        if not (len(X) == len(Y) == len(baseline) == len(G)) or not np.isfinite(X).all():
            raise ValueError("feature alignment invalid")
        target = output / (line + ".npz")
        np.savez_compressed(target, X=X, Y=Y, baseline=baseline, groups=G)
        if target.stat().st_size > MAX_FEATURE_BYTES:
            raise ValueError("derived features exceed bounded collector size")
        results[line] = {"examples": len(X), "groups": len(group_names),
                         "feature_dimensions": X.shape[1], "target_dimensions": Y.shape[1],
                         "bytes": target.stat().st_size, "sha256": sha(target)}
    report = {"datasets": manifest["licenses"], "verified_files": len(files),
              "selection": manifest["selection"], "lines": results,
              "privacy": "No original video, raw motion, participant names or metadata in result.",
              "promotion_authorized": False}
    (output / "preparation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.manifest, args.out, args.scratch), sort_keys=True))
