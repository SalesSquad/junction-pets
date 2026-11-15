#!/usr/bin/env python3
"""Real MuJoCo CPU physics campaign; all robot/glove observations are SYNTHETIC."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
SIM = PRODUCT / "sim"
sys.path.insert(0, str(SIM))
from experiment import demo, normalize_demo_progress, Hold  # M3 source reuse

DT = 0.002
STEPS_PER_TICK = 10
TICKS = 300
GOAL = (0.16, 0.0)
CONTACT_RADIUS_M = 0.020 + 0.012
FRAGILITY_IMPULSE_NS = 0.006  # uncalibrated toy proxy, not real safety
POLICIES = ("aligned_replay", "contact_feedback", "guarded_feedback", "safe_abstain")
REGIMES = ("nominal", "lateral_shift", "friction_mass", "sensor_dropout", "adversarial")

COLUMNS = (
    "case_id","seed","regime","policy","safe_success","goal_dwell_ticks",
    "final_goal_error_m","observed_goal_claim","false_success",
    "pusher_object_contact_steps","object_obstacle_contact_steps",
    "pusher_obstacle_contact_steps","damage_proxy","peak_step_impulse_ns",
    "object_workspace_excursion","held_ticks","unsafe_deadman_target_updates",
    "held_contact_impulse_ns","synthetic_human_requests","synthetic_ack_events",
    "abstained","candidate_refusals","object_initial_x","object_initial_y",
    "object_mass_kg","object_slide_friction","mapped_obstacle_y","actual_obstacle_y",
    "tracking_drop_ticks","deadman_release_tick"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seeded_rng(seed: int, salt: str) -> random.Random:
    material = f"rokoko-mega-v1|{seed}|{salt}".encode("utf8")
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


def scenario(seed: int, regime: str) -> dict:
    rng = seeded_rng(seed, "world")
    x = rng.uniform(-0.011, 0.011)
    y = rng.uniform(-0.008, 0.008)
    friction = rng.uniform(0.32, 0.48)
    mass = rng.uniform(0.065, 0.095)
    obstacle = 0.15
    dropout_start = 90
    dropout_ticks = 0
    deadman_release = -1
    noise_m = 0.001
    if regime == "lateral_shift":
        y = rng.uniform(-0.048, 0.048)
        x = rng.uniform(-0.018, 0.018)
        noise_m = 0.0018
    elif regime == "friction_mass":
        y = rng.uniform(-0.025, 0.025)
        friction = rng.uniform(0.12, 0.9)
        mass = rng.uniform(0.04, 0.15)
        noise_m = 0.002
    elif regime == "sensor_dropout":
        y = rng.uniform(-0.028, 0.028)
        dropout_start = rng.randint(50, 150)
        dropout_ticks = rng.choice((8, 20, 38))
        noise_m = 0.002
    elif regime == "adversarial":
        y = rng.uniform(-0.048, 0.048)
        x = rng.uniform(-0.018, 0.018)
        friction = rng.uniform(0.12, 0.85)
        mass = rng.uniform(0.04, 0.15)
        obstacle = rng.choice((-0.065, -0.03, 0.0, 0.03, 0.065))
        dropout_start = rng.randint(70, 135)
        dropout_ticks = rng.choice((0, 12, 25))
        deadman_release = rng.choice((-1, -1, 150, 190))
        noise_m = 0.003
    # Map with error is a declared sensor assumption, not an oracle geometry read.
    mapped_obstacle_y = round(obstacle + rng.gauss(0, 0.007), 3)
    return dict(
        x=x,y=y,friction=friction,mass=mass,obstacle_y=obstacle,
        mapped_obstacle_y=mapped_obstacle_y,
        dropout_start=dropout_start,dropout_ticks=dropout_ticks,
        deadman_release=deadman_release,noise_m=noise_m,
    )


def interpolate_progress(progress: list[float], ratio: float) -> float:
    v = min(1.0, max(0.0, ratio)) * (len(progress)-1)
    i = min(int(v), len(progress)-2)
    f = v - i
    return progress[i] * (1-f) + progress[i+1] * f


def distance_segment_to_point(a,b,p):
    vx,vy=b[0]-a[0],b[1]-a[1]
    proj=max(0.0,min(1.0,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/max(vx*vx+vy*vy,1e-12)))
    return math.dist((a[0]+proj*vx,a[1]+proj*vy),p)


def feedback_target(obs, pusher, guarded: bool):
    obj = obs["object"]
    vx,vy=GOAL[0]-obj[0],GOAL[1]-obj[1]
    goal_dist=math.hypot(vx,vy)
    if goal_dist<0.020:
        # Release the object; do not keep a force-limited servo pressed into it.
        return (pusher[0]-0.035,pusher[1]), False
    vx,vy=vx/goal_dist,vy/goal_dist
    if guarded:
        obstacle=(0.09,obs["mapped_obstacle_y"])
        # Sensor-based warning: 18mm box half-width + 20mm puck radius + margin.
        if distance_segment_to_point(obj,GOAL,obstacle)<0.043:
            return (pusher[0],pusher[1]), True
    behind=(obj[0]-0.041*vx,obj[1]-0.041*vy)
    if math.dist(pusher,behind)>0.011:
        return behind, False
    # Target at 27.5 mm: up to 4.5mm intentional nominal contact overlap,
    # less than the old 25mm, with force/breakage measured in MuJoCo.
    return (obj[0]-0.0275*vx,obj[1]-0.0275*vy), False


def replay_target(t, initial_observation, progress):
    x0,y0=initial_observation
    if t<0.7:
        return (-0.06,y0)
    if t<5.0:
        p=interpolate_progress(progress,(t-0.7)/4.3)
        start=x0-0.041
        end=GOAL[0]-CONTACT_RADIUS_M-0.003
        return (start+(end-start)*p,y0*(1-p))
    return (GOAL[0]-CONTACT_RADIUS_M-0.045,GOAL[1])


class Runner:
    def __init__(self):
        import mujoco
        import numpy as np
        self.mj=mujoco
        self.np=np
        self.model=mujoco.MjModel.from_xml_path(str(SIM/"scene.xml"))
        self.data=mujoco.MjData(self.model)
        self.obj=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,"object")
        self.pusher=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,"pusher")
        self.og=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_GEOM,"object_geom")
        self.pg=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_GEOM,"pusher_geom")
        self.bg=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_GEOM,"obstacle")
        self.base_inertia=self.model.body_inertia[self.obj].copy()
        self.force=np.zeros(6)
        assert abs(float(self.model.opt.timestep)-DT)<1e-10
        assert self.mj.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_GEOM,self.og)=="object_geom"

    def reset(self,sc):
        mj,m,d=self.mj,self.model,self.data
        mj.mj_resetData(m,d)
        m.geom_pos[self.bg,1]=sc["obstacle_y"]
        m.geom_friction[self.og,0]=sc["friction"]
        m.body_mass[self.obj]=sc["mass"]
        m.body_inertia[self.obj,:]=self.base_inertia*(sc["mass"]/0.08)
        mj.mj_setConst(m,d)
        d.qpos[0:2]=[sc["x"],sc["y"]]
        d.ctrl[:]=[0.0,0.0]
        mj.mj_forward(m,d)

    def run(self,case_id,seed,regime,policy,progress):
        sc=scenario(seed,regime)
        self.reset(sc)
        mj,m,d=self.mj,self.model,self.data
        rng=seeded_rng(seed,"sensor")
        hold=Hold()
        target=(-0.06,0.0)
        last_obs=None
        initial_obs=None
        seen_at=0.0
        abstained = policy=="safe_abstain"
        human_requests=0
        ack_events=0
        contacted=0
        obj_obstacle=0
        pusher_obstacle=0
        broken=False
        peak_impulse=0.0
        violation=False
        held_contact_impulse=0.0
        held_ticks=0
        dwell=0
        unsafe_updates=0
        refused=0
        for tick in range(TICKS):
            t=tick*DT*STEPS_PER_TICK
            dropout=(sc["dropout_start"]<=tick<
                     sc["dropout_start"]+sc["dropout_ticks"])
            if not dropout:
                last_obs=(round(float(d.xpos[self.obj,0]+rng.gauss(0,sc["noise_m"])),3),
                          round(float(d.xpos[self.obj,1]+rng.gauss(0,sc["noise_m"])),3))
                seen_at=t
                if initial_obs is None:
                    initial_obs=last_obs
            age=t-seen_at
            live=not (sc["deadman_release"]>=0 and tick>=sc["deadman_release"])
            quality=0.65 if dropout else 0.99
            # This is a declared position/map sensor. True mass/friction/contact
            # and simulator reward never appear in this allowlisted dictionary.
            obs=dict(object=last_obs,age=age,quality=quality,deadman=live,
                     mapped_obstacle_y=sc["mapped_obstacle_y"])
            ack=bool(sc["dropout_ticks"] and
                     tick==sc["dropout_start"]+sc["dropout_ticks"]+3 and live)
            ack_events+=int(ack)
            held=hold.update(live,age,quality,True,ack)
            if held:
                held_ticks+=1
            old_target=target
            if not held and not abstained and last_obs is not None:
                pusher=tuple(float(x) for x in d.xpos[self.pusher,:2])
                if policy=="aligned_replay":
                    desired=replay_target(t,initial_obs,progress)
                    stop=False
                else:
                    desired,stop=feedback_target(obs,pusher,policy=="guarded_feedback")
                if stop:
                    abstained=True
                    human_requests+=1 # synthetic request, no real response
                else:
                    delta=(desired[0]-target[0],desired[1]-target[1])
                    norm=math.hypot(*delta)
                    frac=min(1.0,0.002/max(norm,1e-12))
                    candidate=(target[0]+frac*delta[0],target[1]+frac*delta[1])
                    if -0.19<=candidate[0]<=0.29 and -0.19<=candidate[1]<=0.19:
                        target=candidate
                    else:
                        refused+=1
                        # No control target update, never auto-ACK invalid input.
            if not live and target!=old_target:
                unsafe_updates+=1
            d.ctrl[:]=(target[0]+0.06,target[1])
            for _ in range(STEPS_PER_TICK):
                mj.mj_step(m,d)
                pos=tuple(float(v) for v in d.xpos[self.obj,:2])
                violation|=not (-0.2<=pos[0]<=0.3 and -0.2<=pos[1]<=0.2
                                and 0<=float(d.xpos[self.obj,2])<=0.06)
                for k in range(d.ncon):
                    pair={d.contact[k].geom1,d.contact[k].geom2}
                    if pair=={self.og,self.pg} or pair=={self.og,self.bg}:
                        mj.mj_contactForce(m,d,k,self.force)
                        impulse=float(self.np.linalg.norm(self.force[:3]))*DT
                        peak_impulse=max(peak_impulse,impulse)
                        broken|=impulse>FRAGILITY_IMPULSE_NS
                        if pair=={self.og,self.pg}:
                            contacted+=int(impulse>1e-8)
                        else:
                            obj_obstacle+=int(impulse>1e-8)
                        if held:
                            held_contact_impulse+=impulse
                    elif pair=={self.pg,self.bg}:
                        pusher_obstacle+=1
            if math.dist(tuple(float(v) for v in d.xpos[self.obj,:2]),GOAL)<0.020:
                dwell+=1
            else:
                dwell=0
        goal_error=math.dist(tuple(float(v) for v in d.xpos[self.obj,:2]),GOAL)
        # Evaluator-only hidden MuJoCo truth, never policy reward leakage.
        safe_success=(dwell>=25 and goal_error<0.020 and contacted>0
                      and not broken and obj_obstacle==0 and not violation)
        sensor_claim=(last_obs is not None and math.dist(last_obs,GOAL)<0.020)
        result=dict(case_id=case_id,seed=seed,regime=regime,policy=policy,
            safe_success=int(safe_success),goal_dwell_ticks=dwell,
            final_goal_error_m=goal_error,observed_goal_claim=int(sensor_claim),
            false_success=int(sensor_claim and not safe_success),
            pusher_object_contact_steps=contacted,
            object_obstacle_contact_steps=obj_obstacle,
            pusher_obstacle_contact_steps=pusher_obstacle,
            damage_proxy=int(broken),peak_step_impulse_ns=peak_impulse,
            object_workspace_excursion=int(violation),held_ticks=held_ticks,
            unsafe_deadman_target_updates=unsafe_updates,
            held_contact_impulse_ns=held_contact_impulse,
            synthetic_human_requests=human_requests,
            synthetic_ack_events=ack_events,abstained=int(abstained),
            candidate_refusals=refused,
            object_initial_x=sc["x"],object_initial_y=sc["y"],
            object_mass_kg=sc["mass"],object_slide_friction=sc["friction"],
            mapped_obstacle_y=sc["mapped_obstacle_y"],
            actual_obstacle_y=sc["obstacle_y"],tracking_drop_ticks=sc["dropout_ticks"],
            deadman_release_tick=sc["deadman_release"])
        return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cases",type=int,default=1000)
    ap.add_argument("--seed",type=int,default=800000)
    ap.add_argument("--shard-index",type=int,default=0)
    ap.add_argument("--shard-count",type=int,default=1)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if not(1<=args.cases<=10000 and 1<=args.shard_count<=8 and
           0<=args.shard_index<args.shard_count and 0<=args.seed<1_000_000_000):
        ap.error("bounded cases/shards/seed required")
    if args.output.resolve().parent != (HERE/"results").resolve():
        ap.error("output must be a CSV immediately in mega/results")
    import mujoco
    src=demo()
    progress=normalize_demo_progress(src["episode"]["steps"])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    runner=Runner()
    start=time.perf_counter()
    tmp=args.output.with_suffix(".partial.csv")
    rows=0
    complete=0
    with tmp.open("w",newline="",encoding="utf8") as fh:
        writer=csv.DictWriter(fh,fieldnames=COLUMNS,extrasaction="raise")
        writer.writeheader()
        for case_id in range(args.cases):
            if case_id%args.shard_count!=args.shard_index:
                continue
            regime=REGIMES[case_id%len(REGIMES)]
            seed=args.seed+case_id
            for policy in POLICIES:
                row=runner.run(case_id,seed,regime,policy,progress)
                writer.writerow(row)
                rows+=1
            complete+=1
            if complete%50==0:
                fh.flush()
                print(json.dumps(dict(completed_cases=complete,physics_episodes=rows,
                                      elapsed_s=round(time.perf_counter()-start,2))),
                      file=sys.stderr,flush=True)
    tmp.replace(args.output)
    manifest=dict(
        schema="motionbridge.megasim.v1",source_kind="SYNTHETIC_MUJOCO",
        input_kind="UNVERIFIED_REPLAY",training="NONE: four scripted controllers",
        actuation_authorized=False,mujoco_version=mujoco.__version__,
        total_case_plan=args.cases,local_shard=args.shard_index,
        shards=args.shard_count,actual_independent_scenarios=complete,
        actual_physics_episodes=rows,seed_base=args.seed,
        regime_plan=list(REGIMES),policies=list(POLICIES),
        physics_timestep_s=DT,physics_steps_per_episode=TICKS*STEPS_PER_TICK,
        actual_physics_steps=rows*TICKS*STEPS_PER_TICK,
        campaign_elapsed_s=round(time.perf_counter()-start,3),
        source_commit=subprocess.check_output(
            ["git","rev-parse","HEAD"],cwd=PRODUCT,text=True).strip(),
        source_sha256={str(x.relative_to(PRODUCT)):digest(x)
          for x in (HERE/"experiment.py",SIM/"scene.xml",SIM/"experiment.py",
                    PRODUCT/"fixtures/synthetic-retarget.csv",
                    PRODUCT/"fixtures/retarget-map.json")},
        raw_csv_sha256=digest(args.output),model_calls=0,provider_cost="unknown",
        notice="MuJoCo CPU contact only; no licensed Rokoko SDK, trained RL, NVIDIA GPU or real human.")
    mp=args.output.with_suffix(".manifest.json")
    mp.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf8")
    print(json.dumps({k:manifest[k] for k in
                      ("actual_independent_scenarios","actual_physics_episodes",
                       "actual_physics_steps","campaign_elapsed_s","raw_csv_sha256")}))
if __name__=="__main__":
    main()
