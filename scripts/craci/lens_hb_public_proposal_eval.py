#!/usr/bin/env python3
"""Evaluate Apple Vision foreground proposals on PUBLIC HB full RGB frames.

No BOP ground-truth box participates in the detector; label boxes used only
AFTER proposals are emitted. All source images stay local in a task-owned
temporary folder. The first bounded smoke uses TRAIN scene 5 only.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

SHA="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
SOURCE_URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
SIZE=2354714266
TRAIN_FRAMES=(0,85,170,255,339)
SCENE=5


def archive_reader():
    helper=Path(__file__).with_name("lens_hb_range.py")
    spec=importlib.util.spec_from_file_location("lens_hb_range",helper)
    if not spec or not spec.loader:
        raise RuntimeError("Exact licensed source range reader unavailable")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module.ZipHTTP(SOURCE_URL,SHA,SIZE)


def xyxy_from_xywh(box):
    if (not isinstance(box, (list, tuple)) or len(box) != 4 or
            any(type(n) is not int for n in box)):
        raise ValueError("Bounding box must contain four integer pixels")
    x,y,w,h = box
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > 10000 or y+h > 10000:
        raise ValueError("Invalid or unbounded pixel box")
    return (x,y,x+w,y+h)


def overlap(box1,box2):
    a=xyxy_from_xywh(box1)
    b=xyxy_from_xywh(box2)
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    size1=(a[2]-a[0])*(a[3]-a[1])
    size2=(b[2]-b[0])*(b[3]-b[1])
    return inter/(size1+size2-inter) if size1+size2-inter>0 else 0


def evaluate(proposals,ground_truth,threshold=0.50):
    """Maximum-cardinality one-to-one IoU matching, never greedy undercount.

    Kuhn's deterministic augmenting-path matching finds the largest number of
    distinct GT objects recoverable by distinct proposals at the frozen IoU
    cutoff. Earlier greedy IoU sorting could count fewer true positives even
    when a valid matching existed. We report IoU only AFTER inference.
    """
    import math
    if (not isinstance(threshold,(float,int)) or isinstance(threshold,bool)
            or not math.isfinite(threshold) or not 0 < threshold <= 1):
        raise ValueError("IoU threshold must be finite and in (0,1]")
    if len(proposals)>64 or len(ground_truth)>1000:
        raise ValueError("Unbounded detector or annotation collection")
    edges=[]
    for proposal in proposals:
        available=[]
        for gi,gt in enumerate(ground_truth):
            iou=overlap(proposal,gt)
            if iou>=threshold:
                available.append((gi,iou))
        edges.append(sorted(available,key=lambda item:(-item[1],item[0])))

    assigned_gt={}  # gt_index -> proposal_index
    def augment(pi,visited):
        for gi,_ in edges[pi]:
            if gi in visited:
                continue
            visited.add(gi)
            if gi not in assigned_gt or augment(assigned_gt[gi],visited):
                assigned_gt[gi]=pi
                return True
        return False

    # Scarce valid edges first; stable index tie-break. Reassignment can still
    # recover every feasible GT/proposal match regardless of initial order.
    for pi in sorted(range(len(proposals)),key=lambda i:(len(edges[i]),i)):
        augment(pi,set())
    matches=sorted(
        (pi,gi,round(next(iou for candidate,iou in edges[pi]
                         if candidate==gi),5))
        for gi,pi in assigned_gt.items()
    )
    return {
        "proposals":len(proposals),"groundTruthObjects":len(ground_truth),
        "matched":len(matches),"unmatchedObjects":len(ground_truth)-len(matches),
        "unmatchedProposals":len(proposals)-len(matches),
        "matches":matches,
        "objectRecall":len(matches)/len(ground_truth) if ground_truth else None,
        "proposalPrecision":len(matches)/len(proposals) if proposals else None,
        "iouThreshold":threshold,
        "assignment":"max_cardinality_bipartite_iou",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--detector",type=Path,required=True)
    parser.add_argument("--scratch",type=Path,required=True)
    parser.add_argument("--sample-size",type=int,choices=(1,3,5),default=3)
    opts=parser.parse_args()
    if not opts.detector.is_file() or not os.access(opts.detector,os.X_OK):
        raise ValueError("Actual compiled on-device Apple Vision detector missing")
    if not str(opts.scratch.resolve()).startswith("/private/tmp/chibi-hb-detector-"):
        raise RuntimeError("Only task-owned public test scratch permitted")
    if not opts.scratch.is_dir() or any(opts.scratch.iterdir()):
        raise RuntimeError("Scratch must exist and be empty, no reuse")
    root=f"val_primesense/{SCENE:06d}/"
    archive=archive_reader()
    # Inference phase: deliberately DO NOT fetch GT scene annotations until
    # every proposal is frozen. No annotated bbox/mask is accessible to the
    # detector subprocess or the threshold selection.
    predictions=[]
    selected=TRAIN_FRAMES[:opts.sample_size]
    for index in selected:
        filename=f"hb_{SCENE:02}_{index:06}.png"
        local=opts.scratch/filename
        image=archive.read(root+f"rgb/{index:06}.png",max_size=8_000_000)
        if image[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Public source image not PNG")
        try:
            local.write_bytes(image)
            output=opts.scratch/f"hb_{SCENE:02}_{index:06}_proposal.json"
            proc=subprocess.run(
                [str(opts.detector),"--root",str(opts.scratch),"--frame",filename,
                 "--output",str(output)],capture_output=True,text=True,timeout=120)
            if proc.returncode!=0:
                raise RuntimeError(f"Real detector failure on frame {index}: {proc.stderr[-360:]}")
            result=json.loads(output.read_text())
            if (result.get("schema")!="chibi.lens.hb.vision-proposal.v1" or
                result.get("detector")!="AppleObjectnessBasedSaliency" or
                result.get("source")!="BOP_HB_CC0_PUBLIC_RGB" or
                result.get("frame")!=filename or
                result.get("usesGroundTruth") is not False or
                result.get("physicalIdentityVerified") is not False or
                result.get("actionAuthorized") is not False or
                type(result.get("maskInstances")) is not int or
                result["maskInstances"]<0 or
                not isinstance(result.get("proposals"),list) or
                len(result["proposals"])>64):
                raise RuntimeError("Untrusted or incorrectly bound detector frame output")
            predicted=[(p["x"],p["y"],p["width"],p["height"])
                       for p in result["proposals"]]
            predictions.append({
                "frame_id":str(index),"frame":filename,
                "sourcePNGsha256":sha256(image).hexdigest(),
                "predicted":predicted,"mask_instances":result["maskInstances"],
            })
        finally:
            # Even on process failure, don't leave public frame pixels in the
            # task directory. Original frames never reach Git or CRACI.
            local.unlink(missing_ok=True)

    # Scoring phase: freeze all detector outputs BEFORE loading annotation.
    gt=json.loads(archive.read(root+"scene_gt.json"))
    info=json.loads(archive.read(root+"scene_gt_info.json"))
    if len(gt)!=340 or set(gt)!=set(info):
        raise RuntimeError("Invalid pinned public RGB source annotations")
    summary=[]
    for frozen in predictions:
        k=frozen["frame_id"]
        if k not in gt:
            raise RuntimeError("Missing annotated train-source frame")
        if len(gt[k])!=len(info[k]):
            raise RuntimeError("GT/visibility metadata alignment mismatch")
        expected=[m["bbox_visib"] for o,m in zip(gt[k],info[k])
                  if m.get("visib_fract",0)>=.20 and m.get("bbox_visib")]
        predicted=frozen["predicted"]
        metric=evaluate(predicted,expected)
        metric["frame"]=frozen["frame"]
        metric["sourcePNGsha256"]=frozen["sourcePNGsha256"]
        metric["observedMaskInstances"]=frozen["mask_instances"]
        metric["predictionUsesGT"]=False
        summary.append(metric)
        print(f"FRAME={metric['frame']} OBJECTS={len(expected)} PROPOSALS={len(predicted)} "
              f"MATCHED={metric['matched']} PRECISION={metric['proposalPrecision']} "
              f"RECALL={metric['objectRecall']}",flush=True)

    matched=sum(x["matched"] for x in summary)
    expected=sum(x["groundTruthObjects"] for x in summary)
    proposed=sum(x["proposals"] for x in summary)
    report={
        "schema":"chibi.lens.bop.public-detector-smoke.v1",
        "source":"BOP_HB_CC0_REAL_RGB_TRAIN_SCENE_5",
        "sourceArchivePointerSha256":SHA,
        "sourceArchivePointerNotFullyRehashed":True,
        "sourceImageFrames":len(summary),
        "sourceImageGTOnlyForPostDetectionScoring":True,
        "frameSet":list(selected),
        "objectRecallAtIoU50":matched/expected if expected else None,
        "proposalPrecisionAtIoU50":matched/proposed if proposed else None,
        "totalAnnotatedObjects":expected,
        "totalProposals":proposed,
        "matched":matched,
        "detectorType":"Apple VNGenerateObjectnessBasedSaliencyImageRequest",
        "noRealUserMedia":True,
        "noPrivateOCR":True,
        "productionDeploymentAllowed":False,
        "claimedObjectDetectionQualification":False,
        "metrics":summary,
    }
    (opts.scratch/"evaluation.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DETECTOR_PUBLIC_SMOKE_RESULT",json.dumps({
        "match":matched,"objects":expected,"proposals":proposed,
        "recallAt50":report["objectRecallAtIoU50"],"precisionAt50":report["proposalPrecisionAtIoU50"],
    }),flush=True)


if __name__=="__main__":
    main()
