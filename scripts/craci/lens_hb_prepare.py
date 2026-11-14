#!/usr/bin/env python3
"""Public CC0 HomebrewedDB REAL-RGB crop preparation with ZIP HTTP Range.

Primary corrected design: same known classes 12/15 occur in train scenes
5/9, calibration scene 10 and *never-used* heldout scene 11. Unknown classes
3/22/23 are present only as negative calibration/heldout examples. Use
ground-truth visible masks to remove background, not ground-truth metadata as
predictor values. No private user, OCR, glasses, children or event media.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import io
import json
from pathlib import Path
import importlib.util
import sys
from typing import Any

URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
SHA="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
SIZE=2354714266
SCENES={"train":[5,9],"cal":[10],"test":[11]}
KNOWN={12,15}
NEGATIVE={3,22,23}
FRAMES_PER_SCENE=48
MIN_VISIBILITY=.20

def load_helper():
    src=Path(__file__).with_name("lens_hb_range.py")
    spec=importlib.util.spec_from_file_location("lens_hb_range",src)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module.ZipHTTP

def load_histogram():
    src=Path(__file__).with_name("lens-real-bop.py")
    spec=importlib.util.spec_from_file_location("lens_hb_prior_hist",src)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod.image_features

def prepare(scratch):
    from PIL import Image,ImageStat
    if not scratch.is_dir() or list(scratch.iterdir()):
        raise RuntimeError("New scratch root must be empty, never overwrite owned data")
    extractor=load_histogram()
    archive=load_helper()(URL,SHA,SIZE)
    print("SOURCE_INDEX",len(archive.members),flush=True)
    target=[]
    for split,scene_ids in SCENES.items():
        for scene in scene_ids:
            root=f"val_primesense/{scene:06}/"
            gt=json.loads(archive.read(root+"scene_gt.json",max_size=8_000_000))
            info=json.loads(archive.read(root+"scene_gt_info.json",max_size=8_000_000))
            if set(gt)!=set(info) or len(gt)!=340:
                raise RuntimeError("Ground truth and annotated boxes differ")
            ids=sorted(gt,key=int)
            sample=[ids[int((i+.5)*len(ids)/FRAMES_PER_SCENE)]
                    for i in range(FRAMES_PER_SCENE)]
            if len(set(sample))!=FRAMES_PER_SCENE:
                raise RuntimeError("Duplicate fixed sampled source frame")
            for frame in sample:
                objects=[]
                observed_classes=set()
                for idx,(o,meta) in enumerate(zip(gt[frame],info[frame])):
                    label=int(o["obj_id"])
                    # Training classes are measured in every split.
                    # Distractors are not fitted, only calibration/test negatives.
                    if label not in KNOWN and (split=="train" or label not in NEGATIVE):
                        continue
                    if label in observed_classes:
                        raise RuntimeError("A known object duplicated in a frame")
                    observed_classes.add(label)
                    box=meta.get("bbox_visib")
                    if not isinstance(box,list) or len(box)!=4:
                        continue
                    x,y,w,h=(int(v) for v in box)
                    visibility=float(meta.get("visib_fract",0))
                    if visibility<MIN_VISIBILITY or w<26 or h<26 or x<0 or y<0:
                        continue
                    objects.append({"idx":idx,"class":label,"box":(x,y,w,h),
                                    "visibility":visibility})
                if objects:
                    target.append((split,scene,frame,objects))
    if len(target)>4*FRAMES_PER_SCENE:
        raise RuntimeError("Unbounded selected source frames")

    # Bound both server requests and local scratch disk. Source image pixels
    # exist only on the authorized Mac in temporary process-owned paths.
    def one(task):
        split,scene,frame,objects=task
        root=f"val_primesense/{scene:06}/"
        rgb_path=root+f"rgb/{int(frame):06}.png"
        rgb=archive.read(rgb_path,max_size=8_000_000)
        with Image.open(io.BytesIO(rgb)) as image:
            if image.format!="PNG":raise RuntimeError("Expected real RGB PNG")
            image.load()
            width,height=image.size
            if not (300<=width<=3000 and 200<=height<=3000):
                raise RuntimeError("Unexpected public camera geometry")
            pixels=image.convert("RGB")
        frame_sha=sha256(rgb).hexdigest()
        produced=[]
        for obj in objects:
            x,y,w,h=obj["box"]
            if x+w>width or y+h>height:
                raise RuntimeError("Object crop outside real camera frame")
            mask_path=root+f"mask_visib/{int(frame):06}_{obj['idx']:06}.png"
            mask_png=archive.read(mask_path,max_size=5_000_000)
            with Image.open(io.BytesIO(mask_png)) as im:
                if im.format!="PNG":raise RuntimeError("Untrusted source mask")
                im.load()
                if im.size!=(width,height):
                    raise RuntimeError("Visible mask/camera frame misalignment")
                visible=im.convert("L").crop((x,y,x+w,y+h))
            crop=pixels.crop((x,y,x+w,y+h))
            # Gray-fill EVERYTHING outside GT object pixels, block background
            # shortcuts. Crop bbox/visibility are used only to prepare and audit.
            normalized=Image.composite(crop,Image.new("RGB",crop.size,(127,127,127)),visible)
            mean_visibility=ImageStat.Stat(visible).mean[0]/255
            if mean_visibility<.13:
                continue
            resized=normalized.resize((224,224),Image.Resampling.BICUBIC)
            row_id=f"hb_{scene:02}_{int(frame):06}_{obj['class']}"
            filename=row_id+".png"
            dest=scratch/filename
            if dest.exists():
                raise RuntimeError("Refuse to overwrite owned crop")
            resized.save(dest,optimize=True,compress_level=5)
            hist=extractor(resized)
            if len(hist)!=48:
                raise RuntimeError("Broken existing pixel feature schema")
            produced.append({
              "row_id":row_id, "file":filename, "split":split,
              "scene_id":scene,"frame_id":int(frame),
              "object_id":obj["class"],"known":obj["class"] in KNOWN,
              "label":str(obj["class"]) if obj["class"] in KNOWN else "UNKNOWN",
              "bbox_visible_fraction":round(obj["visibility"],6),
              "source_frame_sha256":frame_sha,
              "visible_mask_coverage":round(mean_visibility,8),
              "crop_sha256":sha256(dest.read_bytes()).hexdigest(),
              "hist":hist
            })
        return produced

    items=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(one,task):task for task in target}
        for future in as_completed(futures):
            items.extend(future.result())
    items=sorted(items,key=lambda x:(("train","cal","test").index(x["split"]),
                                     x["scene_id"],x["frame_id"],x["object_id"]))
    counter=Counter((row["split"],row["scene_id"],row["label"]) for row in items)
    for split,ids in SCENES.items():
        for scene in ids:
            for label in map(str,sorted(KNOWN)):
                if counter[split,scene,label]<30:
                    raise RuntimeError(f"Insufficient known samples {split}/{scene}/{label}")
    for split in ("cal","test"):
        for label in NEGATIVE:
            if counter[split,SCENES[split][0],"UNKNOWN"]<60:
                raise RuntimeError("Missing sufficient public distractor negatives")
    if len({row["row_id"] for row in items})!=len(items):
        raise RuntimeError("Duplicate image source IDs")
    manifest="".join(row["row_id"]+"\t"+row["file"]+"\n" for row in items)
    (scratch/"manifest.tsv").write_text(manifest)
    (scratch/"rowmeta.json").write_text(json.dumps(items,sort_keys=True)+"\n")
    count_report={
      "schema":"chibi.lens.hb.prepared-public-images.v1",
      "archive":"bop-hb-val-primesense",
      "sourceUrl":URL,"sourceArchivePointerSha256":SHA,
      "sourceArchivePointerBytes":SIZE,
      "sourceVerification":"official_HF_pointer_plus_per_member_ZIP_CRC32_NOT_FULL_ARCHIVE_HASH",
      "license":"CC0-1.0",
      "source":"real_camera_rgb",
      "rows":len(items),
      "selectedFrameGroups":FRAMES_PER_SCENE,
      "knownLabels":[12,15],
      "knownTrainScenes":SCENES["train"],
      "calibrationScene":SCENES["cal"],
      "heldoutScene":SCENES["test"],
      "unknownDistractors":sorted(NEGATIVE),
      "counts":{"/".join(map(str,k)):v for k,v in sorted(counter.items())},
      "maskBackgroundRemoved":True,
      "realPhotosNeverUploaded":True,
      "labelSceneConfounded":False,
      "sourceReportedOnly":True
    }
    (scratch/"preparation.json").write_text(json.dumps(count_report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"rows":len(items),"groups":count_report["counts"],
                      "unique_frames":len({(x["scene_id"],x["frame_id"]) for x in items})},
                     sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--scratch",type=Path,required=True)
    a=p.parse_args()
    prepare(a.scratch)

if __name__=="__main__":
    main()
