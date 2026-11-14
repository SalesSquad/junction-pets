#!/usr/bin/env python3
"""Repro tests for field readiness; passing a green CI job is insufficient."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest

SRC=Path(__file__).with_name("lens_field_gate.py")
sp=importlib.util.spec_from_file_location("hb_field_gate",SRC)
gate=importlib.util.module_from_spec(sp)
sp.loader.exec_module(gate)


def frame_hash(value):
    return hashlib.sha256(value.encode("utf8")).hexdigest()


def scene(i,dev):
    return {
      "scene_id":f"independent-scene-{i}",
      "device":dev,
      "capture_id":f"sealed-capture-{i}",
      "frame_sha256":[frame_hash(f"sealed:{i}:{j}") for j in range(1000)],
      "independent_frames":1000,
      "known_objects":5000,
      "known_correct_accepted":4800,
      "unknown_objects":5000,
      "unknown_falsely_accepted":0,
      "accepted_proposals":4800,
      "accepted_correct":4800,
      "annotated_detectable_objects":5000,
      "detector_true_positives_iou50":4900,
    }


def fixture():
    return {
      "schema":"chibi.lens.full-frame-field-receipt.v1",
      "source_commit":"a"*40,
      "model_sha256":"b"*64,
      "detector_sha256":"c"*64,
      "annotation_sha256":"d"*64,
      "license_status":"approved_for_local_evaluation",
      "sealed_test":True,"previously_seen_test":False,
      "full_frame_proposals_without_gt":True,
      "trained_or_calibrated_on_test":False,
      "contains_family_media":False,"private_ocr_uploaded":False,
      "physical_identity_verified":False,"agent_action_authorized":False,
      "known_classes":[12,15],
      "frozen_fit_frame_sha256":[frame_hash("train:0"),frame_hash("calibration:0")],
      "frozen_fit_capture_ids":["training-capture","calibration-capture"],
      "unknown_classes_in_calibration":[3,22],
      "unknown_classes_in_test":[23,44],
      "scenes":[scene(i,"camera-1" if i<2 else "camera-2") for i in range(4)],
    }


class FieldGate(unittest.TestCase):
    def test_synthetic_fully_qualified_shape_passes(self):
        result=gate.qualify(fixture())
        self.assertTrue(result["passed"],result["reasons"])
        self.assertFalse(result["noModelPromotionInThisTool"] is False)
        self.assertEqual(result["cameraDomains"],2)

    def test_zero_utility_is_not_low_risk_success(self):
        doc=fixture()
        for row in doc["scenes"]:
            row["known_correct_accepted"]=row["accepted_correct"]=row["accepted_proposals"]=0
        result=gate.qualify(doc)
        self.assertFalse(result["passed"])
        self.assertIn("ZERO_UTILITY_ABSTENTION",result["reasons"])

    def test_confounded_unknown_calibration_rejected(self):
        doc=fixture()
        doc["unknown_classes_in_test"]=[22,23]
        self.assertIn("UNKNOWN_CLASSES_NOT_EXCLUDED_FROM_CALIBRATION",
                      gate.qualify(doc)["reasons"])

    def test_annotated_gt_as_detection_input_rejected(self):
        doc=fixture()
        doc["full_frame_proposals_without_gt"]=False
        self.assertIn("GROUND_TRUTH_ASSISTED_LOCALIZATION",
                      gate.qualify(doc)["reasons"])

    def test_one_exposed_scene_not_new_proof(self):
        doc=fixture()
        doc["scenes"]=doc["scenes"][:1]
        doc["previously_seen_test"]=True
        r=gate.qualify(doc)
        self.assertIn("UNSEALED_OR_ALREADY_EXPOSED_TEST",r["reasons"])
        self.assertIn("NOT_ENOUGH_INDEPENDENT_SCENES",r["reasons"])
        self.assertIn("NOT_ENOUGH_CAMERA_DOMAINS",r["reasons"])

    def test_unverified_rights_and_private_ocr_rejected(self):
        doc=fixture()
        doc["license_status"]="unknown"
        doc["private_ocr_uploaded"]=True
        r=gate.qualify(doc)
        self.assertIn("UNVERIFIED_RIGHTS",r["reasons"])
        self.assertIn("PRIVATE_DATA_BOUNDARY",r["reasons"])

    def test_unknown_object_fpr_over_one_pct_fails_even_though_precision_high(self):
        doc=fixture()
        for r in doc["scenes"]:
            r["unknown_falsely_accepted"]=75
            r["accepted_proposals"]=r["accepted_correct"]+75
        result=gate.qualify(doc)
        self.assertFalse(result["passed"])
        self.assertIn("STATISTICALLY_UNQUALIFIED_unknown_false_acceptance",
                      result["reasons"])

    def test_new_detector_below_iou_threshold_fails(self):
        doc=fixture()
        for row in doc["scenes"]:
            row["detector_true_positives_iou50"]=2500
        self.assertIn("STATISTICALLY_UNQUALIFIED_detector_recall_iou50",
                      gate.qualify(doc)["reasons"])

    def test_duplicate_scene_or_impossible_confusion_fails(self):
        doc=fixture()
        doc["scenes"][1]["scene_id"]=doc["scenes"][0]["scene_id"]
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            gate.qualify(doc)
        doc=fixture()
        doc["scenes"][0]["accepted_correct"]=9000
        with self.assertRaisesRegex(ValueError,"Inconsistent"):
            gate.qualify(doc)

    def test_source_with_no_hash_or_no_sealed_run_fails(self):
        doc=fixture()
        doc["detector_sha256"]=""
        doc["sealed_test"]=False
        r=gate.qualify(doc)
        self.assertIn("MISSING_IMMUTABLE_PROVENANCE_detector_sha256",r["reasons"])
        self.assertIn("UNSEALED_OR_ALREADY_EXPOSED_TEST",r["reasons"])

    def test_wilson_does_not_overstate_small_sample(self):
        low,hi=gate.wilson_interval(74,77)
        self.assertLess(low,.97)
        self.assertGreater(hi,low)
        _,upper=gate.wilson_interval(2,142)
        self.assertGreater(upper,.01)

    def test_duplicate_heldout_frame_hashes_not_claimed_independent(self):
        doc=fixture()
        doc["scenes"][1]["frame_sha256"][0]=doc["scenes"][0]["frame_sha256"][0]
        reasons=gate.qualify(doc)["reasons"]
        self.assertIn("REUSED_OR_FIT_FRAME_LEAKAGE",reasons)
        self.assertIn("FRAMES_NOT_GLOBALLY_UNIQUE",reasons)

    def test_training_calibration_frame_or_capture_leakage(self):
        doc=fixture()
        doc["frozen_fit_frame_sha256"].append(doc["scenes"][3]["frame_sha256"][0])
        doc["scenes"][2]["capture_id"]="calibration-capture"
        reasons=gate.qualify(doc)["reasons"]
        self.assertIn("REUSED_OR_FIT_FRAME_LEAKAGE",reasons)
        self.assertIn("TRAIN_CALIBRATION_CAPTURE_LEAKAGE",reasons)

    def test_frame_count_mismatch_and_missing_fit_provenance(self):
        doc=fixture()
        doc["scenes"][0]["frame_sha256"]=doc["scenes"][0]["frame_sha256"][:-1]
        doc.pop("frozen_fit_frame_sha256")
        reasons=gate.qualify(doc)["reasons"]
        self.assertIn("FRAME_COUNT_NOT_VERIFIABLE",reasons)
        self.assertIn("MISSING_OR_INVALID_FIT_PROVENANCE",reasons)

    def test_background_false_positives_are_measured_not_silently_discarded(self):
        doc=fixture()
        for row in doc["scenes"]:
            row["accepted_proposals"]=11000
        reasons=gate.qualify(doc)["reasons"]
        self.assertIn("STATISTICALLY_UNQUALIFIED_accepted_precision",reasons)


    def test_missing_false_flags_fail_closed(self):
        doc=fixture()
        doc.pop("contains_family_media")
        doc["private_ocr_uploaded"]="false"
        doc.pop("agent_action_authorized")
        doc["sealed_test"]="true"
        reasons=gate.qualify(doc)["reasons"]
        self.assertIn("PRIVATE_DATA_BOUNDARY",reasons)
        self.assertIn("UNSUPPORTED_IDENTITY_OR_ACTION_CLAIM",reasons)
        self.assertIn("UNSEALED_OR_ALREADY_EXPOSED_TEST",reasons)


if __name__=="__main__":
    unittest.main()
