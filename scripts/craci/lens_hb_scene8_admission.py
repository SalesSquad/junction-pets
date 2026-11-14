#!/usr/bin/env python3
"""Fail-closed admission: one fresh public HB scene8 OOD test, numerics only.

Not an ML training set. Dataset has known class15 only; class12 is absent.
Prohibits reopening old scene11 as "fresh" or training on scene8 rows.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
OLD_SHA="2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
NEW_SHA="4c29e622d2dd4f709792ef0c41e7a09d28f16020ef941b5b64a1cc8469ae464d"
POINTER="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
PARENT_SHA="3f8d57cbd47e07be97137e03121205248e88d56f"
OLD_SOURCE="bop-hb-val-primesense-public-cc0"
COLUMNS=[f"c{i:02}" for i in range(48)]+[f"v{i:03}" for i in range(768)]
META={"source","license","modality","row_id","split","scene_id","frame_id",
      "object_id","label","known_class","visible_fraction","mask_coverage"}
ALLOWED=META|set(COLUMNS)
OBJECTS={11,15,22,24,31,32}

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as inp:
  for block in iter(lambda:inp.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def admit(old:Path,new:Path,manifest:Path)->dict:
 if not all(p.is_file() and not p.is_symlink() for p in (old,new,manifest)):
  raise RuntimeError("Only pinned ordinary public numerical files are permitted")
 if sha(old)!=OLD_SHA or sha(new)!=NEW_SHA:
  raise RuntimeError("Source SHA256 mismatch, no unchecked data admission")
 p=json.loads(manifest.read_text())
 if (p.get("schema")!="junction.lens.hb.scene8.public-ood-numeric.v1"
     or p.get("sourceParentSHA")!=PARENT_SHA
     or p.get("sourceArchivePointerSHA256")!=POINTER
     or p.get("sourceTrainingCSVsha256")!=OLD_SHA
     or p.get("csvSha256")!=NEW_SHA
     or p.get("sourceLicense")!="CC0-1.0"
     or p.get("scene")!=8
     or p.get("sourceTrainScenes")!=[5,9]
     or p.get("sourceCalibrationScene")!=10
     or p.get("excludedPreviouslyExposedScene")!=11
     or p.get("knownClassPresent")!=[15]
     or p.get("knownClassAbsent")!=[12]
     or set(p.get("unknownClassesPresent",[]))!={11,22,24,31,32}
     or p.get("rawPixelsUploaded") is not False
     or p.get("privateOwnerData") is not False
     or p.get("modelTrainingFromScene8Allowed") is not False
     or p.get("canQualifyTwoClassObjectRecognition") is not False
     or p.get("actionAuthorized") is not False):
  raise RuntimeError("Untrusted public source rights, split or claim")
 with new.open(newline="") as inp:
  reader=csv.DictReader(inp)
  if set(reader.fieldnames or [])!=ALLOWED:
   raise RuntimeError("Unexpected feature schema or sensitive metadata")
  seen=set();counts={};frames=set();rows=0
  for obj in reader:
   rows+=1
   if any(obj[c]=="" for c in COLUMNS):raise RuntimeError("Empty public numeric features")
   if (obj["source"]!=OLD_SOURCE or obj["license"]!="CC0-1.0"
       or obj["modality"]!="REAL_RGB_MASKED" or obj["split"]!="fresh_ood"
       or int(obj["scene_id"])!=8):
    raise RuntimeError("Scene leakage or private source")
   label=int(obj["object_id"])
   if label not in OBJECTS:raise RuntimeError("Unexpected source class")
   if obj["label"]!=("15" if label==15 else "UNKNOWN"):
    raise RuntimeError("Known/unknown label contract broken")
   if obj["known_class"].lower()!=("true" if label==15 else "false"):
    raise RuntimeError("Class flags contradict original source")
   if obj["row_id"] in seen:raise RuntimeError("Duplicate source row")
   seen.add(obj["row_id"])
   if not obj["row_id"].startswith("hb_08_"):raise RuntimeError("Unexpected source ROI key")
   frame=int(obj["frame_id"]);frames.add(frame)
   counts[label]=counts.get(label,0)+1
   values=[float(obj[c]) for c in COLUMNS]
   if (not all(math.isfinite(x) for x in values)
       or not all(0<=x<=1 for x in values[:48])
       or abs(math.sqrt(sum(x*x for x in values[48:]))-1)>.001):
    raise RuntimeError("Invalid public AppleVision embedding or RGB features")
 if rows!=282 or len(frames)!=48 or counts!={11:48,15:42,22:48,24:48,31:48,32:48}:
  raise RuntimeError("Source sample/scene change, needs new preregistration")
 if p.get("rowCount")!=rows or p.get("frameGroups")!=len(frames):
  raise RuntimeError("Admission sizes incompatible with actual sampled features")
 return {
  "schema":"junction.craci.hb.scene8.ood.admission.v1",
  "license":"CC0-1.0","sourceParentSHA":PARENT_SHA,
  "sourceArchivePointerSHA256":POINTER,
  "originalNumericTrainingCSVsha256":OLD_SHA,
  "newBlindOODcsvSHA256":NEW_SHA,
  "scene":8,"sourceModelTrainScenes":[5,9],
  "sourceModelCalibrationScene":10,"excludedExposedTestScene":11,
  "knownPresent":[15],"knownAbsent":[12],
  "unknown":[11,22,24,31,32],
  "rows":rows,"frameGroups":len(frames),
  "sourceReportedProvenanceNotFullArchiveSHA":True,
  "privatePixelsUploaded":False,"privateMediaUsed":False,
  "modelTrainingOnHeldoutAllowed":False,"twoClassClaimAllowed":False,
  "physicalIdentityVerified":False,"actionAuthorized":False,
 }

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--old",type=Path,required=True)
 ap.add_argument("--new",type=Path,required=True)
 ap.add_argument("--manifest",type=Path,required=True)
 ap.add_argument("--out",type=Path,required=True)
 args=ap.parse_args()
 receipt=admit(args.old,args.new,args.manifest)
 with args.out.open("x") as output:
  json.dump(receipt,output,indent=2,sort_keys=True)
  output.write("\n")
 print(json.dumps(receipt,sort_keys=True))
if __name__=="__main__":main()
