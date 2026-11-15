#!/usr/bin/env python3
"""Reset-only cross-platform probe for fixed TRAIN range; no option execution."""
import argparse, hashlib, importlib.util, json, math, platform, subprocess, sys
from pathlib import Path
import numpy as np
import mujoco

parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--survey',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--check-mac-reference',action='store_true')
a=parser.parse_args()
if not __debug__:
    raise RuntimeError('V13_PROBE_REQUIRES_ASSERTIONS_ENABLED')
root=Path(a.source).resolve(strict=True)
survey_path=Path(a.survey).resolve(strict=True)
assert np.__version__=='2.3.4' and mujoco.__version__=='3.3.7'
source_head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert source_head in ('c77158f9ae80acc2b1eafaf9284c4397426799b2',
                       'faec266d6d3a44af3a564f46e0778209c1dc3af1')
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain=v1'],text=True).strip()
survey_bytes=survey_path.read_bytes()
assert hashlib.sha256(survey_bytes).hexdigest()=='099d8cc69d0d11bca1e21d0fe2b4c7c397b3f094a352d80ea3fcc52a2fddad29'
survey=json.loads(survey_bytes)
f=root/'solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_prospective/run.py'
s=importlib.util.spec_from_file_location('v13_portable_probe_original',f); m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
m.verify_historical_source(root)
v7,Env=m.v8.import_v7_and_physics();env=Env(max_options=m.v8.MAX_OPTIONS)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def canon(v):
    if isinstance(v,(float,np.floating)):
        assert math.isfinite(float(v));return round(float(v),12)
    return int(v)
all_rows=[];near=[];clear=[];native_hashes=set()
for seed in range(519024,519536):
    obs=env.reset(seed=seed,ood=False);mask=env.mask(obs)
    assert len(obs)==18 and len(mask)==7 and all(math.isfinite(float(v)) for v in obs)
    values={'initial_x':canon(env.data.qpos[0]),'initial_y':canon(env.data.qpos[1]),
            'mass':canon(env.model.body_mass[env.obj]),'friction':canon(env.model.geom_friction[env.og,0]),
            'obstacle_y':canon(env.model.geom_pos[env.bg,1]),'amplitude':canon(env.amplitude),
            'frequency':canon(env.frequency),'phase':canon(env.phase),'drop_start':canon(env.drop_start),
            'drop_len':canon(env.drop_len),'deadman_release':canon(env.release)}
    world_hash=v7.v6.v5.v4.v3.v2.v1._world_signature(env)
    assert world_hash not in native_hashes;native_hashes.add(world_hash)
    row={'seed':seed,'near':bool(abs(float(obs[7]))<.122),'reference_exact_hash':world_hash,
         'portable_scenario_sha256':digest(values),'public_state_sha256':digest({'observation':[float(v) for v in obs],'mask':[int(v) for v in mask]})}
    all_rows.append(row);(near if row['near'] else clear).append(row)
selected=sorted(near[:40]+clear[:8],key=lambda r:r['seed'])
assert len(near)==178 and len(clear)==334 and len(selected)==48
assert [(r['seed'],r['near']) for r in selected]==[(r['seed'],r['near']) for r in survey['selected_first40_near8_clear']]
if a.check_mac_reference:
    assert [(r['seed'],r['reference_exact_hash']) for r in selected]==[(r['seed'],r['world_hash']) for r in survey['selected_first40_near8_clear']]
portable_all=[{'seed':r['seed'],'near':r['near'],'portable_scenario_sha256':r['portable_scenario_sha256'],'public_state_sha256':r['public_state_sha256']} for r in all_rows]
out={'schema':'junction.rokoko.v13.portable-preflight-probe.v1','source_survey_sha256':hashlib.sha256(survey_bytes).hexdigest(),
     'source_head':source_head,
     'round_decimal_places':12,'seed_range':[519024,519535],'count':512,'near':len(near),'clear':len(clear),
     'all_portable_sha256':digest(portable_all),'architecture':platform.machine(),'python':platform.python_version(),
     'selected':selected,'all_portable':portable_all}
path=Path(a.output);assert not path.exists() and not path.resolve().is_relative_to(root)
path.write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print(json.dumps({'architecture':out['architecture'],'python':out['python'],'all_portable_sha256':out['all_portable_sha256'],
                  'selected':len(selected),'near':len(near),'clear':len(clear),'output':str(path)},sort_keys=True))
