#!/usr/bin/env python3
"""Bind local Apple Vision feature prints to fresh public HB scene8 OOD numeric CSV.

Only a new physical-scene OOD acceptance artifact, NOT model training,
selection, calibration, or a claim about absent known class 12.
"""
from __future__ import annotations
import argparse
import csv
from hashlib import sha256
import json
import math
from pathlib import Path

PUBLIC_POINTER="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
PARENT_SOURCE="3f8d57cbd47e07be97137e03121205248e88d56f"
FROZEN_TRAIN_CSV_SHA="2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
N=768

def digest(path:Path)->str:
    h=sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()

def finalize(prepared:Path, vision:Path, target:Path):
    if (not prepared.is_dir() or not vision.is_file() or not target.is_dir()
        or list(target.iterdir())):
        raise RuntimeError("Require existing prepared scene8 and fresh EMPTY output")
    prep=json.loads((prepared/"preparation.json").read_text())
    if (prep.get("schema")!="junction.lens.hb.scene8.public-crops.v1"
        or prep.get("archivePointerSHA256")!=PUBLIC_POINTER
        or prep.get("scene")!=8 or prep.get("sourceKnownLabels")!=[15]
        or prep.get("sourceAbsentKnownLabels")!=[12]
        or prep.get("modelTrainingOnTheseRows") is not False):
        raise RuntimeError("This is not the strictly preregistered OOD-only source")
    original=json.loads((prepared/"rowmeta.json").read_text())
    manifest=(prepared/"manifest.tsv").read_text().splitlines()
    if len(original)!=len(manifest) or len(original)>288 or len(original)<70:
        raise RuntimeError("Bounded source scene8 size/order mismatch")
    vectors={}
    with vision.open(encoding="utf8") as f:
        for line in f:
            val=json.loads(line)
            key=val.get("row_id")
            if key in vectors or not isinstance(key,str):
                raise RuntimeError("Duplicate or missing Apple Vision row")
            v=val.get("embedding")
            if (val.get("source")!="PUBLIC_HB_CC0" or
                val.get("vision_revision")!=2 or
                val.get("vision_element_type")!="float32" or
                val.get("elements")!=N or
                not isinstance(v,list) or len(v)!=N or
                not all(isinstance(x,(float,int)) and math.isfinite(x) for x in v)):
                raise RuntimeError("Unsupported Apple Vision model version or embedding")
            mag=math.sqrt(sum(float(x)**2 for x in v))
            if not 1e-9<mag<10000:raise RuntimeError("Invalid vector norm")
            vectors[key]=[round(float(x)/mag,8) for x in v]
    if set(vectors)!={r["row_id"] for r in original}:
        raise RuntimeError("Local Apple Vision features missing or duplicated")
    rows=[]
    seen={}
    for i,rec in enumerate(original):
        row=rec["row_id"]
        if manifest[i]!=row+"\t"+rec["file"]:
            raise RuntimeError("Vision source manifest order mismatch")
        pixel=prepared/rec["file"]
        if not pixel.is_file() or digest(pixel)!=rec["crop_sha256"]:
            raise RuntimeError("Public source crop changed after Apple Vision extraction")
        obj=int(rec["object_id"])
        if (rec["scene_id"]!=8 or rec["split"]!="fresh_ood"
            or obj not in (11,15,22,24,31,32)
            or rec["known"]!=(obj==15)
            or rec["label"]!=("15" if obj==15 else "UNKNOWN")):
            raise RuntimeError("Unexpected heldout class, scene or label")
        if len(rec["hist"])!=48 or any(not 0<=v<=1 for v in rec["hist"]):
            raise RuntimeError("Bad RGB baseline features")
        seen[obj]=seen.get(obj,0)+1
        sample={
            "source":"bop-hb-val-primesense-public-cc0",
            "license":"CC0-1.0",
            "modality":"REAL_RGB_MASKED",
            "row_id":row,"split":"fresh_ood",
            "scene_id":8,"frame_id":rec["frame_id"],"object_id":obj,
            "label":rec["label"],"known_class":rec["known"],
            "visible_fraction":rec["bbox_visible_fraction"],
            "mask_coverage":rec["visible_mask_coverage"],
        }
        sample.update({f"c{k:02}":float(v) for k,v in enumerate(rec["hist"])})
        sample.update({f"v{k:03}":float(v) for k,v in enumerate(vectors[row])})
        rows.append(sample)
    if seen.get(15,0)<25 or sum(v for k,v in seen.items() if k!=15)<60:
        raise RuntimeError("Insufficient known and OOD examples")
    if len({r["frame_id"] for r in rows})!=prep["frameGroups"]:
        raise RuntimeError("Frame-cluster provenance mismatch")
    fields=list(rows[0])
    csvfile=target/"fresh-scene8-public-ood.csv"
    with csvfile.open("x",encoding="utf8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator="\n")
        writer.writeheader();writer.writerows(rows)
    admission={
        "schema":"junction.lens.hb.scene8.public-ood-numeric.v1",
        "sourceParentSHA":PARENT_SOURCE,
        "sourceTrainingCSVsha256":FROZEN_TRAIN_CSV_SHA,
        "sourceArchivePointerSHA256":PUBLIC_POINTER,
        "sourceMemberVerification":"Official HF linked pointer plus per-member ZIP CRC; full archive byte hash not verified",
        "sourceLicense":"CC0-1.0",
        "scene":8,"sourceTrainScenes":[5,9],"sourceCalibrationScene":10,
        "excludedPreviouslyExposedScene":11,
        "knownClassPresent":[15],"knownClassAbsent":[12],
        "unknownClassesPresent":sorted(k for k in seen if k!=15),
        "counts":{str(k):v for k,v in sorted(seen.items())},
        "rowCount":len(rows),
        "frameGroups":prep["frameGroups"],
        "originalSourceCropsLocalOnly":True,
        "realPublicVisionFeaturePrintRevision":2,
        "visionDimensions":N,
        "csvSha256":digest(csvfile),
        "rawPixelsUploaded":False,
        "privateOwnerData":False,"physicalIdentityVerified":False,
        "actionAuthorized":False,"modelTrainingFromScene8Allowed":False,
        "freshOODOnly":True,
        "canQualifyKnownClass12":False,
        "canQualifyTwoClassObjectRecognition":False
    }
    (target/"admission.json").write_text(json.dumps(admission,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"rows":len(rows),"frameGroups":prep["frameGroups"],
                      "classCounts":admission["counts"],"csvSha":admission["csvSha256"]},
                     sort_keys=True),flush=True)

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--prepared",type=Path,required=True)
    a.add_argument("--vision",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True)
    p=a.parse_args()
    finalize(p.prepared,p.vision,p.out)
if __name__=="__main__":main()
