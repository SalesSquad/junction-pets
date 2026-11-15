"""Read original, byte-verified CRACI V10 TRAIN-only MuJoCo evidence.

No provider/network calls, no edits to historical artifacts, no hidden physics
state at policy inference.  Original V10 packer's exact ZIP parts are restored
in memory, checked against immutable source-produced manifest and independent
replay files, and the full 800 option traces are structurally rechecked.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


WORK_ID = "CRACI-V11-LEARNING-20261114"
V10_SOURCE_SHA = "9cc583d3f0f24484b79c1929ba875c7a3b667806"
V10_HARNESS_SHA = "a64e6fcc73a1d47485fe052990e31c9d9e45100f"
V10_RUN = 43649224059
V10_RECEIPT_RUN = "craci.43649224059.1.49e1693ab133a3e9"
V10_WEIGHTS_SHA = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
V10_RAW = {
    "training.json": "103091f37e1b7d46937ea002845dda05f08391f4580f0aa7c181722d78b118af",
    "full_transitions.jsonl.gz": "739c30a13ecacdecd404774fc9dadd887944f32df5cef14cfd2758a639460419",
}
V10_PROOFS = {
    "receipt.json": "3dadd442aefb2b5be66793f64c5bc35102da72cafebba6688bfa1517bdd34cca",
    "manifest.json": "456e8d0bc2349761e002fdc3ea52032b4ee00f489426df0505c8f6136fdbaa16",
    "retention-manifest.json": "bf65d45955e83eb217b5d7a06247e6477df11f3c7704aea76cf1d92f30b87bdb",
    "independent-qualification.json": "1678dca9b573c7c6fbacbc4f1eedab916914d324977f87dbf0dc9c3c9001b3d0",
    "independent-positive-replay.json": "71b53d96e11f470f16c182d39fdd8a2c987ae30c041bd7bddd9498bf2f825e4c",
    "independent-clear-goal-replay.json": "e78ef0771371659cc98c10a55c9a33f65e7c3480c9f6b57cd527bd806cad6f26",
    "paired-readout.json": "8e3461c33c79a0b9328adf5b86719f166000f1e931983d3b9c2903ab71f14f0e",
}
PACKER_BLOB = "49099040f60962f9d33b66b5911c88d182f28eaf"
EXPECTED_STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "frozen_v8", "v10_loss_informed")


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def checked_bytes(path: Path, expected: str) -> bytes:
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
            "V11_ORIGINAL_PROOF_FILE_MISSING_OR_UNSAFE")
    data = path.read_bytes()
    require(sha(data) == expected, "V11_ORIGINAL_PROOF_SHA_MISMATCH")
    return data


def _load_packer(source_root: Path):
    path = source_root / "scripts/craci/rokoko-mujoco-v10-retain-evidence.py"
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(blob == PACKER_BLOB, "V11_FROZEN_V10_PACKER_BLOB_CHANGED")
    spec = importlib.util.spec_from_file_location("v11_frozen_v10_evidence_packer", path)
    require(spec is not None and spec.loader is not None,
            "V11_FROZEN_V10_PACKER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_retained_raw(archive_dir: Path, receipt_path: Path, source_root: Path):
    archive_dir = archive_dir.resolve(strict=True)
    require(archive_dir.is_dir() and not archive_dir.is_symlink(),
            "V11_ARCHIVE_SOURCE_UNSAFE")
    proofs = {}
    for name, digest in V10_PROOFS.items():
        path = receipt_path if name == "receipt.json" else archive_dir / name
        proofs[name] = json.loads(checked_bytes(path, digest))
    manifest, qualified, retention = (proofs[name] for name in
                                     ("manifest.json", "independent-qualification.json",
                                      "retention-manifest.json"))
    receipt = proofs["receipt.json"]
    require(receipt.get("binding", {}).get("runId") == V10_RECEIPT_RUN and
            receipt.get("binding", {}).get("sourceSha") == V10_SOURCE_SHA and
            receipt.get("binding", {}).get("harnessSha") == V10_HARNESS_SHA and
            receipt.get("binding", {}).get("workload") == "rokoko-mujoco-v10-prospective" and
            receipt.get("jobStatus") == "success" and
            receipt.get("status") == "succeeded" and
            receipt.get("sourceVerified") is True and
            receipt.get("harnessVerified") is True and
            receipt.get("evidenceLevel") == "source-reported" and
            receipt.get("command", {}).get("exitCode") == 0 and
            receipt.get("evidenceUrl") == (
                f"https://github.com/SalesSquad/junction-pets/actions/runs/{V10_RUN}/attempts/1") and
            manifest.get("executed_head") == V10_SOURCE_SHA and
            manifest.get("candidate_v10_weights_file_sha256") == V10_WEIGHTS_SHA and
            manifest.get("train_only") is True and
            manifest.get("promotion_authorized") is False and
            manifest.get("dev_cal_test_ood_opened") is False and
            manifest.get("file_sha256") == V10_RAW and
            qualified.get("exact_source_sha") == V10_SOURCE_SHA and
            qualified.get("decision") == "valid_source_bound_five_way_train_only_evidence" and
            qualified.get("experiment_complete") is True and
            qualified.get("trials") == 800 and
            qualified.get("actual_real_option_transitions") == 38569 and
            qualified.get("independent_full_trace_public_mask_replay") is True and
            qualified.get("independentHoldout") is False and
            qualified.get("promotion_authorized") is False and
            qualified.get("dev_cal_test_ood_opened") is False and
            proofs["independent-clear-goal-replay.json"].get("claim_verified") is True and
            proofs["independent-positive-replay.json"].get("claim_verified") is True,
            "V11_SOURCE_REPORTED_V10_INCOMPLETE_OR_UNQUALIFIED")
    packer = _load_packer(source_root)
    packer.verify_archive_parts(archive_dir, retention)
    raw = {}
    for file in retention["sources"]:
        parts = []
        for part in file["parts"]:
            with zipfile.ZipFile(archive_dir / part["archive"]) as archive:
                require(archive.namelist() == [part["entry"]], "V11_ARCHIVE_ENTRY_CHANGED")
                parts.append(archive.read(part["entry"]))
        raw[file["name"]] = b"".join(parts)
        require(sha(raw[file["name"]]) == V10_RAW[file["name"]],
                "V11_RECONSTRUCTED_ORIGINAL_BYTES_CHANGED")
    training = json.loads(raw["training.json"])
    full = [json.loads(line) for line in gzip.decompress(raw["full_transitions.jsonl.gz"]).splitlines()]
    require(training.get("actual_trials") == 800 and
            training.get("actual_transition_count") == 38569 and
            tuple(training.get("strategies", ())) == EXPECTED_STRATEGIES and
            training.get("training_only") is True and
            training.get("no_dev_evaluation") is True and
            len(training.get("trials", ())) == len(full) == 800,
            "V11_ORIGINAL_REAL_TRAIN_SHAPE_INVALID")
    rows = {(r["seed"], r["strategy"]): r for r in training["trials"]}
    require(len(rows) == 800 and len({r["seed"] for r in training["trials"]}) == 160,
            "V11_INCOMPLETE_PAIRED_SOURCE_TRIALS")
    trace_by_key = {}
    total = 0
    for item in full:
        key = (item["seed"], item["strategy"])
        require(key in rows and key not in trace_by_key and
                len(item["transitions"]) == rows[key]["full_transition_count"],
                "V11_ORIGINAL_TRANSITION_EPISODE_MISMATCH")
        for event in item["transitions"]:
            mask, action = event["mask"], event["action"]
            require(len(mask) == 7 and all(v in (0, 1) for v in mask) and
                    isinstance(action, int) and 0 <= action < 7 and mask[action] == 1 and
                    len(event["observation"]) == len(event["next_observation"]) == 18,
                    "V11_ORIGINAL_TRANSITION_PUBLIC_LEGAL_MASK_INVALID")
        trace_by_key[key] = item["transitions"]
        total += len(item["transitions"])
    require(total == 38569 and len(trace_by_key) == 800,
            "V11_FULL_ORIGINAL_TRACE_COUNT_MISMATCH")
    return training, rows, trace_by_key, proofs
