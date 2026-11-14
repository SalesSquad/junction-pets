"""Pinned object-aware PatchCore experiment, labelled calibration and OpenVINO.

Offline proposals only. New public-category evidence is not Intel/SO-101 proof.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,platform,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
import pipeline as legacy
from object_core import CaptureRefusal,ROI_CONFIG,extract_objects,object_score,calibrate,decide,metrics

PINS={'manifest.json':'9f159cbda485ad7d761ca9e20844438f7c9cb23f6f456fdc59edd15911f77e93',
      'protocol.json':'59e3f022d46486d48b5e1a65089bb600f235766b943f14208132d41d7c1616dd',
      'selection.json':'9b8db0806819da201323847d5015efdf89941723b5d6214315cd63b73798fc4c',
      'truth.json':'2a441e64a3f07c574124509d557b2af2e1efd5c5473adba165c4758e2f26f62b',
      'visa-1cls.csv':legacy.SPLIT_SHA}
BACKBONES={
 'resnet18':{'architecture':'resnet18','repository':legacy.BACKBONE_REPO,
             'revision':legacy.BACKBONE_REV,'sha256':legacy.BACKBONE_SHA},
 'wide_resnet50_2':{'architecture':'wide_resnet50_2',
             'repository':'timm/wide_resnet50_2.tv2_in1k',
             'revision':'ffb9dc0ac74364ad268e066aa4aea75089bf383d',
             'sha256':'3d0c6ca08444680d7d4a46f95c1fb6a54f88f0419ae7331cebaa32e47e531c98'}
}
MODEL_CONFIG={'backbone':'resnet18','layers':['layer2','layer3'],'neighbors':9,'seed':330,
              'input_size':256,'cpu_threads':2,'maximum_training_patches':60000,'coreset_ratio':.02}

def digest(b):return hashlib.sha256(b).hexdigest()
def write_json(p,j):
    with Path(p).open('x') as f:json.dump(j,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def new_output(path):
    p=Path(path).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent/'.git').exists() and p.is_relative_to(parent):raise ValueError('Outputs cannot be in source repository')
    p.mkdir(exist_ok=False);return p

def validate_inputs(root):
    root=Path(root).resolve();loaded={}
    for name,sha in PINS.items():
        p=legacy.safe_file(root,name);b=p.read_bytes()
        if len(b)>2*1024*1024 or digest(b)!=sha:raise ValueError('Frozen input mismatch: '+name)
        loaded[name]=b
    m=json.loads(loaded['manifest.json']);truth=json.loads(loaded['truth.json']);rows=m['samples']
    if len(rows)!=470 or m['category']!='cashew':raise ValueError('Frozen category/count')
    if m['protocol_sha256']!=PINS['protocol.json'] or m['truth_sha256']!=PINS['truth.json']:raise ValueError('Manifest relationships')
    names=set();hashes=set();counts={}
    for r in rows:
        if r['image'] in names or r['sha256'] in hashes:raise ValueError('Cross-split duplicate')
        names.add(r['image']);hashes.add(r['sha256']);counts[r['role']]=counts.get(r['role'],0)+1
        p=legacy.safe_file(root/'data',r['image']);b=legacy.image_bytes(p)
        if len(b)!=r['bytes'] or digest(b)!=r['sha256']:raise ValueError('Image bytes mismatch')
    if counts!={'fit':256,'calibration':104,'evaluation':110}:raise ValueError('Partition counts')
    if {r['image'] for r in truth}!=names or len(truth)!=470:raise ValueError('Truth membership')
    official={r['image']:r for r in csv.DictReader(io.StringIO(loaded['visa-1cls.csv'].decode())) if r['object']=='cashew'}
    tr={r['image']:r for r in truth}
    expected={('fit','normal'):256,('calibration','normal'):64,('calibration','anomaly'):40,('evaluation','normal'):50,('evaluation','anomaly'):60}
    actual={}
    for r in rows:
        t=tr[r['image']];o=official[r['image']]
        if t['role']!=r['role'] or t['label']!=o['label']:raise ValueError('Official label mismatch')
        if r['role']=='fit' and o['split']!='train':raise ValueError('Training leakage')
        key=(r['role'],t['label']);actual[key]=actual.get(key,0)+1
    if actual!=expected:raise ValueError('Label partition mismatch')
    return rows,tr,loaded

def image_objects(data_root,row):
    b=legacy.image_bytes(legacy.safe_file(data_root,row['image']))
    if digest(b)!=row['sha256']:raise ValueError('Image changed before inference')
    try:
        with Image.open(io.BytesIO(b)) as im:
            if im.width*im.height>20_000_000 or getattr(im,'n_frames',1)!=1:raise CaptureRefusal('Image decode limits')
            rgb=np.asarray(ImageOps.exif_transpose(im).convert('RGB'))
    except (OSError,Image.DecompressionBombError) as exc:
        raise CaptureRefusal('Undecodable verified capture: '+type(exc).__name__) from exc
    return extract_objects(rgb)

def create_model(cache,profile="resnet18",weights_file=None):
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file
    from anomalib.models.image.patchcore.torch_model import PatchcoreModel
    pin=BACKBONES[profile]
    p=Path(weights_file) if weights_file else Path(hf_hub_download(pin['repository'],'model.safetensors',revision=pin['revision'],cache_dir=cache,local_files_only=True,token=False))
    if p.stat().st_size>350*1024*1024 or digest(p.read_bytes())!=pin['sha256']:raise ValueError('Backbone hash')
    weights=load_file(str(p),device='cpu')
    model=PatchcoreModel(backbone=pin['architecture'],layers=['layer2','layer3'],pre_trained=False,num_neighbors=9).cpu()
    extractor=model.feature_extractor.feature_extractor;state={}
    for key in extractor.state_dict():
        first,sep,tail=key.partition('.');source=key if key in weights else first.replace('_','.')+sep+tail
        state[key]=weights[source]
    extractor.load_state_dict(state,strict=True)
    return model


def restore_verified_fit(model,bundle,ledger_sha256,profile):
    """Reuse a locally trusted pinned fit when only scoring-mask geometry changes."""
    import torch
    from safetensors.torch import load_file
    bundle=Path(bundle)
    if not ledger_sha256 or digest(legacy.safe_file(bundle,'artifacts.json').read_bytes())!=ledger_sha256:
        raise ValueError('Fit bundle ledger pin mismatch')
    legacy.verify(bundle)
    config=json.loads((bundle/'config.json').read_bytes())
    if config['model']!=dict(MODEL_CONFIG,backbone=profile) or config.get('backbone_pin')!=BACKBONES[profile] or config['input_pins']!=PINS:
        raise ValueError('Fit configuration mismatch')
    for key in ['size','minimum_area_fraction','maximum_objects','bbox_context']:
        if config['roi'][key]!=ROI_CONFIG[key]:raise ValueError('Feature crop changed; fit reuse not valid')
    # This exact reviewed predecessor differs only in the scoring mask. The
    # calibration-only audit confirmed all104 feature tensors are identical.
    if config['code_sha256']['object_core.py']!='b1eccd07754f093ad470a9e9d1a7aaa9545e3b1532267089308e0b60c9ee5554':
        raise ValueError('Unreviewed feature producer for fit reuse')
    previous=json.loads((bundle/'report.json').read_bytes())
    if previous.get('evaluation_images_scored')!=0 or previous.get('status')!='CALIBRATION_REJECTED_EVALUATION_UNTOUCHED':
        raise ValueError('Fit reuse requires a pre-evaluation calibration-only bundle')
    path=legacy.safe_file(bundle,'model.safetensors')
    if path.stat().st_size>350*1024*1024:raise ValueError('Fit artifact size limit')
    state=load_file(str(path),device='cpu')
    if not all(torch.isfinite(v).all() for v in state.values()):raise ValueError('Nonfinite fitted state')
    fit=json.loads((bundle/'fit.json').read_bytes())
    if state['memory_bank'].shape[0]!=fit['coreset_patches'] or fit['fit_images']!=256:raise ValueError('Fit memory/count mismatch')
    model.load_state_dict(state,strict=True);model.eval()
    return dict(fit,reused_fit=True,source_ledger_sha256=ledger_sha256,
                source_model_sha256=digest(path.read_bytes()),no_training_repeated=True)


def fit_model(model,rows,data_root,out=None):
    import torch
    model.train();bank=None;keys=None;generator=torch.Generator().manual_seed(330);object_count=0
    for i,row in enumerate(rows):
        objects=image_objects(data_root,row) # A refused fit image aborts: never silently omit it.
        for obj in objects:
            with torch.no_grad():embedding=model(torch.from_numpy(obj['tensor']))
            model.embedding_store.clear();object_count+=1
            k=torch.rand(len(embedding),generator=generator)
            bank=embedding if bank is None else torch.cat((bank,embedding))
            keys=k if keys is None else torch.cat((keys,k))
            if len(bank)>60000:
                indices=torch.topk(keys,60000,sorted=False).indices.sort().values
                bank=bank[indices];keys=keys[indices]
        if (i+1)%64==0:print('FIT_IMAGES',i+1,'OBJECTS',object_count,flush=True)
    if out is not None:
        from safetensors.torch import save_file
        save_file({'normal_training_patch_reservoir':bank.detach().cpu().contiguous()},str(out/'training-patch-reservoir.safetensors'))
    model.embedding_store=[bank]
    model.subsample_embedding(sampling_ratio=MODEL_CONFIG['coreset_ratio']);model.eval()
    return {'fit_images':len(rows),'fit_objects':object_count,'reservoir_patches':len(bank),'coreset_patches':len(model.memory_bank)}

def torch_map(model,tensor):
    import torch
    with torch.inference_mode():y=model(torch.from_numpy(tensor))
    a=y.anomaly_map.detach().cpu().numpy().astype('<f4')
    if a.shape!=(1,1,256,256) or not np.isfinite(a).all():raise ValueError('Invalid model map')
    return a

def ov_map(compiled,tensor):
    result=compiled([tensor]);a=np.asarray(result[compiled.output(1)],dtype='<f4')
    if a.shape!=(1,1,256,256) or not np.isfinite(a).all():raise ValueError('Invalid OpenVINO map')
    return a

def predict(model,row,data_root,out,calibration=None,compiled=None):
    began=time.perf_counter()
    try:objects=image_objects(data_root,row)
    except CaptureRefusal as exc:return {'image':row['image'],'sha256':row['sha256'],'score':None,'objects':[],'refusal':str(exc),'seconds':time.perf_counter()-began,'parity':None}
    records=[];issues=[];max_error=0.;ov_scores=[]
    for obj in objects:
        try:
            a=torch_map(model,obj['tensor']);score=object_score(a,obj['mask'])
        except (RuntimeError,ValueError,TypeError) as exc:
            return {'image':row['image'],'sha256':row['sha256'],'score':None,'objects':records,
                    'refusal':'INFERENCE_REFUSAL:'+type(exc).__name__+':'+str(exc),
                    'seconds':time.perf_counter()-began,'parity':None}
        name=f"maps/{digest(row['image'].encode())}-{obj['object_index']}.npy"
        np.save(out/name,a,allow_pickle=False)
        records.append({'object_index':obj['object_index'],'bbox':obj['bbox'],'square':obj['square'],'score':score,'map_path':name,'map_sha256':digest(a.tobytes())})
        if compiled is not None:
            try:
                other=ov_map(compiled,obj['tensor']);other_score=object_score(other,obj['mask']);ov_scores.append(other_score)
                error=float(np.max(np.abs(a-other)));max_error=max(max_error,error)
                if not np.allclose(a,other,atol=.001,rtol=.001) or not math.isclose(score,other_score,abs_tol=.001,rel_tol=.001):issues.append(obj['object_index'])
            except (RuntimeError,ValueError,TypeError):
                issues.append(obj['object_index'])
    score=max(r['score'] for r in records)
    parity=None
    if compiled is not None:
        same=len(ov_scores)==len(objects) and decide(score,calibration)==decide(max(ov_scores),calibration)
        parity={'pass':not issues and same,'object_failures':issues,'decision_match':same,'maximum_map_absolute_error':max_error,'openvino_score':max(ov_scores) if len(ov_scores)==len(objects) else None}
    return {'image':row['image'],'sha256':row['sha256'],'score':score,'objects':records,'refusal':None,'seconds':time.perf_counter()-began,'parity':parity}

def export_model(model,out):
    import torch,openvino as ov
    class Outputs(torch.nn.Module):
        def __init__(self,m):super().__init__();self.m=m
        def forward(self,x):
            y=self.m(x);return y.pred_score.reshape(1,1),y.anomaly_map
    converted=ov.convert_model(Outputs(model).eval(),example_input=torch.zeros(1,3,256,256),input=[1,3,256,256])
    ov.save_model(converted,out/'model.xml',compress_to_fp16=False)
    core=ov.Core();compiled=core.compile_model(core.read_model(out/'model.xml',out/'model.bin'),'CPU',{'INFERENCE_NUM_THREADS':2,'INFERENCE_PRECISION_HINT':'f32'})
    return compiled,{'status':'compiled','devices':core.available_devices,'executor':'CPU','version':ov.__version__}

def run(args):
    import torch,importlib.metadata as metadata
    from safetensors.torch import save_file
    out=new_output(args.output);(out/'maps').mkdir();started=time.monotonic()
    try:
        rows,truth,inputs=validate_inputs(args.inputs);data=Path(args.inputs)/'data'
        for name,b in inputs.items(): (out/name).write_bytes(b)
        torch.set_num_threads(2);torch.set_num_interop_threads(2);torch.manual_seed(330);np.random.seed(330)
        config={'model':dict(MODEL_CONFIG,backbone=args.profile), 'backbone_pin':BACKBONES[args.profile],'roi':ROI_CONFIG,'input_pins':PINS,'mode':'REAL_DATA_OFFLINE_NEW_CATEGORY','category':'cashew','actuation':False,'physical_object_session_independence':'UNKNOWN','versions':{k:metadata.version(k) for k in ['anomalib','torch','openvino','numpy','opencv-python-headless']},'host':{'system':platform.system(),'machine':platform.machine()},'code_sha256':{p.name:digest(p.read_bytes()) for p in [Path(__file__),Path(__file__).with_name('object_core.py'),Path(legacy.__file__)]},'calibration_comparator':'float64 midpoint candidate search, strict >; refusal prevents primary acceptance'}
        write_json(out/'config.json',config)
        model=create_model(args.cache,args.profile,args.weights)
        if bool(args.fit_bundle)!=bool(args.fit_ledger):raise ValueError('Fit bundle and ledger pin must be supplied together')
        fit=(restore_verified_fit(model,args.fit_bundle,args.fit_ledger,args.profile) if args.fit_bundle
             else fit_model(model,[r for r in rows if r['role']=='fit'],data,out))
        save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(out/'model.safetensors'))
        write_json(out/'fit.json',fit);print('MODEL_FITTED',fit,flush=True)
        cal_predictions=[predict(model,r,data,out) for r in rows if r['role']=='calibration']
        calibration=calibrate([{'label':truth[r['image']]['label'],'score':r['score']} for r in cal_predictions])
        write_json(out/'calibration-predictions.json',cal_predictions);write_json(out/'calibration.json',calibration)
        if not calibration['feasible']:
            report={'status':'CALIBRATION_REJECTED_EVALUATION_UNTOUCHED','calibration':calibration,
                    'evaluation_images_scored':0,'actuation':False,'automatic_acceptance':False,
                    'mode':'REAL_DATA_OFFLINE_CALIBRATION_ONLY','total_seconds':time.monotonic()-started}
            write_json(out/'report.json',report);legacy.seal(out);legacy.verify(out)
            print('CALIBRATION_REJECTED_EVALUATION_UNTOUCHED',json.dumps(report),flush=True)
            return
        compiled=None
        try:compiled,export=export_model(model,out)
        except Exception as exc:export={'status':'blocked','error_type':type(exc).__name__,'error':str(exc)}
        write_json(out/'export.json',export)
        if compiled is None:
            report={'status':'EXPORT_BLOCKED_EVALUATION_UNTOUCHED','calibration':calibration,
                    'export':export,'evaluation_images_scored':0,'actuation':False,'automatic_acceptance':False}
            write_json(out/'report.json',report);legacy.seal(out);legacy.verify(out)
            print('EXPORT_BLOCKED_EVALUATION_UNTOUCHED',json.dumps(report),flush=True)
            return
        frozen={'manifest':PINS['manifest.json'],'truth':PINS['truth.json'],'model':digest((out/'model.safetensors').read_bytes()),'config':digest((out/'config.json').read_bytes()),'calibration':digest((out/'calibration.json').read_bytes()),'export':digest((out/'export.json').read_bytes()),'first_evaluation_not_started':True}
        for name in ['model.xml','model.bin']:
            if (out/name).exists():frozen[name]=digest((out/name).read_bytes())
        write_json(out/'FROZEN_BEFORE_EVALUATION.json',frozen)
        print('FROZEN_BEFORE_EVALUATION',digest((out/'FROZEN_BEFORE_EVALUATION.json').read_bytes()),calibration['status'],flush=True)
        # Consuming this local frozen cohort is one-shot. A crash does not grant a rerun.
        marker=Path(args.inputs)/'EVALUATION_CONSUMED.json'
        write_json(marker,{'frozen_sha256':digest((out/'FROZEN_BEFORE_EVALUATION.json').read_bytes()),
                           'output':str(out),'expected_images':110})
        evaluation=[]
        with (out/'evaluation-unlabelled.jsonl').open('x') as journal:
            for row in [r for r in rows if r['role']=='evaluation']:
                result=predict(model,row,data,out,calibration,compiled)
                journal.write(json.dumps(result,allow_nan=False,sort_keys=True)+'\n')
                journal.flush();os.fsync(journal.fileno());evaluation.append(result)
        write_json(out/'evaluation-unlabelled.json',evaluation)
        eval_truth={r['image']:r['label'] for r in truth.values() if r['role']=='evaluation'}
        report=metrics(evaluation,eval_truth,calibration)
        parity={'status':'blocked' if compiled is None else 'pass' if all(r['parity'] and r['parity']['pass'] for r in evaluation) else 'fail','images':len(evaluation),'atol':.001,'rtol':.001,'failed_images':[r['image'] for r in evaluation if r['parity'] is not None and not r['parity']['pass']],'capture_refusals':[r['image'] for r in evaluation if r['score'] is None],'device':'CPU','not_Intel_target_qualification':True}
        report.update(mode=config['mode'],category='cashew',calibration=calibration,export=export,parity=parity,total_seconds=time.monotonic()-started,actual_cost='unknown',actuation=False,automatic_acceptance=False,old_candle_comparison='Different category, not a paired improvement claim',same_object_reinspection='NOT_IMPLEMENTED_NO_ADDITIONAL_CAPTURE')
        write_json(out/'report.json',report)
        with (out/'predictions.csv').open('x',newline='') as f:
            fields=['image','sha256','role','label','score','diagnostic','binary_defect','object_count','refusal','seconds']
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for row in cal_predictions+evaluation:
                t=truth[row['image']];d=decide(row['score'],calibration)
                w.writerow({'image':row['image'],'sha256':row['sha256'],'role':t['role'],'label':t['label'],'score':row['score'],'diagnostic':d['diagnostic'],'binary_defect':d['binary_defect'],'object_count':len(row['objects']),'refusal':row['refusal'],'seconds':row['seconds']})
        legacy.seal(out);legacy.verify(out)
        print('EXPERIMENT_COMPLETE',json.dumps(report,sort_keys=True),flush=True)
    except Exception as exc:
        write_json(out/'failure.json',{'type':type(exc).__name__,'error':str(exc),'elapsed_seconds':time.monotonic()-started});legacy.seal(out);raise

def inspect_image(args):
    import openvino as ov
    bundle=Path(args.bundle);legacy.verify(bundle)
    if (bundle/'failure.json').exists():raise ValueError('Failed model bundle')
    report=json.loads((bundle/'report.json').read_bytes())
    if report.get('parity',{}).get('status')!='pass':
        raise ValueError('Export unqualified: effective HOLD; no calibrated diagnostic')
    config=json.loads((bundle/'config.json').read_bytes());calibration=json.loads((bundle/'calibration.json').read_bytes())
    frozen=json.loads((bundle/'FROZEN_BEFORE_EVALUATION.json').read_bytes())
    profile=config['model'].get('backbone')
    if profile not in BACKBONES or config['model']!=dict(MODEL_CONFIG,backbone=profile) or config.get('backbone_pin')!=BACKBONES[profile] or config['roi']!=ROI_CONFIG or config['input_pins']!=PINS:raise ValueError('Model configuration mismatch')
    for name in ['model.xml','model.bin']:
        if digest(legacy.safe_file(bundle,name).read_bytes())!=frozen[name]:raise ValueError('Export identity mismatch')
    if digest((bundle/'calibration.json').read_bytes())!=frozen['calibration']:raise ValueError('Calibration identity mismatch')
    compiled=ov.Core().compile_model(ov.Core().read_model(bundle/'model.xml',bundle/'model.bin'),'CPU',{'INFERENCE_NUM_THREADS':2,'INFERENCE_PRECISION_HINT':'f32'})
    path=Path(args.image).absolute();row={'image':path.name,'sha256':args.sha256};out=new_output(args.output)
    try:
        objects=image_objects(path.parent,row);scores=[];boxes=[]
        for obj in objects:
            a=ov_map(compiled,obj['tensor']);scores.append(object_score(a,obj['mask']));boxes.append(obj['bbox']);np.save(out/f"map-{obj['object_index']}.npy",a,allow_pickle=False)
        score=max(scores);decision=decide(score,calibration)
    except CaptureRefusal as exc:score=None;boxes=[];decision={'diagnostic':'hold','reason':str(exc),'binary_defect':None}
    write_json(out/'inspection.json',{'mode':'USER_IMAGE_OFFLINE_UNVERIFIED_DOMAIN','image':path.name,'sha256':args.sha256,'score':score,'boxes':boxes,'diagnostic':decision,'effective_decision':'hold','automatic_acceptance':False,'actuation':False,'model_ledger_sha256':digest((bundle/'artifacts.json').read_bytes()),'reason':'No station/domain/operator qualification; diagnostic model only'})
    legacy.seal(out);print('INSPECTION_REQUIRES_HUMAN_REVIEW')

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('run');r.add_argument('--inputs',required=True);r.add_argument('--cache',required=True);r.add_argument('--output',required=True)
    r.add_argument('--profile',choices=sorted(BACKBONES),default='resnet18');r.add_argument('--weights',help='Optional local exact-hash-pinned public safetensors file')
    r.add_argument('--fit-bundle',help='Explicit trusted calibration-only fit for compatible mask correction');r.add_argument('--fit-ledger',help='SHA256 of that fit bundle artifact ledger')
    i=sub.add_parser('inspect');i.add_argument('--bundle',required=True);i.add_argument('--image',required=True);i.add_argument('--sha256',required=True);i.add_argument('--output',required=True)
    v=sub.add_parser('verify');v.add_argument('--bundle',required=True)
    a=p.parse_args()
    if a.command=='run':run(a)
    elif a.command=='inspect':inspect_image(a)
    else:legacy.verify(Path(a.bundle));print('INTEGRITY_VERIFIED_NOT_AUTHENTICITY')
if __name__=='__main__':main()
