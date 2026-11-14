"""Bounded original option Double-DQN; CPU MuJoCo rollouts, torch optimizer device explicit."""
import argparse
import csv
import hashlib
import json
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import torch
from torch import nn
from env import ContactEnv, OBS_SIZE, SCENE, heuristic


class Q(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(OBS_SIZE, 64), nn.ReLU(), nn.Linear(64, 64),
                                 nn.ReLU(), nn.Linear(64, 7))

    def forward(self, x):
        return self.net(x)


def weights_hash(net):
    return hashlib.sha256(b''.join(p.detach().cpu().numpy().tobytes() for p in net.parameters())).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    for name, default in [('train',1000), ('cal',100), ('test',200), ('ood',100)]:
        ap.add_argument(f'--{name}-episodes', type=int, default=default)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--seed', type=int, default=7, help='learner initialization/exploration seed, not world ID')
    ap.add_argument('--device', choices=['cpu','cuda'], default='cuda')
    ap.add_argument('--max-seconds', type=float, default=3600)
    ap.add_argument('--max-options', type=int, default=60)
    ap.add_argument('--only-smoke', action='store_true')
    args = ap.parse_args()
    counts = [args.train_episodes,args.cal_episodes,args.test_episodes,args.ood_episodes]
    if any(n < 0 or n > 10000 for n in counts) or not 1 <= args.max_options <= 300 or not 0 < args.max_seconds <= 86400:
        ap.error('episode limits 0..10000, options 1..300, seconds (0,86400]')
    if args.only_smoke:
        args.train_episodes,args.cal_episodes,args.test_episodes,args.ood_episodes = 2,1,1,1
        args.max_options = min(args.max_options, 3)
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable; no silent CPU fallback')
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        raise RuntimeError('output must be empty to preserve prior receipts')
    start = time.monotonic()
    deadline = start+args.max_seconds
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    online, target = Q().to(device), Q().to(device)
    target.load_state_dict(online.state_dict())
    optimizer = torch.optim.Adam(online.parameters(), lr=3e-4)
    initial_hash = weights_hash(online)
    replay = []
    cursor = updates = transitions = 0
    env = ContactEnv(args.max_options)
    rows = []
    timed_out = False
    config = dict(batch_size=64, gamma=.98, learning_rate=3e-4, target_sync=100,
                  capacity=50000, update_every=4, epsilon_start=1., epsilon_end=.08,
                  shield='independent conservative mask; no learned override', **vars(args))
    config['out'] = str(args.out)
    # Written before any rollout, including heldout rollouts. Calibration is reporting only.
    (args.out/'frozen-config.json').write_text(json.dumps(config, indent=2))
    source_files = sorted(Path(__file__).parent.glob('*.py'))+[SCENE]
    sources = {str(p.relative_to(SCENE.parents[1])): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=SCENE.parent, text=True).strip()
    dirty = subprocess.check_output(['git','status','--porcelain','--',str(Path(__file__).parent),str(SCENE)], text=True).strip()
    log = (args.out/'episodes.jsonl').open('w')

    def episode(split, seed, method, training=False):
        nonlocal cursor, updates, transitions, timed_out
        obs = env.reset(seed, ood=split=='ood')
        total = 0.
        done = False
        info = {}
        while not done:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            mask = env.mask(obs)
            epsilon = max(.08, 1.-.92*len(rows)/max(args.train_episodes*.8, 1)) if training else 0.
            if method == 'abstain':
                action = 6
            elif method == 'heuristic':
                action = heuristic(obs, mask)
            elif random.random() < epsilon:
                action = int(random.choice(np.flatnonzero(mask)))
            else:
                with torch.no_grad():
                    q = online(torch.as_tensor(obs, device=device))
                    action = int(q.masked_fill(~torch.as_tensor(mask,device=device), -torch.inf).argmax())
            nxt, reward, done, info = env.step(action)
            total += reward
            if training:
                item = (obs.copy(), action, reward, nxt.copy(), float(done), env.mask(nxt))
                if len(replay) < 50000:
                    replay.append(item)
                else:
                    replay[cursor] = item
                cursor = (cursor+1)%50000
                transitions += 1
                if len(replay) >= 64 and transitions%4 == 0:
                    batch = random.sample(replay, 64)
                    s,a,r,ns,d,ms = [torch.as_tensor(np.asarray(x),device=device) for x in zip(*batch)]
                    with torch.no_grad():
                        best = online(ns).masked_fill(~ms, -torch.inf).argmax(1)
                        y = r.float()+.98*(1-d.float())*target(ns).gather(1,best[:,None]).squeeze(1)
                    loss = nn.functional.smooth_l1_loss(online(s).gather(1,a.long()[:,None]).squeeze(1),y)
                    optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(online.parameters(), 10.)
                    optimizer.step()
                    updates += 1
                    if updates%100 == 0:
                        target.load_state_dict(online.state_dict())
            obs = nxt
        row = dict(split=split, seed=seed, method=method, complete=bool(done),
                   return_value=total, options=env.steps, **info)
        rows.append(row)
        log.write(json.dumps(row)+'\n')
        log.flush()

    for i in range(args.train_episodes):
        episode('train',120000+i,'dqn',True)
        if timed_out:
            break
    if device.type == 'cuda':
        torch.cuda.synchronize()
    train_wall = time.monotonic()-start
    final_hash = weights_hash(online)
    torch.save(online.state_dict(),args.out/'weights.pt')
    # No optimizer or hyperparameter changes after this point; paired fresh worlds.
    for split,base,n in [('cal',220000,args.cal_episodes),('test',320000,args.test_episodes),('ood',420000,args.ood_episodes)]:
        if timed_out:
            break
        for i in range(n):
            for method in ('dqn','heuristic','abstain'):
                episode(split,base+i,method)
                if timed_out:
                    break
            if timed_out:
                break
    log.close()
    with (args.out/'episodes.csv').open('w') as f:
        writer = csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rows))))
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for split in ('train','cal','test','ood'):
        for method in ('dqn','heuristic','abstain'):
            subset = [r for r in rows if r['split']==split and r['method']==method and r['complete']]
            summary[f'{split}/{method}'] = dict(episodes=len(subset),success=sum(r.get('success',False) for r in subset),unsafe=sum(r.get('unsafe',False) for r in subset))
    test = summary['test/dqn']
    useful = (not timed_out and not args.only_smoke and updates > 0 and initial_hash != final_hash
              and test['episodes'] == args.test_episodes and args.test_episodes > 0
              and test['unsafe'] == 0 and test['success'] > summary['test/heuristic']['success']
              and test['success'] > summary['test/abstain']['success'])
    receipt = dict(source_commit=commit, source_dirty=dirty, producing_sha256=sources,
                   completed_at=datetime.now(timezone.utc).isoformat(),
                   input_sha256=hashlib.sha256((args.out/'frozen-config.json').read_bytes()).hexdigest(),
                   torch_version=torch.__version__, mujoco_version=__import__('mujoco').__version__,
                   device=str(device),cuda_device=torch.cuda.get_device_name(0) if device.type=='cuda' else None,
                   gradient_steps=updates,train_transitions=transitions,train_episodes=summary['train/dqn']['episodes'],
                   physics_steps=sum(r.get('physics_steps',0) for r in rows),train_wall_seconds=train_wall,
                   wall_seconds=time.monotonic()-start,initial_parameter_sha256=initial_hash,
                   final_parameter_sha256=final_hash,weights_sha256=hashlib.sha256((args.out/'weights.pt').read_bytes()).hexdigest(),
                   timed_out=timed_out,summary=summary, quality_claim='PASSED_PAIRED_TEST_USEFULNESS' if useful else 'FAILED_OR_UNQUALIFIED',
                   limits='Synthetic research only. No hardware, safety certification, Isaac or live glove integration. One learner seed; heldout sample evidence only.')
    (args.out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
