#!/usr/bin/env python3
"""Re-fetch one source member in RAM and compare Python with shipped JS."""
import argparse, hashlib, json, re, subprocess, tarfile, urllib.request
from pathlib import Path
from evaluate_len import score
from extract_len import SOURCE
def verify(features,model_path,core,output):
    data=json.loads(Path(features).read_text()); model=json.loads(Path(model_path).read_text())
    if data["source"]!=SOURCE: raise ValueError("Unexpected public source")
    expected=data["records"][0]
    def get(start,size):
        if not 0<size<=512*1024*1024: raise ValueError("Invalid source range size")
        end=start+size-1
        with urllib.request.urlopen(urllib.request.Request(SOURCE,headers={"Range":f"bytes={start}-{end}"}),timeout=90) as r:
            if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{end}/{data['source_bytes']}":raise ValueError("Source range mismatch")
            b=r.read(size+1)
            if len(b)!=size:raise ValueError("Incomplete source range")
            return b
    headers=get(0,1024)
    info=tarfile.TarInfo.frombuf(headers[512:1024],"utf-8","surrogateescape")
    relative=info.name.removeprefix("./small_encoder_final/")
    case=hashlib.sha256(("signal-desk-len-small-v1|"+relative).encode()).hexdigest()
    if not info.isfile() or case!=expected["case"] or info.size!=expected["source_bytes"]:raise ValueError("First source member changed")
    raw=get(1024,info.size)
    if hashlib.sha256(raw).hexdigest()!=expected["source_sha256"]:raise ValueError("Source digest changed")
    graph=json.loads(raw); del raw
    if graph.get("directed") is not True or graph.get("multigraph") is not False:raise ValueError("Source graph schema")
    names={}
    def anonymous(v):
        if v not in names:names[v]="node-"+str(len(names))
        return names[v]
    edges=[[anonymous(e["source"]),anonymous(e["target"])] for e in graph["links"]]
    del graph,names
    javascript="""import fs from 'node:fs';import {pathToFileURL} from 'node:url';
const {graphFeatures,graphScore}=await import(pathToFileURL(process.argv[1]));
const input=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify({features:graphFeatures({edges:input.edges}),result:graphScore({edges:input.edges},input.model)}));"""
    result=subprocess.run(["node","--input-type=module","-e",javascript,str(Path(core).resolve())],
                          input=json.dumps({"edges":edges,"model":model}),capture_output=True,text=True,timeout=30)
    del edges
    if result.returncode:
        errors=[line[:240] for line in result.stderr.splitlines() if re.match(r"^[A-Za-z]*Error(?::| \[)",line)]
        raise ValueError("Shipped runtime rejected verification: "+("; ".join(errors) or "child failed without a safe diagnostic"))
    runtime=json.loads(result.stdout)
    feature_error=max(abs(a-b) for a,b in zip(expected["x"],runtime["features"]["x"]))
    expected_score=score(model,expected); score_error=abs(expected_score-runtime["result"]["score"])
    if feature_error>1e-12 or score_error>1e-12:raise ValueError("Python/JavaScript numerical mismatch")
    if (expected_score>=model["threshold"])!=runtime["result"]["review"]:raise ValueError("Review decision mismatch")
    receipt={"kind":"one-real-source-graph-runtime-parity","member_sha256":expected["source_sha256"],
             "core_sha256":hashlib.sha256(Path(core).read_bytes()).hexdigest(),
             "verifier_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "model_sha256":hashlib.sha256(Path(model_path).read_bytes()).hexdigest(),
             "max_feature_absolute_error":feature_error,"score_absolute_error":score_error,
             "active_nodes":runtime["features"]["nodes"],"edges":runtime["features"]["edges"],
             "review_decision_equal":True,"intent":runtime["result"]["intent"],
             "privacy":"Original fields stayed transiently in local RAM; only opaque node references reached local Node stdin. No records persisted or sent to a provider."}
    Path(output).write_text(json.dumps(receipt,indent=2)+"\n"); print(json.dumps(receipt,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("features","model","core","output"):p.add_argument("--"+name,required=True)
    a=p.parse_args();verify(a.features,a.model,a.core,a.output)
