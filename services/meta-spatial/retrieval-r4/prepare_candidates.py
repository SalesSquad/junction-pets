#!/usr/bin/env python3
"""Export source-bound R2 train/dev and historical R3 cal/test candidate features.

No pixels, providers, model download, query OCR/title/hint features, oracle
candidate injection, or fresh qualification. See --help for the exact inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

import numpy as np

from features import CSV_COLUMNS, FEATURE_NAMES, REQUIRED_COLUMNS, candidate_features, embedding_matrix, select_candidates

ROOT = Path(__file__).resolve().parent
R3 = ROOT.parent / "retrieval-r3"
R2 = ROOT.parent / "retrieval-r2"
WORK_ID = "META-LENS-R4-COVERAGE93-20261114"
PINS = {
    "prior_dataset": "bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c",
    "prior_features": "aff8ebed7112771a5e30b689741e088a4fca22d40e7f0df98dae2a135e99058d",
    "fresh_dataset": "c67c6007da76ae3e106da34754eca15d42315271e55d9174657335390e4d3f9f",
    "fresh_features": "59701519b8ef62c7ff7de65ec5e48fae2f621eb12fd6adca8bf2af24cc73bc9d",
    "selection": "4802c58ea12c9f48892d54eb376d1ac5c2d88eabe812ec9930673f976785f6d7",
}
SOURCE_PINS = {
    "../retrieval-r2/retrieval.py": "ef0103867c05d920a587dae858e6d25fc62f748ae294851bff48c3d19417e813",
    "../retrieval-r3/train_visual.py": "0bb23a98c3d747b87252f72c1b3765a08ecb367e833f0a815c8bb084a1d05b50",
    "../retrieval-r3/visual_adapter.py": "933de9d32de9782e4b399ef7f5d0a87c94e8389dd65f7ed1eae96a541f0250b1",
}
MODEL = {"model_id": "google/siglip2-base-patch16-224",
         "model_revision": "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
         "model_weights_sha256": "612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b"}


def sha256(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular_input_file_required:" + path.name)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_constant(value):
    raise ValueError("nonfinite_json_constant:" + value)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_reject_constant)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def verify_pin(path, expected, label):
    actual = sha256(path)
    if actual != expected:
        raise ValueError("immutable_input_hash_mismatch:" + label)
    return actual


def load_frozen_modules():
    """Use exact earlier loaders; never weaken their source/cached-feature gates."""
    for relative, expected in SOURCE_PINS.items():
        verify_pin(ROOT / relative, expected, relative)
    def module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        sys.modules[name] = value
        spec.loader.exec_module(value)
        return value
    visual = module("meta_r4_frozen_visual_adapter", R3 / "visual_adapter.py")
    old = sys.modules.get("visual_adapter")
    sys.modules["visual_adapter"] = visual
    try:
        training = module("meta_r4_frozen_train_visual", R3 / "train_visual.py")
    finally:
        if old is None:
            sys.modules.pop("visual_adapter", None)
        else:
            sys.modules["visual_adapter"] = old
    return visual, training


def validate_records(records, *, allowed_splits):
    if not isinstance(records, list) or not records:
        raise ValueError("nonempty_dataset_records_required")
    ids = set()
    for record in records:
        if not isinstance(record, dict) or record.get("split") not in allowed_splits:
            raise ValueError("unexpected_record_split")
        pid, family = record.get("product_id"), record.get("family_id")
        if not isinstance(pid, str) or not pid or pid in ids or not isinstance(family, str) or not family:
            raise ValueError("unique_product_and_family_ids_required")
        ids.add(pid)
        views = record.get("views")
        if not isinstance(views, list) or len(views) != 2:
            raise ValueError("two_distinct_source_views_required")
        hashes = [view.get("sha256") if isinstance(view, dict) else None for view in views]
        if any(not isinstance(h, str) or re.fullmatch(r"[0-9a-f]{64}", h) is None for h in hashes) or hashes[0] == hashes[1]:
            raise ValueError("two_distinct_image_hashes_required")
    return dict(Counter(r["split"] for r in records))


def validate_split_separation(partitions):
    """Check IDs, connected families and BOTH source images across every split."""
    seen = {"product": {}, "family": {}, "image": {}}
    for split, records in partitions.items():
        for record in records:
            entries = {"product": [record["product_id"]], "family": [record["family_id"]],
                       "image": [v["sha256"] for v in record["views"]]}
            for kind, values in entries.items():
                for value in values:
                    previous = seen[kind].get(value)
                    if previous is not None and previous != split:
                        raise ValueError(kind + "_split_overlap:" + previous + ":" + split)
                    seen[kind][value] = split
    return {"product_disjoint": True, "family_disjoint": True, "image_hash_disjoint": True,
            "partitions": list(partitions), "unique_counts": {kind: len(values) for kind, values in seen.items()}}


def load_cache(path, records, dataset_sha):
    receipt_path = Path(path).with_suffix(".json")
    receipt = read_json(receipt_path)
    if (receipt.get("dataset_sha256") != dataset_sha or receipt.get("feature_sha256") != sha256(path)
            or receipt.get("product_order") != [r["product_id"] for r in records]
            or any(receipt.get(k) != v for k, v in MODEL.items())
            or receipt.get("encoder_frozen") is not True or receipt.get("image_inference_executed") is not True):
        raise ValueError("feature_receipt_provenance_or_order_mismatch")
    with np.load(path, allow_pickle=False) as archive:
        # Query-side published hints are deliberately not loaded.
        arrays = {key: embedding_matrix(archive[key], rows=len(records), dimension=768).copy()
                  for key in ("query", "gallery", "text")}
    for key, array in arrays.items():
        if receipt.get("feature_shapes", {}).get(key) != list(array.shape):
            raise ValueError("feature_receipt_shape_mismatch")
    return arrays, {"features_sha256": sha256(path), "receipt_sha256": sha256(receipt_path),
                    "model": dict(MODEL), "product_order_sha256": hashlib.sha256(
                        json.dumps(receipt["product_order"], separators=(",", ":")).encode()).hexdigest(),
                    "pixel_inference_executed_by_original_encoder": True,
                    "query_hint_array_loaded": False}


def load_inputs(prior_data, prior_features, fresh_data, fresh_features, training_root):
    paths = {"prior_dataset": Path(prior_data) / "dataset.json", "prior_features": Path(prior_features),
             "fresh_dataset": Path(fresh_data) / "dataset.json", "fresh_features": Path(fresh_features),
             "selection": Path(training_root) / "selection.json"}
    hashes = {name: verify_pin(path, PINS[name], name) for name, path in paths.items()}
    for kind in ("prior", "fresh"):
        seal = paths[kind + "_dataset"].with_name("dataset.sha256")
        if seal.read_text().strip() != hashes[kind + "_dataset"]:
            raise ValueError(kind + "_dataset_seal_mismatch")
        hashes[kind + "_dataset_seal"] = sha256(seal)
    prior, fresh = read_json(paths["prior_dataset"]), read_json(paths["fresh_dataset"])
    prior_records, fresh_records = prior["records"], fresh["records"]
    pc = validate_records(prior_records, allowed_splits={"train", "dev", "cal", "test", "ood"})
    fc = validate_records(fresh_records, allowed_splits={"cal", "test"})
    if (pc != prior.get("counts") or fc != fresh.get("counts")
            or fresh.get("kind") != "meta.public-abo-fresh-r3-holdout"
            or fresh.get("prior_dataset_sha256") != hashes["prior_dataset"]):
        raise ValueError("dataset_contract_or_counts_mismatch")
    # Includes every historical R2 partition, not only the rows fitted in R4.
    all_partitions = {"r2_" + s: [r for r in prior_records if r["split"] == s]
                      for s in ("train", "dev", "cal", "test", "ood")}
    all_partitions.update({"r3_" + s: [r for r in fresh_records if r["split"] == s] for s in ("cal", "test")})
    separation = validate_split_separation(all_partitions)
    visual, train_visual = load_frozen_modules()
    helpers = train_visual.load_r2_helpers()
    prior_views, _, original_binding = train_visual.load_train_dev(Path(prior_data), Path(prior_features), helpers)
    prior_arrays, prior_receipt = load_cache(prior_features, prior_records, hashes["prior_dataset"])
    fresh_arrays, fresh_receipt = load_cache(fresh_features, fresh_records, hashes["fresh_dataset"])
    selection = read_json(paths["selection"])
    if selection.get("dataset_sha256") != hashes["prior_dataset"] or selection.get("feature_sha256") != hashes["prior_features"]:
        raise ValueError("r3_adapter_training_input_mismatch")
    if selection.get("protocol_sha256") != train_visual.sha_bytes(train_visual.canonical(train_visual.PROTOCOL)):
        raise ValueError("r3_training_protocol_mismatch")
    for relative, expected in SOURCE_PINS.items():
        selection_name = relative.replace("../retrieval-r3/", "")
        if selection.get("source_hashes", {}).get(selection_name) != expected:
            raise ValueError("r3_selection_source_mismatch:" + selection_name)
    weights = visual.load_selected(selection, training_root)
    if weights is not None:
        hashes["selected_checkpoint"] = sha256(Path(training_root) / selection["primary"]["checkpoint"])
    partitions = {}
    for split in ("train", "dev", "cal", "test"):
        records, arrays = (prior_records, prior_arrays) if split in ("train", "dev") else (fresh_records, fresh_arrays)
        idx = np.asarray([i for i, r in enumerate(records) if r["split"] == split], dtype=np.int64)
        subset = {key: value[idx] for key, value in arrays.items()}
        if split in prior_views:
            # Reuse the original R3 loader's precise train/dev normalization.
            subset.update(prior_views[split])
        partitions[split] = {"records": [records[i] for i in idx], "arrays": subset}
    admission = validate_split_separation({s: p["records"] for s, p in partitions.items()})
    admission.update({"all_historical_partitions_checked": separation, "immutable_dataset_and_cache_pins_verified": True,
                      "fresh_metadata_graph_exclusion_bound_by_original_dataset_hash": True,
                      "raw_pixel_bytes_rechecked_this_run": False})
    binding = {"input_hashes": hashes, "prior_feature_receipt": prior_receipt,
               "fresh_feature_receipt": fresh_receipt, "r3_load_train_dev": original_binding,
               "r3_selected_model": selection["primary"], "raw_partition_counts": {"r2": pc, "r3": fc}}
    return partitions, weights, visual, admission, binding


def export_partition(split, records, arrays, weights, visual_module, writer, *, limit, policy="rrf"):
    query, gallery, text = (arrays[k] for k in ("query", "gallery", "text"))
    frozen = query @ gallery.T
    image_text = query @ text.T
    # Explicit identity uses exact frozen scores, not an extra normalization.
    adapted = frozen if weights is None else visual_module.project_features(query, weights) @ visual_module.project_features(gallery, weights).T
    ids = [r["product_id"] for r in records]
    candidates, ranks = select_candidates(frozen, adapted, image_text, ids, limit=limit, policy=policy)
    feats = candidate_features(frozen, adapted, image_text, candidates, ranks=ranks)
    diagnostics, hit_count = [], 0
    for qi, record in enumerate(records):
        found = False
        for ci, gi in enumerate(candidates[qi]):
            candidate = records[int(gi)]
            label = int(record["product_id"] == candidate["product_id"])
            found |= bool(label)
            row = {"split": split, "query_id": record["product_id"], "query_family": record["family_id"],
                   "candidate_id": candidate["product_id"], "candidate_family": candidate["family_id"], "label": label,
                   "baseline_rank": int(ranks["adapted"][qi, gi]), "visual_rank": int(ranks["visual"][qi, gi]),
                   "text_rank": int(ranks["text"][qi, gi])}
            row.update({name: format(float(feats[name][qi, ci]), ".17g") for name in FEATURE_NAMES})
            writer.writerow(row)
        hit_count += int(found)
        diagnostics.append({"query_id": record["product_id"], "candidate_count": len(candidates[qi]),
                            "truth_in_candidates": found, "baseline_truth_rank": int(ranks["adapted"][qi, qi])})
    report = {"queries": len(records), "families": len({r["family_id"] for r in records}),
              "rows": int(candidates.size), "candidate_limit": int(candidates.shape[1]), "candidate_policy": policy,
              "queries_with_truth_candidate": hit_count, "queries_missing_truth_candidate": len(records) - hit_count,
              "candidate_recall": hit_count / len(records),
              "baseline_complete_gallery_recall": {str(k): float(np.mean(np.diag(ranks["adapted"]) <= k)) for k in (1, 5, 10, 20, 50, 100)},
              "oracle_positive_injected": False}
    return report, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-data", type=Path, required=True, help="R2 directory with dataset.json and dataset.sha256")
    parser.add_argument("--prior-features", type=Path, required=True, help="R2 features.npz, beside original features.json")
    parser.add_argument("--fresh-data", type=Path, required=True, help="Historical R3 directory with dataset.json and dataset.sha256")
    parser.add_argument("--fresh-features", type=Path, required=True, help="R3 features.npz, beside original features.json")
    parser.add_argument("--training", type=Path, required=True, help="Original R3 selection.json and selected checkpoint root")
    parser.add_argument("--output", type=Path, required=True, help="New or empty output directory; historical output is never overwritten")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument("--candidate-policy", choices=("rrf", "adapted_topk"), default="rrf",
                        help="Explicit predeclared pool: original RRF (default) or stable adapted-score top-k")
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None or not 1 <= args.max_candidates <= 100:
        parser.error("exact source commit and candidate bound 1..100 required")
    if args.output.is_symlink() or (args.output.exists() and any(args.output.iterdir())):
        parser.error("preserve previous evidence; output must be new or empty")
    contract = read_json(ROOT / "contract.json")
    if contract.get("features") != list(FEATURE_NAMES) or contract.get("required_columns") != list(REQUIRED_COLUMNS):
        raise ValueError("shared_candidate_contract_changed")
    started = time.monotonic()
    partitions, weights, visual_module, admission, binding = load_inputs(
        args.prior_data, args.prior_features, args.fresh_data, args.fresh_features, args.training)
    args.output.mkdir(parents=True, exist_ok=True)
    csv_path = args.output / "candidates.csv"
    stats, query_diagnostics = {}, {}
    with csv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for split in ("train", "dev", "cal", "test"):
            stats[split], query_diagnostics[split] = export_partition(
                split, partitions[split]["records"], partitions[split]["arrays"], weights, visual_module, writer,
                limit=args.max_candidates, policy=args.candidate_policy)
            handle.flush()
            print(json.dumps({"stage": "candidate_partition", "split": split, **stats[split]}), flush=True)
    diagnostic_path = args.output / "query_diagnostics.json"
    write_json(diagnostic_path, query_diagnostics)
    source_hashes = {name: sha256(ROOT / name) for name in ("features.py", "prepare_candidates.py", "contract.json")}
    source_hashes.update({name: sha256(ROOT / name) for name in SOURCE_PINS})
    manifest = {"schema_version": 1, "kind": "meta.r4.actual_candidate_features", "work_id": WORK_ID,
                "source_commit": args.source_commit, "source_hashes": source_hashes,
                "input_sha256": sha256(csv_path), "input_file": "candidates.csv", "columns": list(CSV_COLUMNS),
                "feature_names": list(FEATURE_NAMES), "admission": admission, "counts": {s: x["queries"] for s, x in stats.items()},
                "partitions": stats, "binding": binding, "query_diagnostics_sha256": sha256(diagnostic_path),
                "selection": {"candidate_policy": args.candidate_policy,
                              "method": "top_limit_of_RRF_union_of_each_retriever_top_limit" if args.candidate_policy == "rrf" else "stable_adapted_rank_top_limit",
                              "rrf_constant": 60 if args.candidate_policy == "rrf" else None,
                              "max_candidates": args.max_candidates,
                              "tie_break": ["adapted_rank", "visual_rank", "text_rank", "candidate_id"] if args.candidate_policy == "rrf" else ["source_bound_gallery_order"],
                              "per_method_ranks": {"adapted": "baseline_rank", "visual": "visual_rank", "text": "text_rank"},
                              "oracle_positive_injected": False},
                "transduction": {"enabled": True, "features": ["f_reverse_rank", "f_density"],
                                 "scope": "same_split_unlabeled_query_features_and_catalog_only",
                                 "cross_split_statistics": False, "streaming_device_qualification": False},
                "evidence": {"mode": "real_previously_encoded_public_ABO_images", "query_metadata_features": False,
                             "query_ocr_executed": False, "multiview_helper_executed": False,
                             "new_pixel_inference_executed": False, "historical_test_diagnosis_only": True,
                             "fresh_independent_qualification": False, "physical_identity_verified": False,
                             "action_authorized": False, "production_activation": False},
                "seconds": time.monotonic() - started}
    write_json(args.output / "data_manifest.json", manifest)
    print(json.dumps({"stage": "CANDIDATES_EXPORTED", "input_sha256": manifest["input_sha256"],
                      "counts": manifest["counts"], "historical_test_diagnosis_only": True}), flush=True)


if __name__ == "__main__":
    main()
