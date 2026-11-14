#!/usr/bin/env python3
"""Offline research candidate retrieval and R5 evidence reconciliation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

from contract import ContractError, advisory_fields, strict_json_loads

R3_HELPER_SHA256 = "933de9d32de9782e4b399ef7f5d0a87c94e8389dd65f7ed1eae96a541f0250b1"
MAX_FEATURE_BYTES = 256 * 1024 * 1024


def load_feature_bundle(path):
    """Bound ZIP members and array shapes before NumPy materializes their data."""
    import numpy as np
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FEATURE_BYTES:
        raise ContractError("feature_file", "Expected a regular feature NPZ of at most 256 MiB")
    raw = path.read_bytes()
    if len(raw) > MAX_FEATURE_BYTES:
        raise ContractError("feature_file", "Feature NPZ exceeds 256 MiB")
    import io
    required = {"gallery_features", "gallery_ids", "query_features", "query_ids"}
    allowed = required | {"a", "b"}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            keys = {name[:-4] for name in names if name.endswith(".npy")}
            if (len(names) != len(set(names)) or len(keys) != len(names) or
                    not required <= keys or not keys <= allowed or
                    (("a" in keys) != ("b" in keys))):
                raise ContractError("feature_members", "NPZ requires feature/ID arrays and optionally both a and b")
            if sum(info.file_size for info in infos) > MAX_FEATURE_BYTES:
                raise ContractError("feature_expansion", "Expanded feature NPZ exceeds 256 MiB")
            for info in infos:
                key = info.filename[:-4]
                with archive.open(info) as member:
                    version = np.lib.format.read_magic(member)
                    if version == (1, 0):
                        shape, _, dtype = np.lib.format.read_array_header_1_0(member)
                    elif version == (2, 0):
                        shape, _, dtype = np.lib.format.read_array_header_2_0(member)
                    else:
                        raise ContractError("feature_format", "Expected NPY version 1 or 2")
                    if dtype.hasobject or dtype.fields is not None:
                        raise ContractError("feature_dtype", "Object and structured arrays are not supported")
                    limit = 50_000 if key.startswith("gallery") else 4_096
                    if key in ("gallery_features", "query_features"):
                        valid = (len(shape) == 2 and 1 <= shape[0] <= limit and
                                 shape[1] == 768 and dtype.kind == "f" and dtype.itemsize in (4, 8))
                    elif key in ("gallery_ids", "query_ids"):
                        valid = (len(shape) == 1 and 1 <= shape[0] <= limit and
                                 dtype.kind == "U" and 4 <= dtype.itemsize <= 1024)
                    else:
                        valid = shape == ((768, 64) if key == "a" else (64, 768)) and dtype == np.dtype("float32")
                    if not valid:
                        raise ContractError("feature_shape", f"Invalid bounded shape or dtype for {key}")
                    count = 1
                    for extent in shape:
                        count *= extent
                    if member.tell() + count * dtype.itemsize != info.file_size:
                        raise ContractError("feature_length", "NPY header and member byte length disagree")
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in sorted(keys)}
    except ContractError:
        raise
    except (ValueError, OSError, EOFError, zipfile.BadZipFile) as exc:
        raise ContractError("feature_archive", "Invalid bounded feature NPZ") from exc
    return arrays, hashlib.sha256(raw).hexdigest()


def load_r3_selection(training_root):
    """Reuse the unchanged R3 loader, including selected-checkpoint byte hashing."""
    root = Path(training_root).resolve()
    path = root / "selection.json"
    if path.is_symlink():
        raise ContractError("selection_path", "Selection must be a regular file")
    if not path.is_file() or path.stat().st_size > 2_097_152:
        raise ContractError("selection_path", "Selection must be at most 2 MiB")
    raw = path.read_bytes()
    if len(raw) > 2_097_152:
        raise ContractError("selection_path", "Selection must be at most 2 MiB")
    selection = strict_json_loads(raw)
    if not isinstance(selection, dict):
        raise ContractError("r3_selection", "R3 selection must be a JSON object")
    helper = Path(__file__).resolve().parent.parent / "retrieval-r3" / "visual_adapter.py"
    helper_raw = helper.read_bytes() if helper.is_file() else b""
    if hashlib.sha256(helper_raw).hexdigest() != R3_HELPER_SHA256:
        raise ContractError("r3_source", "Expected the pinned repository R3 visual adapter helper")
    name = "meta_acceleration_pinned_r3_visual"
    spec = importlib.util.spec_from_file_location(name, helper)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(helper_raw, str(helper), "exec"), module.__dict__)
    try:
        weights = module.load_selected(selection, root)
    except ModuleNotFoundError as exc:
        raise ContractError("r3_dependency", "Install R3's pinned safetensors==0.6.2 for checkpoint loading") from exc
    except Exception as exc:
        # This boundary also translates the optional Rust safetensors parser's
        # own exception class; malformed artifacts cannot escape as a traceback.
        raise ContractError("r3_selection", "R3 selection or checkpoint validation failed") from exc
    return weights, {"selection_sha256": hashlib.sha256(raw).hexdigest(),
                     "checkpoint_sha256": selection["primary"]["checkpoint_sha256"],
                     "loader_sha256": R3_HELPER_SHA256, "qualification_evaluated": False}


def write_new_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def run(args):
    if args.command == "search":
        from candidate_index import PreparedCandidateIndex
        arrays, digest = load_feature_bundle(args.features)
        weights = {key: arrays[key] for key in ("a", "b")} if "a" in arrays else None
        selection = None
        if args.r3_training_root:
            if weights is not None:
                raise ContractError("ambiguous_adapter", "Choose NPZ weights or an R3 training root")
            weights, selection = load_r3_selection(args.r3_training_root)
        index = PreparedCandidateIndex(arrays["gallery_features"], arrays["gallery_ids"].tolist(),
                                       **(weights or {}))
        result = index.search(arrays["query_features"], arrays["query_ids"].tolist(),
                              top_k=args.top_k, batch_size=args.batch_size)
        result["feature_npz_sha256"] = digest
        result["r3_selection"] = selection
    else:
        from reconcile import reconcile_run
        result = reconcile_run(args.run_dir, args.cases, args.expected_source_commit, args.expected_model)
    write_new_json(args.output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="Rank precomputed embeddings without model calls")
    search.add_argument("--features", type=Path, required=True)
    search.add_argument("--r3-training-root", type=Path)
    search.add_argument("--top-k", type=int, default=32)
    search.add_argument("--batch-size", type=int, default=16)
    reconcile = sub.add_parser("reconcile", help="Check existing R5 specialist artifacts")
    reconcile.add_argument("--run-dir", type=Path, required=True)
    reconcile.add_argument("--cases", type=Path, required=True)
    reconcile.add_argument("--expected-source-commit", required=True)
    reconcile.add_argument("--expected-model", required=True)
    for command in (search, reconcile):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (ContractError, OSError) as exc:
        code = exc.code if isinstance(exc, ContractError) else "filesystem_error"
        print(json.dumps({**advisory_fields("meta.retrieval-acceleration.error"),
                          "code": code, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    print(json.dumps({"kind": result["kind"], "status": result.get("status", "RANKED"),
                      "output": str(args.output), "qualification": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
