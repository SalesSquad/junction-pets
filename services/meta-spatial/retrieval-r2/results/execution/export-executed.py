import pathlib,json,hashlib,tarfile
root=pathlib.Path('/opt/meta-lens-training-r2-20261114')
assert all(x['exit_code']==0 for x in json.loads((root/'training-outcomes.json').read_text()))
assert all(x['exit_code']==0 for x in json.loads((root/'arbitration-outcomes.json').read_text()))
chosen=[]
for d in ['run-r2','dino-r2','nemotron-r2','arbitration-r2','logs','source-6103e6d','source-9b799ed8']:
 for p in (root/d).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts:chosen.append(p)
chosen += [p for p in root.glob('*.json') if p.is_file()]
chosen += [root/'abo-r2/dataset.json',root/'abo-r2/dataset.sha256']
manifest={'work_id':'META-LENS-TRAIN-20261114-R2','private_data_used':False,'files':{str(p.relative_to(root)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(set(chosen))}}
(root/'export-manifest.json').write_text(json.dumps(manifest,indent=2))
archive=root/'training-evidence.tar.gz'
assert not archive.exists()
with tarfile.open(archive,'w:gz',compresslevel=1) as t:
 for p in sorted(set(chosen)):t.add(p,arcname=str(p.relative_to(root)),recursive=False)
 t.add(root/'export-manifest.json',arcname='export-manifest.json')
print(json.dumps({'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archive_bytes':archive.stat().st_size,'files':len(manifest['files'])}),flush=True)
