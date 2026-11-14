#!/usr/bin/env python3
"""Export owned public research evidence without duplicating large model caches."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'retrieval-r2'))
from retrieval import confidence, absent_family_scores


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--campaign', type=Path, required=True)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):
        p.error('new_evidence_output_required')
    a.output.mkdir(parents=True,exist_ok=True)
    report = json.loads((a.campaign/'evaluation/report.json').read_text())
    finish = json.loads((a.campaign/'campaign-finish.json').read_text())
    if finish['status'] != 'COMPLETED':
        raise ValueError('campaign_not_completed')
    def copy(source, relative):
        destination = a.output/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        if sha(source) != sha(destination):
            raise ValueError('copy_hash_mismatch')
    for folder in ('training','logs'):
        for path in sorted((a.campaign/folder).rglob('*')):
            if path.is_file() and path.suffix in ('.json','.log','.safetensors'):
                copy(path,path.relative_to(a.campaign))
    for name in ('campaign-start.json','campaign-finish.json','runtime-smoke.json'):
        copy(a.campaign/name,name)
    for name in ('report.json','features.json','evaluation-freeze.json','frozen-policies.json'):
        copy(a.campaign/'evaluation'/name,'evaluation/'+name)
    copy(a.control/'source.json','execution-source.json')
    for path in sorted((a.control/'setup-logs').glob('*')):
        if path.is_file() and path.suffix in ('.json','.log'):
            copy(path,'setup/'+path.name)
    for name in ('setup-executed.py','campaign-executed.py','cloud_lease.py','lease.json'):
        copy(a.control/name,'execution/'+name)
    if (a.control/'receipt-exports').exists():
        for path in sorted((a.control/'receipt-exports').iterdir()):
            if path.is_file():
                copy(path,'command-receipts/'+path.name)
    if (a.control/'compute-admission.json').exists():
        copy(a.control/'compute-admission.json','compute-admission.json')
    for name in ('selection-before-download.json','dataset.sha256'):
        copy(a.campaign/'fresh-data'/name,'fresh-data/'+name)
    copy(a.campaign/'prior-data/rehydration.json','prior-metadata-rehydration.json')
    raw = (a.campaign/'fresh-data/dataset.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['dataset_sha256']:
        raise ValueError('fresh_dataset_changed')
    (a.output/'dataset.json.gz').write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
    data = json.loads(raw)
    score_path = a.campaign/'evaluation/scores.npz'
    if sha(score_path) != report['scores_sha256']:
        raise ValueError('raw_score_archive_changed')
    events = {}
    with np.load(score_path,allow_pickle=False) as source_scores:
        for split in ('cal','test'):
            families = [r['family_id'] for r in data['records'] if r['split']==split]
            for method in report['partitions'][split]:
                scores = source_scores[split+'__'+method]
                order = np.argsort(-scores,axis=1,kind='stable')
                rank = (order==np.arange(len(scores))[:,None]).argmax(axis=1)+1
                conf,predicted = confidence(scores)
                absent,_ = confidence(absent_family_scores(scores,families))
                prefix = split+'__'+method+'__'
                events[prefix+'rank'] = rank.astype(np.int32)
                events[prefix+'predicted'] = predicted.astype(np.int32)
                events[prefix+'confidence'] = conf
                events[prefix+'absent_confidence'] = absent
    event_path = a.output/'evaluation/score-events.npz'
    np.savez_compressed(event_path,**events)
    write(a.output/'evaluation/score-events.json',{
        'source_scores_sha256':report['scores_sha256'],'events_sha256':sha(event_path),
        'dataset_sha256':report['dataset_sha256'],'ordering':'dataset.records sorted product_id within each partition',
        'fields':'truth rank, predicted gallery index, present confidence, absent-family confidence',
        'purpose':'recompute reported recall, paired-family uncertainty and combined-family risk from actual score events'})
    retained = []
    for path in (a.campaign/'evaluation/features.npz',score_path):
        retained.append({'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'committed':False})
    write(a.output/'retained-public-caches.json',{'artifacts':retained,'private_data':False,
          'reconstruction':'Pinned encoder and public per-image URLs/hashes in dataset; no new private data required',
          'persistence':'owner Mac task archive; not guaranteed cloud/Library durability'})
    training = json.loads((a.campaign/'training/report.json').read_text())
    summary = {'work_id':'META-LENS-ADAPTER-R3-20261114','execution_source_commit':report['source_commit'],
               'status':'COMPLETED','counts':report['counts'],'family_counts':report['family_counts'],
               'training_candidates':len(training['candidates']),'epochs_per_candidate':12,
               'trainable_parameters':98304,'selected_primary':report['selection'],
               'dev_frozen_recall_at_1':training['epoch0']['dev']['recall_at_1'],
               'dev_primary_recall_at_1':report['selection']['dev']['recall_at_1'],
               'test_methods':report['partitions']['test'],
               'paired_primary_vs_frozen':report['paired_primary_vs_frozen'],
               'product_gate':report['product_gate'],'new_cloud_compute_usd':0.0,
               'llm_or_connector_cost_usd':None,'host':'authorized Mac fallback; CPU training and MPS inference',
               'reuse':'R2 NVIDIA A100 SigLIP2 pixel-feature cache; encoder and input hashes checked',
               'private_data_used':False,'production_activation':False,'hosted_or_signed_qualification':False}
    write(a.output/'execution-summary.json',summary)
    files = [{'path':str(path.relative_to(a.output)),'sha256':sha(path),'bytes':path.stat().st_size}
             for path in sorted(a.output.rglob('*')) if path.is_file()]
    write(a.output/'artifacts.json',{'schema_version':1,'source_commit':report['source_commit'],
                                   'artifacts':files,'production_activation':False})
    print(json.dumps({'status':'EXPORTED','artifacts':len(files),'bytes':sum(f['bytes'] for f in files),
                      'product_gate':report['product_gate'],'new_cloud_compute_usd':0.0}),flush=True)


if __name__ == '__main__':
    main()
