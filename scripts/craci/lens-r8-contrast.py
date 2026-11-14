#!/usr/bin/env python3
"""Independent BOP YCB-V *real camera RGB* crop study for Chibi Lens R8.

New object classes 1,3,12; fixed scene splits; numeric pixel & image metadata
only. Scene/camera GT metrics remain EVALUATION-ONLY, not model features.
No user-sourced media, OCR, persons, telemetry or raw pixels leave local host.
"""
import argparse
import csv
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import statistics
import sys
import zipfile

ARCHIVE_SHA = "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
SCENES = {"train": (48,49,51,54), "cal":(55,), "test":(56,57,58)}
CLASSES = (1,3,12)
EXACT_FRAMES = 75


def sha_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1 << 20),b""):h.update(block)
    return h.hexdigest()


def load_feature_extractor(file):
    spec=importlib.util.spec_from_file_location("chibi_lens_public_features",file)
    if spec is None or spec.loader is None:raise RuntimeError("Source feature implementation absent")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module.image_features


def run(archive,source_code,output):
    from PIL import Image, ImageStat
    import pyarrow as pa
    import pyarrow.parquet as pq
    if not output.is_dir() or list(output.iterdir()):
        raise RuntimeError("Output must be a new empty scratch directory")
    if sha_file(archive)!=ARCHIVE_SHA:
        raise RuntimeError("Unapproved or altered real image archive")
    if len(set(s for scenes in SCENES.values() for s in scenes))!=8:
        raise RuntimeError("Scene split contamination")
    features=load_feature_extractor(source_code)
    rows=[]; count=Counter(); frames=set(); camera=Counter(); excluded=Counter()
    with zipfile.ZipFile(archive) as z:
        paths=set(z.namelist())
        if any(p.startswith("/") or ".." in Path(p).parts or "\\" in p for p in paths):
            raise RuntimeError("Untrusted archive entry")
        for split, scenes in SCENES.items():
            for scene in scenes:
                root=f"test/{scene:06d}/"
                gt=json.loads(z.read(root+"scene_gt.json"))
                info=json.loads(z.read(root+"scene_gt_info.json"))
                cam=json.loads(z.read(root+"scene_camera.json"))
                ids=sorted(gt,key=int)
                if len(ids)!=75 or set(ids)!=set(info) or set(ids)!=set(cam):
                    raise RuntimeError(f"Invalid 75 annotated frame alignment for scene {scene}")
                for frame in ids:
                    if len(gt[frame])!=len(info[frame]):
                        raise RuntimeError("GT-bbox mismatch")
                    if not 0 <= int(frame)<=999999:
                        raise RuntimeError("Malformed BOP frame ID")
                    path=root+f"rgb/{int(frame):06d}.png"
                    if path not in paths or z.getinfo(path).file_size>6_000_000:
                        raise RuntimeError("Source frame missing/oversized")
                    rgb=z.read(path)
                    with Image.open(io.BytesIO(rgb)) as image:
                        if image.format!="PNG":
                            raise RuntimeError("Not real public BOP RGB PNG")
                        image.load()
                        width,height=image.size
                        image=image.convert("RGB")
                    if not (200<=width<=3000 and 200<=height<=3000):
                        raise RuntimeError("Unexpected RGB source geometry")
                    digest=hashlib.sha256(rgb).hexdigest()
                    frames.add(digest)
                    k=cam[frame].get("cam_K",[])
                    if not isinstance(k,list) or len(k)!=9:
                        raise RuntimeError("BOP camera intrinsics missing")
                    camera[(scene,round(float(k[0]),2),round(float(k[4]),2))]+=1
                    for idx,(obj,meta) in enumerate(zip(gt[frame],info[frame])):
                        label=int(obj["obj_id"])
                        if label not in CLASSES:
                            continue
                        bbox=meta.get("bbox_visib")
                        vis=float(meta.get("visib_fract",0))
                        if not isinstance(bbox,list) or len(bbox)!=4:
                            excluded["missing_bbox"]+=1;continue
                        x,y,w,h=[int(val) for val in bbox]
                        if vis<0.20 or w<24 or h<24 or x<0 or y<0 or x+w>width or y+h>height:
                            excluded["small_occluded_or_invalid"]+=1;continue
                        crop=image.crop((x,y,x+w,y+h))
                        vals=features(crop)
                        # Runtime-observable metadata from public pixels ONLY.
                        gray=crop.convert("L")
                        stats=ImageStat.Stat(gray)
                        brightness=stats.mean[0]/255
                        contrast=stats.stddev[0]/255
                        thumb=crop.resize((16,16),Image.Resampling.BILINEAR)
                        pix=list(thumb.getdata())
                        saturation=sum((max(px)-min(px))/255 for px in pix)/len(pix)
                        edge=sum(vals[40:48])/8
                        if not all(0<=v<=1 for v in (brightness,contrast,saturation,edge)):
                            raise RuntimeError("Unbounded observational metadata")
                        row=dict(source="bop-ycbv-mit",license="MIT",
                            modality="REAL_RGB",study="contrast_v1",split=split,
                            scene_id=scene,frame_id=int(frame),object_id=label,
                            visible_fraction=round(vis,8),
                            bbox_area_fraction=round(w*h/(width*height),8),
                            camera_fx=round(float(k[0]),4),
                            camera_fy=round(float(k[4]),4),
                            brightness=round(brightness,9),
                            contrast=round(contrast,9),
                            saturation=round(saturation,9),
                            edge_strength=round(edge,9),
                            frame_sha256=digest,
                            crop_id=hashlib.sha256(f"{scene}:{frame}:{idx}:{label}".encode()).hexdigest())
                        row.update({f"f{j:02d}":v for j,v in enumerate(vals)})
                        rows.append(row);count[(split,scene,label)]+=1
    for split in SCENES:
        for label in CLASSES:
            if sum(n for (s,_,l),n in count.items() if s==split and l==label)<50:
                raise RuntimeError(f"Undersampled split class: {split} / {label}")
    if len({r["crop_id"] for r in rows})!=len(rows):
        raise RuntimeError("Duplicate labeled object crop")
    if len(frames)!=8*75:
        raise RuntimeError(f"Unexpected distinct source RGB frames {len(frames)}")
    # Save only numerical data and digest; no image files/EXIF/OCR exports.
    t=pa.Table.from_pylist(rows)
    t=t.replace_schema_metadata({
        "source":"BOP YCB-V MIT licensed public REAL RGB",
        "study":"r8-contrast-v1",
        "pii":"none-ordinary-YCB-object-photographs",
        "training_fields":"f00..f47,brightness,contrast,saturation,edge_strength",
        "audit_only":"scene_id,frame_id,object_id,visible_fraction,bbox_area_fraction,camera_fx,camera_fy",
        "source_archive_sha256":ARCHIVE_SHA})
    pq.write_table(t,output/"contrast-features.parquet",compression="zstd",row_group_size=512)
    if pq.read_table(output/"contrast-features.parquet").num_rows!=len(rows):
        raise RuntimeError("Parquet integrity failure")
    fields=[key for key in t.column_names if key not in ("frame_sha256","crop_id")]
    with (output/"contrast-features.csv").open("x",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n")
        w.writeheader()
        for row in rows:w.writerow({k:row[k] for k in fields})
    def mean(rows,field):
        return round(sum(r[field] for r in rows)/len(rows),8) if rows else None
    groups=[]
    for split in SCENES:
        for scene in SCENES[split]:
            for label in CLASSES:
                subset=[r for r in rows if r["split"]==split and r["scene_id"]==scene and r["object_id"]==label]
                if subset:
                    groups.append(dict(split=split,scene=scene,objectClass=label,
                        n=len(subset),brightnessMean=mean(subset,"brightness"),
                        contrastMean=mean(subset,"contrast"),edgeMean=mean(subset,"edge_strength"),
                        visibleFractionMean=mean(subset,"visible_fraction"),
                        boxAreaMean=mean(subset,"bbox_area_fraction")))
    metadata={
      "schema":"chibi.lens.public-scene-metadata.v1",
      "sourceArchiveSha256":ARCHIVE_SHA,
      "sourceLicenses":["MIT"], "sourceModality":"REAL_RGB",
      "objectClasses":list(CLASSES),"sceneSplits":{k:list(v) for k,v in SCENES.items()},
      "sourceCameraIntrinsics": [{"scene":s,"fx":fx,"fy":fy,"frames":n}
         for (s,fx,fy),n in sorted(camera.items())],
      "groups":groups,"excluded":dict(excluded),
      "metadataAvailability":"Only observable image features enter prediction; source GT is evaluation-only",
      "noPersonalPhotos":True,"noOCR":True,"noFramePayloads":True}
    (output/"scene-metadata.json").write_text(json.dumps(metadata,indent=2,sort_keys=True)+"\n")
    admission={
      "schema":"chibi.lens.real-contrast-source.v1",
      "source":"BOP YCB-Video public MIT",
      "sourceArchiveSha256":ARCHIVE_SHA,
      "sourceUrl":"https://huggingface.co/datasets/bop-benchmark/ycbv/resolve/main/ycbv_test_bop19.zip",
      "license":"MIT","licenseReference":"https://bop.felk.cvut.cz/datasets/",
      "sourceImageCount":len(frames),"sourceCropCount":len(rows),
      "objectClassCount":len(CLASSES),
      "classCounts": {f"{s}:{l}":sum(n for (sp,_,lab),n in count.items() if sp==s and lab==l)
         for s in SCENES for l in CLASSES},
      "sourceSceneGroups":{k:list(v) for k,v in SCENES.items()},
      "sourceManifestSha256":sha_file(source_code),
      "csvSha256":sha_file(output/"contrast-features.csv"),
      "parquetSha256":sha_file(output/"contrast-features.parquet"),
      "sceneMetadataSha256":sha_file(output/"scene-metadata.json"),
      "sourceReported":True,"providerAttestation":False,
      "rawPixelsCloud":False,"familyOrUserPhotos":False,
      "trainingAllowed":True,"inferenceHasGroundTruthVisibility":False,
      "realWearableDataset":False,"bopLeaderboardCompatible":False}
    (output/"admission.json").write_text(json.dumps(admission,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"rows":len(rows),"frames":len(frames),"sha":admission["csvSha256"],
       "classCounts":admission["classCounts"]},sort_keys=True))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--source-extractor",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();run(a.archive,a.source_extractor,a.out)


if __name__=="__main__":
    main()
