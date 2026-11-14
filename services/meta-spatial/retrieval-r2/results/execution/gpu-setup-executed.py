import pathlib,subprocess,concurrent.futures,time,hashlib,json,os
root=pathlib.Path('/opt/meta-lens-training-r2-20261114'); py=str(root/'venv/bin/python')
expected={'prepare_data.py':'d8428e707666e0ab5e2f94d71e639ededdfce9ff845139af1abc0617b958b59e','requirements.txt':'a9cb6e392b61d2a4ddc04a1ca53aff13013ee06cc4e5d161b80b7de1e86bcdde','experiment.json':'37ead4d4d242686528e77bcaf8e1437d03dbaed226ab7b21715f8a84b4dcdf65'}
for name,sha in expected.items(): assert hashlib.sha256((root/'source'/name).read_bytes()).hexdigest()==sha
(root/'preparation-source.json').write_text(json.dumps({'commit':'404aaddd7d6933cdeeabc49d8c4e005bf336d915','files':expected},indent=2)+'\n')
def run(name,argv,timeout):
 start=time.time()
 with (root/'logs'/(name+'.log')).open('w') as out:
  r=subprocess.run(argv,stdout=out,stderr=subprocess.STDOUT,timeout=timeout,env={**os.environ,'PIP_DISABLE_PIP_VERSION_CHECK':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','HF_HUB_DISABLE_TELEMETRY':'1'})
 result={'step':name,'exit_code':r.returncode,'seconds':time.time()-start,'log_sha256':hashlib.sha256((root/'logs'/(name+'.log')).read_bytes()).hexdigest()}
 (root/'logs'/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
 if r.returncode: print((root/'logs'/(name+'.log')).read_text()[-4000:],flush=True); raise RuntimeError(name+'_failed')
 return result
def packages():
 run('torch-install',[py,'-m','pip','install','torch==2.8.0','torchvision==0.23.0','--index-url','https://download.pytorch.org/whl/cu128','--report',str(root/'logs/torch-install-report.json')],900)
 run('requirements-install',[py,'-m','pip','install','-r',str(root/'source/requirements.txt'),'--report',str(root/'logs/requirements-install-report.json')],300)
 run('cuda-verified',[py,'-c','import torch,json; assert torch.cuda.is_available(); print(json.dumps({"torch":torch.__version__,"cuda":torch.version.cuda,"gpu":torch.cuda.get_device_name(),"bf16":torch.cuda.is_bf16_supported()}))'],60)
 run('pip-freeze',[py,'-m','pip','freeze'],30)
 return {'runtime_ready':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 fs=[pool.submit(packages),pool.submit(run,'prepare-data',[py,str(root/'source/prepare_data.py'),'--output',str(root/'abo-r2'),'--max-products','6000','--max-download-bytes','3000000000','--max-seconds','1800','--workers','12'],1900)]
 outcomes=[]
 for f in fs:
  try:outcomes.append(f.result())
  except Exception as exc:outcomes.append({'error':type(exc).__name__+':'+str(exc)})
(root/'setup-outcomes.json').write_text(json.dumps(outcomes,indent=2)+'\n')
print(json.dumps({'setup_outcomes':outcomes}),flush=True)
if any('error' in x for x in outcomes):raise SystemExit(1)
