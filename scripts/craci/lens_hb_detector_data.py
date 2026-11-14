#!/usr/bin/env python3
"""Prepare PRIVATE-TO-TASK scratch from PUBLIC CC0 BOP HomebrewedDB.

Uses TRAIN scene 5 and 9 GT, calibration scene 10 GT. A new scene 12 is
pre-registered and SEALED: only RGB pixels fetched, NO GT file until after
all detector predictions and threshold freeze. Do not commit RGB images.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
ARCHIVE_SHA="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
ARCHIVE_BYTES=2354714266
PLANS={
  "initial":{
    "schema":"chibi.lens.hb.domain-detector-data.v1",
    "splits":{"train":(5,9),"calibration":(10,),"sealed":(12,)},
    "frames":{"train":40,"calibration":30,"sealed":30},
  },
  "diverse":{
    "schema":"chibi.lens.hb.domain-detector-diverse-data.v2",
    "splits":{"train":tuple(range(1,11)),"calibration":(11,),"sealed":(13,)},
    "frames":{"train":16,"calibration":24,"sealed":24},
  },
}
IMAGE_WIDTH=320
IMAGE_HEIGHT=240
MIN_VIS=.20

def load_archive():
    script=Path(__file__).with_name("lens_hb_range.py")
    spec=importlib.util.spec_from_file_location("chibi_hb_range",script)
    if not spec or not spec.loader:raise RuntimeError("Pinned public ZIP range reader absent")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module.ZipHTTP(URL,ARCHIVE_SHA,ARCHIVE_BYTES)

def sample_ids(count:int,n:int)->list[int]:
    if n<1 or count<n:raise ValueError("Not enough physical camera frames")
    result=[int((i+.5)*count/n) for i in range(n)]
    if len(set(result))!=n:raise RuntimeError("Frame sampling has duplicates")
    return result

def digest(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def prepare(out:Path,plan_name:str="initial"):
    from PIL import Image
    if plan_name not in PLANS:
        raise ValueError("Unregistered physical-scene split")
    plan=PLANS[plan_name]
    splits=plan["splits"]
    per_scene=plan["frames"]
    if not out.is_dir() or any(out.iterdir()):
        raise RuntimeError("Expected new, empty task-owned output")
    if not str(out.resolve()).startswith("/private/tmp/chibi-hb-domain-detector-"):
        raise RuntimeError("Only authorized Mac task scratch destination")
    reader=load_archive()
    print("ARCHIVE_INDEX_VERIFIED",len(reader.members),flush=True)
    entries=[]; counts=Counter()
    for split,scene_ids in splits.items():
        for scene in scene_ids:
            base=f"val_primesense/{scene:06d}/"
            # This is intentionally forbidden for sealed scene 12.
            if split!="sealed":
                gt=json.loads(reader.read(base+"scene_gt.json",max_size=8_000_000))
                info=json.loads(reader.read(base+"scene_gt_info.json",max_size=8_000_000))
                if len(gt)!=340 or set(gt)!=set(info):
                    raise RuntimeError("Untrusted public annotations in training/calibration")
            for frame_id in sample_ids(340,per_scene[split]):
                frame=str(frame_id)
                png=reader.read(base+f"rgb/{frame_id:06d}.png",max_size=8_000_000)
                if png[:8]!=bytes.fromhex("89504e470d0a1a0a"):
                    raise RuntimeError("Public source is not PNG")
                with Image.open(io.BytesIO(png)) as img:
                    if img.format!="PNG":raise RuntimeError("Source image decoder mismatch")
                    img.load()
                    width,height=img.size
                    if not 300<=width<=3000 or not 200<=height<=3000:
                        raise RuntimeError("Unexpected RGB source resolution")
                    resized=img.convert("RGB").resize(
                        (IMAGE_WIDTH,IMAGE_HEIGHT),Image.Resampling.BILINEAR)
                filename=f"{split}_s{scene:02d}_f{frame_id:06d}.png"
                path=out/filename
                if path.exists():raise RuntimeError("Will not overwrite source")
                resized.save(path,optimize=True)
                row={"file":filename,"split":split,"scene_id":scene,
                     "frame_id":frame_id,"source_png_sha256":digest(png),
                     "resized_sha256":digest(path.read_bytes()),
                     "source_dimensions":[width,height],
                     "image_dimensions":[IMAGE_WIDTH,IMAGE_HEIGHT],
                     "has_annotations":split!="sealed"}
                if split!="sealed":
                    objects=gt[frame];annotation=info[frame]
                    if len(objects)!=len(annotation):
                        raise RuntimeError("Misaligned source GT")
                    boxes=[];ids=[]
                    for obj,meta in zip(objects,annotation):
                        if float(meta.get("visib_fract",0))<MIN_VIS:continue
                        xywh=meta.get("bbox_visib")
                        if not isinstance(xywh,list) or len(xywh)!=4:continue
                        x,y,w,h=[int(v) for v in xywh]
                        if w<8 or h<8 or x<0 or y<0 or x+w>width or y+h>height:
                            continue
                        xx1=max(0,round(x*IMAGE_WIDTH/width))
                        yy1=max(0,round(y*IMAGE_HEIGHT/height))
                        xx2=min(IMAGE_WIDTH,round((x+w)*IMAGE_WIDTH/width))
                        yy2=min(IMAGE_HEIGHT,round((y+h)*IMAGE_HEIGHT/height))
                        if xx2-xx1<4 or yy2-yy1<4:continue
                        boxes.append([xx1,yy1,xx2,yy2])
                        ids.append(int(obj["obj_id"]))
                    if not boxes:raise RuntimeError(f"No trainable public objects: {scene}/{frame}")
                    row["boxes_xyxy"]=boxes
                    row["object_class_ids_audit_only"]=ids
                    counts[(split,str(scene))]+=len(boxes)
                else:
                    if any(k in row for k in ("boxes_xyxy","object_class_ids_audit_only")):
                        raise RuntimeError("Sealed test contains GT")
                entries.append(row)
                if len(entries)%25==0:
                    print("PUBLIC_FRAMES_PREPARED",len(entries),flush=True)
    # Force video+scene isolation: never random-split neighboring video frames.
    if len({r["source_png_sha256"] for r in entries})!=len(entries):
        raise RuntimeError("Duplicate source video frame across splits")
    expected_total=sum(len(scenes)*per_scene[split] for split,scenes in splits.items())
    if len(entries)!=expected_total:
        raise RuntimeError(f"Unexpected public split size {len(entries)}")
    record={
      "schema":plan["schema"],
      "plan":plan_name,
      "source":"PUBLIC_BOP_HOMEBREWEDDB_CC0",
      "sourceUrl":URL,"officialLicense":"CC0-1.0",
      "licenseReference":"https://bop.felk.cvut.cz/datasets/",
      "sourceArchivePointerSHA256":ARCHIVE_SHA,
      "sourceArchiveSizeBytes":ARCHIVE_BYTES,
      "sourceVerification":"Official HF linked etag plus per-member CRC32; FULL_ARCHIVE_NOT_REHASHED",
      "sourceFrameCounts":{s:len(splits[s])*per_scene[s] for s in splits},
      "framesPerScene":per_scene,
      "sceneSplits":{k:list(v) for k,v in splits.items()},
      "sealedSceneGTRead":False,
      "knownInstanceClassesNotUsedForDetector":True,
      "allVisibleObjectsSingleObjectnessClass":True,
      "gtOnlyTrainAndCalibration":True,
      "rawImagesLocalOnly":True,
      "familyMediaUsed":False,
      "privateOCRUsed":False,
      "physicalIdentityVerified":False,
      "actionAuthorized":False,
      "objectCountsTrainCalibration":{"/".join(k):v for k,v in sorted(counts.items())},
      "samples":entries,
    }
    path=out/"manifest.json"
    path.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    print("DOMAIN_DETECTOR_PREP_COMPLETE",json.dumps({
      "images":len(entries),"train":record["sourceFrameCounts"]["train"],
      "cal":record["sourceFrameCounts"]["calibration"],
      "sealed":record["sourceFrameCounts"]["sealed"],
      "objects":record["objectCountsTrainCalibration"]},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--plan",choices=("initial","diverse"),default="initial")
    opts=p.parse_args()
    prepare(opts.out,plan_name=opts.plan)

if __name__=="__main__":
    main()
