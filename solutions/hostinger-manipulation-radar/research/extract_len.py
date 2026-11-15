#!/usr/bin/env python3
"""LEN research extractor: stream public JSON; never persist raw records."""
import argparse, collections, hashlib, json, math, tarfile, time, urllib.request
from pathlib import Path
import ijson
FEATURES=["log_nodes","log_edges","density","zero_in_fraction","zero_out_fraction","reciprocal_fraction","in_gini","out_gini","max_in_share","max_out_share","in_hhi","out_hhi"]
SOURCE="https://cse.buffalo.edu/~erdem/small_encoder_final.tar"
def gini(values):
    a=sorted(values); total=sum(a)
    return sum((2*i-len(a)-1)*v for i,v in enumerate(a,1))/(len(a)*total) if total else 0.0
def topology(edges):
    incoming=collections.Counter(); outgoing=collections.Counter(); nodes=set(); unique=set()
    for source,target in edges:
        if not isinstance(source,(str,int)) or not isinstance(target,(str,int)): raise ValueError("Unsupported endpoint")
        key=(source,target)
        if key in unique: raise ValueError("Unexpected duplicate edge")
        unique.add(key); nodes.update(key); outgoing[source]+=1; incoming[target]+=1
    n=len(nodes); m=len(unique)
    if n<2 or m<1: raise ValueError("Empty graph")
    iv=[incoming[v] for v in nodes]; ov=[outgoing[v] for v in nodes]
    return [math.log1p(n),math.log1p(m),m/(n*(n-1)),iv.count(0)/n,ov.count(0)/n,
            sum((b,a) in unique for a,b in unique)/m,gini(iv),gini(ov),
            max(iv)/m,max(ov)/m,sum((v/m)**2 for v in iv),sum((v/m)**2 for v in ov)],n,m
class DigestReader:
    def __init__(self,raw): self.raw=raw; self.sha=hashlib.sha256(); self.bytes=0
    def read(self,n=-1):
        b=self.raw.read(n); self.sha.update(b); self.bytes+=len(b); return b
def extract(output):
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic(); records=[]
    req=urllib.request.Request(SOURCE,headers={"User-Agent":"SignalDesk-LEN-research/1.0"})
    with urllib.request.urlopen(req,timeout=90) as response:
        expected=int(response.headers["Content-Length"]); raw=DigestReader(response)
        with tarfile.open(fileobj=raw,mode="r|",bufsize=262144) as archive:
            for member in archive:
                if member.isdir(): continue
                if not member.isfile() or not member.name.endswith(".json"): raise ValueError("Unsupported archive member")
                if member.size>512*1024*1024: raise ValueError("Oversized member")
                name=member.name.removeprefix("./small_encoder_final/")
                if "_noncampaign_" in name: label=0
                elif "_campaign_" in name: label=1
                else: raise ValueError("Unknown source annotation")
                reader=DigestReader(archive.extractfile(member))
                edges=((edge["source"],edge["target"]) for edge in ijson.items(reader,"links.item"))
                values,n,m=topology(edges)
                if reader.bytes!=member.size: raise ValueError("Incomplete JSON consumption")
                case=hashlib.sha256(("signal-desk-len-small-v1|"+name).encode()).hexdigest()
                records.append({"case":case,"label":label,"source_sha256":reader.sha.hexdigest(),
                                "source_bytes":reader.bytes,"active_nodes":n,"edges":m,"x":values})
                output.with_suffix(".partial.json").write_text(json.dumps({"features":FEATURES,"records":records},indent=2)+"\n")
                print(json.dumps({"graphs":len(records),"bytes":raw.bytes,"seconds":round(time.monotonic()-start,1)}),flush=True)
        while raw.read(1048576): pass
        if raw.bytes!=expected: raise ValueError("Incomplete source download")
    if len(records)!=100: raise ValueError("LEN-small release count changed")
    if len({r["case"] for r in records})!=len(records): raise ValueError("Duplicate case")
    result={"source":SOURCE,"source_sha256":raw.sha.hexdigest(),"source_bytes":raw.bytes,
            "extracted_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"features":FEATURES,"records":records}
    output.write_text(json.dumps(result,indent=2)+"\n")
    output.with_suffix(".partial.json").unlink(missing_ok=True)
    print(json.dumps({"complete":True,"graphs":len(records),"class_counts":dict(collections.Counter(r["label"] for r in records)),
                      "source_sha256":result["source_sha256"],"elapsed_seconds":round(time.monotonic()-start,1)}),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--output",required=True); args=parser.parse_args(); extract(args.output)
