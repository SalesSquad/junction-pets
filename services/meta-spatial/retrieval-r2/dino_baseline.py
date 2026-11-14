#!/usr/bin/env python3
"""Pinned Meta DINOv2 alternate-photo baseline, on the same sealed ABO splits.

This is actual frozen image inference, not DINO fine-tuning or glasses evidence.
The choice was fixed before inspecting the new campaign's test/OOD outcomes.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time

import numpy as np

from retrieval import (calibrate_threshold, file_sha256, normalize,
                       policy_metrics, retrieval_metrics, validate_dataset,
                       write_json)
from train_retrieval import verify_images

MODEL = 'facebook/dinov2-small'
REVISION = 'ed25f3a31f01632728cabb09d1542f84ab7b0056'
WEIGHT_SHA = 'ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--cache', required=True, type=Path)
    p.add_argument('--batch-size', type=int, default=64)
    p.add_argument('--max-seconds', type=int, default=1800)
    a = p.parse_args()
    if not 1 <= a.batch_size <= 128 or not 60 <= a.max_seconds <= 3600:
        p.error('bounded batch and runtime required')
    if a.output.exists() and any(a.output.iterdir()):
        p.error('preserve existing result; choose fresh output')
    a.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    digest = file_sha256(a.data / 'dataset.json')
    if (a.data / 'dataset.sha256').read_text().strip() != digest:
        raise ValueError('dataset_seal_mismatch')
    manifest = json.loads((a.data / 'dataset.json').read_text())
    integrity = validate_dataset(manifest)
    records = manifest['records']
    checked = verify_images(a.data, records)
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import torch
    from PIL import Image
    from huggingface_hub import snapshot_download
    from transformers import AutoImageProcessor, AutoModel
    if not torch.cuda.is_available():
        raise RuntimeError('cuda_required_for_this_campaign')
    model_path = Path(snapshot_download(MODEL, revision=REVISION, token=False,
                                       cache_dir=str(a.cache), allow_patterns=[
                                           'config.json', 'preprocessor_config.json',
                                           'model.safetensors', 'README.md']))
    if file_sha256(model_path / 'model.safetensors') != WEIGHT_SHA:
        raise ValueError('model_weight_hash_mismatch')
    model = AutoModel.from_pretrained(str(model_path), local_files_only=True,
                                     trust_remote_code=False, torch_dtype=torch.float16,
                                     attn_implementation='eager').to('cuda:0').eval()
    model.requires_grad_(False)
    processor = AutoImageProcessor.from_pretrained(str(model_path), local_files_only=True,
                                                  trust_remote_code=False, use_fast=False)
    torch.cuda.reset_peak_memory_stats()
    arrays = {}
    for index, label in enumerate(('gallery', 'query')):
        parts = []
        for offset in range(0, len(records), a.batch_size):
            if time.monotonic() - start > a.max_seconds:
                raise RuntimeError('dino_deadline_exceeded')
            images = []
            for record in records[offset:offset + a.batch_size]:
                with Image.open(a.data / record['views'][index]['path']) as im:
                    images.append(im.convert('RGB'))
            inputs = processor(images=images, return_tensors='pt')
            inputs = {k: v.to(device='cuda:0', dtype=torch.float16) for k, v in inputs.items()}
            with torch.inference_mode():
                # Official HF DINOv2 pooler is the final CLS representation.
                output = model(**inputs).pooler_output
            parts.append(output.float().cpu().numpy())
            for im in images:
                im.close()
            if offset % (10 * a.batch_size) == 0:
                print(json.dumps({'stage': 'dino_encode', 'view': label,
                                  'done': min(offset + a.batch_size, len(records)),
                                  'total': len(records)}), flush=True)
        arrays[label] = normalize(np.concatenate(parts))
    torch.cuda.synchronize()
    encoding_seconds = time.monotonic() - start
    np.savez_compressed(a.output / 'features.npz', **arrays)
    scores = {}
    families = {}
    for split in ('cal', 'test', 'ood'):
        ids = np.asarray([i for i, r in enumerate(records) if r['split'] == split])
        families[split] = [records[i]['family_id'] for i in ids]
        scores[split] = arrays['query'][ids] @ arrays['gallery'][ids].T
    policy = calibrate_threshold(scores['cal'], families['cal'], 0.01)
    partitions = {s: {'retrieval': retrieval_metrics(scores[s], families[s]),
                      'refusal': policy_metrics(scores[s], families[s], policy)}
                  for s in ('cal', 'test', 'ood')}
    report = {
        'schema_version': 1, 'work_id': 'META-LENS-TRAIN-20261114-R2',
        'status': 'COMPLETED', 'kind': 'ACTUAL_FROZEN_META_DINOV2_BASELINE',
        'model_id': MODEL, 'model_revision': REVISION, 'model_weight_sha256': WEIGHT_SHA,
        'model_license': 'Apache-2.0', 'encoder_frozen': True,
        'dataset_sha256': digest, 'data_integrity': integrity, 'image_bytes_verified': checked,
        'source_hashes': {x.name: file_sha256(x) for x in
                          (Path(__file__), Path(__file__).with_name('retrieval.py'),
                           Path(__file__).with_name('train_retrieval.py'))},
        'preprocessing_sha256': file_sha256(model_path / 'preprocessor_config.json'),
        'feature_sha256': file_sha256(a.output / 'features.npz'),
        'product_order': [r['product_id'] for r in records],
        'runtime': {'python': platform.python_version(), 'torch': torch.__version__,
                    'transformers': importlib.metadata.version('transformers'),
                    'cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(),
                    'dtype': 'float16', 'pooling': 'final_CLS', 'dimension': 384},
        'encoder_seconds': encoding_seconds, 'wall_seconds': time.monotonic() - start,
        'peak_torch_gpu_bytes': torch.cuda.max_memory_allocated(),
        'policy': policy, 'partitions': partitions,
        'deployment_authorized': False, 'identity_verified': False, 'action_authorized': False,
        'limitations': ['Catalog photographs, not live glasses.',
                       'Pretraining overlap with public ABO is unknown for all foundation encoders.',
                       'Our heldouts concern this campaign; they do not prove foundation-model decontamination.',
                       'No DINO weights or test-dependent configuration was trained.',
                       'A catalog candidate never proves physical object identity.']}
    write_json(a.output / 'report.json', report)
    print(json.dumps({'stage': 'DINO_COMPLETED', 'report': str(a.output / 'report.json')}), flush=True)


if __name__ == '__main__':
    main()
