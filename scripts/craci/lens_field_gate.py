#!/usr/bin/env python3
"""Fail-closed Chibi Lens *full-frame* field qualification gate.

Distinct from R-model training success: a low false-accept count with zero
coverage or GT-assisted proposals NEVER qualifies. The required signal is
from a sealed scene/device-heldout full-frame test, with unseen unknown classes.
No production action or OAuth scope can be granted by this report.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
import re
from pathlib import Path

MIN_TEST_SCENES=4
MIN_DEVICES=2
MIN_FRAMES_PER_SCENE=40
TARGET_ACCEPTED_PRECISION=.97
TARGET_KNOWN_COVERAGE=.80
MAX_UNKNOWN_FALSE_ACCEPT=.01
MIN_DETECTION_RECALL=.90
Z95=1.959963984540054

def canonical_class_id(token)->str:
    # A declared object class must have one representation across JSON int and
    # string encodings. Class 23, "23", and "023" are the SAME object ID.
    if isinstance(token,bool):
        raise ValueError("Boolean is not a class ID")
    if isinstance(token,int) and token>=0:
        return "id:"+str(token)
    if isinstance(token,str):
        if re.fullmatch(r"[0-9]{1,20}",token):
            return "id:"+str(int(token))
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}",token):
            return "symbol:"+token
    raise ValueError("Noncanonical or unsupported object class ID")


def wilson_interval(successes:int,trials:int)->tuple[float,float]:
    if not isinstance(successes,int) or not isinstance(trials,int) or trials<=0 or successes<0 or successes>trials:
        raise ValueError("Invalid integer binomial counts")
    p=successes/trials
    z2=Z95*Z95
    denominator=1+z2/trials
    centre=(p+z2/(2*trials))/denominator
    radius=(Z95/denominator)*math.sqrt(p*(1-p)/trials+z2/(4*trials*trials))
    return max(0,centre-radius),min(1,centre+radius)


def qualify(data:dict)->dict:
    reasons=[]
    if not isinstance(data,dict) or data.get("schema")!="chibi.lens.full-frame-field-receipt.v1":
        raise ValueError("Untrusted field receipt")
    source_keys={"source_commit":40,"model_sha256":64,
                 "detector_sha256":64,"annotation_sha256":64}
    for key,length in source_keys.items():
        value=data.get(key)
        if not isinstance(value,str) or not re.fullmatch("[a-f0-9]{"+str(length)+"}",value):
            reasons.append(f"MISSING_IMMUTABLE_PROVENANCE_{key}")
    if data.get("license_status")!="approved_for_local_evaluation":
        reasons.append("UNVERIFIED_RIGHTS")
    if (data.get("sealed_test") is not True or
        data.get("previously_seen_test") is not False):
        reasons.append("UNSEALED_OR_ALREADY_EXPOSED_TEST")
    if data.get("full_frame_proposals_without_gt") is not True:
        reasons.append("GROUND_TRUTH_ASSISTED_LOCALIZATION")
    if data.get("trained_or_calibrated_on_test") is not False:
        reasons.append("MODEL_OR_THRESHOLD_TEST_LEAKAGE")
    if (data.get("contains_family_media") is not False or
        data.get("private_ocr_uploaded") is not False):
        reasons.append("PRIVATE_DATA_BOUNDARY")
    if (data.get("physical_identity_verified") is not False or
        data.get("agent_action_authorized") is not False):
        reasons.append("UNSUPPORTED_IDENTITY_OR_ACTION_CLAIM")
    cal_unknown=data.get("unknown_classes_in_calibration")
    test_unknown=data.get("unknown_classes_in_test")
    known=data.get("known_classes")
    try:
        if (not isinstance(cal_unknown,list) or not isinstance(test_unknown,list) or
            not isinstance(known,list) or not cal_unknown or not test_unknown or not known):
            raise ValueError("Missing object class lists")
        cal_ids={canonical_class_id(x) for x in cal_unknown}
        test_ids={canonical_class_id(x) for x in test_unknown}
        known_ids={canonical_class_id(x) for x in known}
        if (len(cal_ids)!=len(cal_unknown) or len(test_ids)!=len(test_unknown) or
            len(known_ids)!=len(known) or cal_ids&test_ids or
            known_ids&(cal_ids|test_ids)):
            raise ValueError("Overlapping or duplicate object class IDs")
    except (TypeError,ValueError):
        reasons.append("UNKNOWN_CLASSES_NOT_EXCLUDED_FROM_CALIBRATION")
    scenes=data.get("scenes")
    if not isinstance(scenes,list) or not 1<=len(scenes)<=64:
        raise ValueError("No or unbounded per-physical-scene field evidence")

    # A scene name or an aggregate frame count does NOT prove that a frame
    # was never in the training/calibration data, or repeated under a new
    # scene label. Bind actual frame SHA-256 and immutable capture IDs.
    fit_frames=data.get("frozen_fit_frame_sha256")
    fit_captures=data.get("frozen_fit_capture_ids")
    fit_scenes=data.get("frozen_fit_scene_ids")
    valid_scene=lambda x: isinstance(x,str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",x) is not None
    if (not isinstance(fit_scenes,list) or not 1<=len(fit_scenes)<=10000 or
        not all(valid_scene(x) for x in fit_scenes) or
        len(set(fit_scenes))!=len(fit_scenes)):
        reasons.append("MISSING_OR_INVALID_FIT_SCENE_PROVENANCE")
        fit_scene_set=set()
    else:
        fit_scene_set=set(fit_scenes)
    valid_hash=lambda x: isinstance(x,str) and re.fullmatch(r"[a-f0-9]{64}",x) is not None
    valid_capture=lambda x: isinstance(x,str) and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}",x) is not None
    if (not isinstance(fit_frames,list) or not 1<=len(fit_frames)<=100000 or
        not all(valid_hash(x) for x in fit_frames) or
        len(set(fit_frames))!=len(fit_frames) or
        not isinstance(fit_captures,list) or not 1<=len(fit_captures)<=10000 or
        not all(valid_capture(x) for x in fit_captures) or
        len(set(fit_captures))!=len(fit_captures)):
        reasons.append("MISSING_OR_INVALID_FIT_PROVENANCE")
        fit_frame_set=set()
        fit_capture_set=set()
    else:
        fit_frame_set=set(fit_frames)
        fit_capture_set=set(fit_captures)
    ids=set()
    devices=set()
    captures=set()
    test_frames=set()
    totals=Counter()
    for record in scenes:
        if not isinstance(record,dict):
            raise ValueError("Invalid physical scene")
        scene_id=record.get("scene_id")
        device=record.get("device")
        capture=record.get("capture_id")
        hashes=record.get("frame_sha256")
        if not valid_scene(scene_id) or scene_id in ids:
            raise ValueError("Duplicate/missing physical scene")
        if not isinstance(device,str) or not device:
            raise ValueError("Missing camera/device group")
        if not valid_capture(capture) or capture in captures:
            raise ValueError("Duplicate/missing physical video capture")
        ids.add(scene_id);devices.add(device);captures.add(capture)
        if scene_id in fit_scene_set:
            reasons.append("TRAIN_CALIBRATION_PHYSICAL_SCENE_LEAKAGE")
        if capture in fit_capture_set:
            reasons.append("TRAIN_CALIBRATION_CAPTURE_LEAKAGE")
        if (not isinstance(hashes,list) or not 1<=len(hashes)<=100000 or
            not all(valid_hash(h) for h in hashes) or
            len(hashes)!=len(set(hashes))):
            reasons.append("MISSING_OR_DUPLICATE_SCENE_FRAME_HASHES")
        else:
            current=set(hashes)
            if current & (test_frames | fit_frame_set):
                reasons.append("REUSED_OR_FIT_FRAME_LEAKAGE")
            test_frames.update(current)
        fields=("independent_frames","known_objects","known_correct_accepted",
                "unknown_objects","unknown_falsely_accepted",
                "accepted_proposals","accepted_correct",
                "annotated_detectable_objects","detector_true_positives_iou50")
        n={}
        for field in fields:
            value=record.get(field)
            if not isinstance(value,int) or isinstance(value,bool) or value<0:
                raise ValueError(f"Malformed field metric: {field}")
            n[field]=value
            totals[field]+=value
        if (n["independent_frames"]<MIN_FRAMES_PER_SCENE or
            n["known_objects"]<30 or n["unknown_objects"]<30):
            reasons.append("SCENE_TOO_SMALL")
        if not isinstance(hashes,list) or len(hashes)!=n["independent_frames"]:
            reasons.append("FRAME_COUNT_NOT_VERIFIABLE")
        if (n["known_correct_accepted"]>n["known_objects"] or
            n["unknown_falsely_accepted"]>n["unknown_objects"] or
            n["accepted_correct"]!=n["known_correct_accepted"] or
            n["accepted_proposals"]<n["accepted_correct"]+n["unknown_falsely_accepted"] or
            n["detector_true_positives_iou50"]>n["annotated_detectable_objects"] or
            n["known_correct_accepted"]>n["detector_true_positives_iou50"]):
            raise ValueError("Inconsistent real-world confusion or localization counts")
    if len(ids)<MIN_TEST_SCENES:reasons.append("NOT_ENOUGH_INDEPENDENT_SCENES")
    if len(devices)<MIN_DEVICES:reasons.append("NOT_ENOUGH_CAMERA_DOMAINS")
    if len(test_frames)!=totals["independent_frames"]:
        reasons.append("FRAMES_NOT_GLOBALLY_UNIQUE")
    if totals["accepted_proposals"]<=0 or totals["known_correct_accepted"]<=0:
        reasons.append("ZERO_UTILITY_ABSTENTION")
    if totals["annotated_detectable_objects"]<=0:
        reasons.append("NO_DETECTOR_GROUND_TRUTH")

    intervals={}
    tuples=(
      ("accepted_precision",totals["accepted_correct"],totals["accepted_proposals"],TARGET_ACCEPTED_PRECISION,"lower"),
      ("known_coverage",totals["known_correct_accepted"],totals["known_objects"],TARGET_KNOWN_COVERAGE,"lower"),
      ("unknown_false_acceptance",totals["unknown_falsely_accepted"],totals["unknown_objects"],MAX_UNKNOWN_FALSE_ACCEPT,"upper"),
      ("detector_recall_iou50",totals["detector_true_positives_iou50"],totals["annotated_detectable_objects"],MIN_DETECTION_RECALL,"lower"),
    )
    for key,succ,n,goal,side in tuples:
        if n<=0:
            reasons.append(f"INSUFFICIENT_{key}")
            continue
        lo,hi=wilson_interval(succ,n)
        intervals[key]={"observed":succ/n,"lower95":lo,"upper95":hi,
                        "numerator":succ,"denominator":n}
        if (side=="lower" and lo<goal) or (side=="upper" and hi>goal):
            reasons.append(f"STATISTICALLY_UNQUALIFIED_{key}")
    # Safeguard scene outliers: aggregate numbers cannot conceal one
    # catastrophic camera environment. Do not use per-scene confidence intervals
    # with n<40 as a standalone authorization; require <=2% empirical
    # wrong proposals and >0 correct per scene as a _minimum_.
    for scene in scenes:
        accepted=scene["accepted_proposals"]
        correct=scene["known_correct_accepted"]
        wrong=accepted-correct
        if (correct==0 or accepted==0 or wrong/max(accepted,1)>.02):
            reasons.append("PER_SCENE_RISK_OR_UTILITY")
            break
    reasons=sorted(set(reasons))
    return {
       "schema":"chibi.lens.field-gate-outcome.v1",
       "passed":len(reasons)==0,
       "reasons":reasons,
       "sourceCommit":data.get("source_commit"),
       "testedDistinctScenes":len(ids),
       "cameraDomains":len(devices),
       "uniqueFrameCount":len(test_frames),
       "verifiedCaptureGroups":len(captures),
       "trainCalibrationFrameHashesPresent":len(fit_frame_set),
       "trainCalibrationCaptureIdsPresent":len(fit_capture_set),
       "trainCalibrationPhysicalSceneIdsPresent":len(fit_scene_set),
       "totals":dict(totals),
       "wilson95":intervals,
       "noProductionChange":True,
       "noModelPromotionInThisTool":True,
       "signedExternalAttestation":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    data=json.loads(a.receipt.read_text())
    report=qualify(data)
    if a.output.exists():
        raise RuntimeError("Refuse overwrite existing source-bound evaluation")
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"passed":report["passed"],"reasons":report["reasons"],
                      "scenes":report["testedDistinctScenes"],"intervals":report["wilson95"]},
                     sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
