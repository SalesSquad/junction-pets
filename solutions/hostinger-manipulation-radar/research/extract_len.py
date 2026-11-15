#!/usr/bin/env python3
"""LEN research extractor: stream public JSON; never persist raw records."""
import argparse, collections, hashlib, json, math, tarfile, time, urllib.request
from pathlib import Path
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
    return [math.log1p(n),math.log1p(m),m/(n*n),iv.count(0)/n,ov.count(0)/n,
            sum(a!=b and (b,a) in unique for a,b in unique)/m,gini(iv),gini(ov),
            max(iv)/m,max(ov)/m,sum((v/m)**2 for v in iv),sum((v/m)**2 for v in ov)],n,m
class DigestReader:
    def __init__(self,raw): self.raw=raw; self.sha=hashlib.sha256(); self.bytes=0
    def read(self,n=-1):
        b=self.raw.read(n); self.sha.update(b); self.bytes+=len(b); return b
class RangeStream:
    """Bounded parallel reads; preserves exact archive byte order and digest."""
    def __init__(self,url,total,workers=8,chunk=4*1024*1024):
        import concurrent.futures
        self.url=url; self.total=total; self.chunk=chunk
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        self.pending=collections.deque();self.next=0;self.buffer=b"";self.closed=False
        for _ in range(workers): self.enqueue()
    def enqueue(self):
        if self.next>=self.total:return
        start=self.next;end=min(self.total,start+self.chunk)-1;self.next=end+1
        self.pending.append(self.pool.submit(self.fetch,start,end))
    def fetch(self,start,end):
        req=urllib.request.Request(self.url,headers={"Range":f"bytes={start}-{end}","User-Agent":"SignalDesk-LEN-research/1.0"})
        with urllib.request.urlopen(req,timeout=90) as response:
            if response.status!=206 or response.headers.get("Content-Range")!=f"bytes {start}-{end}/{self.total}":
                raise ValueError("Source does not honor exact public byte ranges")
            data=response.read(end-start+2)
            if len(data)!=end-start+1:raise ValueError("Incomplete source range")
            return data
    def read(self,n=-1):
        if n<0: n=self.total
        parts=[];left=n
        while left:
            if not self.buffer:
                if not self.pending: break
                self.buffer=self.pending.popleft().result();self.enqueue()
            take=min(left,len(self.buffer));parts.append(self.buffer[:take]);self.buffer=self.buffer[take:];left-=take
        return b"".join(parts)
    def close(self):
        if not self.closed:self.pool.shutdown(wait=True,cancel_futures=True);self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def extract(output):
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic(); records=[]
    req=urllib.request.Request(SOURCE,headers={"User-Agent":"SignalDesk-LEN-research/1.0"})
    with urllib.request.urlopen(urllib.request.Request(SOURCE,method="HEAD"),timeout=30) as response:
        expected=int(response.headers["Content-Length"])
    with RangeStream(SOURCE,expected) as ranges:
        raw=DigestReader(ranges)
        with tarfile.open(fileobj=raw,mode="r|",bufsize=262144) as archive:
            for member in archive:
                if member.isdir(): continue
                if not member.isfile() or not member.name.endswith(".json"): raise ValueError("Unsupported archive member")
                if member.size>512*1024*1024: raise ValueError("Oversized member")
                name=member.name.removeprefix("./small_encoder_final/")
                markers=("_noncampaign_" in name,"_campaign_" in name)
                if sum(markers)!=1: raise ValueError("Ambiguous source annotation")
                label=int(markers[1])
                reader=DigestReader(archive.extractfile(member))
                data=json.load(reader)  # Released unused embeddings contain non-standard NaN; stdlib accepts it.
                if data.get("directed") is not True or data.get("multigraph") is not False or not isinstance(data.get("links"),list):
                    raise ValueError("Unexpected source graph schema")
                data.pop("nodes",None)  # Personal fields never retained or used.
                edges=((edge["source"],edge["target"]) for edge in data["links"])
                values,n,m=topology(edges)
                del edges,data
                if reader.bytes!=member.size: raise ValueError("Incomplete JSON consumption")
                case=hashlib.sha256(("signal-desk-len-small-v1|"+name).encode()).hexdigest()
                records.append({"case":case,"label":label,"source_sha256":reader.sha.hexdigest(),
                                "source_bytes":reader.bytes,"active_nodes":n,"edges":m,"x":values})
                output.with_suffix(".partial.json").write_text(json.dumps({"features":FEATURES,"records":records},indent=2)+"\n")
                print(json.dumps({"graphs":len(records),"bytes":raw.bytes,"seconds":round(time.monotonic()-start,1)}),flush=True)
        while raw.read(1048576): pass
        if raw.bytes!=expected: raise ValueError("Incomplete source download")
    if len(records)!=104 or collections.Counter(r["label"] for r in records)!={0:51,1:53}:
        raise ValueError("LEN-small released class counts changed")
    if len({r["case"] for r in records})!=len(records): raise ValueError("Duplicate case")
    result={"source":SOURCE,"source_sha256":raw.sha.hexdigest(),"source_bytes":raw.bytes,
            "extracted_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"features":FEATURES,"records":records}
    output.write_text(json.dumps(result,indent=2)+"\n")
    output.with_suffix(".partial.json").unlink(missing_ok=True)
    print(json.dumps({"complete":True,"graphs":len(records),"class_counts":dict(collections.Counter(r["label"] for r in records)),
                      "source_sha256":result["source_sha256"],"elapsed_seconds":round(time.monotonic()-start,1)}),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--output",required=True); args=parser.parse_args(); extract(args.output)
