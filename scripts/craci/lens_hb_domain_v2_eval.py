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
INITIAL_MANIFEST_SHA="2197e6c3d0721d6c452a7b4914fe35286ef501ddf76b1424de3a21b1d0591e43"


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


def reserve_single_source_reveal(root:Path,manifest_sha:str,
                                 checkpoint_sha:str,predictions_sha:str,
                                 baseline_checkpoint_sha:str,
                                 baseline_predictions_sha:str)->Path:
    """Local single-use GT-reveal guard; NOT a provider-signed attestation.

    A different --output path no longer permits a second evaluation on the
    same prepared data. A manual deletion of local task scratch is outside the
    protection provided by this tool and must not be misreported as tamperproof.
    """
    if (not root.is_dir() or root.is_symlink() or
        not all(isinstance(value,str) and len(value)==64
                for value in (manifest_sha,checkpoint_sha,predictions_sha,
                              baseline_checkpoint_sha,baseline_predictions_sha))):
        raise RuntimeError("Unverified seal guard source")
    lock=root/".hb-scene13-gt-revealed.json"
    proof={
      "schema":"chibi.lens.hb.scene13-local-single-use-guard.v1",
      "sourceArchivePointerSHA256":ARCHIVE,
      "manifestSHA256":manifest_sha,
      "checkpointSHA256":checkpoint_sha,
      "frozenPredictionsSHA256":predictions_sha,
      "priorBaselineModelSHA256":baseline_checkpoint_sha,
      "priorBaselinePredictionsSHA256":baseline_predictions_sha,
      "bothIndependentModelsPredictedBeforeGroundTruth":True,
      "sceneGTAllowedOnlyAfterPredictionsFrozen":True,
      "providerSigned":False,
    }
    # Exclusive mode is atomic on the local filesystem; do NOT overwrite.
    with lock.open("x",encoding="utf8") as file:
        file.write(json.dumps(proof,indent=2,sort_keys=True)+"\n")
    return lock


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


def frozen_prior_baseline(opts,source_module,device)->tuple:
    """Calibrate previously frozen 80-step model on SAME scene11, no scene13 GT."""
    import torch
    prior_root=opts.baseline_root
    checkpoint_file=prior_root/"detector-state.pt"
    report_file=prior_root/"training-report.json"
    if not checkpoint_file.is_file() or not report_file.is_file():
        raise RuntimeError("Missing previously source-pinned baseline evidence")
    if sha(checkpoint_file)!=INITIAL_MODEL_SHA:
        raise RuntimeError("Historical baseline checkpoint SHA256 changed")
    old_report=json.loads(report_file.read_text())
    if (old_report.get("modelCheckpointSHA256")!=INITIAL_MODEL_SHA or
        old_report.get("manifestSHA256")!=INITIAL_MANIFEST_SHA or
        old_report.get("trainingScenes")!=[5,9] or
        old_report.get("calibrationScene")!=10 or
        old_report.get("sealedScene")!=12 or
        old_report.get("trainingOptimizerSteps")!=80 or
        old_report.get("sourceOnlyCalibrationDecision") is not True):
        raise RuntimeError("Previously frozen baseline provenance mismatch")
    prior_state=torch.load(checkpoint_file,map_location="cpu",weights_only=True)
    if (prior_state.get("manifest_sha256")!=INITIAL_MANIFEST_SHA or
        prior_state.get("trained_steps")!=80 or
        prior_state.get("architecture")!="Torchvision_FasterRCNN_MobileNetV3_320"):
        raise RuntimeError("Original baseline weights/source do not match")
    model=source_module.model_builder(weights=False)
    model.load_state_dict(prior_state["state"],strict=True)
    model=model.to(device)
    model.eval()
    records=json.loads((opts.data_root/"manifest.json").read_text())
    calibration=[r for r in records["samples"] if r["split"]=="calibration"]
    if len(calibration)!=24 or any(r["scene_id"]!=11 for r in calibration):
        raise RuntimeError("Original baseline comparison may use scene11 only")
    # Same calibration budget/model selection rule as V2; old model weights
    # remain FROZEN, threshold is selected without touching scene13.
    predicted=source_module.predict_rows(
        model,calibration,opts.data_root,device,include_targets=True)
    metrics=[source_module.match_predictions(
        predicted,t) for t in source_module.ALLOWED_THRESHOLDS]
    eligible=[m for m in metrics if m["precisionAtIoU50"]>=.5 and m["matched"]>0]
    search=eligible or metrics
    best=sorted(search,key=lambda m:(-m["f1"],-m["recallAtIoU50"],
                                     -m["precisionAtIoU50"],-m["threshold"]))[0]
    return model,best["threshold"],{
        "sourceModelCheckpointSHA256":INITIAL_MODEL_SHA,
        "originalSourceManifestSHA256":INITIAL_MANIFEST_SHA,
        "calibrationScene":11,
        "calibrationFrames":24,
        "calibrationCandidates":metrics,
        "selectedCalibratedThreshold":best["threshold"],
        "selectedCalibratedObjectRecall":best["recallAtIoU50"],
        "selectedCalibratedProposalPrecision":best["precisionAtIoU50"],
        "noScene13GTRead":True,
    }


