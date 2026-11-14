"""Real VisA offline PaDiM inspection. No synthetic-core or station integration."""
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import platform
import time
import importlib.metadata as metadata

import numpy as np
from PIL import Image, ImageOps

SOURCE = '2a692ab575001cbde74d402d897a7286086c6199'
SPLIT_SHA = 'a48557e6033318cb90556f706196bc9d247a776a23ea51aecee5a80dd0332995'
PREPROCESS = dict(size=[128, 128], color='RGB', exif_transpose=True,
                  resize='Pillow bilinear', mean=[.485,.456,.406], std=[.229,.224,.225])
CONFIG = dict(seed=330, backbone='resnet18', features=50, threads=2,
              binary_quantile=.95, good_quantile=.90, defect_quantile=.99,
              quantile_method='higher', parity_atol=.001, parity_rtol=.001,
              batch=1, mode='REAL_DATA_OFFLINE', robot='NO ROBOT')


def digest(b):
    return hashlib.sha256(b).hexdigest()


def image_bytes(path):
    with path.open('rb') as f:
        b = f.read(8*1024*1024+1)
    if not 0 < len(b) <= 8*1024*1024:
        raise ValueError('Image byte limit')
    return b


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def new_output(path):
    out = Path(path).resolve()
    if out.is_relative_to(Path(__file__).resolve().parents[3]):
        raise ValueError('Experiment outputs must be outside the repository')
    out.mkdir(parents=False,exist_ok=False)
    return out


def write_json(path, obj):
    path.write_bytes(encoded(obj))


def finite(values):
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite numerical value')
    return values


def safe_file(root, name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError('Unsafe relative path')
    root = Path(root).resolve(strict=True)
    candidate = root.joinpath(*p.parts)
    # Reject symlinks even when they currently resolve within root.
    cursor = root
    for part in p.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Symlink rejected')
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('Path escape or nonfile')
    return resolved


def validate_manifest(path, root):
    raw = Path(path).read_bytes()
    manifest = json.loads(raw)
    if (manifest.get('schema') != 1 or manifest.get('dataset') != 'VisA_20220922'
        or manifest.get('category') != 'candle' or manifest.get('license') != 'CC-BY-4.0'
        or manifest.get('source_commit') != SOURCE or manifest.get('split_csv_sha256') != SPLIT_SHA):
        raise ValueError('Unexpected dataset provenance')
    rows = manifest['samples']
    if len(rows) != 392:
        raise ValueError('Expected exactly 392 frozen samples')
    names, hashes = set(), set()
    counts = {}
    for r in rows:
        name, sha, part, label = r['image'], r['sha256'], r['partition'], r['label']
        if part not in ('train','calibration','heldout') or label not in ('normal','anomaly'):
            raise ValueError('Invalid partition/label')
        if r.get('object') != 'candle' or r.get('split') != ('test' if part == 'heldout' else 'train'):
            raise ValueError('Official split leakage')
        if part != 'heldout' and label != 'normal':
            raise ValueError('Fit/calibration must contain only normals')
        if name in names or sha in hashes or len(sha) != 64:
            raise ValueError('Duplicate sample/path/hash across partitions')
        names.add(name); hashes.add(sha)
        counts[part,label] = counts.get((part,label),0)+1
        p = safe_file(root, name)
        size = p.stat().st_size
        if type(r['bytes']) is not int or size != r['bytes'] or not 0 < size <= 8*1024*1024:
            raise ValueError('Image byte limit/size mismatch')
        if digest(image_bytes(p)) != sha:
            raise ValueError('Image hash mismatch')
    if counts != {('train','normal'):128, ('calibration','normal'):64,
                  ('heldout','normal'):100, ('heldout','anomaly'):100}:
        raise ValueError('Frozen partition sizes violated')
    # The acquisition manifest must retain the declared salted ordering.
    normals = sorted([r for r in rows if r['partition'] != 'heldout'],
                     key=lambda r:digest(('330|'+r['image']).encode()))
    if any(r['partition'] != ('train' if i < 128 else 'calibration') for i,r in enumerate(normals)):
        raise ValueError('Frozen selection ordering violated')
    return manifest, raw


def verify_selection(manifest, split_path):
    raw = Path(split_path).read_bytes()
    if digest(raw) != SPLIT_SHA:
        raise ValueError('Official split CSV hash mismatch')
    official = [r for r in csv.DictReader(io.StringIO(raw.decode())) if r['object']=='candle']
    train = sorted([r for r in official if r['split']=='train'],
                   key=lambda r:digest(('330|'+r['image']).encode()))
    expected = {}
    for part, items in [('train',train[:128]),('calibration',train[128:192]),
                        ('heldout',[r for r in official if r['split']=='test'])]:
        for r in items:
            expected[r['image']] = (part,r['label'],r['split'])
    actual = {r['image']:(r['partition'],r['label'],r['split']) for r in manifest['samples']}
    if len(train)!=900 or actual != expected:
        raise ValueError('Selection differs from frozen official CSV')


def image_tensor(root, row):
    import torch
    p = safe_file(root, row['image'])
    b = image_bytes(p)
    if len(b) > 8*1024*1024 or digest(b) != row['sha256']:
        raise ValueError('Image changed before decode')
    with Image.open(io.BytesIO(b)) as im:
        if im.width*im.height > 20_000_000 or getattr(im,'n_frames',1) != 1:
            raise ValueError('Pixel/frame limit')
        im = ImageOps.exif_transpose(im).convert('RGB').resize((128,128), Image.Resampling.BILINEAR)
        x = np.asarray(im, dtype=np.float32)/255
    x = (x-np.array(PREPROCESS['mean'],dtype=np.float32))/np.array(PREPROCESS['std'],dtype=np.float32)
    return torch.from_numpy(finite(x).transpose(2,0,1).copy()).unsqueeze(0)


def thresholds(scores):
    a = finite(np.asarray(scores,dtype=float))
    if a.shape != (64,):
        raise ValueError('Expected 64 normal calibration scores')
    return {k:float(np.quantile(a,q,method='higher')) for k,q in [('good',.90),('binary',.95),('defect',.99)]}


def proposal(score, t):
    finite([score,*t.values()])
    if not t['good'] <= t['binary'] <= t['defect']:
        raise ValueError('Unordered thresholds')
    return 'good' if score < t['good'] else 'defect' if score > t['defect'] else 'hold'


def infer(model, x):
    import torch
    with torch.inference_mode():
        y = model(x)
    score = float(y.pred_score.reshape(-1)[0])
    amap = y.anomaly_map.detach().cpu().numpy().astype('<f4')
    finite([score]); finite(amap)
    if amap.shape != (1,1,128,128):
        raise ValueError('Unexpected map shape')
    return score, amap


def tensor_hashes(state):
    return {k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=digest(v.detach().cpu().contiguous().numpy().tobytes()))
            for k,v in state.items()}


