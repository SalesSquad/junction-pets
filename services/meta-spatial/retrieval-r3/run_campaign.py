#!/usr/bin/env python3
"""Finite pinned-source experiment, preserving every step and failure log."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prior-dataset', type=Path, required=True)
    p.add_argument('--prior-features', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--training-device', default='cpu')
    p.add_argument('--encoding-device', default='mps')
    a = p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):
        p.error('new_campaign_output_required')
    root = Path(__file__).resolve().parent
    a.output.mkdir(parents=True, exist_ok=True)
    logs = a.output/'logs'; logs.mkdir()
    from prepare_holdout import PRIOR_DATASET_SHA256
    from train_retrieval import WEIGHTS_SHA
    if digest(a.prior_dataset) != PRIOR_DATASET_SHA256:
        raise ValueError('historical_dataset_hash_mismatch')
    prior = a.output/'prior-data'; prior.mkdir()
    (prior/'dataset.json').write_bytes(a.prior_dataset.read_bytes())
    (prior/'dataset.sha256').write_text(PRIOR_DATASET_SHA256+'\n')
    env = dict(os.environ, HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1',
               OMP_NUM_THREADS='4', VECLIB_MAXIMUM_THREADS='4', OPENBLAS_NUM_THREADS='4',
               TOKENIZERS_PARALLELISM='false', PYTHONDONTWRITEBYTECODE='1')
    start = {'source_commit':a.source_commit,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
             'prior_dataset_sha256':PRIOR_DATASET_SHA256,'prior_features_sha256':digest(a.prior_features),
             'training_device':a.training_device,'encoding_device':a.encoding_device,
             'source_hashes':{f.name:digest(f) for f in root.iterdir() if f.is_file()},
             'thread_limit':4,'new_cloud_compute_usd':0.0,'private_data_used':False}
    (a.output/'campaign-start.json').write_text(json.dumps(start,indent=2)+'\n')

    def step(name, command, timeout):
        began = time.time()
        with (logs/(name+'.log')).open('w') as stream:
            try:
                r = subprocess.run(command, cwd=root, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, timeout=timeout, text=True)
                code, error = r.returncode, None
            except subprocess.TimeoutExpired:
                code, error = None, 'timeout'
        receipt = {'step':name,'command':command,'source_commit':a.source_commit,
                   'started_epoch':began,'ended_epoch':time.time(),'exit_code':code,'error':error,
                   'log_sha256':digest(logs/(name+'.log'))}
        (logs/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt),flush=True)
        if code != 0:
            raise RuntimeError('step_failed:'+name)
        return receipt

    py = sys.executable
    step('dependencies',[py,'-c','import torch,safetensors; assert torch.__version__.startswith("2.8.0"); print(torch.__version__,torch.backends.mps.is_available())'],45)
    step('focused-tests',[py,'-m','unittest','-v','test_visual_adapter','test_holdout','test_evaluation','test_runtime'],120)
    model_code = ('import sys,json; from pathlib import Path; '
                  'sys.path.insert(0,sys.argv[1]); '
                  'from train_retrieval import MODEL_ID,REVISION,MODEL_FILES,WEIGHTS_SHA,file_sha256; '
                  'from huggingface_hub import snapshot_download; '
                  'p=Path(snapshot_download(MODEL_ID,revision=REVISION,allow_patterns=MODEL_FILES,cache_dir=sys.argv[2],token=False)); '
                  'assert file_sha256(p/"model.safetensors")==WEIGHTS_SHA; '
                  'print(json.dumps({"model_id":MODEL_ID,"revision":REVISION,"weight_sha256":WEIGHTS_SHA}))')
    # Public model download is independent I/O; only one training/inference lane.
    with ThreadPoolExecutor(max_workers=1) as executor:
        model = executor.submit(step,'model-cache',[py,'-c',model_code,str(root.parent/'retrieval-r2'),str(a.output/'model-cache')],1800)
        step('train-visual',[py,str(root/'train_visual.py'),'--data',str(prior),'--features',str(a.prior_features),
                             '--output',str(a.output/'training'),'--device',a.training_device,'--max-seconds','1800'],1860)
        step('rehydrate-metadata',[py,str(root/'restore_prior_cache.py'),'--dataset',str(a.prior_dataset),
                                  '--output',str(prior)],960)
        step('prepare-holdout',[py,str(root/'prepare_holdout.py'),'--prior-data',str(prior),
                               '--output',str(a.output/'fresh-data'),'--max-products','2400',
                               '--min-families-per-split','400','--workers','12','--max-seconds','900'],960)
        model.result()
    step('fresh-evaluation',[py,str(root/'evaluation.py'),'--data',str(a.output/'fresh-data'),
                            '--prior-data',str(prior),'--training',str(a.output/'training'),
                            '--output',str(a.output/'evaluation'),'--cache',str(a.output/'model-cache'),
                            '--source-commit',a.source_commit,'--device',a.encoding_device,'--max-seconds','3600'],3660)
    # Runtime smoke uses actual trained bytes and actual fresh query/gallery.
    smoke = ('import json,sys,numpy as np; from pathlib import Path; from runtime import VisualRetrievalAdapter; '
             'r=Path(sys.argv[1]); d=json.loads((r/"fresh-data/dataset.json").read_text()); '
             'idx=[i for i,x in enumerate(d["records"]) if x["split"]=="test"]; '
             'z=np.load(r/"evaluation/features.npz",allow_pickle=False); '
             'adapter=VisualRetrievalAdapter.from_artifacts(r/"training",r/"evaluation"); '
             'out=adapter.propose(z["query"][idx[:3]],z["gallery"][idx],[d["records"][i]["product_id"] for i in idx]); '
             '(r/"runtime-smoke.json").write_text(json.dumps(out,indent=2)+"\\n"); print(json.dumps(out))')
    step('runtime-smoke',[py,'-c',smoke,str(a.output)],120)
    report = json.loads((a.output/'evaluation/report.json').read_text())
    finish = {'source_commit':a.source_commit,'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
              'status':'COMPLETED','product_gate':report['product_gate'],'production_activation':False,
              'new_cloud_compute_usd':0.0,'model_weights_sha256':WEIGHTS_SHA}
    (a.output/'campaign-finish.json').write_text(json.dumps(finish,indent=2)+'\n')
    print(json.dumps(finish),flush=True)


if __name__ == '__main__':
    # Import R2 shared helpers only from the frozen sibling source tree.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'retrieval-r2'))
    main()
