import pathlib,subprocess,os,time,json,hashlib,urllib.request,urllib.error,concurrent.futures,base64
root=pathlib.Path('/opt/meta-lens-training-r2-20261114');py=str(root/'venv/bin/python')
req=base64.b64decode('IyBTRUNPTkRBUlkgaXNvbGF0ZWQgZW52aXJvbm1lbnQgb25seS4gUmV1c2UgdGhlIGFwcHJvdmVkIENVREEgdG9yY2ggYnVpbGQuCiMgTlZJRElBIGNoZWNrcG9pbnQgcmVjb3JkcyBUcmFuc2Zvcm1lcnMgNS41LjA7IHByaW1hcnkgU2lnTElQIHN0YXlzIG9uIDQuNTcuMS4KdHJhbnNmb3JtZXJzPT01LjUuMApudW1weT09Mi4yLjYKUGlsbG93PT0xMS4zLjAKc2FmZXRlbnNvcnM9PTAuNi4yCg==');assert hashlib.sha256(req).hexdigest()=='0181667ea6d3cc679a53bc2ec7ef8dd83bd05bfd60f4a98e5504f1a66a00a0b8'
(root/'source/nemotron-requirements.txt').write_bytes(req)
def run(name,args,timeout):
 start=time.time()
 with (root/'logs'/(name+'.log')).open('w') as out:
  r=subprocess.run(args,stdout=out,stderr=subprocess.STDOUT,timeout=timeout,env={**os.environ,'PIP_DISABLE_PIP_VERSION_CHECK':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','HF_HUB_DISABLE_TELEMETRY':'1'})
 result={'step':name,'exit_code':r.returncode,'seconds':time.time()-start,'log_sha256':hashlib.sha256((root/'logs'/(name+'.log')).read_bytes()).hexdigest()}
 (root/'logs'/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
 if r.returncode: print((root/'logs'/(name+'.log')).read_text()[-3500:],flush=True);raise RuntimeError(name+'_failed')
def secondary():
 before=subprocess.check_output([py,'-m','pip','freeze'])
 second=root/'nemotron-venv'
 run('nemotron-venv',['python3','-m','venv',str(second)],60)
 sites=list((second/'lib').glob('python*/site-packages')); assert len(sites)==1
 primary=list((root/'venv/lib').glob('python*/site-packages'));assert len(primary)==1
 (sites[0]/'approved_primary_runtime.pth').write_text(str(primary[0])+'\n')
 sp=str(second/'bin/python')
 run('nemotron-install',[sp,'-m','pip','install','-r',str(root/'source/nemotron-requirements.txt'),'--report',str(root/'logs/nemotron-install-report.json')],400)
 after=subprocess.check_output([py,'-m','pip','freeze']);assert before==after
 run('nemotron-runtime',[sp,'-c','import torch,transformers,json;assert torch.cuda.is_bf16_supported();assert transformers.__version__=="5.5.0";print(json.dumps({"torch":torch.__version__,"transformers":transformers.__version__,"gpu":torch.cuda.get_device_name()}))'],60)
 (root/'logs/primary-runtime-preserved.json').write_text(json.dumps({'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest(),'unchanged':True})+'\n')
def models():
 code="import os,pathlib,hashlib,json,time\nos.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'\nos.environ['HF_HUB_DISABLE_TELEMETRY']='1'\nfrom huggingface_hub import snapshot_download\nmodels=[('google/siglip2-base-patch16-224','75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2','612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b'),('facebook/dinov2-small','ed25f3a31f01632728cabb09d1542f84ab7b0056','ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1'),('nvidia/Nemotron-3-Embed-1B-BF16','c0c9fea93ea424587517f2c59e20db9f1d6bf615','f959c3b04e66b42de280bfb97c140cb7e0bfe25e3ecb0b4464c68a8436b2d04f')]\nreceipts=[]\nfor name,rev,sha in models:\n start=time.time();p=pathlib.Path(snapshot_download(name,revision=rev,token=False,cache_dir='/opt/meta-lens-training-r2-20261114/cache/hf',allow_patterns=['*.json','*.safetensors','tokenizer.model','README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md']))\n f=p/'model.safetensors';h=hashlib.sha256()\n with f.open('rb') as stream:\n  for b in iter(lambda:stream.read(1048576),b''):h.update(b)\n assert h.hexdigest()==sha\n r={'model':name,'revision':rev,'weights_sha256':sha,'bytes':f.stat().st_size,'seconds':time.time()-start};receipts.append(r);print(json.dumps(r),flush=True)\n pathlib.Path('/opt/meta-lens-training-r2-20261114/logs/model-downloads.json').write_text(json.dumps(receipts,indent=2)+'\\n')\n"
 run('model-downloads',[py,'-c',code],900)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 fs=[pool.submit(secondary),pool.submit(models)]
 results=[]
 for f in fs:
  try:f.result();results.append('success')
  except Exception as exc:results.append(type(exc).__name__+':'+str(exc))
print(json.dumps({'model_setup':results}),flush=True)
try:
 u='https://huggingface.co/facebook/sam3.1/resolve/daa63191845a41281374e725f4c9e51c7a824460/sam3.1_multiplex.pt'
 with urllib.request.urlopen(urllib.request.Request(u,method='HEAD'),timeout=30) as response: sam={'model':'facebook/sam3.1','anonymous_head_status':response.status,'weights_downloaded':False}
except urllib.error.HTTPError as e:sam={'model':'facebook/sam3.1','anonymous_head_status':e.code,'weights_downloaded':False,'authorization':'no_credential_used'}
except Exception as e:sam={'model':'facebook/sam3.1','probe_error':type(e).__name__,'weights_downloaded':False}
(root/'logs/sam-access.json').write_text(json.dumps(sam,indent=2)+'\n');print(json.dumps(sam),flush=True)
if any(x!='success' for x in results):raise SystemExit(1)
