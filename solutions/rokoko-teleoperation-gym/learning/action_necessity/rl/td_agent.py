#!/usr/bin/env python3
"""Reward-driven tile-coded Expected SARSA on the synthetic multi-action arena.

No teacher demonstrations or teacher action labels enter optimization. The
learning signals are simulator rewards only. Not MuJoCo, not robotics safety.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arena import (ACTIONS, ABORT, BRAKE, FWD, REOBSERVE, Arena,
                   SEEDS, constant_forward, make_world, run_episode)

TRAIN_START = 122000
FROZEN_TEST_START = 325000   # NEVER use for model selection/development
FROZEN_OOD_START = 425000    # NEVER use for model selection/development
DEVELOPMENT_START = 120000
CALIBRATION_START = 220000
GAMMA = .976
MOVES = tuple(a for a in range(len(ACTIONS)) if a != ABORT)


def bucket(v: float, lo: float, hi: float, n: int, offset: float=0.) -> int:
    p = (min(hi, max(lo, v)) - lo) / (hi-lo) * n + offset
    return max(0, min(n, int(math.floor(p))))


def tile_features(o) -> tuple:
    """Observable state only. Shared safety shield remains in Arena.step."""
    xc = bucket(o.x, -.70, .86, 8)
    gx = bucket(o.goal_y-o.y, -.50, .50, 8)
    vy = bucket(o.vy, -.37, .37, 5)
    vx = bucket(o.vx, -.37, .37, 4)
    yy = bucket(o.y, -.43, .43, 7)
    my = bucket(o.moving_y, -.31, .31, 5)
    near_static = o.static_enabled and abs(o.x-o.static_x) < .27
    centered = o.static_enabled and abs(o.static_y) < .17
    stale = o.quality < .8 or o.age > 7
    goal_late = int(o.x>.32)
    keys = [
        ('bias',), ('x',xc), ('y',yy), ('goal',gx), ('vx',vx), ('vy',vy),
        ('x-goal',xc,gx), ('x-vy',xc,vy), ('goal-vy',gx,vy),
        ('static',int(o.static_enabled),int(centered)),
        ('static-y',bucket(o.static_y,-.40,.40,5)),
        ('x-static',xc,int(near_static),int(centered)),
        ('static-lane',int(near_static),int(centered),yy),
        ('moving',int(o.moving_enabled),my),
        ('moving-y',int(o.moving_enabled),my,yy),
        ('x-moving',xc,int(o.moving_enabled),my),
        ('goallate',goal_late,gx),
        ('age',min(o.age,9)), ('stale',int(stale)),
    ]
    # Second displaced tiling reduces sensitivity to arbitrary bins.
    for off in (.45,):
        x2 = bucket(o.x,-.70,.86,6,off)
        g2 = bucket(o.goal_y-o.y,-.50,.50,6,off)
        y2 = bucket(o.y,-.43,.43,6,off)
        keys += [('tile2-xg',x2,g2),('tile2-xy',x2,y2),
                 ('tile2-ym',y2,bucket(o.moving_y,-.31,.31,4,off))]
    return tuple(keys)


class TDAgent:
    def __init__(self, weights=None):
        self.weights = weights if weights is not None else [dict() for _ in ACTIONS]
        self.last_delta = 0.

    def q(self, fs, action):
        weights = self.weights[action]
        return sum(weights.get(f, 0.) for f in fs)

    def action(self, o, epsilon=0., rng=None):
        # Explicit fail-safe policy, NOT safety qualification for any robot.
        if not o.deadman:
            return ABORT
        if o.quality < .8 or o.age > 7:
            return REOBSERVE
        fs = tile_features(o)
        if rng is not None and rng.random() < epsilon:
            return rng.choice(MOVES)
        return max(MOVES, key=lambda a: (self.q(fs,a),-a))

    def update(self, o, act, reward, following, terminal, alpha, eps):
        fs = tile_features(o)
        before = self.q(fs, act)
        if terminal:
            target = reward
        else:
            nf = tile_features(following)
            choices = [self.q(nf,a) for a in MOVES]
            target = reward + GAMMA * ((1.-eps)*max(choices)+eps*sum(choices)/len(choices))
        delta = max(-40.,min(40.,target-before))
        self.last_delta = delta
        k = alpha / len(fs)
        for f in fs:
            old = self.weights[act].get(f,0.)
            self.weights[act][f] = old + k*delta


def guarded_constant_forward(o):
    """No-learning null with the TD policy's *same* sensor/deadman fallback."""
    if not o.deadman:
        return ABORT
    if o.quality < .8 or o.age > 7:
        return REOBSERVE
    return FWD


def reward(arena, prev, act, pre_refusals, pre_reobserve):
    """Dense potential shaping + terminal success/safety; actual reward only."""
    progress = 6.0*(arena.x-prev[0])
    target = 1.4*(abs(prev[1]-arena.world.goal_y)-abs(arena.y-arena.world.goal_y))
    temporal = -.035
    shield = -.10*(arena.refusals-pre_refusals)
    refresh = -.05*(arena.reobservations-pre_reobserve)
    terminal = (32. if arena.success else -22. if arena.unsafe else
                -10. if arena.aborted else -3. if arena.done else 0.)
    return progress + target + temporal + shield + refresh + terminal


