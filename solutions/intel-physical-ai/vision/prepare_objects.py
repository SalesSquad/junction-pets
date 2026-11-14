"""Prepare exact public cashew inputs or a pinned backbone. Never auto-runs."""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,io,json,tarfile,urllib.request
from pathlib import Path,PurePosixPath
from object_pipeline import PINS,BACKBONES,new_output,validate_inputs
from pipeline import digest

SPEC_SHA='3f0d9f2c62b140d9c8647cbedbdd7ea220d10a2fb8ab655bd72b2ac214508a6c'
ARCHIVE='https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar'
SOURCE='2a692ab575001cbde74d402d897a7286086c6199'
ATTRIBUTION='VisA / SPot-the-Difference, ECCV 2022: Yang Zou, Jongheon Jeong, Latha Pemula, Dongqing Zhang, Onkar Dabeer. CC-BY-4.0. https://registry.opendata.aws/visa/'

def encoded(j):return (json.dumps(j,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def public_get(url,limit,*,start=None):
    headers={} if start is None else {'Range':f'bytes={start}-{start+limit-1}'}
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=120) as r:
        if start is not None and (r.status!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{start+limit-1}/')):
            raise ValueError('Public range response mismatch')
        b=r.read(limit+1)
    if len(b)>limit or (start is not None and len(b)!=limit):raise ValueError('Public download byte limit/short read')
    return b

def data(args):
    spec_path=Path(__file__).with_name('object_dataset.json');raw=spec_path.read_bytes()
    if digest(raw)!=SPEC_SHA:raise ValueError('Portable dataset specification hash mismatch')
    spec=json.loads(raw);out=new_output(args.output)
    for name,obj in spec.items():
        if name not in PINS:raise ValueError('Unexpected metadata name')
        b=encoded(obj)
        if digest(b)!=PINS[name]:raise ValueError('Metadata byte mismatch: '+name)
        (out/name).write_bytes(b)
    csv_url=f'https://raw.githubusercontent.com/amazon-science/spot-diff/{SOURCE}/split_csv/1cls.csv'
    csv_bytes=public_get(csv_url,1024*1024)
    if digest(csv_bytes)!=PINS['visa-1cls.csv']:raise ValueError('Official split checksum mismatch')
    (out/'visa-1cls.csv').write_bytes(csv_bytes)
    # Exact valid tar header before cashew; this public range excludes most unrelated categories.
    start=300318208;end=537944064;chunk_size=4194304
    spans=[(i,s,min(chunk_size,end-s)) for i,s in enumerate(range(start,end,chunk_size))]
    chunks=out/'archive-chunks';chunks.mkdir()
    def fetch(span):
        i,s,n=span;b=public_get(ARCHIVE,n,start=s);p=chunks/f'{i:04d}.part'
        with p.open('xb') as f:f.write(b)
        return {'index':i,'start':s,'bytes':n,'sha256':digest(b)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.connections) as pool:receipts=list(pool.map(fetch,spans))
    window=out/'public-category-window.tar'
    with window.open('xb') as f:
        for i,_,_ in spans:
            with (chunks/f'{i:04d}.part').open('rb') as part:
                while b:=part.read(1048576):f.write(b)
    wanted={r['image']:r for r in spec['manifest.json']['samples']};seen=set();root=out/'data';root.mkdir()
    with tarfile.open(window,mode='r:') as archive:
        for member in archive:
            name=member.name.removeprefix('./')
            if name not in wanted:continue
            path=PurePosixPath(name);row=wanted[name]
            if name in seen or path.is_absolute() or '..' in path.parts or '\\' in name or not member.isfile():raise ValueError('Unsafe archive member')
            if not 0<member.size<=8*1024*1024 or member.size!=row['bytes']:raise ValueError('Archive size mismatch')
            stream=archive.extractfile(member)
            if stream is None:raise ValueError('Missing public member')
            b=stream.read(member.size+1)
            if len(b)!=member.size or digest(b)!=row['sha256']:raise ValueError('Selected image hash mismatch')
            target=root.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(b)
            seen.add(name)
            if len(seen)==len(wanted):break
    if seen!=set(wanted):raise ValueError('Selected image missing')
    validate_inputs(out)
    (out/'ATTRIBUTION.txt').write_text(ATTRIBUTION+'\n'+ARCHIVE+'\n')
    (out/'download-receipts.json').write_bytes(encoded({'source':ARCHIVE,'ranges':receipts,'all470image_hashes_verified':True}))
    print('FROZEN_CASHEW470_READY',PINS['manifest.json'])

def backbone(args):
    from huggingface_hub import hf_hub_download
    pin=BACKBONES[args.profile];out=new_output(args.output);files={}
    for name in ['model.safetensors','README.md','config.json']:
        p=Path(hf_hub_download(pin['repository'],name,revision=pin['revision'],cache_dir=args.cache,token=False))
        if p.stat().st_size>350*1024*1024:raise ValueError('Bounded model size exceeded')
        sha=digest(p.read_bytes())
        if name=='model.safetensors' and sha!=pin['sha256']:raise ValueError('Pinned backbone mismatch')
        files[name]={'sha256':sha,'bytes':p.stat().st_size,'cached_path':str(p)}
        if name!='model.safetensors':(out/name).write_bytes(p.read_bytes())
    (out/'source.json').write_bytes(encoded({'pin':pin,'files':files,'token_used':False,'license':'Read upstream model card; model and dataset rights are separate'}))
    print('PINNED_BACKBONE_READY',args.profile)

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('data');d.add_argument('--output',required=True);d.add_argument('--connections',type=int,choices=range(1,9),default=4)
    b=sub.add_parser('backbone');b.add_argument('--profile',choices=sorted(BACKBONES),required=True);b.add_argument('--output',required=True);b.add_argument('--cache',required=True)
    args=p.parse_args();(data if args.command=='data' else backbone)(args)
if __name__=='__main__':main()
