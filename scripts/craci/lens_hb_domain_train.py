#!/usr/bin/env python3
"""Fine-tune a real image-region detector on licensed BOP HB full frames.

Torchvision BSD-3 MobileNetV3 Faster R-CNN, pretrained COCO weights consumed
locally only. Train only TRAIN scenes 5/9; choose threshold only on CAL scene10.
Sealed RGB scene12 images and annotations never accessed during this script.
Two detector labels: 0=background, 1=ANY visible public BOP object. This is
objectness, NOT Chibi identity/authorization or live glasses deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time

SEED=20261115
WEIGHTS_URL="https://download.pytorch.org/models/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth"
EXPECTED_SPLITS={"train":[5,9],"calibration":[10],"sealed":[12]}
ALLOWED_THRESHOLDS=(.05,.10,.20,.30,.40,.50)

def file_sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(1048576),b""):h.update(part)
    return h.hexdigest()

def read_manifest(data_root:Path):
    manifest=data_root/"manifest.json"
    raw=manifest.read_bytes()
    record=json.loads(raw)
    if (record.get("schema")!="chibi.lens.hb.domain-detector-data.v1" or
        record.get("source")!="PUBLIC_BOP_HOMEBREWEDDB_CC0" or
        record.get("sceneSplits")!=EXPECTED_SPLITS or
        record.get("sealedSceneGTRead") is not False or
        record.get("rawImagesLocalOnly") is not True or
        record.get("familyMediaUsed") is not False or
        record.get("privateOCRUsed") is not False):
        raise ValueError("Public source/scene partition or consent boundary failed")
    rows=record["samples"]
    if len(rows)!=140 or len({r["file"] for r in rows})!=140:
        raise ValueError("Source frame count or uniqueness violated")
    for r in rows:
        if r["split"] not in EXPECTED_SPLITS or r["scene_id"] not in EXPECTED_SPLITS[r["split"]]:
            raise ValueError("Source scene leakage")
        if r["split"]=="sealed" and (
            "boxes_xyxy" in r or "object_class_ids_audit_only" in r):
            raise ValueError("Sealed scene annotation leaked into training")
        if r["split"]!="sealed" and (
            not r.get("boxes_xyxy") or len(r["boxes_xyxy"])!=len(r["object_class_ids_audit_only"])):
            raise ValueError("Train/validation object boxes missing")
        path=data_root/r["file"]
        if path.is_symlink() or not path.is_file() or file_sha256(path)!=r["resized_sha256"]:
            raise ValueError("Image bytes changed after public source preparation")
    return record,file_sha256(manifest)

def xyxy_to_xywh(box):
    x1,y1,x2,y2=[float(v) for v in box]
    return (max(0,int(round(x1))),max(0,int(round(y1))),
            max(1,int(round(x2-x1))),max(1,int(round(y2-y1))))

def model_builder(weights:bool):
    from torchvision.models.detection import (
        fasterrcnn_mobilenet_v3_large_320_fpn,
        FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
    )
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    base=fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1 if weights else None,
        weights_backbone=None,trainable_backbone_layers=0,
        min_size=256,max_size=480,
        box_detections_per_img=60,
        rpn_pre_nms_top_n_train=450,rpn_post_nms_top_n_train=200,
        rpn_pre_nms_top_n_test=280,rpn_post_nms_top_n_test=80)
    n=base.roi_heads.box_predictor.cls_score.in_features
    base.roi_heads.box_predictor=FastRCNNPredictor(n,2)
    for param in base.backbone.parameters():param.requires_grad=False
    return base

def image_tensor(file:Path,device):
    from PIL import Image
    import torchvision.transforms.functional as F
    with Image.open(file) as img:
        if img.format!="PNG":raise RuntimeError("Non-PNG public source")
        img.load()
        tensor=F.to_tensor(img.convert("RGB"))
    return tensor.to(device)

def sample_target(entry,device):
    import torch
    boxes=torch.tensor(entry["boxes_xyxy"],dtype=torch.float32,device=device)
    labels=torch.ones((len(boxes),),dtype=torch.int64,device=device)
    if (boxes.shape[1]!=4 or not torch.isfinite(boxes).all() or
        not ((boxes[:,2]>boxes[:,0]) & (boxes[:,3]>boxes[:,1])).all()):
        raise ValueError("Invalid BOP public annotation coordinates")
    return {"boxes":boxes,"labels":labels}

def match_predictions(rows,score_threshold):
    """Aggregate class-agnostic one-to-one IoU matches for VALIDATION ONLY."""
    import importlib.util
    import sys
    module_path=Path(__file__).with_name("lens_hb_public_proposal_eval.py")
    spec=importlib.util.spec_from_file_location("chibi_iou_matcher",module_path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    matched=0;proposals=0;objects=0
    per_frame=[]
    for row in rows:
        candidates=[xyxy_to_xywh(x["xyxy"]) for x in row["predictions"]
                    if x["score"]>=score_threshold]
        # Score from precomputed model output: no test labels used here.
        target=[xyxy_to_xywh(x) for x in row["target_boxes_xyxy"]]
        if len(candidates)>64:
            raise RuntimeError("Unbounded object proposal count")
        result=mod.evaluate(candidates,target,threshold=.50)
        matched+=result["matched"]
        proposals+=result["proposals"]
        objects+=result["groundTruthObjects"]
        per_frame.append({"scene":row["scene"],"frame":row["frame"],
                          "matched":result["matched"],"proposals":result["proposals"],
                          "objects":result["groundTruthObjects"]})
    precision=matched/proposals if proposals else 0
    recall=matched/objects if objects else 0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0
    return {"threshold":score_threshold,"frames":len(rows),
            "matched":matched,"proposals":proposals,"objects":objects,
            "precisionAtIoU50":round(precision,7),
            "recallAtIoU50":round(recall,7),"f1":round(f1,7),
            "frameStats":per_frame}

def predict_rows(model,entries,root,device,include_targets=True):
    import torch
    model.eval()
    records=[]
    with torch.inference_mode():
        for i,entry in enumerate(entries):
            image=image_tensor(root/entry["file"],device)
            output=model([image])[0]
            scores=output["scores"].detach().cpu().tolist()
            xyxy=output["boxes"].detach().cpu().tolist()
            if len(scores)!=len(xyxy):raise RuntimeError("Model prediction alignment")
            predictions=[]
            for score,box in zip(scores,xyxy):
                if len(predictions)>=60:break
                if not math.isfinite(float(score)) or not 0<=score<=1:
                    raise RuntimeError("Unbounded pretrained detector score")
                if score<.025:continue
                predictions.append({"score":round(float(score),8),
                                    "xyxy":[round(float(v),4) for v in box]})
            record={"scene":entry["scene_id"],"frame":entry["frame_id"],
                    "publicPNGsha256":entry["resized_sha256"],
                    "predictions":predictions}
            if include_targets:
                record["target_boxes_xyxy"]=entry["boxes_xyxy"]
            records.append(record)
            if (i+1)%10==0:
                print("CAL_FRAMES_INFERRED",i+1,flush=True)
    return records

def train(opts):
    import torch
    from torchvision import __version__ as torchvision_version
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(4)
    if opts.device=="mps" and not torch.backends.mps.is_available():
        raise RuntimeError("Verified Apple MPS backend not available")
    device=torch.device(opts.device)
    root=Path(opts.data_root)
    record,manifest_sha=read_manifest(root)
    if opts.output.exists() and any(opts.output.iterdir()):
        raise RuntimeError("Training output already exists: no overwrite")
    opts.output.mkdir(parents=True,exist_ok=True)
    train_samples=[r for r in record["samples"] if r["split"]=="train"]
    calibration=[r for r in record["samples"] if r["split"]=="calibration"]
    if len(train_samples)!=80 or len(calibration)!=30:
        raise RuntimeError("Train/cal split count changed")
    if opts.max_steps<5 or opts.max_steps>400:
        raise RuntimeError("Invalid bounded training steps")
    print("START_PRETRAINED_SOURCE",WEIGHTS_URL,"DEVICE",device,flush=True)
    begin=time.monotonic()
    model=model_builder(weights=True).to(device)
    params=[p for p in model.parameters() if p.requires_grad]
    opt=torch.optim.SGD(params,lr=.002,momentum=.9,weight_decay=1e-4)
    model.train()
    losses=[]
    count=0
    for epoch in range(opts.epochs):
        order=list(train_samples)
        random.Random(SEED+epoch).shuffle(order)
        for sample in order:
            image=image_tensor(root/sample["file"],device)
            target=sample_target(sample,device)
            opt.zero_grad(set_to_none=True)
            result=model([image],[target])
            if not isinstance(result,dict) or not result:
                raise RuntimeError("FasterRCNN returned no training losses")
            loss=sum(result.values())
            if not torch.isfinite(loss):
                raise RuntimeError("Nonfinite actual model optimization")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params,5)
            opt.step()
            count+=1
            losses.append(float(loss.item()))
            if count%10==0 or count==1:
                print("DETECTOR_TRAIN_STEP",count,"LOSS",round(losses[-1],5),
                      "EPOCH",epoch,"ELAPSED",round(time.monotonic()-begin,1),
                      flush=True)
            if count>=opts.max_steps:break
        if count>=opts.max_steps:break
    if count<5:raise RuntimeError("Not actually fitted")
    # Freeze model BEFORE any novel sealed-scene evaluation. Only CAL scene10
    # GT determines the detector score threshold.
    results=predict_rows(model,calibration,root,device)
    metrics=[match_predictions(results,t) for t in ALLOWED_THRESHOLDS]
    # Pre-registered selection: F1 on cal, with preference for >=50% proposal
    # precision; if nothing meets precision, keep max F1 as unqualified.
    eligible=[m for m in metrics if m["precisionAtIoU50"]>=.5 and m["matched"]>0]
    search=eligible or metrics
    best=sorted(search,key=lambda m:(-m["f1"],-m["recallAtIoU50"],
                                     -m["precisionAtIoU50"],-m["threshold"]))[0]
    checkpoint=opts.output/"detector-state.pt"
    state={name:value.detach().cpu() for name,value in model.state_dict().items()}
    torch.save({"state":state,"threshold":best["threshold"],
                "architecture":"Torchvision_FasterRCNN_MobileNetV3_320",
                "trained_steps":count,"manifest_sha256":manifest_sha,
                "seed":SEED},checkpoint)
    report={
      "schema":"chibi.lens.hb.domain-objectness-finetune.v1",
      "workId":"CHIBI-LENS-DOMAIN-DETECTOR-20261115",
      "source":"PUBLIC_BOP_HB_CC0_RGB",
      "sourceArchivePointerSha256":record["sourceArchivePointerSHA256"],
      "sourceArchiveFullyRehashed":False,
      "trainingScenes":[5,9],"calibrationScene":10,
      "sealedScene":12,"sealedSceneGTEverRead":False,
      "modelSource":"Torchvision BSD-3-Clause COCO pretrained 320 MobileNetV3",
      "pretrainedWeightsUrl":WEIGHTS_URL,
      "torchVersion":torch.__version__,"torchvisionVersion":torchvision_version,
      "device":opts.device,
      "trainingFrames":len(train_samples),"calibrationFrames":len(calibration),
      "trainingOptimizerSteps":count,"epochsAllocated":opts.epochs,
      "maxTrainSteps":opts.max_steps,"seed":SEED,
      "initialTrainingLoss":round(losses[0],7),
      "finalTrainingLoss":round(losses[-1],7),
      "trainableParameterCount":sum(x.numel() for x in params),
      "manifestSHA256":manifest_sha,
      "candidateThresholds":metrics,
      "frozenThreshold":best["threshold"],
      "sourceOnlyCalibrationDecision":True,
      "modelCheckpointSHA256":file_sha256(checkpoint),
      "modelWeightsInGit":False,"rawRGBInGit":False,
      "privateOrFamilyMediaUsed":False,"personalOCRUsed":False,
      "productionDeploymentAllowed":False,
      "physicalIdentityVerified":False,"actionAuthorized":False,
      "modelLicenseAndCOCOWeightDeploymentNotApproved":True,
      "actualProviderCost":None,
      "elapsedSeconds":round(time.monotonic()-begin,2),
    }
    (opts.output/"training-report.json").write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("ACTUAL_DOMAIN_DETECTOR_TRAIN_COMPLETED",json.dumps({
        "steps":count,"manifestSHA256":manifest_sha,
        "checkpointSHA256":report["modelCheckpointSHA256"],
        "calThreshold":best["threshold"],"calRecall":best["recallAtIoU50"],
        "calPrecision":best["precisionAtIoU50"]},sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--epochs",type=int,default=2)
    parser.add_argument("--max-steps",type=int,default=64)
    parser.add_argument("--device",choices=("mps","cpu"),default="mps")
    opts=parser.parse_args()
    train(opts)

if __name__=="__main__":
    main()