def load_fitted(out):
    """Only locally produced safetensors; ledger verifies integrity, not authorship."""
    import torch
    from safetensors.torch import load_file
    from anomalib.models.image.padim.torch_model import PadimModel
    out = Path(out)
    verify(out)
    if (out/'model.safetensors').stat().st_size > 256*1024*1024:
        raise ValueError('Model byte limit')
    config = json.loads((out/'config.json').read_text())
    if config['config'] != CONFIG or config['preprocess'] != PREPROCESS:
        raise ValueError('Model configuration mismatch')
    model = PadimModel(n_features=50,backbone='resnet18',pre_trained=False).cpu()
    state = load_file(str(out/'model.safetensors'),device='cpu')
    if tensor_hashes(state) != json.loads((out/'model-tensors.json').read_text()):
        raise ValueError('Tensor identity mismatch')
    for value in state.values():
        if not torch.isfinite(value).all(): raise ValueError('Nonfinite model tensor')
    model.load_state_dict(state,strict=True)
    t = json.loads((out/'thresholds.json').read_text())['values']
    proposal(0.,t)
    frozen = json.loads((out/'frozen.json').read_text())
    if frozen != dict(model=digest((out/'model.safetensors').read_bytes()),
                      thresholds=digest((out/'thresholds.json').read_bytes())):
        raise ValueError('Frozen model/threshold identity mismatch')
    return model.eval(),t


def inspect_image(args):
    import torch
    torch.set_num_threads(2);torch.set_num_interop_threads(2)
    model,t = load_fitted(args.artifact_dir)
    root = Path(args.image).absolute().parent
    image = Path(args.image).name
    out = new_output(args.output_dir)
    score,amap = infer(model,image_tensor(root,dict(image=image,sha256=args.sha256)))
    np.save(out/'map.npy',amap,allow_pickle=False)
    write_json(out/'inspection.json',dict(mode='REAL_DATA_OFFLINE',robot='NO ROBOT',
               image=image,sha256=args.sha256,score=score,proposal=proposal(score,t),
               binary_defect=score>t['binary'],map_sha256=digest(amap.tobytes()),
               source_artifact_ledger=digest((Path(args.artifact_dir)/'artifacts.json').read_bytes())))
    seal(out)


