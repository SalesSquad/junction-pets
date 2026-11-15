#!/usr/bin/env python3
"""Finite real-image retrieval training; the pretrained vision tower is frozen.

The trainable model is a dual residual low-rank embedding projection. Pixel
features come from pinned actual SigLIP inference, never synthetic scores.
Dev selects epochs/seed and hybrid weights; cal chooses refusal thresholds;
sealed test/OOD are opened only after all checkpoint selection is complete.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np

from retrieval import (apply_residual, bm25_scores, calibrate_threshold,
                       file_sha256, normalize, policy_metrics, rank_normalize,
                       retrieval_metrics, validate_dataset, write_json)

MODEL_ID = "google/siglip2-base-patch16-224"
REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
WEIGHTS_SHA = "612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b"
MODEL_FILES = ["config.json", "model.safetensors", "preprocessor_config.json", "special_tokens_map.json", "tokenizer.json", "tokenizer.model", "tokenizer_config.json", "README.md"]


def check_deadline(deadline):
    if time.monotonic() > deadline:
        raise RuntimeError("experiment_deadline_exceeded")


def verify_images(root, records):
    checked = set()
    root = root.resolve()
    for r in records:
        for view in r["views"]:
            path = root / view["path"]
            resolved = path.resolve()
            if path.is_symlink() or not resolved.is_relative_to(root):
                raise ValueError("image_path_outside_dataset")
            if view["path"] not in checked:
                if file_sha256(path) != view["sha256"]:
                    raise ValueError("image_hash_mismatch")
                checked.add(view["path"])
    return len(checked)


def encode(root, records, output, device, batch, cache, deadline, dataset_sha):
    import torch
    from PIL import Image
    from huggingface_hub import snapshot_download
    from transformers import AutoModel, AutoProcessor

    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    started = time.monotonic()
    model_path = Path(snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=MODEL_FILES, cache_dir=str(cache) if cache else None, token=False))
    if file_sha256(model_path / "model.safetensors") != WEIGHTS_SHA:
        raise ValueError("model_weight_hash_mismatch")
    dtype = torch.float16 if str(device).startswith("cuda") else torch.float32
    model = AutoModel.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False, torch_dtype=dtype, attn_implementation="eager").to(device).eval()
    model.requires_grad_(False)
    if any(p.requires_grad for p in model.parameters()):
        raise RuntimeError("encoder_not_frozen")
    processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)

    def image_features(view_index):
        result = []
        for start in range(0, len(records), batch):
            check_deadline(deadline)
            images = []
            for r in records[start:start+batch]:
                with Image.open(root / r["views"][view_index]["path"]) as im:
                    images.append(im.convert("RGB"))
            inputs = processor(images=images, return_tensors="pt")
            inputs = {k: v.to(device=device, dtype=dtype) for k, v in inputs.items()}
            with torch.inference_mode():
                features = model.get_image_features(**inputs)
            result.append(features.float().cpu().numpy())
            for im in images:
                im.close()
            if start % (batch*10) == 0:
                print(json.dumps({"stage": "pixel_encoder", "view": view_index, "done": min(start+batch, len(records)), "total": len(records)}), flush=True)
        return normalize(np.concatenate(result))

    def text_features(texts):
        result = []
        for start in range(0, len(texts), batch):
            check_deadline(deadline)
            inputs = processor(text=texts[start:start+batch], padding="max_length", max_length=64, truncation=True, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.inference_mode():
                features = model.get_text_features(**inputs)
            result.append(features.float().cpu().numpy())
        return normalize(np.concatenate(result))

    arrays = {"gallery": image_features(0), "query": image_features(1), "text": text_features([r["metadata_text"] for r in records]), "hint": text_features([r["text_hint"] for r in records])}
    if str(device).startswith("cuda"):
        torch.cuda.synchronize()
    np.savez_compressed(output / "features.npz", **arrays)
    receipt = {"schema_version": 1, "dataset_sha256": dataset_sha, "model_id": MODEL_ID, "model_revision": REVISION, "model_weights_sha256": WEIGHTS_SHA, "model_files": {name: file_sha256(model_path/name) for name in MODEL_FILES if (model_path/name).exists()}, "product_order": [r["product_id"] for r in records], "feature_sha256": file_sha256(output / "features.npz"), "feature_shapes": {k: list(v.shape) for k,v in arrays.items()}, "encoder_frozen": True, "image_inference_executed": True, "dtype": str(dtype), "attention": "eager", "seconds": time.monotonic()-started, "text_max_tokens": 64, "device": str(device)}
    write_json(output / "features.json", receipt)
    del model
    if str(device).startswith("cuda"):
        torch.cuda.empty_cache()
    return arrays, receipt


def load_features(path, records, dataset_sha):
    receipt = json.loads(path.with_suffix(".json").read_text())
    if receipt["dataset_sha256"] != dataset_sha or receipt["model_revision"] != REVISION or receipt["model_weights_sha256"] != WEIGHTS_SHA or not receipt.get("image_inference_executed") or receipt["product_order"] != [r["product_id"] for r in records] or receipt["feature_sha256"] != file_sha256(path):
        raise ValueError("feature_provenance_mismatch")
    with np.load(path, allow_pickle=False) as loaded:
        arrays = {key: normalize(loaded[key]) for key in ("gallery", "query", "text", "hint")}
    if any(v.shape[0] != len(records) for v in arrays.values()):
        raise ValueError("feature_count_mismatch")
    return arrays, receipt


def train_one(seed, features, records, indices, args, deadline):
    import torch
    from torch import nn
    from torch.nn import functional as F
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    train = indices["train"]
    dev = indices["dev"]
    dimension = features["query"].shape[1]

    class Projection(nn.Module):
        def __init__(self):
            super().__init__()
            self.vision_a = nn.Parameter(torch.randn(dimension, args.rank)*0.01)
            self.vision_b = nn.Parameter(torch.zeros(args.rank, dimension))
            self.text_a = nn.Parameter(torch.randn(dimension, args.rank)*0.01)
            self.text_b = nn.Parameter(torch.zeros(args.rank, dimension))

        def forward(self, x, tower):
            a, b = getattr(self, tower+"_a"), getattr(self, tower+"_b")
            return F.normalize(x + (x@a)@b, dim=-1)

    model = Projection().to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.0001)
    tensors = {k: torch.tensor(v[train], device=args.device) for k, v in features.items() if k != "hint"}
    families = np.asarray([records[i]["family_id"] for i in train])
    similarity = features["query"][train] @ features["text"][train].T
    similarity[families[:,None] == families[None,:]] = -np.inf
    neighbors = np.argpartition(-similarity, kth=min(3, len(train)-1), axis=1)[:, :min(4, len(train)-1)]
    del similarity
    history, best, best_metrics, max_gradient = [], None, None, 0.0
    started = time.monotonic()
    rng = np.random.default_rng(seed)
    for epoch in range(args.epochs):
        check_deadline(deadline)
        model.train()
        permutation = rng.permutation(len(train))
        losses = []
        for start in range(0, len(train), max(8, args.batch_size//2)):
            check_deadline(deadline)
            anchors = permutation[start:start+max(8, args.batch_size//2)]
            hard = neighbors[anchors, epoch % neighbors.shape[1]]
            chosen = np.unique(np.concatenate((anchors, hard)))[:args.batch_size]
            if len(chosen) < 2:
                continue
            batch_indices = torch.as_tensor(chosen, device=args.device)
            q = model(tensors["query"][batch_indices], "vision")
            g = model(tensors["gallery"][batch_indices], "vision")
            t = model(tensors["text"][batch_indices], "text")
            labels = torch.arange(len(chosen), device=args.device)
            same = families[chosen, None] == families[None, chosen]
            np.fill_diagonal(same, False)
            exclude = torch.as_tensor(same, device=args.device)
            qt = ((q@t.T)/0.07).masked_fill(exclude, -1e4)
            qg = ((q@g.T)/0.07).masked_fill(exclude, -1e4)
            preservation = F.mse_loss(q, tensors["query"][batch_indices]) + F.mse_loss(t, tensors["text"][batch_indices])
            loss = 0.5*(F.cross_entropy(qt, labels)+F.cross_entropy(qt.T, labels)) + 0.25*F.cross_entropy(qg, labels) + 0.05*preservation
            if not torch.isfinite(loss):
                raise RuntimeError("non_finite_training_loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            grad = float(nn.utils.clip_grad_norm_(model.parameters(), 1.0).cpu())
            if not np.isfinite(grad):
                raise RuntimeError("non_finite_training_gradient")
            max_gradient = max(max_gradient, grad)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        model.eval()
        weights = {k: v.detach().cpu().numpy().copy() for k,v in model.state_dict().items()}
        q = apply_residual(features["query"][dev], weights["vision_a"], weights["vision_b"])
        t = apply_residual(features["text"][dev], weights["text_a"], weights["text_b"])
        metrics = retrieval_metrics(q@t.T)
        row = {"epoch": epoch+1, "train_loss": float(np.mean(losses)), "dev": metrics}
        history.append(row)
        if best_metrics is None or (metrics["recall_at_1"], metrics["mrr"]) > (best_metrics["recall_at_1"], best_metrics["mrr"]):
            best, best_metrics = weights, metrics
            best_epoch = epoch+1
        print(json.dumps({"stage": "training", "seed": seed, **row}), flush=True)
    if best is None or max_gradient <= 0 or np.max(np.abs(best["vision_b"])) <= 0:
        raise RuntimeError("training_did_not_update_visual_projection")
    return best, {"seed": seed, "selected_epoch": best_epoch, "dev": best_metrics, "epochs_run": len(history), "history": history, "seconds": time.monotonic()-started, "trainable_parameters": sum(p.numel() for p in model.parameters()), "max_observed_gradient_norm": max_gradient, "encoder_frozen": True, "pixel_features_used": True, "hard_negative_source": "train_partition_frozen_image_text_similarity_only"}


def visual_scores(features, subset, weights=None):
    q, t, g = (features[k][subset] for k in ("query", "text", "gallery"))
    if weights is not None:
        q = apply_residual(q, weights["vision_a"], weights["vision_b"])
        g = apply_residual(g, weights["vision_a"], weights["vision_b"])
        t = apply_residual(t, weights["text_a"], weights["text_b"])
    return q@t.T, q@g.T


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--cache", type=Path)
    p.add_argument("--features", type=Path)
    p.add_argument("--stage", choices=("all", "encode"), default="all")
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--encode-batch", type=int, default=32)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--rank", type=int, default=64)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--learning-rate", type=float, default=0.001)
    p.add_argument("--seeds", type=int, nargs="+", default=[17,31,53])
    p.add_argument("--max-seconds", type=int, default=10800)
    p.add_argument("--risk-target", type=float, default=0.01)
    args = p.parse_args()
    if not 1 <= args.epochs <= 50 or not 1 <= args.rank <= 256 or not 8 <= args.batch_size <= 512 or not 1 <= args.encode_batch <= 128 or not 1 <= len(args.seeds) <= 3 or len(set(args.seeds)) != len(args.seeds) or not 60 <= args.max_seconds <= 14400 or not 0 < args.learning_rate <= 0.1:
        p.error("invalid bounded experiment settings")
    if args.output.exists() and any(args.output.iterdir()):
        p.error("output is not empty; preserve old evidence and choose a fresh directory")
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + args.max_seconds
    dataset_path = args.data / "dataset.json"
    dataset_sha = file_sha256(dataset_path)
    if (args.data / "dataset.sha256").read_text().strip() != dataset_sha:
        raise ValueError("dataset_seal_mismatch")
    manifest = json.loads(dataset_path.read_text())
    integrity = validate_dataset(manifest)
    records = manifest["records"]
    verified_images = verify_images(args.data, records)
    import torch
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("requested_cuda_unavailable")
    if args.device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    runtime = {"python": platform.python_version(), "platform": platform.platform(), "torch": torch.__version__, "cuda_runtime": torch.version.cuda, "device": args.device, "gpu": torch.cuda.get_device_name() if args.device.startswith("cuda") else None, "gpu_capability": list(torch.cuda.get_device_capability()) if args.device.startswith("cuda") else None, "packages": {k: importlib.metadata.version(k) for k in ("numpy", "Pillow", "transformers", "huggingface-hub", "safetensors")}}
    source_hashes = {p.name: file_sha256(p) for p in Path(__file__).parent.iterdir() if p.is_file() and p.suffix in {".py", ".json", ".txt"}}
    write_json(args.output / "run-start.json", {"dataset_sha256": dataset_sha, "source_hashes": source_hashes, "runtime": runtime, "arguments": {k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()}, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "private_data_used": False})
    if args.features:
        features, feature_receipt = load_features(args.features, records, dataset_sha)
    else:
        features, feature_receipt = encode(args.data, records, args.output, args.device, args.encode_batch, args.cache, deadline, dataset_sha)
    if args.stage == "encode":
        print(json.dumps({"stage": "ENCODE_COMPLETED", "features": str(args.output / "features.npz")}), flush=True)
        return
    indices = {split: np.asarray([i for i,r in enumerate(records) if r["split"] == split]) for split in ("train", "dev", "cal", "test", "ood")}
    # No test/OOD score or label is consulted before this selection block ends.
    dev_it, dev_ii = visual_scores(features, indices["dev"])
    hybrid_weight = max((0.0,0.25,0.5,0.75,1.0), key=lambda w: (retrieval_metrics(w*dev_it+(1-w)*dev_ii)["recall_at_1"], retrieval_metrics(w*dev_it+(1-w)*dev_ii)["mrr"]))
    from safetensors.numpy import save_file
    trained = []
    for seed in args.seeds:
        weights, training = train_one(seed, features, records, indices, args, deadline)
        checkpoint = args.output / f"projection-seed-{seed}.safetensors"
        save_file(weights, str(checkpoint))
        training["checkpoint"] = checkpoint.name
        training["checkpoint_sha256"] = file_sha256(checkpoint)
        trained.append((weights, training))
        write_json(args.output / f"training-seed-{seed}.json", training)
    selected = max(range(len(trained)), key=lambda i: (trained[i][1]["dev"]["recall_at_1"], trained[i][1]["dev"]["mrr"]))
    selection = {"partition": "dev", "selected_seed": trained[selected][1]["seed"], "selected_epoch": trained[selected][1]["selected_epoch"], "frozen_hybrid_image_text_weight": hybrid_weight, "checkpoint_sha256": trained[selected][1]["checkpoint_sha256"], "test_or_ood_used_for_selection": False}
    write_json(args.output / "selection.json", selection)
    results = {}
    method_weights = {"frozen_image_text": None, "frozen_image_image": None, "frozen_image_hybrid": None}
    method_weights.update({f"learned_projection_seed_{run['seed']}": w for w,run in trained})
    for method, weights in method_weights.items():
        check_deadline(deadline)
        scores_by_split = {}
        for split in ("cal", "test", "ood"):
            it, ii = visual_scores(features, indices[split], weights)
            scores_by_split[split] = ii if method == "frozen_image_image" else hybrid_weight*it+(1-hybrid_weight)*ii if method == "frozen_image_hybrid" else it
        cal_families = [records[i]["family_id"] for i in indices["cal"]]
        policy = calibrate_threshold(scores_by_split["cal"], cal_families, args.risk_target)
        measurements = {}
        for split in ("cal", "test", "ood"):
            families = [records[i]["family_id"] for i in indices[split]]
            measurements[split] = {"retrieval": retrieval_metrics(scores_by_split[split], families), "refusal": policy_metrics(scores_by_split[split], families, policy)}
        results[method] = {"policy": policy, "partitions": measurements}
    # Supplemental query hints are published attributes, not OCR or camera inference.
    text_results = {}
    for split in ("test", "ood"):
        subset = indices[split]
        subset_records = [records[i] for i in subset]
        lexical = bm25_scores([r["text_hint"] for r in subset_records], [r["metadata_text"] for r in subset_records])
        text_cosine = features["hint"][subset] @ features["text"][subset].T
        image_text, image_image = visual_scores(features, subset)
        multimodal = rank_normalize(lexical)+rank_normalize(text_cosine)+rank_normalize(image_text)+rank_normalize(image_image)
        families = [r["family_id"] for r in subset_records]
        text_results[split] = {"query_provenance": "deterministic_published_attribute_hint_not_observed_ocr", "bm25_text_hint": retrieval_metrics(lexical, families), "frozen_text_hint": retrieval_metrics(text_cosine, families), "frozen_multimodal_hint": retrieval_metrics(multimodal, families), "not_same_input_track_as_image_only": True}
    selected_weights = trained[selected][0]
    benchmark_gallery = apply_residual(features["text"][indices["test"]], selected_weights["text_a"], selected_weights["text_b"])
    latencies = []
    for j in range(min(100,len(indices["test"]))):
        tick = time.perf_counter()
        q = apply_residual(features["query"][indices["test"]][j:j+1], selected_weights["vision_a"], selected_weights["vision_b"])
        np.argmax(q @ benchmark_gallery.T)
        latencies.append((time.perf_counter()-tick)*1000)
    best_name = f"learned_projection_seed_{selection['selected_seed']}"
    selected_result = results[best_name]
    base = results["frozen_image_hybrid"]
    no_regression = all(selected_result["partitions"][s]["retrieval"]["recall_at_1"] >= base["partitions"][s]["retrieval"]["recall_at_1"] for s in ("test", "ood"))
    coverage = all(selected_result["partitions"][s]["refusal"]["coverage"] >= 0.2 for s in ("test", "ood"))
    risk = all(selected_result["partitions"][s]["refusal"]["absent_family_upper95"] <= args.risk_target for s in ("test", "ood"))
    no_observed_present_error = all(selected_result["partitions"][s]["refusal"]["wrong_present_accepted"] == 0 for s in ("test", "ood"))
    report = {"schema_version": 1, "status": "COMPLETED", "work_id": "META-LENS-TRAIN-20261114-R2", "evidence_mode": "ACTUAL_FROZEN_PIXEL_ENCODER_AND_TRAINED_RETRIEVAL_PROJECTION", "dataset_sha256": dataset_sha, "source_hashes": source_hashes, "runtime": runtime, "data_integrity": integrity, "image_bytes_verified": verified_images, "feature_receipt": feature_receipt, "selection": selection, "training": [r for _,r in trained], "image_only_results": results, "supplemental_hint_results": text_results, "latency": {"scope": "warm_CPU_projection_and_dense_search_only; excludes_encoder_camera_network_audio", "gallery_products": len(benchmark_gallery), "observations": len(latencies), "p50_ms": float(np.percentile(latencies,50)), "p95_ms": float(np.percentile(latencies,95))}, "wall_seconds": time.monotonic()-started, "peak_torch_gpu_bytes": torch.cuda.max_memory_allocated() if args.device.startswith("cuda") else None, "compute_cost_usd": None, "cost_owner": "provider_controller_must_join_actual_billing_receipt", "research_gate": {"no_recall_regression_vs_frozen_hybrid_on_test_and_ood": no_regression, "coverage_at_least_20pct_on_test_and_ood": coverage, "absent_family_false_accept_target_met_on_test_and_ood": risk, "zero_observed_wrong_present_all_queries_on_test_and_ood": no_observed_present_error, "conditional_accepted_error_certified": False, "passes": bool(no_regression and coverage and risk and no_observed_present_error)}, "deployment_authorized": False, "identity_verified": False, "action_authorized": False, "limitations": ["vision and text backbone weights were frozen; only residual projection weights trained", "public catalog photography, not egocentric or live glasses data", "attribute text hints are generated from public metadata; no OCR performance measured", "same-product alternate catalog photos may still be visually similar", "heuristic family grouping cannot prove absence of all near-duplicate product variants", "closed galleries and absent-family replay are limited open-world simulations", "family-any-error binomial bounds assume independent connected families; source collection correlations remain; zero observed present errors does not certify conditional accepted error", "no user learning, temporal location, real spatial registration, physical identity or end-to-end glasses latency qualified"]}
    write_json(args.output / "report.json", report)
    write_json(args.output / "checkpoint-manifest.json", {"model_id": MODEL_ID, "model_revision": REVISION, "model_weights_sha256": WEIGHTS_SHA, "dataset_sha256": dataset_sha, "projection": trained[selected][1]["checkpoint"], "projection_sha256": selection["checkpoint_sha256"], "policy": selected_result["policy"], "source_hashes": source_hashes, "encoder_frozen": True, "identity_verified": False, "action_authorized": False, "deployment_authorized": False})
    print(json.dumps({"stage": "COMPLETED", "report": str(args.output/"report.json"), "selected_seed": selection["selected_seed"], "research_gate": report["research_gate"]}), flush=True)


if __name__ == "__main__":
    main()
