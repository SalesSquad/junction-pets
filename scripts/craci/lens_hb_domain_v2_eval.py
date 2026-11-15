#!/usr/bin/env python3
"""ONE-TIME, SEALED HB scene13 evaluation of the domain-diverse detector.

Scene 13 GT must not be read until actual inference on ALL frozen scene13
pixels is finished and SHA-bound. Never retune on this source afterwards.
NO product deployment, family media or identity implications.
"""
from __future__ import annotations
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import random

ARCHIVE="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
ARCHIVE_BYTES=2354714266
TRAIN_SCENES=list(range(1,11))
CAL_SCENE=11
SEALED_SCENE=13
SEALED_COUNT=24
INITIAL_MODEL_SHA="df9b0155636392be4220248b2cc3b8fe96157edd26e580a423ddd033bf3bb2c6"


def sha(path:Path)->str:
    h=sha256()
    with path.open("rb") as fd:
        for part in iter(lambda:fd.read(1048576),b""):
            h.update(part)
    return h.hexdigest()


def check_frozen_source(record:dict,report:dict,checkpoint:dict,manifest_digest:str)->list:
    if (record.get("schema")!="chibi.lens.hb.domain-detector-diverse-data.v2" or
        record.get("plan")!="diverse" or
        record.get("sceneSplits")!=
            {"train":TRAIN_SCENES,"calibration":[CAL_SCENE],"sealed":[SEALED_SCENE]} or
        record.get("sourceArchivePointerSHA256")!=ARCHIVE or
        record.get("sealedSceneGTRead") is not False or
        report.get("datasetPlan")!="diverse" or
        report.get("datasetSchema")!=record["schema"] or
        report.get("manifestSHA256")!=manifest_digest or
        report.get("sourceArchivePointerSha256")!=ARCHIVE or
        report.get("initialSourceModelSHA256")!=INITIAL_MODEL_SHA or
        report.get("trainingScenes")!=TRAIN_SCENES or
        report.get("calibrationScene")!=CAL_SCENE or
        report.get("sealedScene")!=SEALED_SCENE or
        report.get("sealedSceneGTEverRead") is not False or
        report.get("sourceOnlyCalibrationDecision") is not True or
        report.get("productionDeploymentAllowed") is not False or
        checkpoint.get("manifest_sha256")!=manifest_digest or
        checkpoint.get("dataset_plan")!="diverse" or
        checkpoint.get("initial_model_sha256")!=INITIAL_MODEL_SHA or
        checkpoint.get("threshold")!=report.get("frozenThreshold") or
        checkpoint.get("trained_steps",0)<5):
        raise RuntimeError("Source, prior model, calibration or scene-13 seal mismatch")
    rows=[r for r in record["samples"] if r["split"]=="sealed"]
    if (len(rows)!=SEALED_COUNT or any(r["scene_id"]!=SEALED_SCENE for r in rows) or
        any("boxes_xyxy" in r or "object_class_ids_audit_only" in r for r in rows) or
        {tuple(r.get("source_dimensions",[])) for r in rows}!={(640,480)} or
        len({r["source_png_sha256"] for r in rows})!=SEALED_COUNT):
        raise RuntimeError("Sealed frame duplicate, GT exposure or geometry drift")
    return rows


