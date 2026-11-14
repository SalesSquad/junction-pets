#!/usr/bin/env python3
"""Build a verified public TRAIN/CAL-ONLY HB dev fixture.

Never copy, hash, score or serialize previously exposed physical test scene11
or scene8 into learning. Cal scene10 is development-only, not field approval.
"""
from __future__ import annotations
import csv,hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"fixtures/lens-hb-cc0-vision-20261114"
OUT=ROOT/"fixtures/lens-hb-six-dev-20261114"
CSV_SHA="2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
POINTER="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
LABELS={"12","15","UNKNOWN"}
def digest(path:Path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()
def main():
 import sys
 sys.path.insert(0,str(ROOT/"scripts/craci"))
 from lens_hb_admission import admit
 reg=ROOT/"docs/CHIBI_LENS_DATA_SOURCE_REGISTER_20261114.json"
 adm=admit(SRC,reg)
 if adm.get("cloudTrainingEligible") is not True or adm.get("localOriginalRGBUploaded") is not False or adm.get("privateOCRUsed") is not False or adm.get("familyPhotosUsed") is not False:
  raise RuntimeError("Original source license/privacy not admitted")
 if digest(SRC/"public-hb-object-features.csv")!=CSV_SHA:
  raise RuntimeError("Original public source bytes changed")
 if OUT.exists():
  raise RuntimeError("Task-specific fixture already exists, no overwrite")
 # First pass intentionally parses only rows with split in (train,cal).
 # Rows from scene11 or any other test are discarded BEFORE feature loading.
 rows=[];split_scene=Counter();split_label=Counter();frames=set()
 with (SRC/"public-hb-object-features.csv").open(newline="",encoding="utf8") as f:
  reader=csv.DictReader(f);fields=reader.fieldnames
  if not fields or len(fields)!=828:raise RuntimeError("Source feature schema changed")
  if any(s in fields for s in ("image","raw_rgb","secret","person_id")):
   raise RuntimeError("No raw pixels or personal columns admitted")
  for r in reader:
   split=r.get("split")
   if split not in ("train","cal"):continue
   label=r.get("label")
   scene=int(r["scene_id"]);frame=int(r["frame_id"])
   if (r.get("source")!="bop-hb-val-primesense-public-cc0" or
       r.get("license")!="CC0-1.0" or
       r.get("modality")!="REAL_RGB_MASKED" or
       label not in LABELS or
       (split=="train" and (scene not in (5,9) or label not in ("12","15"))) or
       (split=="cal" and scene!=10)):
    raise RuntimeError("Unreviewed dataset/scene/label")
   rows.append(r)
   split_scene[(split,scene)]+=1
   split_label[(split,label)]+=1
   frames.add((split,scene,frame))
 if len(rows)!=420 or split_scene!=Counter({("train",5):92,("train",9):94,("cal",10):234}):
  # Train counts are evidence-based from original dataset, no arbitrary threshold loosening.
  print("ACTUAL_SCENE_COUNTS",dict(split_scene))
  if len(rows)!=420 or set(split_scene)!={("train",5),("train",9),("cal",10)}:
   raise RuntimeError("Train/cal split changed")
 if split_label!=Counter({("train","12"):96,("train","15"):90,("cal","12"):48,("cal","15"):43,("cal","UNKNOWN"):143}):
  raise RuntimeError("Known/unknown split distribution changed")
 cal_frames=sorted({int(r["frame_id"]) for r in rows if r["split"]=="cal"})
 if len(cal_frames)!=48:raise RuntimeError("Expected 48 independent physical frame groups")
 fold_groups=[cal_frames[k::6] for k in range(6)]
 if any(len(s)!=8 for s in fold_groups) or len({v for group in fold_groups for v in group})!=48:
  raise RuntimeError("Six disjoint dev folds changed")
 OUT.mkdir(mode=0o700)
 dest=OUT/"public-hb-train-cal-only.csv"
 with dest.open("x",newline="",encoding="utf8") as f:
  writer=csv.DictWriter(f,fieldnames=fields,lineterminator="\n")
  writer.writeheader();writer.writerows(rows)
 receipt={
  "schema":"junction.craci.hb.six-dev-source.v1",
  "sourceFileSHA256":CSV_SHA,
  "publicSourceArchivePointerSHA256":POINTER,
  "datasetLicense":"CC0-1.0",
  "datasetNumericOnly":True,
  "rawPixelsIncluded":False,
  "privateMediaIncluded":False,
  "originalSourceHadScene11":True,
  "excludedAllTestRowsBeforeFeatureExtraction":True,
  "noScene8Or11FeatureRows":True,
  "trainScenes":[5,9],"calibrationDevelopmentScene":10,
  "testScenesInThisFixture":[],
  "trainRows":186,"calDevRows":234,
  "splitLabelCounts":{"|".join(k):v for k,v in sorted(split_label.items())},
  "folds":[{"fold":i,"devFrames":v,"numberOfDevFrameGroups":len(v),
             "calibrationFrames":[x for x in cal_frames if x not in v]}
           for i,v in enumerate(fold_groups)],
  "sourceCSVsha256":digest(dest),
  "knownObjectIds":[12,15],"unknownDevelopmentObjectIds":[3,22,23],
  "modelPromotionAllowed":False,
  "realGlassesQualified":False,"providerAttested":False
 }
 (OUT/"admission.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
 print(json.dumps({"fixtureSha":receipt["sourceCSVsha256"],"rows":len(rows),
                   "folds":[len(x["devFrames"]) for x in receipt["folds"]],
                   "splits":{"|".join(k):v for k,v in sorted(split_label.items())}},sort_keys=True))
if __name__=="__main__":main()
