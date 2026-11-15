#!/usr/bin/env python3
"""One-time SEALED real-scene12 objectness evaluation for BOP HB.

The trained model and calibration threshold are frozen on scenes5/9/10.
Inference on every scene12 RGB frame MUST finish and prediction evidence be
written before source scene12 annotation ZIP members are requested. Unknown
objects are counted as physical object proposals, never identity verification.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

EXPECTED_SOURCE="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
SOURCE_URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
SOURCE_BYTES=2354714266
EXPECTED_SEALED_SCENE=12
EXPECTED_SIZE=30
KNOWN_OBJECT_IDS={12,15}

def import_domain():
    path=Path(__file__).with_name("lens_hb_domain_train.py")
    spec=importlib.util.spec_from_file_location("hb_domain_train",path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod

def import_remote_zip():
    path=Path(__file__).with_name("lens_hb_range.py")
    spec=importlib.util.spec_from_file_location("hb_range",path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod.ZipHTTP

def score_closed_scene(prediction_rows,gt,infos,threshold,orig_w=640,orig_h=480):
    # Use exactly frozen model-proposal scores; IoU pairing is read-only.
    mod=import_domain()
    actual=[]
    freq=Counter()
    for row in prediction_rows:
        frame=str(row["frame"])
        if frame not in gt or frame not in infos:
            raise RuntimeError("Missing sealed annotation source entry")
        objects=gt[frame]
        info=infos[frame]
        if len(objects)!=len(info):
            raise RuntimeError("BOP annotation alignment changed")
        boxes=[]
        for obj,anno in zip(objects,info):
            visibility=float(anno.get("visib_fract",0))
            xywh=anno.get("bbox_visib")
            if visibility<.20 or not isinstance(xywh,list) or len(xywh)!=4:
                continue
            x,y,w,h=(int(t) for t in xywh)
            if w<8 or h<8 or x<0 or y<0 or x+w>orig_w or y+h>orig_h:
                continue
            sx=320/orig_w;sy=240/orig_h
            box=[round(x*sx),round(y*sy),round((x+w)*sx),round((y+h)*sy)]
            if box[2]-box[0]<4 or box[3]-box[1]<4:
                continue
            boxes.append(box)
            freq[int(obj["obj_id"])]+=1
        copy=dict(row)
        copy["target_boxes_xyxy"]=boxes
        actual.append(copy)
    metrics=mod.match_predictions(actual,threshold)
    return metrics,dict(sorted(freq.items())),actual

def evaluate(args):
    import torch
    module=import_domain()
    torch.set_num_threads(4)
    device=torch.device(args.device)
    if args.device=="mps" and not torch.backends.mps.is_available():
        raise RuntimeError("Apple MPS missing")
    data,manifest_sha=module.read_manifest(args.data_root)
    scene_rows=[r for r in data["samples"] if r["split"]=="sealed"]
    if (len(scene_rows)!=EXPECTED_SIZE or
        set(r["scene_id"] for r in scene_rows)!={EXPECTED_SEALED_SCENE} or
        any("boxes_xyxy" in r or "object_class_ids_audit_only" in r for r in scene_rows)):
        raise RuntimeError("Heldout scene source/label pre-exposure")
    ckpt_path=args.training_root/"detector-state.pt"
    report=json.loads((args.training_root/"training-report.json").read_text())
    if (report.get("schema")!="chibi.lens.hb.domain-objectness-finetune.v1" or
        report.get("manifestSHA256")!=manifest_sha or
        report.get("sealedSceneGTEverRead") is not False or
        report.get("trainingScenes")!=[5,9] or
        report.get("calibrationScene")!=10 or
        report.get("sealedScene")!=12 or
        module.file_sha256(ckpt_path)!=report.get("modelCheckpointSHA256")):
        raise RuntimeError("Unqualified previously frozen trained detector")
    ckpt=torch.load(ckpt_path,map_location="cpu",weights_only=True)
    if (ckpt.get("manifest_sha256")!=manifest_sha or
        ckpt.get("threshold")!=report.get("frozenThreshold") or
        ckpt.get("trained_steps",0)<5):
        raise RuntimeError("Checkpoint/source/score threshold mismatch")
    if args.out.exists() and any(args.out.iterdir()):
        raise RuntimeError("Sealed test output path already exists (no rerun)")
    args.out.mkdir(parents=True,exist_ok=True)
    model=module.model_builder(weights=False)
    model.load_state_dict(ckpt["state"],strict=True)
    model=model.to(device)
    model.eval()

    # STOP HERE IF INFERENCE FAILS. NEVER READ THE ANNOTATIONS FIRST.
    print("SEALED_RGB_ONLY_INFERENCE_BEGIN",len(scene_rows),flush=True)
    predictions=module.predict_rows(model,scene_rows,args.data_root,device,
                                    include_targets=False)
    if len(predictions)!=EXPECTED_SIZE or any("target_boxes_xyxy" in row for row in predictions):
        raise RuntimeError("Seal broken in prediction serialization")
    serialized=json.dumps({
        "schema":"chibi.lens.hb.sealed-inference-predictions.v1",
        "sourceScene":12,"thresholdFrozen":ckpt["threshold"],
        "modelWeightsSHA256":report["modelCheckpointSHA256"],
        "manifestSHA256":manifest_sha,
        "usedGroundTruth":False,
        "predictions":predictions,
    },indent=2,sort_keys=True)+"\n"
    prediction_file=args.out/"sealed-predictions.json"
    with prediction_file.open("x") as f:
        f.write(serialized)
        f.flush()
    pred_hash=module.file_sha256(prediction_file)
    print("SEALED_PREDICTIONS_FROZEN",pred_hash,flush=True)

    # Now, and ONLY now, open original GT annotation bytes for the never
    # previously used scene. The model and cutoff must not be refitted from
    # these observations. Score source independent scene 12 once.
    reader=import_remote_zip()(SOURCE_URL,EXPECTED_SOURCE,SOURCE_BYTES)
    base="val_primesense/000012/"
    gt=json.loads(reader.read(base+"scene_gt.json"))
    info=json.loads(reader.read(base+"scene_gt_info.json"))
    if len(gt)!=340 or set(gt)!=set(info):
        raise RuntimeError("Unknown new sealed-scene annotation shape")
    metrics,classes,with_gt=score_closed_scene(
        predictions,gt,info,ckpt["threshold"],orig_w=640,orig_h=480)
    record={
      "schema":"chibi.lens.hb.domain-detector-sealed-eval.v1",
      "sourceArchivePointerSHA256":EXPECTED_SOURCE,
      "sourcePointerFullyRehashed":False,
      "modelCheckpointSHA256":report["modelCheckpointSHA256"],
      "predictionsFrozenSHA256":pred_hash,
      "datasetManifestSHA256":manifest_sha,
      "sourceScene":12,"calibrationScene":10,
      "independentFromKnownSourceScenes":[5,9,10,11],
      "usedHeldoutGTForTrainingOrThreshold":False,
      "sealingVerifiedByProcessOrder":True,
      "sealedFrames":len(scene_rows),
      "matchedAtIoU50":metrics["matched"],
      "annotatedObjects":metrics["objects"],
      "detectorProposals":metrics["proposals"],
      "objectRecallAtIoU50":metrics["recallAtIoU50"],
      "proposalPrecisionAtIoU50":metrics["precisionAtIoU50"],
      "frozenDetectionScoreThreshold":ckpt["threshold"],
      "sealedObjectClassCountsAuditOnly":classes,
      "sourceIncludedKnown12":12 in classes,
      "sourceIncludedKnown15":15 in classes,
      "sourceIncludedUnknowns":any(int(k) not in KNOWN_OBJECT_IDS for k in classes),
      "evaluationPurpose":"Research one heldout physical scene, NOT official BOP leaderboard or live camera",
      "notFullProductQualification":True,
      "notLiveMetaGlasses":True,
      "modelDeployed":False,
      "familyMediaUsed":False,
      "costEur":None,
    }
    with (args.out/"sealed-evaluation.json").open("x") as f:
        f.write(json.dumps(record,indent=2,sort_keys=True)+"\n")
    print("SEALED_REAL_DETECTOR_SCORE",json.dumps({
        "matched":record["matchedAtIoU50"],"objects":record["annotatedObjects"],
        "proposals":record["detectorProposals"],
        "recall":record["objectRecallAtIoU50"],
        "precision":record["proposalPrecisionAtIoU50"],
        "classes":classes,
    },sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",type=Path,required=True)
    p.add_argument("--training-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--device",choices=("mps","cpu"),default="mps")
    args=p.parse_args()
    evaluate(args)

if __name__=="__main__":
    main()