def train(episodes=6000, seed=20261114, alpha=.24, epsilon_start=.36):
    if not 20 <= episodes <= 6000:
        raise ValueError('train episodes must be 20..6000')
    rng = random.Random(seed)
    agent = TDAgent()
    outcomes=[]
    for i in range(episodes):
        world = make_world('dev', TRAIN_START+i)
        arena = Arena(world)
        eps=max(.035,epsilon_start*(1.-i/episodes))
        rate=alpha*(.45+.55*(1.-i/episodes))
        total=0.
        while not arena.done:
            before=arena.observe()
            a=agent.action(before, eps, rng)
            prev=(arena.x,arena.y)
            nref,nobs=arena.refusals,arena.reobservations
            following=arena.step(a)
            r=reward(arena,prev,a,nref,nobs)
            total+=r
            agent.update(before,a,r,following,arena.done,rate,eps)
        outcomes.append((arena.success,arena.unsafe,total))
    summary={'worlds':episodes, 'train_seed_range':[TRAIN_START,TRAIN_START+episodes-1],
             'training_method':'reward-driven tile-coded Expected SARSA with potential shaping',
             'teacher_actions_seen':0, 'world_success':sum(int(x[0]) for x in outcomes),
             'world_unsafe':sum(int(x[1]) for x in outcomes),
             'mean_return':round(sum(x[2] for x in outcomes)/episodes,4),
             'gamma':GAMMA,'alpha_initial':alpha,'epsilon_start':epsilon_start,
             'random_seed':seed,'learned_nonzero_weights':sum(len(w) for w in agent.weights)}
    return agent,summary


def score(agent, split, start, episodes):
    if split not in ('dev','cal','test','ood') or not 1<=episodes<=400:
        raise ValueError('invalid split/episodes')
    if split == 'test' and start != FROZEN_TEST_START:
        raise ValueError('frozen RL test start is preregistered')
    if split == 'ood' and start != FROZEN_OOD_START:
        raise ValueError('frozen RL OOD start is preregistered')
    # Controls share exactly the same Arena.shield. Learned policy includes an
    # explicit sensor/deadman safety fallback; comparison notes this asymmetry.
    learned=[]; constant=[]; guarded=[]
    for n in range(episodes):
        world=make_world(split,start+n)
        learned.append(run_episode(world,'td_reward_agent',lambda: lambda o: agent.action(o)))
        constant.append(run_episode(world,'shielded_constant_forward',lambda:constant_forward))
        guarded.append(run_episode(world,'same_guard_constant_forward',lambda:guarded_constant_forward))
    from run import paired_bootstrap,summarize
    return {'split':split, 'seed_range':[start,start+episodes-1],
            'learned':summarize(learned),'constant':summarize(constant),
            'guarded_constant':summarize(guarded),
            'paired':paired_bootstrap(learned,constant),
            'paired_guarded':paired_bootstrap(learned,guarded),
            'rows':{'learned':learned,'constant':constant,'guarded_constant':guarded}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train-episodes',type=int,default=6000)
    p.add_argument('--eval-split',choices=['dev','cal','test','ood'],default='dev')
    p.add_argument('--eval-episodes',type=int,default=200)
    p.add_argument('--confirm-locked',action='store_true',
                   help='Required before the first independent test/OOD qualification run')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise RuntimeError('refuse overwriting prior evidence')
    if args.eval_split in ('test','ood') and not args.confirm_locked:
        p.error('Locked test/OOD sets may be run only by the independent qualifier')
    starts={'dev':DEVELOPMENT_START,'cal':CALIBRATION_START,
            'test':FROZEN_TEST_START,'ood':FROZEN_OOD_START}
    agent,train_receipt=train(args.train_episodes)
    evals=score(agent,args.eval_split,starts[args.eval_split],args.eval_episodes)
    canonical_weights = [[(repr(key), round(value, 12)) for key, value in
                          sorted(table.items(), key=lambda pair: repr(pair[0]))]
                         for table in agent.weights]
    weight_digest=hashlib.sha256(json.dumps(canonical_weights,separators=(',',':')).encode()).hexdigest()
    local=Path(__file__).resolve().parent
    primary=evals['paired']
    matched_guard=evals['paired_guarded']
    comparison={'predeclared_delta_pp':15,
                'learned_vs_null_delta_at_least_15pp':primary['delta_pp']>=15,
                'learned_vs_null_lower_paired_95_above_zero':primary['paired_bootstrap_95_pp'][0]>0,
                'learned_vs_same_guard_delta_at_least_15pp':matched_guard['delta_pp']>=15,
                'unsafe_learned_no_higher_than_null':evals['learned']['unsafe']<=evals['constant']['unsafe'],
                'unsafe_learned_no_higher_than_same_guard':evals['learned']['unsafe']<=evals['guarded_constant']['unsafe']}
    receipt={'schema':'junction.rokoko.reward-driven-td.v1',
             'environment':'SYNTHETIC_2D_KINEMATICS_NOT_MUJOCO',
             'method':'actual simulator return optimization, no teacher actions or imitation labels',
             'train':train_receipt,'test':evals,'comparison':comparison,
             'weights_sha256':weight_digest,'model_weights':canonical_weights,
             'producer_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                               for f in local.glob('*.py')},
             'limitations':['No MuJoCo or physical robot qualification.',
                            'Scripted fallback for deadman/stale observations is not learned.',
                            'Training and policy may overfit dev/cal; locked test/OOD are independent.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'train':train_receipt,'test':{k:v for k,v in evals.items() if k!='rows'},
                      'comparison':comparison,'weights_sha256':weight_digest},sort_keys=True))


if __name__=='__main__':
    main()
