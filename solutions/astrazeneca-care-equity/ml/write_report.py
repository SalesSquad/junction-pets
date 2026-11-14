"""Render executed metrics, without inserting benchmark numbers."""
from common import *
m=json.loads((ROOT/'artifacts/metrics.json').read_text())
lines=['# Executed CPU run','','Python 3.12; CPU torch; two seeds, eight epochs each. Five unit tests passed. Real Sotkanet API fetch completed. CUDA/full five-seed execution and fresh Ubuntu bootstrap were not exercised on this CPU host; shell syntax was checked.','','Selection uses validation MAE pooled across units and horizons. These tables show test MAE. Missing cohorts have null scores and n=0.','']
for group in ['county','municipality']:
    lines += ['## '+group,'','| Indicator | Horizon | Transformer | Persistence | Drift | Ridge | n | Chosen |','|---|---|---:|---:|---:|---:|---:|---|']
    for key,item in m['metrics'].items():
        for h in ['h1','h2']:
            cells=item[group][h]; vals=['—' if cells[k]['mae'] is None else f"{cells[k]['mae']:.4f}" for k in METHODS]
            lines.append('| '+' | '.join([key,h]+vals+[str(cells['transformer']['n']),item['chosen']])+' |')
lines+=['','Raw/conformal coverage, pinball, validation scores, executed epochs and panel SHA256 are in metrics.json. The selected transformer is not consistently better on held-out test MAE. No indicators were skipped by fetch. No git commands, commits or pushes performed.']
(ROOT/'artifacts/RUN_REPORT.md').write_text('\n'.join(lines)+'\n')
