#!/usr/bin/env python3
"""Bounded from-scratch MLP training, never on-device qualification."""
import argparse
import copy
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import random
import sys
from pathlib import Path
import numpy as np
import torch
from common import FEATURES, dump, load_data, metrics, model, probabilities, sha


def bounded(lo, hi):
    def parse(s):
        n = int(s)
        if not lo <= n <= hi:
            raise argparse.ArgumentTypeError(f'Expected {lo}..{hi}')
        return n
    return parse


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', required=True); p.add_argument('--out', required=True)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    p.add_argument('--epochs', type=bounded(1, 50), default=30)
    p.add_argument('--batch', type=bounded(64, 8192), default=2048)
    p.add_argument('--seed', type=bounded(0, 2**31 - 1), default=42)
    a = p.parse_args()
    if a.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('--device cuda requires a real available CUDA GPU; no CPU fallback')
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    if a.device == 'cuda':
        torch.cuda.manual_seed_all(a.seed)
        torch.backends.cudnn.benchmark = False
    m, data = load_data(a.data)
    train_x, train_y, _ = data['train']
    mean = train_x.mean(axis=0); std = train_x.std(axis=0); std[std < 1e-6] = 1
    norm = {k: ((x - mean) / std, y, s) for k, (x, y, s) in data.items()}
    net = model().to(a.device)
    opt = torch.optim.Adam(net.parameters(), lr=0.003)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    x = torch.as_tensor(norm['train'][0], device=a.device)
    y = torch.as_tensor(train_y, device=a.device)
    vx = torch.as_tensor(norm['validation'][0], device=a.device)
    vy = torch.as_tensor(norm['validation'][1], device=a.device)
    history, best_state, best_loss, patience, best_epoch = [], None, float('inf'), 0, 0
    for epoch in range(a.epochs):
        net.train(); order = torch.randperm(len(x), device=a.device); total = 0
        for idx in order.split(a.batch):
            opt.zero_grad(set_to_none=True)
            loss = loss_fn(net(x[idx]).flatten(), y[idx]); loss.backward(); opt.step()
            total += loss.item() * len(idx)
        net.eval()
        with torch.no_grad():
            val = loss_fn(net(vx).flatten(), vy).item()
        history.append(dict(epoch=epoch + 1, train_loss=total / len(x), validation_loss=val))
        if val < best_loss - 1e-6:
            best_loss = val; best_state = copy.deepcopy(net.state_dict()); patience = 0; best_epoch = epoch + 1
        else:
            patience += 1
        if patience >= 5:
            break
    net.load_state_dict(best_state); net.eval()
    # Calibration ONLY chooses a conservative low-occupancy gate. Test never tunes it.
    cp = probabilities(net, norm['calibration'][0], a.device); cy = norm['calibration'][1]
    safe = [t for t in [0.01, 0.025, 0.05, 0.1] if ((cp <= t) & (cy == 1)).sum() == 0 and (cp <= t).sum() > 0]
    low = max(safe, default=0.0)
    test_p = probabilities(net, norm['test'][0], a.device); ty = norm['test'][1]; scenarios = norm['test'][2]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    weights = out / 'weights.pt'
    torch.save({k: v.cpu() for k, v in net.state_dict().items()}, weights)
    metadata = dict(schema='green-edge.active.model.v1', evidence='SYNTHETIC/OFFBOARD', source_commit=m['source_commit'],
                    sources=m['sources'], dataset_manifest_sha256=sha(Path(a.data) / 'manifest.json'), dataset_hashes=m['files'],
                    features=FEATURES, normalization=dict(mean=mean.tolist(), std=std.tolist(), fit='train only', dtype='float32'),
                    support=dict(min=train_x.min(axis=0).tolist(), max=train_x.max(axis=0).tolist()),
                    architecture='6 -> 16 ReLU -> 8 ReLU -> 1 logit', parameters=sum(t.numel() for t in net.parameters()),
                    torch_version=str(torch.__version__), python_version=sys.version, device=a.device,
                    cuda_name=torch.cuda.get_device_name(0) if a.device == 'cuda' else None,
                    seed=a.seed, optimizer='Adam lr=0.003', loss='BCEWithLogitsLoss', batch=a.batch,
                    epochs_requested=a.epochs, epochs_executed=len(history), best_epoch=best_epoch,
                    early_stopping='validation loss, patience 5; no heldout selection', history=history,
                    low_probability_threshold=low, calibration_low_count=int((cp <= low).sum()),
                    calibration_false_empty_count=int(((cp <= low) & (cy == 1)).sum()),
                    heldout={s: metrics(ty[scenarios == s], test_p[scenarios == s]) for s in sorted(set(scenarios))},
                    weights_sha256=sha(weights), implementation_hashes={f: sha(Path(__file__).with_name(f)) for f in ['train_gpu.py', 'common.py']},
                    arduino_runnable=False, calibration_is_safety_certificate=False)
    dump(out / 'metadata.json', metadata)
    print(__import__('json').dumps({k: metadata[k] for k in ['device', 'cuda_name', 'torch_version', 'epochs_executed', 'heldout', 'weights_sha256']}, indent=2))


if __name__ == '__main__':
    main()
