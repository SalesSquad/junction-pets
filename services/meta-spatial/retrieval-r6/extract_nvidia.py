#!/usr/bin/env python3
"""Pinned public NVIDIA OCR + RADIO feature extraction on an admitted CUDA host.

No labels, credentials, training or quality claims enter this process. The caller
admits the GPU and installs the pinned OCR package (including its CUDA extension).
Downloads are public, revision-bound and never use an implicit Hugging Face token.
Run outputs are append-only; a failed or prefix-only run is never a complete run.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import numbers
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

OCR_ID = "nvidia/nemotron-ocr-v2"
OCR_REV = "0e83e83f17943524b90afa6c0fd82ac2bc1a40ca"
RADIO_ID = "nvidia/C-RADIOv4-SO400M"
RADIO_REV = "c0457f5dc26ca145f954cd4fc5bb6114e5705ad8"
SHA = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
PUBLIC_PATH = re.compile(r"source/images/small/[a-z0-9]{2}/[a-z0-9]+\.jpg")
PUBLIC_BASE = "https://amazon-berkeley-objects.s3.amazonaws.com/"
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_IMAGES = 20000
OCR_REQUIRED = ("detector.pth", "recognizer.pth", "relational.pth", "charset.txt", "model_config.json")
DOCS = {
    "ocr": "https://huggingface.co/nvidia/nemotron-ocr-v2",
    "ocr_package": "https://huggingface.co/nvidia/nemotron-ocr-v2/blob/main/nemotron-ocr/pyproject.toml",
    "radio": "https://huggingface.co/nvidia/C-RADIOv4-SO400M",
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def file_sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "regular_file_required:" + str(path))
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def append_json(stream, value):
    stream.write(canonical(value).decode() + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def raw_json_value(value):
    """Preserve NumPy scalar observations, including explicit invalid values."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        return number if math.isfinite(number) else {"nonfinite_number": str(number)}
    if isinstance(value, dict):
        require(all(isinstance(key, str) for key in value), "raw_ocr_string_keys_required")
        return {key: raw_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [raw_json_value(item) for item in value]
    if hasattr(value, "tolist"):
        return raw_json_value(value.tolist())
    raise ValueError("unsupported_raw_ocr_value_type:" + type(value).__name__)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key:" + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("nonfinite_json:" + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def load_manifest(path, source_commit):
    require(COMMIT.fullmatch(source_commit) is not None, "source_commit_required")
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "regular_manifest_required")
    require(path.stat().st_size <= MAX_MANIFEST_BYTES, "manifest_too_large")
    raw = path.read_bytes()
    obj = strict_json(raw)
    require(type(obj) is dict and set(obj) == {"schema", "source_commit", "dataset_sha256", "images"},
            "unexpected_manifest_fields")
    require(obj["schema"] == "meta_r6_images_v1", "unexpected_manifest_schema")
    require(obj["source_commit"] == source_commit, "manifest_source_commit_mismatch")
    require(type(obj["dataset_sha256"]) is str and SHA.fullmatch(obj["dataset_sha256"]),
            "invalid_dataset_sha256")
    require(type(obj["images"]) is list and 0 < len(obj["images"]) <= MAX_IMAGES,
            "bounded_nonempty_images_required")
    ids, paths = set(), set()
    for row in obj["images"]:
        require(type(row) is dict and set(row) == {"image_id", "sha256", "path", "url"},
                "unexpected_image_fields")
        require(type(row["sha256"]) is str and SHA.fullmatch(row["sha256"]), "invalid_image_sha256")
        require(row["image_id"] == "img-" + row["sha256"], "invalid_image_id")
        require(type(row["path"]) is str and PUBLIC_PATH.fullmatch(row["path"]), "invalid_public_image_path")
        require(row["url"] == PUBLIC_BASE + row["path"].removeprefix("source/"), "invalid_public_image_url")
        require(row["image_id"] not in ids and row["path"] not in paths, "duplicate_image")
        ids.add(row["image_id"])
        paths.add(row["path"])
    return obj, digest(raw)


