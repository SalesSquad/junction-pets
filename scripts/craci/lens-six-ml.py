#!/usr/bin/env python3
"""Six predeclared corrective supervised learning rounds on public YCB-V numeric features.
All six train independently; calibrated with distinct scenes; test read only after freeze.
No identity, authority, camera-device or hardware-safety claims.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, random, subprocess
from collections import Counter, defaultdict
from pathlib import Path

ARCHIVE="c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
CSV_SHA="c2374f53bc510b6655623f5fa05bb23d08bd1531f24b0aa4e2bcdccab11899a6"
LABELS=(4,6,9,15)
ARMS={
 1:"class_balanced_softmax",
 2:"occlusion_weighted_softmax",
 3:"lighting_normalized_color",
 4:"spatial_gradient_joint",
 5:"cross_modal_interactions",
 6:"conservative_smooth_abstention",
}
TRAIN_SCENES={48,49,50,51,54,55}
CAL_SCENES={52,53,56,57}
TEST_SCENES={59}

def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1048576),b""):h.update(block)
 return h.hexdigest()

def read_fixture(root):
 folder=root/"fixtures/lens-public-ycbv-20261114"
 admission=json.loads((folder/"admission.json").read_text())
 assert (admission["sourceArchiveSha256"]==ARCHIVE
         and admission["csvSha256"]==CSV_SHA
         and admission["rawPixelsExported"] is False
         and admission["actionAuthorized"] is False
         and admission["physicalIdentityVerified"] is False)
 path=folder/"real-object-features.csv"
 if sha(path)!=CSV_SHA:raise RuntimeError("SOURCE_FEATURE_DIGEST_MISMATCH")
 rows=defaultdict(list)
 with path.open(newline="") as f:
  reader=csv.DictReader(f)
  for row in reader:
   split=row["split"]; label=int(row["object_id"]); scene=int(row["scene_id"])
   if split not in ("train","cal","test") or label not in LABELS:
    raise RuntimeError("UNTRUSTED_DATA_LABEL_OR_SPLIT")
   allowed={"train":TRAIN_SCENES,"cal":CAL_SCENES,"test":TEST_SCENES}[split]
   if scene not in allowed or row["source"]!="bop-ycbv-mit" or row["license"]!="MIT":
    raise RuntimeError("UNTRUSTED_PROVENANCE")
   feat=[float(row[f"f{i:02d}"]) for i in range(48)]
   if any(not math.isfinite(x) or x<0 or x>1 for x in feat):
    raise RuntimeError("FEATURE_OUT_OF_BOUNDS")
   rows[split].append((label,int(row["frame_id"]),feat,float(row["visible_fraction"])))
 if [len(rows[x]) for x in ("train","cal","test")] != [580,375,300]:
  raise RuntimeError("SOURCE_CROP_COUNT_MISMATCH")
 return rows

def represent(feat,round_id):
 if round_id==3:
  rgb=[]
  for i in (0,8,16):
   block=feat[i:i+8];s=sum(block)
   rgb.extend((v/(s+1e-10) for v in block))
  return rgb+feat[24:]
 if round_id==4:
  return feat[24:48]+[sum(feat[0:24])/24]
 if round_id==5:
  return feat+[sum(feat[:8])/8*sum(feat[24:40])/16,
               sum(feat[8:16])/8*sum(feat[40:48])/8,
               sum(feat[16:24])/8*sum(feat[24:40])/16]
 return feat

def softmax(logits):
 z=max(logits);e=[math.exp(min(40.0,x-z)) for x in logits];t=sum(e)
 return [v/t for v in e]

def predict(w,x):
 return softmax([sum(v*b for v,b in zip(row[:-1],x))+row[-1] for row in w])

def fit(train,round_id):
 seed=20261114+round_id*1301
 rng=random.Random(seed)
 features=[represent(x[2],round_id) for x in train]
 p=len(features[0]);weights=[[0.0]*(p+1) for _ in LABELS]
 counts=Counter(x[0] for x in train)
 for epoch in range(115):
  order=list(range(len(train)));rng.shuffle(order)
  lr=0.052/(1+epoch/65.0)
  for i in order:
   label,_,_,visible=train[i];x=features[i]
   scores=predict(weights,x);actual=LABELS.index(label)
   amount=1.0
   if round_id==1:amount=min(1.7,580/(len(LABELS)*counts[label]))
   if round_id==2:amount=1.0+1.2*(1-visible)
   if round_id==6:amount=min(1.7,580/(len(LABELS)*counts[label]))
   smooth=0.07 if round_id==6 else 0.0
   l2=0.0025 if round_id==6 else 0.0012
   for cls,row in enumerate(weights):
    target=(1-smooth if cls==actual else 0.0)+smooth/len(LABELS)
    delta=amount*(target-scores[cls])
    for j,val in enumerate(x):
     row[j]+=lr*(delta*val-l2*row[j])
    row[-1]+=lr*delta
  if any(not math.isfinite(v) for row in weights for v in row):
   raise RuntimeError("UNSTABLE_TRAINING")
 return weights,seed

def centroid_train(rows):
 centers=[]
 for label in LABELS:
  items=[r[2] for r in rows if r[0]==label]
  centers.append([sum(r[j] for r in items)/len(items) for j in range(48)])
 return centers

def centroid_scores(centers,feat):
 ds=[sum((x-y)**2 for x,y in zip(feat,c)) for c in centers]
 return softmax([-v/.07 for v in ds])

def threshold(rows,scores,target=.05):
 errors=sorted((max(v) for r,v in zip(rows,scores) if LABELS[v.index(max(v))]!=r[0]),reverse=True)
 k=int(len(rows)*target)
 if len(errors)<=k:return 0.0
 t=errors[k]+1e-9
 return float("inf") if t>1.0 else t

def metrics(rows,scores,t):
 correct=0;wrong=0;abstained=0
 decisions=[]
 for row,s in zip(rows,scores):
  chosen=LABELS[s.index(max(s))]
  accepted=max(s)>=t
  ok=(chosen==row[0])
  correct+=int(accepted and ok)
  wrong+=int(accepted and not ok)
  abstained+=int(not accepted)
  decisions.append(int(accepted and ok))
 return {
  "n":len(rows),"acceptedCorrect":correct,"wrongAccepted":wrong,
  "wrongCandidateFraction":wrong/len(rows),"correctCoverage":correct/len(rows),
  "abstained":abstained,"rawTop1":sum(LABELS[s.index(max(s))]==r[0] for r,s in zip(rows,scores))/len(rows),
  "threshold":t if math.isfinite(t) else "infinity",
 },decisions

def group_bootstrap(test,a,b,round_id):
 groups=defaultdict(list)
 for idx,row in enumerate(test):
  groups[row[1]].append(idx)
 frames=sorted(groups)
 if len(frames)!=75:raise RuntimeError("HELDOUT_FRAME_COUNT_MISMATCH")
 rng=random.Random(122000+round_id)
 diffs=[]
 for _ in range(3000):
  ix=[j for _ in frames for j in groups[rng.choice(frames)]]
  diffs.append(sum(a[i]-b[i] for i in ix)/len(ix))
 diffs.sort()
 low=int((.05/(2*6))*len(diffs))
 hi=min(len(diffs)-1,int((1-.05/(2*6))*len(diffs)))
 return [diffs[low],diffs[hi]]

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--source-root",type=Path,required=True)
 p.add_argument("--expected-head",required=True)
 p.add_argument("--round",type=int,choices=range(1,7),required=True)
 p.add_argument("--out",type=Path,required=True)
 args=p.parse_args()
 if len(args.expected_head)!=40 or any(c not in "0123456789abcdef" for c in args.expected_head):
  raise RuntimeError("EXPECTED_FULL_HEAD_REQUIRED")
 head=subprocess.check_output(["git","-C",str(args.source_root),"rev-parse","HEAD"],text=True).strip()
 if head!=args.expected_head:raise RuntimeError("SOURCE_HEAD_CHANGED")
 rows=read_fixture(args.source_root)
 train,cal,test=(rows[s] for s in ("train","cal","test"))
 # Train baseline and candidate using training split only.
 centers=centroid_train(train)
 weights,seed=fit(train,args.round)
 candidate_cal=[predict(weights,represent(r[2],args.round)) for r in cal]
 baseline_cal=[centroid_scores(centers,r[2]) for r in cal]
 target=.025 if args.round==6 else .05
 ct=threshold(cal,candidate_cal,target);bt=threshold(cal,baseline_cal,target)
 cal_metrics,_=metrics(cal,candidate_cal,ct)
 base_cal,_=metrics(cal,baseline_cal,bt)
 if cal_metrics["wrongCandidateFraction"]>target+1e-12:
  raise RuntimeError("CALIBRATION_WRONG_ACCEPT_GUARD_RED")
 # Test not used in training, threshold, feature-selection or model selection.
 candidate_test=[predict(weights,represent(r[2],args.round)) for r in test]
 baseline_test=[centroid_scores(centers,r[2]) for r in test]
 c,cv=metrics(test,candidate_test,ct);b,bv=metrics(test,baseline_test,bt)
 interval=group_bootstrap(test,cv,bv,args.round)
 pass_science=(c["correctCoverage"]>b["correctCoverage"]
   and c["wrongCandidateFraction"]<=b["wrongCandidateFraction"]
   and interval[0]>0)
 report={
  "schema":"junction.lens.six-corrections.v1","source_head":head,
  "source_archive_sha":ARCHIVE,"numeric_csv_sha":CSV_SHA,
  "round":args.round,"variant":ARMS[args.round],"train_seed":seed,
  "trained_examples":len(train),"calibration_examples":len(cal),"heldout_examples":len(test),
  "train_scenes":sorted(TRAIN_SCENES),"cal_scenes":sorted(CAL_SCENES),
  "test_scenes":sorted(TEST_SCENES),
  "calibration_wrong_accept_cap":target,
  "calibration":cal_metrics,"baseline_calibration":base_cal,
  "heldout":c,"baseline_heldout":b,
  "paired_frame_bootstrap_bonferroni95_six_rounds":interval,
  "exploratory_positive":pass_science,
  "quality":"EXPLORATORY_HELDOUT_GAIN" if pass_science else "NO_QUALIFIED_GAIN",
  "limitations":["Real public dataset labels repurposed into one scene-heldout internal study",
    "Same heldout scene reused descriptively in six preregistered arms, no blind winner selection",
    "No physical device identity, end-user consent, access authorization or production performance"],
  "synthetic_features_only":False,"public_real_rgb_derived_numeric_only":True,
  "raw_pixels_uploaded":False,"identityVerified":False,"actionAuthorized":False,
  "provider_bill_eur":None,"provider_attested":False
 }
 args.out.mkdir(parents=True,exist_ok=False)
 (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
 (args.out/"weights.json").write_text(json.dumps({
  "round":args.round,"variant":ARMS[args.round],"source_head":head,
  "labels":LABELS,"weights":weights,"feature_count":len(weights[0])-1,
  "calibrated_threshold":ct if math.isfinite(ct) else "infinity"},separators=(",",":"))+"\n")
 assert (args.out/"report.json").stat().st_size>300
 assert (args.out/"weights.json").stat().st_size>300
 print(json.dumps({"round":args.round,"variant":ARMS[args.round],
  "n":len(train),"candidate":c,"baseline":b,
  "six_family_ci":interval,"quality":report["quality"]},sort_keys=True))
if __name__=="__main__":main()
