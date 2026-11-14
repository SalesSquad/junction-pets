#!/usr/bin/env python3
"""Rehydrate only public source metadata into a new owned cache, hash checked."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from prepare_holdout import r2, PRIOR_DATASET_SHA256


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = a.dataset.read_bytes()
    if r2.sha256(raw) != PRIOR_DATASET_SHA256:
        raise ValueError('prior_dataset_sha_mismatch')
    manifest = json.loads(raw)
    if a.output.resolve() == a.dataset.parent.resolve():
        raise ValueError('fresh_owned_cache_required')
    a.output.mkdir(parents=True, exist_ok=True)
    target = a.output/'dataset.json'
    if target.exists() and target.read_bytes() != raw:
        raise ValueError('refuse_different_dataset')
    if not target.exists():
        with target.open('xb') as stream:
            stream.write(raw)
    (a.output/'dataset.sha256').write_text(PRIOR_DATASET_SHA256+'\n')
    wanted = {'source/LICENSE-CC-BY-4.0.txt', 'source/images/metadata/images.csv.gz'}
    wanted.update(f'source/listings/metadata/listings_{i:x}.json.gz' for i in range(16))
    sources = [s for s in manifest['sources'] if s['path'] in wanted]
    if len(sources) != 18:
        raise ValueError('missing_pinned_metadata_sources')
    started = time.monotonic()
    download = r2.Downloader(a.output, 600000000, started+900)
    def restore(source):
        key = source['path'].removeprefix('source/')
        data, _ = download.get(key, 64000000)
        if r2.sha256(data) != source['sha256']:
            raise ValueError('public_source_changed:'+key)
        return {'path':source['path'],'sha256':source['sha256'],'bytes':len(data)}
    with ThreadPoolExecutor(max_workers=6) as pool:
        verified = list(pool.map(restore, sources))
    receipt = {'prior_dataset_sha256':PRIOR_DATASET_SHA256,'restored_sources':verified,
               'network_or_cached_bytes':download.total_bytes,'seconds':time.monotonic()-started,
               'private_data_accessed':False,'prior_images_rehydrated':False}
    (a.output/'rehydration.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'stage':'PRIOR_PUBLIC_METADATA_REHYDRATED','sources':len(verified),
                      'bytes':download.total_bytes}),flush=True)


if __name__ == '__main__':
    main()