def report_metrics(all_preds,gt,info,cutoff,matcher):
    from lens_hb_domain_train import xyxy_to_xywh
    seen=Counter()
    matched_by_label=Counter()
    result_frames=[]
    counts={"proposals":0,"matches":0,"objects":0}
    for pred in all_preds:
        fid=str(pred["frame"])
        if fid not in gt or fid not in info or len(gt[fid])!=len(info[fid]):
            raise RuntimeError("Sealed GT frame/instance alignment invalid")
        boxes=[]
        labels=[]
        for annotation,visibility in zip(gt[fid],info[fid]):
            if float(visibility.get("visib_fract",0))<.20:
                continue
            raw=visibility.get("bbox_visib")
            if not isinstance(raw,list) or len(raw)!=4:
                continue
            x,y,w,h=[int(v) for v in raw]
            if x<0 or y<0 or w<8 or h<8 or x+w>640 or y+h>480:
                continue
            box=[round(x*.5),round(y*.5),round((x+w)*.5),round((y+h)*.5)]
            if box[2]-box[0]<4 or box[3]-box[1]<4:continue
            boxes.append(xyxy_to_xywh(box))
            labels.append(int(annotation["obj_id"]))
        selected=[xyxy_to_xywh(p["xyxy"]) for p in pred["predictions"]
                  if p["score"]>=cutoff]
        scores=matcher.evaluate(selected,boxes,threshold=.50)
        counts["proposals"]+=scores["proposals"]
        counts["matches"]+=scores["matched"]
        counts["objects"]+=scores["groundTruthObjects"]
        for label in labels:seen[label]+=1
        for _,gi,_ in scores["matches"]:
            matched_by_label[labels[gi]]+=1
        result_frames.append({
            "frame":int(fid),
            "proposals":scores["proposals"],
            "objects":scores["groundTruthObjects"],
            "matches":scores["matched"],
            "unknownLabelsUsedInInference":False,
        })
    return counts,seen,matched_by_label,result_frames


def frame_cluster_intervals(frames:list[dict],replicates=1200)->dict:
    if len(frames)<12:
        raise RuntimeError("Insufficient independent frames for bootstrap")
    import statistics
    random.seed(20261115)
    recall=[]
    precision=[]
    for _ in range(replicates):
        chosen=random.choices(frames,k=len(frames))
        matched=sum(f["matches"] for f in chosen)
        objects=sum(f["objects"] for f in chosen)
        proposals=sum(f["proposals"] for f in chosen)
        if objects>0:recall.append(matched/objects)
        if proposals>0:precision.append(matched/proposals)
    def confidence(nums):
        if not nums:return None
        nums.sort()
        return [round(nums[int(.025*len(nums))],6),
                round(nums[min(len(nums)-1,int(.975*len(nums)))],6)]
    return {"unit":"BOP physical RGB frame within one camera scene",
            "sourceIndependentCameraCount":1,
            "recallIoU50_95pct":confidence(recall),
            "precisionIoU50_95pct":confidence(precision),
            "method":"nonparametric_frame_cluster_bootstrap",
            "notMultiSceneFieldCertification":True}


