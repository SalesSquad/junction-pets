"""Local synthetic experiment primitives. No network, hardware or provider API."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import torch

FEATURES = ['time_sin', 'time_cos', 'temperature_c', 'rh_percent', 'connected', 'age_seconds']
SOURCE = 'eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4'
MAX_ROWS = 48 * 4 * 1440


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')


def load_data(directory):
    directory = Path(directory)
    m = json.loads((directory / 'manifest.json').read_text())
    if m['source_commit'] != SOURCE or m['features'] != FEATURES or not 4 <= m['days_per_scenario'] <= 48:
        raise ValueError('Unsupported source/schema/bounds')
    here = Path(__file__).parent
    for name, expected_hash in m['sources'].items():
        if name not in ['sim/engine.mjs', 'core.mjs'] or sha(here.parent / name) != expected_hash:
            raise ValueError('M3 source hash mismatch')
    if set(m['sources']) != {'sim/engine.mjs', 'core.mjs'} or sha(here / 'export.mjs') != m['exporter_sha256']:
        raise ValueError('Generator/source provenance mismatch')
    if (not isinstance(m['seed'], int) or not 0 <= m['seed'] <= 0xffffffff - 1000 or
        not isinstance(m['days_per_scenario'], int)):
        raise ValueError('Invalid generation bounds')
    expected_plan = []
    for part in ['train', 'validation', 'calibration', 'test']:
        for scenario in (['winter', 'summer', 'evening', 'fault'] if part == 'test' else ['winter', 'summer', 'evening']):
            for i in range(m['days_per_scenario']):
                expected_plan.append(dict(day_id=f'{part}-{scenario}-{i}', partition=part,
                                          scenario=scenario, seed=m['seed'] + len(expected_plan)))
    if m['days'] != expected_plan:
        raise ValueError('Unexpected day plan')
    data, seen = {}, set()
    for part in ['train', 'validation', 'calibration', 'test']:
        path = directory / (part + '.csv')
        if sha(path) != m['files'][part]['sha256']:
            raise ValueError('Dataset SHA mismatch: ' + part)
        if path.stat().st_size > 80_000_000:
            raise ValueError('CSV exceeds bounded byte size')
        with path.open() as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ['day_id', 'partition', 'scenario', 'seed', 'second'] + FEATURES + ['target_occupied']:
                raise ValueError('Unexpected CSV schema')
            rows = list(reader)
        if len(rows) != m['files'][part]['rows'] or not 1 <= len(rows) <= MAX_ROWS:
            raise ValueError('Row count mismatch/bound')
        expected = {d['day_id']: d for d in m['days'] if d['partition'] == part}
        grouped = {}
        for r in rows:
            d = expected.get(r['day_id'])
            if d is None or any(str(r[k]) != str(d[k]) for k in ['partition', 'scenario', 'seed']):
                raise ValueError('Day membership mismatch')
            grouped.setdefault(r['day_id'], []).append(int(r['second']))
        if set(grouped) != set(expected) or any(v != list(range(0, 86400, 60)) for v in grouped.values()):
            raise ValueError('Incomplete or duplicate day')
        seeds = {d['seed'] for d in expected.values()}
        if seen & seeds or len(seeds) != len(expected):
            raise ValueError('Day/seed leakage')
        seen |= seeds
        if part != 'test' and any(d['scenario'] == 'fault' for d in expected.values()):
            raise ValueError('Fault must be held out')
        x = np.array([[float(r[f]) for f in FEATURES] for r in rows], dtype=np.float32)
        y = np.array([float(r['target_occupied']) for r in rows], dtype=np.float32)
        if not np.isfinite(x).all() or not np.isin(y, [0, 1]).all():
            raise ValueError('Nonfinite features or invalid labels')
        data[part] = (x, y, np.array([r['scenario'] for r in rows]))
    return m, data


def model():
    return torch.nn.Sequential(torch.nn.Linear(6, 16), torch.nn.ReLU(),
                               torch.nn.Linear(16, 8), torch.nn.ReLU(), torch.nn.Linear(8, 1))


def probabilities(net, x, device='cpu'):
    with torch.no_grad():
        return torch.cat([net(torch.as_tensor(c, device=device)).flatten().sigmoid().cpu()
                          for c in np.array_split(x, max(1, (len(x) + 8191) // 8192))]).numpy()


def metrics(y, p, threshold=0.5):
    pred = p >= threshold
    tp = int(((y == 1) & pred).sum()); tn = int(((y == 0) & ~pred).sum())
    fp = int(((y == 0) & pred).sum()); fn = int(((y == 1) & ~pred).sum())
    def ratio(a, b):
        return a / b if b else None
    recall, specificity = ratio(tp, tp + fn), ratio(tn, tn + fp)
    return dict(tp=tp, tn=tn, fp=fp, fn=fn, precision=ratio(tp, tp + fp), recall=recall,
                false_negative_rate=ratio(fn, tp + fn), balanced_accuracy=(recall + specificity) / 2
                if recall is not None and specificity is not None else None)