def seal(out):
    files = {p.relative_to(out).as_posix():digest(p.read_bytes()) for p in sorted(out.rglob('*'))
             if p.is_file() and p.name != 'artifacts.json'}
    write_json(out/'artifacts.json', dict(schema=1,files=files))


def verify(out):
    out = Path(out)
    ledger = json.loads((out/'artifacts.json').read_bytes())
    expected = ledger['files']
    actual = {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file() and p.name != 'artifacts.json'}
    if actual != set(expected):
        raise ValueError('Artifact file set mismatch')
    for name, sha in expected.items():
        if digest(safe_file(out,name).read_bytes()) != sha:
            raise ValueError('Corrupted artifact: '+name)
    return ledger


def evaluate(rows):
    held = [r for r in rows if r['partition']=='heldout']
    pos = [r['score'] for r in held if r['label']=='anomaly']
    neg = [r['score'] for r in held if r['label']=='normal']
    auc = sum((a>b)+.5*(a==b) for a in pos for b in neg)/(len(pos)*len(neg))
    confusion = {k:0 for k in ('tp','fp','tn','fn')}
    counts = {label:{p:0 for p in ('good','hold','defect')} for label in ('normal','anomaly')}
    for r in held:
        confusion[('t' if r['binary_defect']==(r['label']=='anomaly') else 'f') + ('p' if r['binary_defect'] else 'n')] += 1
        counts[r['label']][r['proposal']] += 1
    return dict(image_auroc=auc, heldout_count=len(held), binary_confusion=confusion,
                ternary_counts=counts, coverage=sum(r['proposal']!='hold' for r in held)/len(held))


def run(args):
    import torch
    from anomalib.models.image.padim.torch_model import PadimModel
    started = time.time()
    out = new_output(args.output_dir)  # Never overwrite a prior experiment.
    try:
        manifest, raw = validate_manifest(args.manifest,args.data_root)
        verify_selection(manifest,args.split_csv)
        (out/'manifest.json').write_bytes(raw)
        torch.set_num_threads(2); torch.set_num_interop_threads(2)
        torch.manual_seed(330); random.seed(330); np.random.seed(330)
        versions = {k:metadata.version(k) for k in ('anomalib','torch','torchvision','timm','openvino','numpy','Pillow','safetensors')}
        write_json(out/'config.json',dict(config=CONFIG, preprocess=PREPROCESS, versions=versions,
                   executor=dict(system=platform.system(),machine=platform.machine(),python=platform.python_version()),
                   manifest_sha256=digest(raw), preprocess_sha256=digest(encoded(PREPROCESS)),
                   config_sha256=digest(encoded(CONFIG)), pipeline_sha256=digest(Path(__file__).read_bytes())))
        model = PadimModel(n_features=50,backbone='resnet18',pre_trained=True).cpu()
        backbone = tensor_hashes(model.feature_extractor.state_dict())
        pretrained = model.feature_extractor.feature_extractor.pretrained_cfg
        write_json(out/'backbone.json',dict(config=pretrained,tensors=backbone,
                   limits='timm Apache-2.0 code; pretrained ImageNet weights/data have separate upstream terms. Not a license grant.'))
        model.train()
        for r in manifest['samples']:
            if r['partition']=='train':
                with torch.no_grad(): model(image_tensor(args.data_root,r))
        model.fit(); model.eval()
        from safetensors.torch import save_file
        state = {k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()}
        save_file(state,str(out/'model.safetensors'))
        write_json(out/'model-tensors.json',tensor_hashes(state))
        fit_seconds = time.time()-started
        predictions = {}
        for r in manifest['samples']:
            if r['partition']=='calibration':
                predictions[r['image']] = infer(model,image_tensor(args.data_root,r))
        t = thresholds([v[0] for v in predictions.values()])
        write_json(out/'thresholds.json',dict(values=t,meaning='Normal-only empirical quantiles, not probabilities or escape guarantees'))
        # Freeze model and thresholds before any heldout inference or label join.
        frozen = dict(model=digest((out/'model.safetensors').read_bytes()),thresholds=digest((out/'thresholds.json').read_bytes()))
        write_json(out/'frozen.json',frozen)
        for r in manifest['samples']:
            if r['partition']=='heldout':
                predictions[r['image']] = infer(model,image_tensor(args.data_root,r))
        parity = export_parity(model,manifest,args.data_root,out,predictions,t)
        # Labels are used for reporting only after inference has finished.
        rows = []
        for r in manifest['samples']:
            if r['partition']=='train': continue
            score, amap = predictions[r['image']]
            rows.append(dict(image=r['image'],sha256=r['sha256'],partition=r['partition'],label=r['label'],
                             score=score,map_sha256=digest(amap.tobytes()),proposal=proposal(score,t),binary_defect=score>t['binary']))
        with (out/'predictions.csv').open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        write_json(out/'report.json',dict(mode='REAL_DATA_OFFLINE',robot='NO ROBOT',metrics=evaluate(rows),
                   parity=parity,fit_seconds=fit_seconds,total_seconds=time.time()-started,
                   physical_object_ids='UNKNOWN',session_ids='UNKNOWN',cost='unknown',
                   limits='File-level only. VisA candle is not Intel/robot evidence. CPU is not Intel NPU/iGPU. No cycles/min or reliability bounds.'))
        seal(out); verify(out)
        print(json.dumps(json.loads((out/'report.json').read_text()),indent=2))
    except Exception as e:
        write_json(out/'failure.json',dict(type=type(e).__name__,error=str(e),elapsed=time.time()-started))
        seal(out)
        raise


