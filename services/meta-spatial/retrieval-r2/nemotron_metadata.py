#!/usr/bin/env python3
"""Finite NVIDIA frozen metadata-retrieval study; no server or paid API.

Run in a SECONDARY environment containing Transformers 5.5.0 and the approved
CUDA PyTorch. Inputs are the sealed public ABO dataset and verified SigLIP
features. This model is not trained here. The same generated attribute hints,
documents, gallery and partitions are used for BM25, SigLIP and Nemotron.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np

from retrieval import (bm25_scores, calibrate_threshold, file_sha256, normalize,
                       policy_metrics, retrieval_metrics, validate_dataset,
                       write_json)

MODEL_ID = "nvidia/Nemotron-3-Embed-1B-BF16"
REVISION = "c0c9fea93ea424587517f2c59e20db9f1d6bf615"
WEIGHTS_SHA = "f959c3b04e66b42de280bfb97c140cb7e0bfe25e3ecb0b4464c68a8436b2d04f"
WEIGHTS_BYTES = 2281852472
TOKENIZER_SHA = "797410dfb649a5b9ba92bc4fef7dbf4022d00e73de6867c4ac199a8846439421"
SIGLIP_REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
FILES = ["config.json", "model.safetensors", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json", "README.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "config_sentence_transformers.json", "1_Pooling/config.json"]


def check_deadline(deadline):
    if time.monotonic() > deadline:
        raise RuntimeError("nemotron_deadline_exceeded")


def bilingual_title(record):
    titles = record.get("titles", {})
    priorities = ["fi_FI", "de_DE", "fr_FR", "es_ES", "ja_JP", "zh_CN"]
    candidates = priorities + sorted(titles)
    for language in candidates:
        value = titles.get(language)
        if not language.lower().startswith("en") and language != "und" and isinstance(value, str) and value.strip() and value.strip() != record["title"].strip():
            return language, value
    return None, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--siglip-features", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path)
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--max-length", type=int, default=256)
    p.add_argument("--max-seconds", type=int, default=3600)
    p.add_argument("--risk-target", type=float, default=0.01)
    p.add_argument("--skip-multilingual", action="store_true")
    args = p.parse_args()
    if not 1 <= args.batch_size <= 64 or not 64 <= args.max_length <= 512 or not 60 <= args.max_seconds <= 7200 or not args.device.startswith("cuda") or not 0 < args.risk_target < 1:
        p.error("bounded CUDA run required")
    if args.output.exists() and any(args.output.iterdir()):
        p.error("choose a new output directory; previous evidence is preserved")
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + args.max_seconds
    dataset_path = args.data / "dataset.json"
    dataset_sha = file_sha256(dataset_path)
    if (args.data / "dataset.sha256").read_text().strip() != dataset_sha:
        raise ValueError("dataset_seal_mismatch")
    dataset = json.loads(dataset_path.read_text())
    integrity = validate_dataset(dataset)
    all_records = dataset["records"]
    feature_receipt = json.loads(args.siglip_features.with_suffix(".json").read_text())
    if feature_receipt["dataset_sha256"] != dataset_sha or feature_receipt["model_revision"] != SIGLIP_REVISION or feature_receipt["product_order"] != [r["product_id"] for r in all_records] or feature_receipt["feature_sha256"] != file_sha256(args.siglip_features) or not feature_receipt.get("image_inference_executed"):
        raise ValueError("siglip_feature_provenance_mismatch")
    selected_indices = [i for i,r in enumerate(all_records) if r["split"] in {"cal", "test", "ood"}]
    records = [all_records[i] for i in selected_indices]
    with np.load(args.siglip_features, allow_pickle=False) as f:
        siglip_hint = normalize(f["hint"][selected_indices])
        siglip_text = normalize(f["text"][selected_indices])
    indices = {s: np.asarray([i for i,r in enumerate(records) if r["split"] == s]) for s in ("cal", "test", "ood")}
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModel, AutoTokenizer
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("native_bf16_cuda_required")
    torch.cuda.reset_peak_memory_stats()
    runtime = {"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability()), "dtype": "bfloat16", "attention": "sdpa", "packages": {name: importlib.metadata.version(name) for name in ("transformers", "numpy", "huggingface-hub", "safetensors")}}
    write_json(args.output / "run-start.json", {"model_id": MODEL_ID, "model_revision": REVISION, "dataset_sha256": dataset_sha, "script_sha256": file_sha256(__file__), "runtime": runtime, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "max_seconds": args.max_seconds})
    model_path = Path(snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=FILES, cache_dir=str(args.cache) if args.cache else None, token=False))
    if (model_path / "model.safetensors").stat().st_size != WEIGHTS_BYTES or file_sha256(model_path / "model.safetensors") != WEIGHTS_SHA or file_sha256(model_path / "tokenizer.json") != TOKENIZER_SHA:
        raise ValueError("nemotron_model_or_tokenizer_hash_mismatch")
    config = json.loads((model_path / "config.json").read_text())
    if config.get("model_type") != "ministral3" or config.get("hidden_size") != 2048 or config.get("is_causal") is not False or config.get("auto_map"):
        raise ValueError("unexpected_nemotron_config")
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False, padding_side="left")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModel.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16, attn_implementation="sdpa").to(args.device).eval()
    model.requires_grad_(False)
    if model.config.is_causal is not False or any(v.requires_grad for v in model.parameters()):
        raise RuntimeError("model_is_not_frozen_bidirectional_encoder")
    batch_times, token_count = [], 0

    def encode(texts, prefix):
        nonlocal token_count
        batches = []
        for start in range(0, len(texts), args.batch_size):
            check_deadline(deadline)
            text_batch = [prefix + text for text in texts[start:start+args.batch_size]]
            encoded = tokenizer(text_batch, padding=True, truncation=True, max_length=args.max_length, return_tensors="pt")
            token_count += int(encoded["attention_mask"].sum())
            encoded = {k: v.to(args.device) for k,v in encoded.items()}
            torch.cuda.synchronize()
            tick = time.perf_counter()
            with torch.inference_mode():
                output = model(**encoded, use_cache=False)
                # NVIDIA's documented attention-mask mean pooling; accumulate in F32.
                mask = encoded["attention_mask"].bool()
                hidden = output.last_hidden_state.float().masked_fill(~mask[...,None], 0.0)
                pooled = hidden.sum(dim=1) / mask.sum(dim=1)[...,None]
                result = torch.nn.functional.normalize(pooled, dim=-1)
            torch.cuda.synchronize()
            batch_times.append(time.perf_counter()-tick)
            batches.append(result.cpu().numpy())
            if start % (args.batch_size*10) == 0:
                print(json.dumps({"stage": "nemotron_embed", "prefix": prefix.strip(), "done": min(start+args.batch_size,len(texts)), "total": len(texts)}), flush=True)
        if not batches:
            return np.empty((0,2048), dtype=np.float32)
        embeddings = normalize(np.concatenate(batches))
        if embeddings.shape[1] != 2048:
            raise ValueError("unexpected_nemotron_embedding_dimension")
        return embeddings

    docs = encode([r["metadata_text"] for r in records], "passage: ")
    hints = encode([r["text_hint"] for r in records], "query: ")
    multilingual_rows, multilingual_texts, languages = [], [], []
    if not args.skip_multilingual:
        for i,r in enumerate(records):
            language, title = bilingual_title(r)
            if title and r["split"] in {"test", "ood"}:
                multilingual_rows.append(i)
                multilingual_texts.append(title)
                languages.append(language)
    multilingual = encode(multilingual_texts, "query: ")
    np.savez_compressed(args.output / "nemotron-features.npz", documents=docs, hints=hints, multilingual=multilingual, multilingual_rows=np.asarray(multilingual_rows,dtype=np.int64))
    results = {}
    for method in ("bm25", "siglip2", "nemotron_512", "nemotron_1024", "nemotron_2048"):
        scores_by_split = {}
        for split, subset in indices.items():
            check_deadline(deadline)
            if method == "bm25":
                scores = bm25_scores([records[i]["text_hint"] for i in subset], [records[i]["metadata_text"] for i in subset])
            elif method == "siglip2":
                scores = siglip_hint[subset] @ siglip_text[subset].T
            else:
                dim = int(method.split("_")[1])
                scores = normalize(hints[subset,:dim]) @ normalize(docs[subset,:dim]).T
            scores_by_split[split] = scores
        policy = calibrate_threshold(scores_by_split["cal"], [records[i]["family_id"] for i in indices["cal"]], args.risk_target)
        measurements = {}
        for split, subset in indices.items():
            families = [records[i]["family_id"] for i in subset]
            measurements[split] = {"retrieval": retrieval_metrics(scores_by_split[split], families), "refusal": policy_metrics(scores_by_split[split], families, policy)}
        results[method] = {"policy": policy, "partitions": measurements}
    multilingual_results = {}
    for split in ("test", "ood"):
        positions = [j for j,i in enumerate(multilingual_rows) if records[i]["split"] == split]
        if not positions:
            multilingual_results[split] = {"queries": 0, "status": "NO_DISTINCT_LANGUAGE_TITLES"}
            continue
        rows = [multilingual_rows[j] for j in positions]
        corpus = [records[i]["metadata_text"] for i in rows]
        # This separate square-gallery task has exactly those multilingual products.
        lexical = bm25_scores([multilingual_texts[j] for j in positions], corpus)
        dense = multilingual[positions] @ docs[rows].T
        families = [records[i]["family_id"] for i in rows]
        multilingual_results[split] = {"queries": len(rows), "languages": dict(Counter(languages[j] for j in positions)), "bm25": retrieval_metrics(lexical,families), "nemotron_2048": retrieval_metrics(dense,families), "siglip_multilingual": "NOT_MEASURED; existing feature cache contains only attribute hints", "gallery_scope": "products_with_distinct_non_English_title_only", "query_provenance": "publisher_product_translation_not_independent_human_query"}
    model_receipt = {"id": MODEL_ID, "revision": REVISION, "license": "OpenMDW-1.1", "weights_sha256": WEIGHTS_SHA, "weights_bytes": WEIGHTS_BYTES, "tokenizer_sha256": TOKENIZER_SHA, "files_sha256": {name: file_sha256(model_path/name) for name in FILES if (model_path/name).is_file()}, "trust_remote_code": False, "encoder_frozen": True, "actual_inference_executed": True, "max_tokens": args.max_length, "pooling": "mask-aware mean including query/passage prefix; F32 accumulation; L2 norm", "dimensionality": 2048, "dimension_slicing": "prefix slice then L2 renormalize"}
    report = {"schema_version": 1, "status": "COMPLETED", "work_id": "META-LENS-TRAIN-20261114-R2", "evidence_mode": "ACTUAL_NVIDIA_FROZEN_TEXT_MODEL_INFERENCE", "model": model_receipt, "script_sha256": file_sha256(__file__), "dataset_sha256": dataset_sha, "dataset_integrity": integrity, "siglip_feature_sha256": feature_receipt["feature_sha256"], "runtime": runtime, "product_order": [r["product_id"] for r in records], "feature_sha256": file_sha256(args.output/"nemotron-features.npz"), "same_input_attribute_hint_comparison": results, "multilingual_title_comparison": multilingual_results, "inference": {"input_texts": len(records)*2+len(multilingual_rows), "non_padding_tokens": token_count, "batches": len(batch_times), "synchronized_batch_p50_seconds": float(np.percentile(batch_times,50)), "synchronized_batch_p95_seconds": float(np.percentile(batch_times,95)), "batch_size": args.batch_size, "scope": "model-forward-and-pooling; excludes tokenization/download/camera/network/audio"}, "wall_seconds": time.monotonic()-started, "peak_torch_gpu_bytes": torch.cuda.max_memory_allocated(), "compute_cost_usd": None, "cost_owner": "provider_controller_actual_receipt", "model_training_performed": False, "hosted_api_calls": 0, "private_data_used": False, "deployment_authorized": False, "identity_verified": False, "action_authorized": False, "limitations": ["attribute hints come from the same published metadata as target documents; queries are not independent natural user requests", "many products share valid attribute hints; exact-product relevance can penalize valid alternative products", "frozen SigLIP used max64 model tokens; Nemotron uses the reported different token budget", "cross-language published titles can contain matching brand/model tokens", "no Finnish-query capability is measured unless Finnish titles are present in reported language counts", "no universal model ranking from this one catalog task", "no OCR, private-memory learning, image perception, live glasses, temporal memory or spatial registration is measured"]}
    write_json(args.output / "report.json", report)
    print(json.dumps({"stage": "COMPLETED", "model": MODEL_ID, "report": str(args.output/"report.json"), "input_texts": report["inference"]["input_texts"]}), flush=True)


if __name__ == "__main__":
    main()
