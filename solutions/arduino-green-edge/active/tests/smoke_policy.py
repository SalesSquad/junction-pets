#!/usr/bin/env python3
"""Optional NumPy-only arithmetic/shield smoke; NO trained model or CUDA.

Isolate evaluator functions using AST so absent Torch does not get replaced by
fake installed modules. Substitute explicit fixed zero occupancy probabilities
solely to exercise conservative gating/accounting. Not a model-performance test.
"""
import ast
import json
from pathlib import Path
import subprocess
import sys
import numpy as np


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python smoke_policy.py DATA_DIRECTORY')
    active = Path(__file__).resolve().parents[1]
    path = active / 'eval_policy.py'
    tree = ast.parse(path.read_text())
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ['camera_call', 'shield', 'evaluate_day']:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'STRATEGIES' for t in node.targets):
            body.append(node)
    ns = dict(np=np, probabilities=lambda net, x: np.zeros(len(x), dtype=np.float32))
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), ns)
    shield, camera = ns['shield'], ns['camera_call']
    base = dict(fan=True, light=True); cheap = [0, 1, 24, 60, 1, 0]
    row = dict(second=36000, cheap=cheap, sample=dict(connected=True, occupancy=3))
    assert not camera(row, 'nominal')['empty']
    assert camera(row, 'correlated_false_empty')['empty']
    assert not camera(row, 'untrusted_camera')['valid']
    c = dict(empty=True, valid=True, second=36000)
    assert shield(base, cheap, c, 36000, True) == dict(fan=False, light=True)
    for features in [[0, 1, 26, 60, 1, 0], [0, 1, 24, 68, 1, 0], [0, 1, 24, 60, 0, 0], [0, 1, 24, 60, 1, 40]]:
        assert shield(base, features, c, 36000, True) == base
    assert shield(base, cheap, c, 36060, True) == base
    assert shield(base, cheap, c, 36000, False) == base
    assert shield(base, cheap, None, 36000, True) == base
    meta = dict(normalization=dict(mean=[0]*6, std=[1]*6),
                support=dict(min=[-1, -1, 0, 0, 0, 0], max=[1, 1, 50, 100, 1, 100]), low_probability_threshold=0.1)
    costs = dict(query_wh=0.01, board_w=4, always_camera_w=1, cheap_inference_wh=0.000001)
    manifest_path = Path(sys.argv[1]) / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    proc = subprocess.Popen(['node', str(active / 'export.mjs'), '--evaluation=' + str(manifest_path)],
                            stdout=subprocess.PIPE, text=True)
    records = 0
    try:
        for line in proc.stdout:
            packet = json.loads(line)
            result = ns['evaluate_day'](packet, None, meta, costs)
            records += len(result)
            a, b, c, d, e = result
            assert abs(a['net_wh']) < 1e-9 and a['extra_missed_fan_seconds'] == 0
            assert b['queries_per_day'] == 1440 and c['queries_per_day'] == e['queries_per_day'] == 144
            assert abs(b['camera_assumed_wh'] - 38.4) < 1e-8
            assert abs(c['camera_assumed_wh'] - 1.44) < 1e-8
            for r in result[1:]:
                assert r['board_assumed_wh'] == 96
                assert abs(r['net_wh'] - (r['gross_wh'] - 96 - r['camera_assumed_wh'] - r['cheap_inference_assumed_wh'])) < 1e-8
                if packet['variant'] != 'nominal':
                    assert not r['candidate']
            assert d['cheap_inferences'] == 1440
        assert proc.wait() == 0
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.terminate(); proc.wait()
    assert records == manifest['days_per_scenario'] * 4 * 4 * 5
    print(f'PASS: shield/camera and {records} paired accounting records; fixed zero probabilities, NO trained model/CUDA.')


if __name__ == '__main__':
    main()
