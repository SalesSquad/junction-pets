#!/usr/bin/env python3
"""Six source-pinned, synthetic-only adversarial rounds for Chibi Lens field gate.

This verifies research safety/claims from PR #208, NOT a trained full-frame
detector, camera accuracy, consent, identity, provider attestation, or release.
No live images, private information, OCR, model API, network, or GPU involved.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

SOURCE_COMMIT = "2e338f72ac6e912b23b38b66526c2cb645852868"
SOURCE_BLOB = "7267e11a1bdc211dbede9d09374ceed7a61f4692"
WORK_ID = "CHIBI-LENS-SIX-FAULT-20261115"
ROUNDS = (
    "exposed_test_scenes",
    "gt_assisted_training_leak",
    "reused_frames_and_capture",
    "new_unknown_false_acceptance",
    "zero_utility_abstention",
    "private_media_and_false_identity",
)


def file_blob(path: Path) -> str:
    completed = subprocess.run(
        ["git", "hash-object", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=True, timeout=10
    )
    return completed.stdout.strip()


def load_gate(path: Path):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Missing ordinary frozen full-frame gate")
    blob = file_blob(path)
    if blob != SOURCE_BLOB:
        raise RuntimeError(f"Wrong source gate blob {blob}; expected {SOURCE_BLOB}")
    spec = importlib.util.spec_from_file_location("lens_field_gate_source_208", path)
    if not spec or not spec.loader:
        raise RuntimeError("Could not load exact gate file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "qualify"):
        raise RuntimeError("Original source gate missing")
    return module


def frozen_receipt(round_id: int) -> dict:
    # Synthetic large counts are deliberately UNREALISTIC per 40-frame
    # physical scene; they probe the existing Wilson aggregation only.
    # They cannot certify calibrated frame independence or deploy safety.
    salt = f"fieldgate-adversarial-{WORK_ID}-round-{round_id}"
    sha = lambda v: hashlib.sha256(f"{salt}:{v}".encode("utf8")).hexdigest()
    scenes = []
    for scene in range(4):
        scenes.append({
            "scene_id": f"synthetic-scene-{round_id}-{scene}",
            "device": "simulated-domain-a" if scene % 2 == 0 else "simulated-domain-b",
            "capture_id": f"synthetic-capture-{round_id}-{scene}",
            "frame_sha256": [sha(f"field:{scene}:{frame}") for frame in range(40)],
            "independent_frames": 40,
            "known_objects": 3000,
            "known_correct_accepted": 3000,
            "unknown_objects": 3000,
            "unknown_falsely_accepted": 0,
            "accepted_proposals": 3000,
            "accepted_correct": 3000,
            "annotated_detectable_objects": 3000,
            "detector_true_positives_iou50": 3000,
        })
    return {
        "schema": "chibi.lens.full-frame-field-receipt.v1",
        "source_commit": SOURCE_COMMIT,
        "model_sha256": sha("model"),
        "detector_sha256": sha("detector"),
        "annotation_sha256": sha("annotation"),
        "license_status": "approved_for_local_evaluation",
        "sealed_test": True,
        "previously_seen_test": False,
        "full_frame_proposals_without_gt": True,
        "trained_or_calibrated_on_test": False,
        "contains_family_media": False,
        "private_ocr_uploaded": False,
        "physical_identity_verified": False,
        "agent_action_authorized": False,
        "unknown_classes_in_calibration": ["synthetic-unknown-cal"],
        "unknown_classes_in_test": ["synthetic-unknown-test"],
        "known_classes": ["12", "15"],
        "frozen_fit_frame_sha256": [sha("fit-0")],
        "frozen_fit_capture_ids": [f"synthetic-train-capture-{round_id}"],
        "scenes": scenes,
    }


def malicious_change(round_id: int, source: dict) -> tuple[dict, set[str]]:
    data = copy.deepcopy(source)
    if round_id == 0:
        data["sealed_test"] = False
        data["previously_seen_test"] = True
        expected = {"UNSEALED_OR_ALREADY_EXPOSED_TEST"}
    elif round_id == 1:
        data["full_frame_proposals_without_gt"] = False
        data["trained_or_calibrated_on_test"] = True
        expected = {"GROUND_TRUTH_ASSISTED_LOCALIZATION", "MODEL_OR_THRESHOLD_TEST_LEAKAGE"}
    elif round_id == 2:
        data["scenes"][0]["capture_id"] = data["frozen_fit_capture_ids"][0]
        data["scenes"][0]["frame_sha256"][0] = data["frozen_fit_frame_sha256"][0]
        expected = {"TRAIN_CALIBRATION_CAPTURE_LEAKAGE", "REUSED_OR_FIT_FRAME_LEAKAGE"}
    elif round_id == 3:
        data["unknown_classes_in_calibration"] = ["synthetic-unknown-test"]
        for scene in data["scenes"]:
            scene["unknown_falsely_accepted"] = 120
            scene["accepted_proposals"] += 120
        expected = {
            "UNKNOWN_CLASSES_NOT_EXCLUDED_FROM_CALIBRATION",
            "STATISTICALLY_UNQUALIFIED_unknown_false_acceptance",
            "PER_SCENE_RISK_OR_UTILITY",
        }
    elif round_id == 4:
        for scene in data["scenes"]:
            scene["known_correct_accepted"] = 0
            scene["accepted_correct"] = 0
            scene["accepted_proposals"] = 0
            scene["detector_true_positives_iou50"] = 0
        expected = {"ZERO_UTILITY_ABSTENTION", "PER_SCENE_RISK_OR_UTILITY"}
    elif round_id == 5:
        data["contains_family_media"] = True
        data["private_ocr_uploaded"] = True
        data["physical_identity_verified"] = True
        data["agent_action_authorized"] = True
        data["license_status"] = "unverified"
        expected = {
            "PRIVATE_DATA_BOUNDARY",
            "UNSUPPORTED_IDENTITY_OR_ACTION_CLAIM",
            "UNVERIFIED_RIGHTS",
        }
    else:
        raise ValueError("Only six preregistered tests")
    return data, expected


def run(gate_script: Path, out_path: Path | None = None) -> dict:
    gate = load_gate(gate_script)
    outcomes = []
    for i, label in enumerate(ROUNDS):
        control = gate.qualify(frozen_receipt(i))
        if control.get("passed") is not True:
            raise RuntimeError(f"Research-only synthetic control {i} no longer valid")
        if control.get("signedExternalAttestation") is not False or \
           control.get("noModelPromotionInThisTool") is not True:
            raise RuntimeError(f"Synthetic control {i} falsely claims deployment approval")
        candidate, required = malicious_change(i, frozen_receipt(i))
        failure = gate.qualify(candidate)
        reasons = set(failure.get("reasons", []))
        if failure.get("passed") is not False or not reasons.issuperset(required):
            raise RuntimeError(f"Unsafe defect: {label}: {sorted(reasons)}; required {required}")
        if failure.get("noProductionChange") is not True or \
           failure.get("noModelPromotionInThisTool") is not True or \
           failure.get("signedExternalAttestation") is not False:
            raise RuntimeError(f"Unexpected provider or deployment claim in {label}")
        outcomes.append({
            "round": i + 1, "faultFamily": label,
            "syntheticControlInternalThresholdPassed": True,
            "maliciousOutcome": "DENIED",
            "requiredFailures": sorted(required), "actualReasons": sorted(reasons),
            "realWorldFieldQualification": False,
        })
    receipt = {
        "schema": "junction.chibi-lens.six-adversarial.v1",
        "workId": WORK_ID, "pr208SourceCommit": SOURCE_COMMIT,
        "pr208GateGitBlob": SOURCE_BLOB,
        "allPass": True, "rounds": outcomes,
        "syntheticControls": 6, "mutatedFaultCasesDenied": 6,
        "zeroNewImagesOrRealModelTraining": True,
        "modelAccuracyOrProductQualityProven": False,
        "sourceReportedNotProviderAttested": True,
        "noModelDeploymentOrIdentityAuthorization": True,
    }
    if out_path is not None:
        if out_path.exists():
            raise FileExistsError(f"No overwrite of previous source evidence: {out_path}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("x", encoding="utf8") as output:
            json.dump(receipt, output, indent=2, sort_keys=True)
            output.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.gate, args.output)
    print(json.dumps({
        "sourceCommit": result["pr208SourceCommit"],
        "rounds": len(result["rounds"]),
        "faultsDenied": result["mutatedFaultCasesDenied"],
        "syntheticOnly": True,
        "fieldQualified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