def paired_frame_cluster_intervals(new_frames:list[dict],
                                   prior_frames:list[dict],replicates=1200)->dict:
    """Paired within-scene frame bootstrap, NOT multi-camera proof."""
    if (len(new_frames)!=SEALED_COUNT or len(prior_frames)!=SEALED_COUNT or
        [r["frame"] for r in new_frames]!=[r["frame"] for r in prior_frames]):
        raise RuntimeError("Mismatched sealed physical RGB frame groups")
    random.seed(2026111502)
    deltas_recall=[]
    deltas_precision=[]
    for _ in range(replicates):
        indexes=random.choices(range(len(new_frames)),k=len(new_frames))
        n_matched=sum(new_frames[i]["matches"] for i in indexes)
        p_matched=sum(prior_frames[i]["matches"] for i in indexes)
        objects=sum(new_frames[i]["objects"] for i in indexes)
        if objects<=0 or objects!=sum(prior_frames[i]["objects"] for i in indexes):
            raise RuntimeError("Paired GT counts disagree across models")
        deltas_recall.append((n_matched-p_matched)/objects)
        newprops=sum(new_frames[i]["proposals"] for i in indexes)
        priorprops=sum(prior_frames[i]["proposals"] for i in indexes)
        if newprops>0 and priorprops>0:
            deltas_precision.append(n_matched/newprops-p_matched/priorprops)
    def interval(x):
        if not x:return None
        x.sort()
        return [round(x[int(.025*len(x))],6),
                round(x[min(len(x)-1,int(.975*len(x)))],6)]
    return {
        "unit":"same physical scene13 frame, two frozen model checkpoints",
        "pairedRecallDifference95pct":interval(deltas_recall),
        "pairedPrecisionDifference95pct":interval(deltas_precision),
        "onlyOnePhysicalSceneNotFieldCertification":True,
        "oneBaselineAndOneNewModelNoTestRetuning":True,
    }


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
    if (opts.data_root/".hb-scene13-gt-revealed.json").exists():
        raise RuntimeError("Scene13 GT already revealed for this source dataset")
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
    # Original 80-step model gets the SAME scene11 calibration opportunity.
    # Neither model touches scene13 GT before its predictions are frozen.
    prior_model,prior_cutoff,prior_cal=frozen_prior_baseline(
        opts,__import__("lens_hb_domain_train"),torch.device(opts.device))
    opts.output.mkdir(parents=True,exist_ok=False)
    # Stage 1: all source images without ANY test GT access.
    print("SEALED_SCENE13_RGB_INFERENCE_BEGIN",len(frames),flush=True)
    predicted=predict_rows(model,frames,opts.data_root,torch.device(opts.device),
                           include_targets=False)
    if len(predicted)!=SEALED_COUNT or any("target_boxes_xyxy" in r for r in predicted):
        raise RuntimeError("Incomplete sealed inference or GT leak")
    prior_predicted=predict_rows(
        prior_model,frames,opts.data_root,torch.device(opts.device),include_targets=False)
    if len(prior_predicted)!=SEALED_COUNT or any("target_boxes_xyxy" in r for r in prior_predicted):
        raise RuntimeError("Prior baseline sealed inference incomplete or GT leaked")
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
    prior_artifact={
      "schema":"chibi.lens.hb.scene13.original-baseline-frozen-predictions.v1",
      "scene":SEALED_SCENE,"modelCheckpointSHA256":INITIAL_MODEL_SHA,
      "calibrationScene":11,"calibratedThreshold":prior_cutoff,
      "calibrationEvidence":prior_cal,"manifestSHA256":manifest_digest,
      "sourceGTAvailableDuringInference":False,
      "predictions":prior_predicted,
    }
    prior_file=opts.output/"sealed13-original-baseline-predictions.json"
    with prior_file.open("x") as fp:
        fp.write(json.dumps(prior_artifact,indent=2,sort_keys=True)+"\n")
    prior_prediction_sha=sha(prior_file)
    print("SEALED_SCENE13_BOTH_MODELS_FROZEN",sealed_prediction_sha,
          prior_prediction_sha,flush=True)
    # Before ANY HTTP GT request, atomically record the one-time reveal. This
    # remains even if an external network error interrupts scoring.
    guard=reserve_single_source_reveal(
        opts.data_root,manifest_digest,report["modelCheckpointSHA256"],
        sealed_prediction_sha,INITIAL_MODEL_SHA,prior_prediction_sha)
    guard_sha=sha(guard)
    print("SEALED_SCENE13_GT_REVEAL_GUARD",guard_sha,flush=True)
    # Stage 2 ONLY: annotation reveal after immutable output and hashes.
    reader=ZipHTTP(URL,ARCHIVE,ARCHIVE_BYTES)
    prefix=f"val_primesense/{SEALED_SCENE:06}/"
    gt=json.loads(reader.read(prefix+"scene_gt.json"))
    info=json.loads(reader.read(prefix+"scene_gt_info.json"))
    if len(gt)!=340 or set(gt)!=set(info):
        raise RuntimeError("Sealed GT mismatch")
    counts,by_label,matched_by_label,frame_metrics=report_metrics(
        predicted,gt,info,checkpoint["threshold"],matcher)
    old_counts,old_labels,old_matched,prior_frames=report_metrics(
        prior_predicted,gt,info,prior_cutoff,matcher)
    if old_counts["objects"]!=counts["objects"] or old_labels!=by_label:
        raise RuntimeError("Paired scene13 source GT changed between frozen models")
    precision=counts["matches"]/counts["proposals"] if counts["proposals"] else None
    recall=counts["matches"]/counts["objects"] if counts["objects"] else None
    prior_precision=(old_counts["matches"]/old_counts["proposals"]
                     if old_counts["proposals"] else None)
    prior_recall=(old_counts["matches"]/old_counts["objects"]
                  if old_counts["objects"] else None)
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
      "originalBaselinePredictionsSHA256":prior_prediction_sha,
      "originalBaselineModelSHA256":INITIAL_MODEL_SHA,
      "originalBaselineCalibrationScene":11,
      "originalBaselineCalibratedThreshold":prior_cutoff,
      "originalBaselineCalibration":prior_cal,
      "localRevealGuardSHA256":guard_sha,
      "groundTruthReadOnlyAfterPredictionsFrozen":True,
      "singleUseLocalGuardCreated":True,
      "operatorReportedFirstQualification":True,
      "notCryptographicallySingleUse":True,
      "test13UsedForTrainingOrCalibration":False,
      "objectsVisibleAtLeast20pct":counts["objects"],
      "proposals":counts["proposals"],"matchedIoU50":counts["matches"],
      "objectRecallIoU50":round(recall,7) if recall is not None else None,
      "proposalPrecisionIoU50":round(precision,7) if precision is not None else None,
      "objectsByClassAuditOnly":dict(sorted(by_label.items())),
      "matchedByClassAuditOnly":dict(sorted(matched_by_label.items())),
      "frameBootstrap":frame_cluster_intervals(frame_metrics),
      "originalBaselineIoU50":{
        "objects":old_counts["objects"],
        "proposals":old_counts["proposals"],
        "matched":old_counts["matches"],
        "recall":round(prior_recall,7) if prior_recall is not None else None,
        "precision":round(prior_precision,7) if prior_precision is not None else None,
      },
      "pairedScene13Deltas":{
        "recall":round(recall-prior_recall,7) if recall is not None and prior_recall is not None else None,
        "precision":round(precision-prior_precision,7) if precision is not None and prior_precision is not None else None,
      },
      "pairedFrameClusterBootstrap":paired_frame_cluster_intervals(
          frame_metrics,prior_frames),
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
        "old_recall":out["originalBaselineIoU50"]["recall"],
        "old_precision":out["originalBaselineIoU50"]["precision"],
        "paired_recall_delta":out["pairedScene13Deltas"]["recall"],
        "modelSHA":out["modelCheckpointSHA256"]},sort_keys=True),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",type=Path,required=True)
    p.add_argument("--training-root",type=Path,required=True)
    p.add_argument("--baseline-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--device",choices=("mps","cpu"),default="mps")
    evaluate(p.parse_args())

if __name__=="__main__":
    main()