def safe_root(path):
    path = Path(path)
    require(path.is_absolute(), "absolute_root_required")
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), "root_symlink_refused")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve(strict=True)


def image_path(root, relative):
    require(PUBLIC_PATH.fullmatch(relative) is not None, "invalid_public_image_path")
    path = root / relative
    for parent in [path, *path.parents]:
        if parent == root.parent:
            break
        require(not parent.is_symlink(), "image_symlink_refused")
    require(path.resolve().is_relative_to(root), "image_path_escape")
    return path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("public_image_redirect_refused")


def admit_image(root, row):
    from PIL import Image
    path = image_path(root, row["path"])
    downloaded = False
    if not path.exists():
        request = urllib.request.Request(row["url"], headers={"User-Agent": "MetaLensR6/1.0"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            require(response.status == 200 and response.geturl() == row["url"], "unexpected_public_response")
            raw = response.read(MAX_IMAGE_BYTES + 1)
        require(0 < len(raw) <= MAX_IMAGE_BYTES and digest(raw) == row["sha256"], "download_hash_or_size_mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        path = image_path(root, row["path"])
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".r6-", delete=False) as stream:
                temp = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temp, path)  # Never overwrite a concurrent or previous file.
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        downloaded = True
    require(path.stat().st_size <= MAX_IMAGE_BYTES and file_sha(path) == row["sha256"], "image_hash_or_size_mismatch")
    with Image.open(path) as img:
        require(img.format == "JPEG" and 0 < img.width <= 8192 and 0 < img.height <= 8192,
                "invalid_admitted_jpeg")
        shape = [img.width, img.height]
        img.verify()
    return path, {"image_id": row["image_id"], "sha256": row["sha256"], "downloaded": downloaded,
                  "bytes": path.stat().st_size, "size_wh": shape}


def inventory(root, names):
    rows = []
    for name in sorted(names):
        path = root / name
        rows.append({"path": name, "sha256": file_sha(path), "size_bytes": path.stat().st_size})
    return rows


def prepare_models(root):
    from huggingface_hub import snapshot_download
    # Explicit token=False prevents use of an unrelated logged-in account.
    result = {}
    for key, model_id, revision, patterns in (
        ("ocr", OCR_ID, OCR_REV, ["nemotron-ocr/**", "v2_english/*", "LICENSE*", "README.md", "THIRD_PARTY_NOTICES.md"]),
        ("radio", RADIO_ID, RADIO_REV, ["*.py", "config.json", "preprocessor_config.json", "model.safetensors", "LICENSE*", "README.md"]),
    ):
        destination = root / (model_id.split("/")[1] + "-" + revision)
        require(not destination.is_symlink(), "model_root_symlink_refused")
        snapshot_download(repo_id=model_id, revision=revision, local_dir=str(destination),
                          allow_patterns=patterns, token=False, max_workers=4)
        if key == "ocr":
            for name in OCR_REQUIRED:
                require((destination / "v2_english" / name).is_file(), "incomplete_pinned_ocr_checkpoint:" + name)
            names = ["v2_english/" + name for name in OCR_REQUIRED]
            names += [str(p.relative_to(destination)) for p in (destination / "nemotron-ocr").rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts]
            weights = ["v2_english/" + name for name in OCR_REQUIRED if name.endswith(".pth")]
        else:
            names = [str(p.relative_to(destination)) for p in destination.glob("*.py")]
            names += ["config.json", "preprocessor_config.json", "model.safetensors"]
            weights = ["model.safetensors"]
        names += [str(p.relative_to(destination)) for pattern in ("LICENSE*", "README.md", "THIRD_PARTY_NOTICES.md")
                  for p in destination.glob(pattern) if p.is_file()]
        files = inventory(destination, set(names))
        weight_files = inventory(destination, weights)
        result[key] = {"model_id": model_id, "revision": revision, "path": str(destination),
                       "weights_sha256": digest(canonical(weight_files)), "files": weight_files,
                       "source_and_weights_sha256": digest(canonical(files)), "source_and_weight_files": files}
    # Both models are now complete and local; refuse a loader's silent Hub fallback.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    # huggingface_hub has already been imported for snapshot_download; its
    # constants module otherwise retains the pre-download environment value.
    import huggingface_hub.constants
    huggingface_hub.constants.HF_HUB_OFFLINE = True
    return result


def verify_ocr_install(snapshot):
    require(importlib.metadata.version("nemotron-ocr") == "1.0.0", "unexpected_ocr_package_version")
    spec = importlib.util.find_spec("nemotron_ocr")
    require(spec is not None and spec.submodule_search_locations, "install_pinned_nemotron_ocr_package_first")
    installed = Path(next(iter(spec.submodule_search_locations))).resolve()
    expected = snapshot / "nemotron-ocr" / "src" / "nemotron_ocr"
    expected_files = {str(p.relative_to(expected)) for p in expected.rglob("*.py")}
    actual_files = {str(p.relative_to(installed)) for p in installed.rglob("*.py")}
    require(expected_files and expected_files == actual_files, "ocr_installed_python_file_set_mismatch")
    for name in sorted(expected_files):
        require(file_sha(expected / name) == file_sha(installed / name), "ocr_installed_source_mismatch:" + name)
    extension_spec = importlib.util.find_spec("nemotron_ocr_cpp")
    require(extension_spec is not None, "ocr_cuda_extension_missing")
    extension_paths = []
    if extension_spec.origin and Path(extension_spec.origin).is_file():
        extension_paths.append(Path(extension_spec.origin))
    for directory in extension_spec.submodule_search_locations or []:
        extension_paths.extend(Path(directory).rglob("*.so"))
    require(any(p.suffix == ".so" for p in extension_paths), "ocr_compiled_extension_missing")
    return {"package_version": importlib.metadata.version("nemotron-ocr"),
            "python_source_verified_against_snapshot": True,
            "extension_files": [{"name": p.name, "sha256": file_sha(p)} for p in sorted(set(extension_paths))]}


def normalize_ocr(predictions):
    require(type(predictions) is list and len(predictions) <= 4096, "bounded_ocr_list_required")
    spans = []
    for row in predictions:
        require(type(row) is dict and isinstance(row.get("text"), str), "ocr_text_required")
        require(len(row["text"]) <= 65536, "ocr_text_too_long")
        values = []
        for key in ("confidence", "left", "lower", "right", "upper"):
            value = row.get(key)
            require(not isinstance(value, (str, bool)) and value is not None, "ocr_numeric_field_required:" + key)
            value = float(value)
            require(math.isfinite(value) and 0 <= value <= 1, "invalid_ocr_numeric_field:" + key)
            values.append(value)
        confidence, left, top, right, bottom = values
        require(left < right and top < bottom, "degenerate_or_reversed_ocr_geometry")
        spans.append({"text": row["text"], "confidence": confidence,
                      "box_normalized": [left, top, right, bottom]})
    return {"status": "ok", "spans": spans}


def source_receipt(source_commit):
    script = Path(__file__).resolve()
    result = {"source_commit": source_commit, "source_sha256": file_sha(script),
              "git_commit_verified": False, "observed_git_head": None}
    try:
        process = subprocess.run(["git", "-C", str(script.parent), "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, timeout=5)
        if process.returncode == 0:
            root = Path(process.stdout.strip())
            head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=5).decode().strip()
            require(head == source_commit, "execution_git_head_mismatch")
            committed = subprocess.check_output(["git", "-C", str(root), "show", head + ":" + str(script.relative_to(root))], timeout=5)
            require(digest(committed) == result["source_sha256"], "execution_script_differs_from_commit")
            result.update(git_commit_verified=True, observed_git_head=head)
    except FileNotFoundError:
        pass  # Portable source bundles have an independently verifiable script SHA.
    return result


def runtime_receipt(torch):
    packages = {}
    for name in ("torch", "torchvision", "transformers", "timm", "numpy", "pillow", "huggingface_hub", "einops", "nemotron-ocr"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        smi = subprocess.run(["nvidia-smi", "--query-gpu=uuid,name,driver_version,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10)
        smi_value = smi.stdout.strip() if smi.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        smi_value = None
    return {"python": sys.version, "platform": platform.platform(), "packages": packages,
            "cuda_runtime": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
            "gpu": torch.cuda.get_device_name(0), "device": "cuda:0",
            "device_count": torch.cuda.device_count(), "nvidia_smi_csv": smi_value}


def run(args):
    start = time.monotonic()
    require(1 <= args.batch_size <= 16, "batch_size_out_of_range")
    manifest, input_sha = load_manifest(args.manifest, args.source_commit)
    require(args.max_images is None or 1 <= args.max_images <= len(manifest["images"]), "invalid_max_images")
    rows = manifest["images"][:args.max_images] if args.max_images else manifest["images"]
    image_root, model_root = safe_root(args.image_root), safe_root(args.model_root)
    source = source_receipt(args.source_commit)
    output = Path(args.output)
    require(output.is_absolute() and not output.exists() and not output.is_symlink(), "new_absolute_output_required")
    require(all(not parent.is_symlink() for parent in output.parents), "output_parent_symlink_refused")
    output.mkdir(parents=True, exist_ok=False)
    state = {"schema": "meta_r6_extraction_v1", **source, "input_sha256": input_sha,
             "dataset_sha256": manifest["dataset_sha256"], "status": "running", "complete": False,
             "counts": {"manifest_images": len(manifest["images"]), "expected_images": len(rows), "observed_images": 0, "failed_images": 0},
             "settings": {"batch_size": args.batch_size, "ocr_variant": "v2_english", "skip_relational": True,
                          "ocr_infer_length": 1024, "radio_input_size_wh": [512, 512], "radio_center_crop": False,
                          "radio_normalize_pixels": False, "radio_l2_normalized": True},
             "models": {}, "qualification": False, "physical_identity_verified": False, "action_authorized": False,
             "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "docs": DOCS}
    write_json(output / "plan.json", state)
    stage, current_ids = "runtime", []
    torch = None
    observations = output / "observations.jsonl"
    raw_ocr = output / "raw-ocr.jsonl"
    admissions = output / "image-admissions.jsonl"
    try:
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        import torch
        from PIL import Image
        require(torch.cuda.is_available(), "cuda_required")
        torch.cuda.set_device(0)
        torch.cuda.reset_peak_memory_stats(0)
        state["runtime"] = runtime_receipt(torch)
        stage = "model_download"
        models = prepare_models(model_root)
        state["models"] = models
        write_json(output / "models.json", models)
        stage = "ocr_package_provenance"
        state["ocr_install"] = verify_ocr_install(Path(models["ocr"]["path"]))
        from nemotron_ocr.inference.pipeline_v2 import NemotronOCRV2
        from transformers import AutoModel, CLIPImageProcessor
        stage = "model_load"
        ocr = NemotronOCRV2(model_dir=str(Path(models["ocr"]["path"]) / "v2_english"),
                            detector_max_batch_size=args.batch_size, recognizer_chunk_size=32,
                            skip_relational=True, infer_length=1024)
        radio = AutoModel.from_pretrained(models["radio"]["path"], trust_remote_code=True,
                                         local_files_only=True, use_safetensors=True).eval().cuda()
        processor = CLIPImageProcessor.from_pretrained(models["radio"]["path"], local_files_only=True)
        amp_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        state["runtime"]["radio_autocast_dtype"] = str(amp_dtype)
        dimension = None
        with observations.open("x", encoding="utf-8") as obs_stream, raw_ocr.open("x", encoding="utf-8") as raw_stream, admissions.open("x", encoding="utf-8") as admission_stream:
            for offset in range(0, len(rows), args.batch_size):
                batch = rows[offset:offset + args.batch_size]
                current_ids = [row["image_id"] for row in batch]
                stage = "image_admission"
                paths = []
                for row in batch:
                    path, receipt = admit_image(image_root, row)
                    paths.append(path)
                    append_json(admission_stream, receipt)
                stage = "ocr_inference"
                raw_results = ocr([str(path) for path in paths], merge_level="word")
                require(type(raw_results) is list and len(raw_results) == len(batch), "ocr_batch_shape_mismatch")
                normalized = []
                for row, raw in zip(batch, raw_results):
                    # Preserve raw provider observations before geometry validation.
                    append_json(raw_stream, {"image_id": row["image_id"], "sha256": row["sha256"], "predictions": raw_json_value(raw)})
                    normalized.append(normalize_ocr(raw))
                stage = "radio_inference"
                images = []
                try:
                    for path in paths:
                        with Image.open(path) as image:
                            images.append(image.convert("RGB"))
                    pixels = processor(images=images, return_tensors="pt", do_resize=True,
                                       size={"height": 512, "width": 512}, do_center_crop=False,
                                       do_normalize=False, do_rescale=True).pixel_values.cuda()
                finally:
                    for image in images:
                        image.close()
                with torch.inference_mode(), torch.autocast("cuda", dtype=amp_dtype):
                    summary, features = radio(pixels)
                require(summary.ndim == 2 and summary.shape[0] == len(batch) and 32 <= summary.shape[1] <= 65536,
                        "radio_embedding_shape_mismatch")
                vectors = summary.float()
                norms = torch.linalg.vector_norm(vectors, dim=1, keepdim=True)
                require(bool(torch.isfinite(vectors).all()) and bool(torch.isfinite(norms).all()) and bool((norms > 0).all()),
                        "nonfinite_or_zero_radio_embedding")
                vectors = (vectors / norms).cpu().tolist()
                if dimension is None:
                    dimension = len(vectors[0])
                require(all(len(vector) == dimension for vector in vectors), "radio_dimension_changed")
                del summary, features, pixels
                stage = "observation_write"
                for row, text, vector in zip(batch, normalized, vectors):
                    append_json(obs_stream, {"image_id": row["image_id"], "sha256": row["sha256"],
                                            "ocr": text, "radio": {"embedding": vector, "dimension": dimension}})
                    state["counts"]["observed_images"] += 1
                    current_ids.remove(row["image_id"])
                print(json.dumps({"stage": "extracted", "observed_images": state["counts"]["observed_images"],
                                  "expected_images": len(rows)}, sort_keys=True), flush=True)
        require(file_sha(Path(__file__).resolve()) == source["source_sha256"], "execution_script_changed")
        require(file_sha(Path(args.manifest)) == input_sha, "input_manifest_changed")
        state["complete"] = len(rows) == len(manifest["images"])
        state["status"] = "complete" if state["complete"] else "pilot_complete"
        state["radio_dimension"] = dimension
        return_code = 0
    except Exception as error:
        state["status"] = "failed"
        state["counts"]["failed_images"] = len(current_ids)
        state["failure"] = {"stage": stage, "image_ids": current_ids, "error_type": type(error).__name__, "message": str(error)[:2000]}
        write_json(output / "failure.json", state["failure"])
        return_code = 1
    finally:
        state["elapsed_seconds"] = time.monotonic() - start
        state["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for key, path in (("observations_sha256", observations), ("raw_ocr_sha256", raw_ocr), ("admissions_sha256", admissions)):
            state[key] = file_sha(path) if path.exists() else None
        if torch is not None and torch.cuda.is_available():
            state["gpu_memory"] = {"peak_allocated_bytes": torch.cuda.max_memory_allocated(0),
                                   "peak_reserved_bytes": torch.cuda.max_memory_reserved(0)}
        write_json(output / "summary.json", state)
        print(json.dumps({"status": state["status"], "counts": state["counts"], "output": str(output)}, sort_keys=True), flush=True)
    return return_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-images", type=int)
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as error:
        print(json.dumps({"status": "preflight_failed", "error_type": type(error).__name__, "message": str(error)[:2000]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
