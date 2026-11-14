#!/usr/bin/env python3
"""Original CPU contact experiment; no hardware/network/model dispatch exists."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = '84dceb0347771590035a7f973a264cb2a4540c7f'
DT = 0.002
GOAL = (0.16, 0.0)
IMPULSE_LIMIT = 0.006  # N s per physics step; toy fragility proxy, not material calibration
CHOICES = ('CONTINUE', 'REPLAN', 'REOBSERVE', 'REQUEST_HUMAN', 'HALT')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def demo():
    # Reuse the actual M2 retargeter, including its validation and provenance.
    script = """import {readFileSync as r} from 'node:fs';
import {retargetCsv} from './src/retarget.mjs';
console.log(JSON.stringify(retargetCsv(r('fixtures/synthetic-retarget.csv','utf8'),r('fixtures/retarget-map.json','utf8'))));"""
    return json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script], cwd=ROOT))


class Hold:
    def __init__(self):
        self.held = False
        self.healthy = 0

    def update(self, deadman, age, quality, inside, ack):
        if not deadman or age > 0.12 or quality < 0.8 or not inside:
            self.held, self.healthy = True, 0
        elif self.held:
            self.healthy += 1
            if self.healthy >= 2 and ack:
                self.held = False
        return self.held


def decision(obs, budget):
    # Allowlisted observed features only. Never receives simulator data or scenario seed.
    if not obs['deadman'] or not obs['inside']:
        return 'HALT'
    if obs['age'] > 0.12 or obs['quality'] < 0.8:
        return 'REOBSERVE'
    if obs['obstacle_distance'] < 0.045:
        return 'REQUEST_HUMAN' if budget else 'HALT'
    if abs(obs['object'][1]) > 0.012:
        return 'REPLAN'
    return 'CONTINUE'


def scenario(seed, shifted):
    r = random.Random(seed)
    return dict(x=r.uniform(-0.012, 0.012), y=r.uniform(-0.045 if shifted else -0.01, 0.045 if shifted else 0.01),
                friction=r.uniform(0.15, 0.8 if shifted else 0.45), mass=r.uniform(0.05, 0.12),
                obstacle_y=r.choice([0.0, -0.065, 0.065, 0.15]) if shifted else 0.15,
                stale_start=r.randint(45, 110), stale_length=r.choice([0, 8, 20]) if shifted else 0,
                deadman_step=140 if shifted and seed % 7 == 0 else -1)


def run(seed, policy, shifted, progress, force_deadman=False):
    import mujoco as mj
    import numpy as np
    s = scenario(seed, shifted)
    m = mj.MjModel.from_xml_path(str(HERE / 'scene.xml'))
    d = mj.MjData(m)
    oid = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, 'object')
    og = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, 'object_geom')
    pg = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, 'pusher_geom')
    bg = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, 'obstacle')
    m.geom_pos[bg, 1] = s['obstacle_y']
    m.geom_friction[og, 0] = s['friction']
    m.body_mass[oid] = s['mass']
    # Scale inertia with mass, then refresh model constants before state initialization.
    m.body_inertia[oid] *= s['mass'] / 0.08
    mj.mj_setConst(m, d)
    d.qpos[0:2] = [s['x'], s['y']]
    mj.mj_forward(m, d)
    hold = Hold()
    target = [-0.06, 0.0]
    last_seen = [s['x'], s['y']]
    seen_at = 0.0
    counts = {k: 0 for k in CHOICES}
    contacts = obstacle_contacts = held_steps = unsafe_commands = 0
    workspace_violation = False
    max_impulse = 0.0
    budget, requests = 2, 0
    broken = False
    force = np.zeros(6)
    # 300 sensor/controller ticks, 10 actual physics steps per tick (6 seconds).
    for tick in range(300):
        t = tick * 0.02
        occluded = s['stale_start'] <= tick < s['stale_start'] + s['stale_length']
        if not occluded:
            # Sensor boundary: quantized vision, not true velocities/contact/reward.
            last_seen = [round(float(v), 3) for v in d.xpos[oid, :2]]
            seen_at = t
        deadman = not (force_deadman or tick >= s['deadman_step'] >= 0)
        obs = dict(object=last_seen[:], age=t-seen_at, quality=0.6 if occluded else 0.99,
                   deadman=deadman, inside=all(-0.19 <= v <= 0.29 for v in target),
                   obstacle_distance=math.dist(last_seen, [0.09, s['obstacle_y']]))
        choice = decision(obs, budget)
        counts[choice] += 1
        if choice == 'REQUEST_HUMAN':
            budget -= 1
            requests += 1  # No simulated oracle takeover: request then abstain.
        held = hold.update(deadman, obs['age'], obs['quality'], obs['inside'], not occluded)
        if held or choice in ('HALT', 'REQUEST_HUMAN'):
            held_steps += 1
            # Freeze requested joint target, not object physics; no teleport or qvel reset.
        else:
            if policy == 'open_loop':
                u = min(t / 3.3, 1.0) * (len(progress)-1)
                i = min(int(u), len(progress)-2)
                f = u-i
                p = progress[i]*(1-f) + progress[i+1]*f
                desired = [-0.06 + 0.235*p, 0.0]
            else:
                obj = obs['object']
                v = [GOAL[0]-obj[0], GOAL[1]-obj[1]]
                norm = max(math.hypot(*v), 1e-9)
                # Align behind observed puck before slow push; a hand-coded controller, not RL.
                behind = [obj[j]-0.025*v[j]/norm for j in range(2)]
                desired = behind
                if norm < 0.012:
                    desired = target[:]
            delta = [desired[j]-target[j] for j in range(2)]
            length = max(math.hypot(*delta), 1e-12)
            candidate = [target[j]+delta[j]*min(1.0, 0.0016/length) for j in range(2)]
            if all(-0.19 <= v <= 0.29 for v in candidate):
                target = candidate
            else:
                hold.update(True, 0, 1, False, False)
            if not deadman:
                unsafe_commands += 1
        d.ctrl[:] = [target[0]+0.06, target[1]]
        for _ in range(10):
            mj.mj_step(m, d)
            workspace_violation |= not (-0.2 <= d.xpos[oid, 0] <= 0.3 and -0.2 <= d.xpos[oid, 1] <= 0.2 and 0 <= d.xpos[oid, 2] <= 0.06)
            for c in range(d.ncon):
                pair = {d.contact[c].geom1, d.contact[c].geom2}
                if og in pair and (pg in pair or bg in pair):
                    mj.mj_contactForce(m, d, c, force)
                    impulse = float(np.linalg.norm(force[:3])) * DT
                    max_impulse = max(max_impulse, impulse)
                    broken |= impulse > IMPULSE_LIMIT
                    contacts += int(pg in pair and impulse > 1e-8)
                    obstacle_contacts += int(bg in pair and impulse > 1e-8)
    # Evaluator alone reads hidden ground truth, including contact and breakage.
    error = math.dist(d.xpos[oid, :2], GOAL)
    claimed = math.dist(last_seen, GOAL) < 0.02
    success = score(error, broken, contacts, obstacle_contacts, workspace_violation)
    return dict(seed=seed, policy=policy, scenario=s, success=success, error_m=error,
                sensor_claim=claimed, false_success=claimed and not success, broken=bool(broken),
                workspace_violation=bool(workspace_violation),
                max_step_impulse_ns=max_impulse, pusher_object_contact_steps=contacts,
                obstacle_contact_steps=obstacle_contacts, held_ticks=held_steps,
                unsafe_deadman_commands=unsafe_commands, human_requests=requests, human_takeovers=0,
                remaining_human_budget=budget, decisions=counts, final_object_xyz=d.xpos[oid].tolist())


def score(error, broken, contacts, obstacle_contacts, workspace_violation):
    return error < 0.02 and not broken and contacts > 0 and obstacle_contacts == 0 and not workspace_violation


def summarize(rows):
    return {p: dict(trials=len(rs), successes=sum(r['success'] for r in rs),
                    false_successes=sum(r['false_success'] for r in rs), broken=sum(r['broken'] for r in rs),
                    contact_trials=sum(r['pusher_object_contact_steps'] > 0 for r in rs),
                    mean_error_m=sum(r['error_m'] for r in rs)/len(rs),
                    human_requests=sum(r['human_requests'] for r in rs),
                    unsafe_deadman_commands=sum(r['unsafe_deadman_commands'] for r in rs))
            for p in ('open_loop', 'object_centered') if (rs := [r for r in rows if r['policy'] == p])}


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--seed', type=int, default=104)
    a.add_argument('--trials', type=int, default=30)
    a.add_argument('--output', type=Path)
    args = a.parse_args()
    if not 1 <= args.trials <= 50 or not 0 <= args.seed <= 1000000:
        a.error('bounded trials 1..50 and seed 0..1000000 required')
    import mujoco
    source = demo()
    steps = source['episode']['steps']
    path = [math.dist([steps[0]['hand'][k] for k in ('x','y')], [s['hand'][k] for k in ('x','y')]) for s in steps]
    progress = [p/path[-1] for p in path]
    train_seeds = list(range(args.seed, args.seed+6))
    holdout_seeds = list(range(args.seed+40000, args.seed+40000+args.trials))
    train = [run(s, p, False, progress) for s in train_seeds for p in ('open_loop','object_centered')]
    holdout = [run(s, p, True, progress) for s in holdout_seeds for p in ('open_loop','object_centered')]
    negative = run(args.seed, 'object_centered', False, progress, force_deadman=True)
    assert negative['pusher_object_contact_steps'] == 0 and negative['unsafe_deadman_commands'] == 0
    assert any(r['pusher_object_contact_steps'] > 0 for r in train), 'No real contact evidence'
    import platform
    from datetime import datetime, timezone
    result = dict(executed_at_utc=datetime.now(timezone.utc).isoformat(), executor=platform.platform(),
                  python_version=platform.python_version(), schema='motionbridge.counterfactual.v1', source_kind='SYNTHETIC_MUJOCO',
                  input_source_kind='UNVERIFIED_REPLAY', actuation_authorized=False, model_decisions='OFFLINE_STUB',
                  source_base_sha=BASE, source_head_at_execution=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  mujoco_version=mujoco.__version__, source_hashes={str(p.relative_to(ROOT)):sha(p) for p in
                  [HERE/'experiment.py', HERE/'scene.xml', HERE/'physics_smoke.py', ROOT/'cli.mjs', ROOT/'src/csv.mjs', HERE/'decisions.py', HERE/'decision-fixtures.json', HERE/'test_sim.py', ROOT/'src/engine.mjs', ROOT/'src/retarget.mjs',
                   ROOT/'fixtures/synthetic-retarget.csv', ROOT/'fixtures/retarget-map.json']},
                  demo_provenance=source['provenance'], demo_progress=progress,
                  work_id='J26-ROKOKO-FORGE-M3-20261114', working_source_binding='source_base_sha plus SHA256 of executed working files; uncommitted at execution',
                  training='NONE: train split is calibration/development evaluation; no fitted or RL policy',
                  train_seeds=train_seeds, holdout_seeds=holdout_seeds, fragility_step_impulse_ns=IMPULSE_LIMIT,
                  train_summary=summarize(train), holdout_summary=summarize(holdout),
                  negative_deadman=negative, train=train, holdout=holdout, costs='unknown; no paid provider/model calls')
    text = json.dumps(result, indent=2, allow_nan=False)+'\n'
    if args.output:
        if args.output.resolve().parent != HERE or args.output.suffix != '.json':
            a.error('receipt output must be directly inside sim/')
        args.output.write_text(text)
    print(json.dumps(dict(train=result['train_summary'], holdout=result['holdout_summary'], negative='PASS'), indent=2))


if __name__ == '__main__':
    main()