def export_parity(model,manifest,root,out,predictions,t):
    import torch
    import openvino as ov
    class Outputs(torch.nn.Module):
        def __init__(self,m):
            super().__init__(); self.m=m
        def forward(self,x):
            y=self.m(x)
            return y.pred_score,y.anomaly_map
    phase='conversion'
    try:
        converted=ov.convert_model(Outputs(model).eval(),example_input=torch.zeros(1,3,128,128),input=[1,3,128,128])
        ov.save_model(converted,out/'model.xml',compress_to_fp16=False)
        phase='CPU readback'
        core=ov.Core(); loaded=core.read_model(out/'model.xml')
        compiled=core.compile_model(loaded,'CPU',{'INFERENCE_NUM_THREADS':2,'INFERENCE_PRECISION_HINT':'f32'})
        failures=[]; max_score=0.; max_map=0.; count=0
        for r in manifest['samples']:
            if r['partition']!='heldout': continue
            result=compiled([image_tensor(root,r).numpy()])
            score=float(np.asarray(result[compiled.output(0)]).reshape(-1)[0])
            amap=np.asarray(result[compiled.output(1)])
            finite([score]);finite(amap)
            ref,m=predictions[r['image']]
            se=abs(score-ref); me=float(np.max(np.abs(amap-m)))
            max_score=max(max_score,se);max_map=max(max_map,me);count+=1
            if (not np.allclose(score,ref,atol=.001,rtol=.001) or not np.allclose(amap,m,atol=.001,rtol=.001)
                or proposal(score,t)!=proposal(ref,t) or (score>t['binary'])!=(ref>t['binary'])):
                failures.append(dict(image=r['image'],score_error=se,map_error=me))
        record=dict(status='fail' if failures else 'pass',device='CPU',count=count,
                    atol=.001,rtol=.001,max_score_error=max_score,max_map_error=max_map,failures=failures)
    except Exception as e:
        record=dict(status='blocked',phase=phase,error_type=type(e).__name__,error=str(e))
    write_json(out/'parity.json',record)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('run',aliases=['train']);r.add_argument('--manifest',required=True)
    r.add_argument('--data-root',required=True);r.add_argument('--output-dir',required=True)
    r.add_argument('--split-csv',required=True)
    v=sub.add_parser('verify');v.add_argument('--output-dir',required=True)
    i=sub.add_parser('inspect');i.add_argument('--artifact-dir',required=True)
    i.add_argument('--image',required=True);i.add_argument('--sha256',required=True)
    i.add_argument('--output-dir',required=True)
    m=sub.add_parser('validate-manifest');m.add_argument('--manifest',required=True)
    m.add_argument('--data-root',required=True);m.add_argument('--split-csv',required=True)
    args=p.parse_args()
    if args.command=='verify': verify(args.output_dir);print('ARTIFACT_HASHES_VERIFIED (integrity, not authenticity)')
    elif args.command=='inspect': inspect_image(args)
    elif args.command=='validate-manifest':
        manifest,_=validate_manifest(args.manifest,args.data_root)
        verify_selection(manifest,args.split_csv);print('FROZEN_SELECTION_AND_392_IMAGE_HASHES_VERIFIED')
    else: run(args)


if __name__=='__main__':
    main()
