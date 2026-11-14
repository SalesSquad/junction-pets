import pathlib,json,subprocess,hashlib,io,tarfile,os
repo=pathlib.Path('/Users/mikaelervamaa/Developer/meta-lens-adapter-r3-20261114')
c=pathlib.Path('/Users/mikaelervamaa/Developer/meta-lens-adapter-r3-control-20261114')
expected=json.loads("{\"train_visual.py\":\"0bb23a98c3d747b87252f72c1b3765a08ecb367e833f0a815c8bb084a1d05b50\",\"test_visual_adapter.py\":\"fcfd362e125763134083c0e43204d2fe6d032992e2d15ede0d81bec1a197a666\",\"test_evaluation.py\":\"acbe01a6515384116322de1408d1e159577a7d828b91e28ac63354472e683fbf\",\"restore_prior_cache.py\":\"2fe52c716d0e736bc4d1b5c677537551611976428c6f4080f680091f8a95eb1f\",\"evaluation.py\":\"3bc293ded8d212150a559ea31e8e1e59b2b023567a751ed0e29e6dc2dea5f259\",\"README.md\":\"4ba25db86b2a451f0fac56053bee0a88ce182bbc5e6d980004e5636f07d4c4ff\",\"test_runtime.py\":\"b3bbeb1095b629a305f7605769831b6faf6433c847b2d1e61baf9b83fa4c5e4d\",\"visual_adapter.py\":\"933de9d32de9782e4b399ef7f5d0a87c94e8389dd65f7ed1eae96a541f0250b1\",\"runtime.py\":\"e2bb3096ef062758fc956a81b780f4954bbc7224465cc787bec16a77c406328d\",\"cloud_lease.py\":\"eee107ed72863c516f1d7a46d00836427177d1c16b7a27e18f8271841b5f3e2c\",\"test_holdout.py\":\"228fe1be72eaf937df329c413231e06869a8d2e7c5ddb3d61bed220444051b3a\",\"protocol.json\":\"0900b0d4d96e6787fa9f63a9d0e04af087d65dc33202810a4fd29f1ebefb1756\",\"prepare_holdout.py\":\"baa43173353705893dec58a7f6ab73c1dfb3c0d1ef8fc965e54ee85fe9c91cb0\",\"requirements.txt\":\"0b15afce56842b103dd267acd21ffbc5f39bad8362370e4dd893f6a5bbf67ced\",\".gitignore\":\"4cad133d4f0a6cf4bba15f1b8bbae48d6a55f20b94f75487c51a93cc6a5af59f\",\"run_campaign.py\":\"5956827c4bd4361e4a2fe133158887b0c2c73ee509f1e765eb7499bf426a0862\"}")
def git(*args,timeout=90):
    r=subprocess.run(['/usr/bin/git','-C',str(repo),*args],capture_output=True,text=True,timeout=timeout)
    if r.stdout: print(r.stdout,flush=True)
    if r.stderr: print(r.stderr,flush=True)
    r.check_returncode(); return r.stdout.strip()
if git('rev-parse','HEAD')!='633523f2cc007fae2d3b8a912e3ac3eaa12b934e': raise RuntimeError('source_base_changed')
status=git('status','--porcelain=v1')
if any('services/meta-spatial/retrieval-r3/' not in row for row in status.splitlines()): raise RuntimeError('unrelated_dirty_paths')
root=repo/'services/meta-spatial/retrieval-r3'
for name,digest in expected.items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest: raise RuntimeError('source_hash_changed:'+name)
git('diff','--check')
git('add','--','services/meta-spatial/retrieval-r3')
git('commit','-m','feat(meta): implement shared visual retrieval adapters and fresh holdout protocol')
head=git('rev-parse','HEAD')
git('push','-u','origin','HEAD:refs/heads/codex/meta-lens-adapter-r3-20261114',timeout=150)
remote=git('ls-remote','origin','refs/heads/codex/meta-lens-adapter-r3-20261114')
if not remote.startswith(head+'\t'): raise RuntimeError('remote_tip_mismatch')
archive=subprocess.run(['/usr/bin/git','-C',str(repo),'archive',head,'services/meta-spatial/retrieval-r3','services/meta-spatial/retrieval-r2/retrieval.py','services/meta-spatial/retrieval-r2/prepare_data.py','services/meta-spatial/retrieval-r2/train_retrieval.py'],capture_output=True,check=True,timeout=30).stdout
frozen=c/('source-'+head[:12]); frozen.mkdir(exist_ok=False)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    for member in tar.getmembers():
        if not (frozen/member.name).resolve().is_relative_to(frozen.resolve()) or member.issym() or member.islnk(): raise RuntimeError('unsafe_source_archive')
    tar.extractall(frozen,filter='data')
for path in frozen.rglob('*'):
    if path.is_file(): path.chmod(0o444)
receipt={'source_commit':head,'source_files':expected,'archive_sha256':hashlib.sha256(archive).hexdigest(),'snapshot':str(frozen),'remote_tip_verified':True}
(c/'source.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
command=[str(c/'venv/bin/python'),'-B',str(frozen/'services/meta-spatial/retrieval-r3/run_campaign.py'),'--prior-dataset','/Users/mikaelervamaa/Developer/meta-lens-training-r2-control-20261114/evidence/abo-r2/dataset.json','--prior-features','/Users/mikaelervamaa/Developer/meta-lens-training-r2-control-20261114/evidence/run-r2/features.npz','--output',str(c/'experiment'),'--source-commit',head,'--training-device','cpu','--encoding-device','mps']
subprocess.run(command,env=env,check=True,timeout=7200)
