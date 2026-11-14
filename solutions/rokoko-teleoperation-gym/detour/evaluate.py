"""Paired CPU native physics evaluation; no training or provider calls."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time
import mujoco
import numpy as np
from env import DetourEnv, frozen
from planner import heuristic, routes

DEV_SEEDS = tuple(range(150000, 150100))
HOLDOUT_SEEDS = tuple(range(450500, 450600))


def run(seed, method, max_options=60):
    env = DetourEnv(max_options) if method == 'detour' else frozen.ContactEnv(max_options)
    obs = env.reset(seed, ood=True)
    coverage = len(routes(obs))
    initial_mask = env.mask().tolist()
    info = {}
    collision = damage = workspace = False
    while not env.done:
        allowed = env.mask()
        action = (6 if method == 'abstain' else
                  heuristic(obs, allowed, env._next_waypoint(obs)) if method == 'detour' else frozen.heuristic(obs, allowed))
        obs, _, _, info = env.step(action)
        # Outcome-only telemetry; never passed to planner/controller.
        collision |= any(env.bg in {env.data.contact[k].geom1, env.data.contact[k].geom2}
                         and bool({env.og, env.pg} & {env.data.contact[k].geom1, env.data.contact[k].geom2})
                         for k in range(env.data.ncon))
        damage |= env.peak > .006
        workspace |= any(not (-.2 <= env.data.xpos[b, 0] <= .3 and
                             abs(env.data.xpos[b, 1]) <= .2 and 0 <= env.data.xpos[b, 2] <= .06)
                         for b in (env.obj, env.push))
    return dict(seed=seed, method=method, **info, collision=collision,
                damage=damage, workspace=workspace, human_requests=int(env.abstained or env.held),
                initial_candidate_count=coverage, initial_mask=initial_mask)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', choices=['dev', 'holdout'], default='dev')
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error('count must be 1..100')
    args.out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[3]
    files = sorted(Path(__file__).parent.glob('*.py')) + [Path(frozen.__file__), frozen.SCENE]
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True)
    seeds = (DEV_SEEDS if args.cohort == 'dev' else HOLDOUT_SEEDS)[:args.count]
    rows = [run(seed, method) for seed in seeds for method in ('original', 'detour', 'abstain')]
    summary = {method: {key: sum(bool(r[key]) for r in rows if r['method'] == method)
                       for key in ('success', 'unsafe', 'abstained', 'collision', 'damage', 'workspace', 'human_requests')}
               for method in ('original', 'detour', 'abstain')}
    receipt = dict(source_sha=head, dirty_state=dirty, producing_sha256=hashes,
                   imported_source_sha=subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
                   str(Path(frozen.__file__).relative_to(root)), str(frozen.SCENE.relative_to(root))], cwd=root, text=True).strip(),
                   scene_version='original sim/scene.xml (sha256 above)', mujoco=mujoco.__version__,
                   numpy=np.__version__, time_unix=time.time(), cohort=args.cohort,
                   seeds=list(seeds), max_options=60, ood=True, summary=summary,
                   truth='Native synthetic physics; shield + controller intervention, NOT RL or device qualification',
                   limits='3 sigma map bound is probabilistic, not guaranteed. HOLD retains force. No holdout tuning.', rows=rows)
    (args.out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    with (args.out/'episodes.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
