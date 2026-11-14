#!/usr/bin/env python3
"""Fresh HB scene-8 public RGB masked crops; local only, no model fitting.

A one-class-known open-set stress target for the frozen HB 12/15 classifier:
known object 15, unknown 11/22/24/31/32. Object 12 is ABSENT, so the
result cannot qualify two-class recognition or deployment. Never reuse
previously viewed physical heldout scene 11 as a newly blind scene.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import io
import json
from pathlib import Path

from lens_hb_prepare import load_helper, load_histogram

URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
POINTER="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
BYTES=2354714266
SCENE=8
KNOWN={15}
UNKNOWN={11,22,24,31,32}
FRAMES=48

def prepare(out:Path):
    from PIL import Image, ImageStat
    if not out.is_dir() or list(out.iterdir()):
        raise RuntimeError("Scene8 scratch must be a fresh EMPTY local directory")
    archive=load_helper()(URL,POINTER,BYTES)
    root=f"val_primesense/{SCENE:06d}/"
    gt=json.loads(archive.read(root+"scene_gt.json",max_size=8_000_000))
    inf=json.loads(archive.read(root+"scene_gt_info.json",max_size=8_000_000))
    if set(gt)!=set(inf) or len(gt)!=340:
        raise RuntimeError("HB scene8 GT/visibility source mismatch")
    available=Counter(int(obj["obj_id"]) for values in gt.values() for obj in values)
    if available[12]!=0 or any(available[x]!=340 for x in KNOWN|UNKNOWN):
        raise RuntimeError("Unexpected changed scene8 source class census")
    ids=sorted(gt,key=int)
    frames=[ids[int((i+.5)*len(ids)/FRAMES)] for i in range(FRAMES)]
    if len(set(frames))!=FRAMES:raise RuntimeError("Duplicate sampled frame")
    tasks=[]
    for frame in frames:
        selected=[]
        seen=set()
        for idx,(obj,meta) in enumerate(zip(gt[frame],inf[frame])):
            cls=int(obj["obj_id"])
            if cls not in KNOWN|UNKNOWN:continue
            if cls in seen:raise RuntimeError("Duplicate object in one frame")
            seen.add(cls)
            box=meta.get("bbox_visib")
            if not isinstance(box,list) or len(box)!=4:continue
            x,y,w,h=(int(v) for v in box)
            visibility=float(meta.get("visib_fract",0))
            if visibility<.20 or w<26 or h<26 or x<0 or y<0:continue
            selected.append((idx,cls,(x,y,w,h),visibility))
        if selected:tasks.append((frame,selected))
    if len(tasks)>FRAMES:raise RuntimeError("Unbounded frame count")
    featurize=load_histogram()
    def one(task):
        frame,items=task
        png=archive.read(root+f"rgb/{int(frame):06}.png",max_size=8_000_000)
        with Image.open(io.BytesIO(png)) as im:
            if im.format!="PNG":raise RuntimeError("Expected actual PNG")
            im.load(); rgb=im.convert("RGB")
        W,H=rgb.size
        if not (300<=W<=3000 and 200<=H<=3000):
            raise RuntimeError("Untrusted camera geometry")
        output=[]
        for idx,cls,(x,y,w,h),visibility in items:
            if x+w>W or y+h>H:raise RuntimeError("Crop outside source frame")
            mask=archive.read(root+f"mask_visib/{int(frame):06}_{idx:06}.png",
                              max_size=5_000_000)
            with Image.open(io.BytesIO(mask)) as mi:
                if mi.format!="PNG" or mi.size!=(W,H):
                    raise RuntimeError("Untrusted visibility mask")
                mi.load()
                visibility_mask=mi.convert("L").crop((x,y,x+w,y+h))
            coverage=ImageStat.Stat(visibility_mask).mean[0]/255
            if coverage<.13:continue
            crop=Image.composite(rgb.crop((x,y,x+w,y+h)),
                                 Image.new("RGB",(w,h),(127,127,127)),
                                 visibility_mask).resize((224,224),Image.Resampling.BICUBIC)
            row_id=f"hb_08_{int(frame):06}_{cls}"
            image_file=row_id+".png"
            image_path=out/image_file
            with image_path.open("xb") as stream:
                crop.save(stream,format="PNG",optimize=True,compress_level=5)
            values=featurize(crop)
            if len(values)!=48 or any(not 0<=float(v)<=1 for v in values):
                raise RuntimeError("Public RGB histogram feature schema changed")
            output.append({
              "row_id":row_id,"file":image_file,"split":"fresh_ood",
              "scene_id":8,"frame_id":int(frame),"object_id":cls,
              "known":cls in KNOWN,"label":str(cls) if cls in KNOWN else "UNKNOWN",
              "bbox_visible_fraction":round(visibility,6),
              "visible_mask_coverage":round(coverage,8),
              "source_frame_sha256":sha256(png).hexdigest(),
              "crop_sha256":sha256(image_path.read_bytes()).hexdigest(),
              "hist":values})
        return output
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(one,task) for task in tasks]
        for f in as_completed(futures):
            rows+=f.result()
    rows.sort(key=lambda r:(r["frame_id"],r["object_id"]))
    counts=Counter(r["object_id"] for r in rows)
    if counts[15]<25 or sum(v for k,v in counts.items() if k!=15)<60:
        raise RuntimeError(f"Too few known 15 or unknown in scene 8: {counts}")
    if len({r["row_id"] for r in rows})!=len(rows):
        raise RuntimeError("Duplicate public source ROI")
    if len({r["frame_id"] for r in rows})>FRAMES:
        raise RuntimeError("Excessive frame groups")
    (out/"manifest.tsv").write_text("".join(r["row_id"]+"\t"+r["file"]+"\n"
                                              for r in rows))
    (out/"rowmeta.json").write_text(json.dumps(rows,sort_keys=True)+"\n")
    receipt={
      "schema":"junction.lens.hb.scene8.public-crops.v1",
      "archivePointerSHA256":POINTER,"license":"CC0-1.0",
      "sourceVerification":"Official HF pointer and per-member ZIP CRC, NOT full archive digest",
      "scene":8,"sceneUsedInPriorModelTrainOrCalibration":False,
      "sceneUsedInPriorModelTest":False,
      "sourceKnownLabels":[15],"sourceAbsentKnownLabels":[12],
      "unknownLabels":[11,22,24,31,32],
      "knownAndUnknownPerFrame":True,
      "freshOODOnly":True,"modelTrainingOnTheseRows":False,
      "frameGroups":len({r["frame_id"] for r in rows}),
      "rows":len(rows),"counts":dict(sorted((str(k),v) for k,v in counts.items())),
      "rawPixelsUploaded":False,"privateUserData":False,
      "physicalIdentityVerified":False,"actionAuthorized":False,
      "scientificScope":"known15 coverage and rejection of open-set classes ONLY; no two-class claim"
    }
    (out/"preparation.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"rows":len(rows),"frames":receipt["frameGroups"],"counts":receipt["counts"],
                      "sourcePointer":POINTER},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--scratch",type=Path,required=True)
    args=p.parse_args()
    prepare(args.scratch)

if __name__=="__main__":main()