def evaluate(opts):
    import importlib.util
    import sys
    import torch
    from lens_hb_domain_train import read_manifest,model_builder,predict_rows
    from lens_hb_range import ZipHTTP
    matcher_path=Path(__file__).with_name("lens_hb_public_proposal_eval.py")
    spec=importlib.util.spec_from_file_location("chibi_sealed_matcher",matcher_path)
    matcher=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=matcher
    spec.loader.exec_module(matcher)
    torch.set_num_threads(4)
    if opts.device=="mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS unavailable")
    if opts.output.exists():
        raise RuntimeError("Sealed output exists — no second run or threshold tuning")
    data,manifest_digest=read_manifest(opts.data_root)
    checkpoint_path=opts.training_root/"detector-state.pt"
    report_path=opts.training_root/"training-report.json"
    if not checkpoint_path.is_file() or not report_path.is_file():
        raise RuntimeError("Training/calibration did not freeze")
    report=json.loads(report_path.read_text())
    if sha(checkpoint_path)!=report.get("modelCheckpointSHA256"):
        raise RuntimeError("Checkpoint bytes changed after calibration")
    checkpoint=torch.load(checkpoint_path,weights_only=True,map_location="cpu")
    frames=check_frozen_source(data,report,checkpoint,manifest_digest)
    model=model_builder(weights=False)
    model.load_state_dict(checkpoint["state"],strict=True)
    model=model.to(torch.device(opts.device))
    model.eval()
    opts.output.mkdir(parents=True,exist_ok=False)
    # Stage 1: all source images without ANY test GT access.
    print("SEALED_SCENE13_RGB_INFERENCE_BEGIN",len(frames),flush=True)
    predicted=predict_rows(model,frames,opts.data_root,torch.device(opts.device),
                           include_targets=False)
    if len(predicted)!=SEALED_COUNT or any("target_boxes_xyxy" in r for r in predicted):
        raise RuntimeError("Incomplete sealed inference or GT leak")
    frozen={
      "schema":"chibi.lens.hb.diverse.sealed-predictions.v1",
      "scene":SEALED_SCENE,"threshold":checkpoint["threshold"],
      "manifestSHA256":manifest_digest,
      "checkpointSHA256":report["modelCheckpointSHA256"],
      "sourceGTAvailableDuringInference":False,
      "predictions":predicted,
    }
    blob=json.dumps(frozen,sort_keys=True,indent=2)+"\n"
    prediction_file=opts.output/"sealed13-predictions.json"
    with prediction_file.open("x") as fp:fp.write(blob);fp.flush()
    sealed_prediction_sha=sha(prediction_file)
    print("SEALED_SCENE13_PREDICTIONS_FROZEN",sealed_prediction_sha,flush=True)
    # Stage 2 ONLY: annotation reveal after immutable output and hashes.
    reader=ZipHTTP(URL,ARCHIVE,ARCHIVE_BYTES)
    prefix=f"val_primesense/{SEALED_SCENE:06}/"
    gt=json.loads(reader.read(prefix+"scene_gt.json"))
    info=json.loads(reader.read(prefix+"scene_gt_info.json"))
    if len(gt)!=340 or set(gt)!=set(info):
        raise RuntimeError("Sealed GT mismatch")
    counts,by_label,matched_by_label,frame_metrics=report_metrics(
        predicted,gt,info,checkpoint["threshold"],matcher)
    precision=counts["matches"]/counts["proposals"] if counts["proposals"] else None
    recall=counts["matches"]/counts["objects"] if counts["objects"] else None
    out={
      "schema":"chibi.lens.hb.domain-diverse-scene13-sealed-eval.v1",
      "source":"PUBLIC_BOP_HOMEBREWEDDB_CC0",
      "sourceArchivePointerSha256":ARCHIVE,
      "sourceArchiveFullyRehashed":False,
      "trainScenes":TRAIN_SCENES,"calibrationScene":CAL_SCENE,
      "sealedScene":SEALED_SCENE,"sealedFrameCount":len(frames),
      "trainedSteps":checkpoint["trained_steps"],
      "warmStartModelSHA256":INITIAL_MODEL_SHA,
      "frozenThreshold":checkpoint["threshold"],
      "sourceManifestSHA256":manifest_digest,
      "modelCheckpointSHA256":report["modelCheckpointSHA256"],
      "predictionsSHA256":sealed_prediction_sha,
      "groundTruthReadOnlyAfterPredictionsFrozen":True,
      "testedOnceNoCalibrationOnScene13":True,
      "objectsVisibleAtLeast20pct":counts["objects"],
      "proposals":counts["proposals"],"matchedIoU50":counts["matches"],
      "objectRecallIoU50":round(recall,7) if recall is not None else None,
      "proposalPrecisionIoU50":round(precision,7) if precision is not None else None,
      "objectsByClassAuditOnly":dict(sorted(by_label.items())),
      "matchedByClassAuditOnly":dict(sorted(matched_by_label.items())),
      "frameBootstrap":frame_cluster_intervals(frame_metrics),
      "sourceReportsOnlyNotProviderSigned":True,
      "fieldCertified":False,
      "noMetaWearableCameraQualified":True,
      "productionModelDeployed":False,
      "familyOrPrivateMediaUsed":False,
      "monetaryCostUnknown":True,
    }
    with (opts.output/"sealed13-evaluation.json").open("x") as fp:
        fp.write(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("SEALED_SCENE13_EVALUATION_FINAL",json.dumps({
        "matched":counts["matches"],"objects":counts["objects"],
        "proposals":counts["proposals"],"recall":out["objectRecallIoU50"],
        "precision":out["proposalPrecisionIoU50"],
        "modelSHA":out["modelCheckpointSHA256"]},sort_keys=True),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",type=Path,required=True)
    p.add_argument("--training-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--device",choices=("mps","cpu"),default="mps")
    evaluate(p.parse_args())

if __name__=="__main__":
    main()
