#!/usr/bin/env python3
"""Frozen graph-level evaluation. No sklearn, network or source-text access."""
import argparse, collections, hashlib, json, math
from pathlib import Path

FEATURES=["log_nodes","log_edges","density","zero_in_fraction","zero_out_fraction","reciprocal_fraction","in_gini","out_gini","max_in_share","max_out_share","in_hhi","out_hhi"]
def split_records(records):
    parts={"train":[],"calibration":[],"test":[]}
    for label in (0,1):
        rows=sorted((r for r in records if r["label"]==label),key=lambda r:r["case"])
        n=len(rows); a=int(.6*n); b=a+int(.2*n)
        for key,group in zip(parts,(rows[:a],rows[a:b],rows[b:])): parts[key].extend(group)
    return parts
def sigmoid(z):
    return 1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))
def fit(rows,indices):
    p=len(indices); n=len(rows)
    means=[sum(r["x"][j] for r in rows)/n for j in indices]
    scales=[math.sqrt(sum((r["x"][j]-means[k])**2 for r in rows)/n) or 1 for k,j in enumerate(indices)]
    xs=[[(r["x"][j]-means[k])/scales[k] for k,j in enumerate(indices)] for r in rows]
    counts=collections.Counter(r["label"] for r in rows)
    weights=[n/(2*counts[r["label"]]) for r in rows]
    w=[0.0]*p; intercept=0.0
    for _ in range(3000):
        errors=[weights[i]*(sigmoid(intercept+sum(a*b for a,b in zip(w,xs[i])))-r["label"]) for i,r in enumerate(rows)]
        gradients=[sum(e*x[j] for e,x in zip(errors,xs))/n+.1*w[j] for j in range(p)]
        intercept-=.05*sum(errors)/n
        w=[a-.05*b for a,b in zip(w,gradients)]
    return {"features":[FEATURES[j] for j in indices],"indices":indices,"means":means,"scales":scales,"weights":w,"intercept":intercept}
def score(model,row):
    return sigmoid(model["intercept"]+sum(w*(row["x"][j]-mean)/scale for j,mean,scale,w in zip(model["indices"],model["means"],model["scales"],model["weights"])))
def interval(k,n):
    if not n: return None
    z=1.959963984540054; p=k/n; d=1+z*z/n
    mid=(p+z*z/(2*n))/d; spread=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [mid-spread,mid+spread]
def metrics(labels,predictions):
    counts={"tp":0,"fp":0,"tn":0,"fn":0}
    for y,p in zip(labels,predictions): counts[("tp" if y else "fp") if p else ("fn" if y else "tn")]+=1
    tp,fp,tn,fn=(counts[k] for k in ("tp","fp","tn","fn"))
    def ratio(a,b): return a/b if b else None
    return {**counts,"n":tp+fp+tn+fn,"accuracy":ratio(tp+tn,tp+fp+tn+fn),
            "precision":ratio(tp,tp+fp),"recall":ratio(tp,tp+fn),"false_positive_rate":ratio(fp,fp+tn),
            "balanced_accuracy":(tp/(tp+fn)+tn/(tn+fp))/2,
            "accuracy_wilson95":interval(tp+tn,tp+fp+tn+fn),"precision_wilson95":interval(tp,tp+fp),
            "recall_wilson95":interval(tp,tp+fn),"fpr_wilson95":interval(fp,fp+tn)}
def threshold(model,calibration):
    scores=[score(model,r) for r in calibration]; labels=[r["label"] for r in calibration]
    candidates=sorted(set(scores+[1.000000001]))
    valid=[]
    for t in candidates:
        m=metrics(labels,[s>=t for s in scores])
        if m["false_positive_rate"]<=.10: valid.append((m["recall"],m["precision"] or 0,t,m))
    _,_,t,m=max(valid,key=lambda a:a[:3])
    return t,m
def run(source,output):
    source=Path(source); output=Path(output); data=json.loads(source.read_text())
    assert data["features"]==FEATURES
    rows=data["records"]
    if len(rows)!=100 or len({r["case"] for r in rows})!=100 or collections.Counter(r["label"] for r in rows)!={0:49,1:51}: raise ValueError("Unexpected corpus")
    for r in rows:
        if r["label"] not in (0,1) or len(r["x"])!=len(FEATURES) or not all(math.isfinite(x) for x in r["x"]): raise ValueError("Invalid record")
    parts=split_records(rows)
    if [len(v) for v in parts.values()]!=[59,19,22]: raise ValueError("Unexpected frozen split")
    split_hash=hashlib.sha256(json.dumps({k:sorted(r["case"] for r in v) for k,v in parts.items()},sort_keys=True).encode()).hexdigest()
    models={}
    # Model fitting and threshold choice finish before any test scores are evaluated.
    for name,indices in (("size_only",[0,1]),("topology",list(range(len(FEATURES))))):
        model=fit(parts["train"],indices); t,cal=threshold(model,parts["calibration"])
        models[name]={"model":model,"threshold":t,"calibration":cal}
    majority=int(sum(r["label"] for r in parts["train"])>=len(parts["train"])/2)
    test=parts["test"]; labels=[r["label"] for r in test]
    results={"majority":metrics(labels,[majority]*len(test))}
    for name,entry in models.items():
        scores=[score(entry["model"],r) for r in test]
        results[name]=metrics(labels,[s>=entry["threshold"] for s in scores])
        results[name+"_fixed_0_5"]=metrics(labels,[s>=.5 for s in scores])
    here=Path(__file__).parent
    report={"schema":"signal-desk-len-evaluation-v1","protocol_sha256":hashlib.sha256((here/"len-protocol.json").read_bytes()).hexdigest(),
            "source":{"url":data["source"],"sha256":data["source_sha256"],"bytes":data["source_bytes"],"extracted_at":data["extracted_at"]},
            "feature_artifact_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"split_sha256":split_hash,
            "counts":{k:{"n":len(v),"campaign":sum(r["label"] for r in v),"organic":sum(1-r["label"] for r in v)} for k,v in parts.items()},
            "calibration":{k:{"threshold":v["threshold"],"metrics":v["calibration"]} for k,v in models.items()},
            "held_out":results,
            "limits":["One frozen LEN-small split; no field-generalization estimate.",
                      "Target is source graph campaign annotation, not deception, bots, factuality or malicious intent.",
                      "Only active edge endpoints count; isolates and all text/account fields excluded.",
                      "Collection, selection and graph-size biases; actors may recur across trends.",
                      "Wilson intervals are descriptive at graph level; unknown cross-graph dependence.",
                      "Scores are uncalibrated model outputs, not probabilities. No automatic enforcement."]}
    output.mkdir(parents=True,exist_ok=True)
    (output/"len-evaluation.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    exported={**models["topology"]["model"],"threshold":models["topology"]["threshold"],
              "schema":"signal-desk-len-model-v1","source_sha256":data["source_sha256"],
              "protocol_sha256":report["protocol_sha256"],"evaluation_split_sha256":split_hash}
    (output/"len-model.json").write_text(json.dumps(exported,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"counts":report["counts"],"held_out":results},indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",required=True);p.add_argument("--output",required=True);a=p.parse_args();run(a.source,a.output)
