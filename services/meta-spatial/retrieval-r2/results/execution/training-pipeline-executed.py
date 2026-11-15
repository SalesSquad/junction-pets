import pathlib,json,hashlib,subprocess,time,os,shutil
root=pathlib.Path('/opt/meta-lens-training-r2-20261114')
source=root/'source';m=json.loads((source/'training-sources.json').read_text())
assert m['source_commit']=='6103e6d09141090348ff213d850192b895c6cc8a'
snapshot=root/'source-6103e6d'
snapshot.mkdir(exist_ok=False)
for name,sha in m['files'].items():
 b=(source/name).read_bytes();assert hashlib.sha256(b).hexdigest()==sha
 (snapshot/name).write_bytes(b);(snapshot/name).chmod(0o444)
(snapshot/'training-sources.json').write_text(json.dumps(m,indent=2)+'\n')
deadline=time.time()+1800
while not (root/'abo-r2/dataset.json').exists():
 if time.time()>deadline:raise RuntimeError('sealed_data_not_ready')
 fail=root/'logs/prepare-data.json'
 if fail.exists() and json.loads(fail.read_text())['exit_code']!=0:raise RuntimeError('preparation_failed')
 time.sleep(10)
assert json.loads((root/'logs/cuda-verified.json').read_text())['exit_code']==0
py=str(root/'venv/bin/python'); npy=str(root/'nemotron-venv/bin/python')
commands=[('siglip-train',[py,str(snapshot/'train_retrieval.py'),'--data',str(root/'abo-r2'),'--output',str(root/'run-r2'),'--cache',str(root/'cache/hf'),'--epochs','12','--seeds','17','31','53','--max-seconds','7200'],7350),('dino-eval',[py,str(snapshot/'dino_baseline.py'),'--data',str(root/'abo-r2'),'--output',str(root/'dino-r2'),'--cache',str(root/'cache/hf'),'--max-seconds','1800'],1900),('nemotron-eval',[npy,str(snapshot/'nemotron_metadata.py'),'--data',str(root/'abo-r2'),'--siglip-features',str(root/'run-r2/features.npz'),'--output',str(root/'nemotron-r2'),'--cache',str(root/'cache/hf'),'--max-seconds','1800'],1900)]
outcomes=[]
for name,argv,timeout in commands:
 start=time.time();print(json.dumps({'stage':name,'state':'starting','source_commit':m['source_commit']}),flush=True)
 try:
  with (root/'logs'/(name+'.log')).open('w') as log:
   p=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','OPENBLAS_NUM_THREADS':'4','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','HF_HUB_DISABLE_TELEMETRY':'1','TOKENIZERS_PARALLELISM':'false'})
  code=p.returncode;error=None
 except Exception as exc:code=None;error=type(exc).__name__
 result={'step':name,'source_commit':m['source_commit'],'exit_code':code,'exception':error,'started_epoch':start,'ended_epoch':time.time(),'seconds':time.time()-start,'log_sha256':hashlib.sha256((root/'logs'/(name+'.log')).read_bytes()).hexdigest()}
 (root/'logs'/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');outcomes.append(result)
 (root/'training-outcomes.json').write_text(json.dumps(outcomes,indent=2)+'\n')
 print(json.dumps(result),flush=True)
 if code!=0:print((root/'logs'/(name+'.log')).read_text(errors='replace')[-5000:],flush=True)
print(json.dumps({'state':'training_pipeline_finished','outcomes':outcomes}),flush=True)
if any(r['exit_code']!=0 for r in outcomes):raise SystemExit(1)
