#!/usr/bin/env python3
"""Verify the preserved R2 campaign, without retraining or model activation.

Checks hashes and cross-artifact bindings; it is not a signed attestation or a
claim that public catalog results transfer to real glasses.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    root = Path(__file__).resolve().parent
    results = root / "results"
    read = lambda name: json.loads((results / name).read_text())
    manifest = read("artifact-manifest.json")
    require(manifest["work_id"] == "META-LENS-TRAIN-20261114-R2", "wrong_work_id")
    for name, expected in manifest["files"].items():
        p = Path(name)
        require(not p.is_absolute() and ".." not in p.parts, "unsafe_artifact_path")
        data = (results / p).read_bytes()
        require(sha(data) == expected["sha256"] and len(data) == expected["bytes"], f"artifact_changed:{name}")
    for name, expected in manifest["source_sha256"].items():
        p = Path(name)
        require(not p.is_absolute() and ".." not in p.parts, "unsafe_source_path")
        require(sha((root / p).read_bytes()) == expected, f"executed_source_changed:{name}")
    dataset_bytes = gzip.decompress((results / "dataset.json.gz").read_bytes())
    dataset = json.loads(dataset_bytes)
    digest = sha(dataset_bytes)
    require(digest == "bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c", "dataset_changed")
    order = [r["product_id"] for r in dataset["records"]]
    require(len(order) == 6000 and len(set(order)) == 6000, "dataset_product_count")
    run = read("run-r2/report.json")
    dino = read("dino-r2/report.json")
    nemotron = read("nemotron-r2/report.json")
    arbitration = read("arbitration-r2/report.json")
    for report in (run, dino, nemotron, arbitration):
        require(report["status"] == "COMPLETED", "incomplete_run")
        require(report["dataset_sha256"] == digest, "report_dataset_mismatch")
        require(report["deployment_authorized"] is False and report["action_authorized"] is False, "authority_changed")
    require(run["feature_receipt"]["product_order"] == order, "siglip_order_mismatch")
    require(dino["product_order"] == order, "dino_order_mismatch")
    # The frozen metadata track encodes only calibration and evaluation rows.
    # Bind its exact order to the executed source's explicit partition filter.
    metadata_order = [r["product_id"] for r in dataset["records"] if r["split"] in {"cal", "test", "ood"}]
    require(len(metadata_order) == 1960 and nemotron["product_order"] == metadata_order, "nemotron_evaluation_order_mismatch")
    require(run["research_gate"]["passes"] is False, "original_failed_gate_was_changed")
    require(run["selection"]["partition"] == "dev" and run["selection"]["selected_seed"] == 31, "selection_changed")
    for item in run["training"]:
        require(item["trainable_parameters"] == 196608 and item["epochs_run"] == 12, "training_recipe_mismatch")
        require(item["max_observed_gradient_norm"] > 0 and item["encoder_frozen"] is True, "training_not_observed")
        checkpoint = results / "checkpoints" / Path(item["checkpoint"]).name
        require(sha(checkpoint.read_bytes()) == item["checkpoint_sha256"], "checkpoint_changed")
    require(arbitration["cache_sha256"]["siglip"] == run["feature_receipt"]["feature_sha256"], "arbitration_siglip_cache_mismatch")
    require(arbitration["cache_sha256"]["dino"] == dino["feature_sha256"], "arbitration_dino_cache_mismatch")
    require(nemotron["siglip_feature_sha256"] == run["feature_receipt"]["feature_sha256"], "nemotron_siglip_cache_mismatch")
    require(arbitration["actual_new_view_observed"] is False and arbitration["parameters_trained"] == 0, "arbitration_claim_changed")
    execution = read("execution-summary.json")
    require(execution["provider_status"] in ("offline", "discontinued", "deleted"), "own_gpu_not_stopped")
    require(execution["admitted_task_machines"] == 1, "machine_count_changed")
    require(execution["estimated_attributed_usd"] < execution["authorized_budget_usd"] == 50, "budget_exceeded")
    print(json.dumps({"status": "PASS", "work_id": manifest["work_id"], "artifacts_verified": len(manifest["files"]), "executed_source_files_verified": len(manifest["source_sha256"]), "dataset_sha256": digest, "research_gate": "FAIL_PRESERVED", "deployment_authorized": False, "signed_or_hosted_qualification": False}))


if __name__ == "__main__":
    main()
