"""Optional public pinned preparation. Never called by pipeline; no credentials."""
import argparse
import csv
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request
from pipeline import (SOURCE, SPLIT_SHA, MANIFEST_SHA, BACKBONE_REPO, BACKBONE_REV,
                      BACKBONE_SHA, digest, encoded, new_output, write_json)

URL='https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar'
ATTRIBUTION=('VisA / SPot-the-Difference, ECCV 2022; Yang Zou, Jongheon Jeong, '
             'Latha Pemula, Dongqing Zhang, Onkar Dabeer. CC-BY-4.0.')


class BoundedReader:
    def __init__(self,response,limit):
        self.response=response;self.remaining=limit
    def read(self,n=-1):
        if n<0: n=self.remaining
        if n>self.remaining: n=self.remaining
        if n==0: raise ValueError('Archive read budget exhausted')
        b=self.response.read(n);self.remaining-=len(b)
        return b


def data(args):
    out=new_output(args.output_dir)
    csv_url=f'https://raw.githubusercontent.com/amazon-research/spot-diff/{SOURCE}/split_csv/1cls.csv'
    with urllib.request.urlopen(csv_url,timeout=45) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024 or digest(raw)!=SPLIT_SHA: raise ValueError('Pinned CSV mismatch')
    (out/'visa-1cls.csv').write_bytes(raw)
    rows=[r for r in csv.DictReader(io.StringIO(raw.decode())) if r['object']=='candle']
    train=sorted([r for r in rows if r['split']=='train'],key=lambda r:digest(('330|'+r['image']).encode()))
    selected=[]
    for part,items in [('train',train[:128]),('calibration',train[128:192]),
                       ('heldout',[r for r in rows if r['split']=='test'])]:
        for r in items:
            selected.append(dict(r,partition=part,physical_object_id=None,acquisition_session_id=None))
    wanted={r['image']:r for r in selected}
    if len(wanted)!=392: raise ValueError('Frozen sample count')
    request=urllib.request.Request(URL,headers={'Range':'bytes=0-268435455'})
    seen=set();root=out/'data';root.mkdir()
    with urllib.request.urlopen(request,timeout=45) as response:
        if response.status!=206 or not response.headers.get('Content-Range','').startswith('bytes 0-268435455/'):
            raise ValueError('Bounded range response required')
        with tarfile.open(fileobj=BoundedReader(response,268435456),mode='r|') as archive:
            for member in archive:
                name=member.name.removeprefix('./')
                if name not in wanted: continue
                p=PurePosixPath(name)
                if name in seen or p.is_absolute() or '..' in p.parts or '\\' in name:
                    raise ValueError('Unsafe/duplicate archive path')
                if not member.isfile() or not 0<member.size<=8*1024*1024:
                    raise ValueError('Archive member type/size')
                f=archive.extractfile(member)
                if f is None: raise ValueError('Missing member stream')
                b=f.read(member.size+1)
                if len(b)!=member.size: raise ValueError('Incomplete image bytes')
                dest=root.joinpath(*p.parts);dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open('xb') as target: target.write(b)
                wanted[name].update(sha256=digest(b),bytes=len(b));seen.add(name)
                if len(seen)==392: break
    if len(seen)!=392: raise ValueError('Incomplete frozen selection')
    manifest={'schema':1,'dataset':'VisA_20220922','category':'candle','license':'CC-BY-4.0',
              'source_url':URL,'source_commit':SOURCE,'split_csv_sha256':SPLIT_SHA,
              'selection':'SHA256(330|image), first128 train normals, next64 calibration normals, all200 official test heldout; fixed before fitting',
              'independence':'Physical object/session IDs unavailable; unique file-level split only. No physical independence or station claim.',
              'samples':selected}
    b=encoded(manifest)
    if digest(b)!=MANIFEST_SHA: raise ValueError('Frozen benchmark bytes differ; retain acquisition for investigation')
    (out/'manifest.json').write_bytes(b)
    (out/'ATTRIBUTION.txt').write_text(ATTRIBUTION+'\n'+csv_url+'\n'+URL+'\n')
    print('FROZEN_PUBLIC_SELECTION_READY',MANIFEST_SHA)


def backbone(args):
    from huggingface_hub import hf_hub_download
    out=new_output(args.output_dir);files={}
    for name in ('model.safetensors','README.md','config.json'):
        path=Path(hf_hub_download(BACKBONE_REPO,name,revision=BACKBONE_REV,
                                 cache_dir=args.cache_dir,token=False))
        if path.stat().st_size>256*1024*1024: raise ValueError('Backbone byte limit')
        b=path.read_bytes()
        if name=='model.safetensors' and digest(b)!=BACKBONE_SHA:
            raise ValueError('Pinned public weight mismatch')
        files[name]=dict(bytes=len(b),sha256=digest(b),cached_path=str(path))
        if name!='model.safetensors': (out/name).write_bytes(b)
    write_json(out/'source.json',dict(repository=BACKBONE_REPO,revision=BACKBONE_REV,files=files,
               license_declared_by_model_card='Apache-2.0; data rights separate',token_used=False))
    print('PINNED_PUBLIC_BACKBONE_READY',BACKBONE_SHA)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('data');d.add_argument('--output-dir',required=True)
    b=sub.add_parser('backbone');b.add_argument('--output-dir',required=True);b.add_argument('--cache-dir',required=True)
    args=p.parse_args()
    # Exceptions preserve partial bytes and traceback; never write into an
    # existing destination when exclusive output creation was refused.
    (data if args.command=='data' else backbone)(args)


if __name__=='__main__':main()
