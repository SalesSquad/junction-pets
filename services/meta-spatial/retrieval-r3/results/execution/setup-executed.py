import pathlib,subprocess,json,hashlib,time,os,shutil
c=pathlib.Path('/Users/mikaelervamaa/Developer/meta-lens-adapter-r3-control-20261114')
logs=c/'setup-logs'; logs.mkdir(exist_ok=True)
free=shutil.disk_usage(c).free
if free<8000000000: raise RuntimeError('insufficient_disk_8GB')
def step(name,argv,timeout):
    t=time.time()
    with (logs/(name+'.log')).open('w') as f:
        r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,text=True,timeout=timeout)
    result={'name':name,'returncode':r.returncode,'started_epoch':t,'ended_epoch':time.time(),'log_sha256':hashlib.sha256((logs/(name+'.log')).read_bytes()).hexdigest()}
    (logs/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result),flush=True); r.check_returncode()
step('venv',['/opt/homebrew/bin/python3.12','-m','venv',str(c/'venv')],60)
py=str(c/'venv/bin/python')
step('install',[py,'-m','pip','install','--disable-pip-version-check','--report',str(logs/'install-report.json'),'torch==2.8.0','torchvision==0.23.0','numpy==2.2.6','Pillow==11.3.0','transformers==4.57.1','huggingface-hub==0.36.0','safetensors==0.6.2','sentencepiece==0.2.1'],900)
step('runtime',[py,'-c','import torch,numpy,safetensors,json,platform; print(json.dumps({"torch":torch.__version__,"numpy":numpy.__version__,"safetensors":safetensors.__version__,"mps_available":torch.backends.mps.is_available(),"mps_built":torch.backends.mps.is_built(),"platform":platform.platform(),"machine":platform.machine()}))'],30)
step('freeze',[py,'-m','pip','freeze'],30)
