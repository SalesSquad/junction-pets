"""Action-conditioned world-disjoint learning from executed public MuJoCo traces.

No counterfactual action labels: every supervised row is an action actually
executed under the original seven-option shield. Post-step physics dwell and
cost are TRAIN labels only and are never inference inputs. FIT, CAL and DIAG
are disjoint by *world seed*, not by option/episode.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

OBS=18
ACTIONS=7
FEATURES=("intercept","goal_dx10","goal_dy10","pusher_dx10","pusher_dy10",
          "object_vx01","object_vy01","obstacle_dx10","obstacle_dy10",
          "sensor_age10","sensor_quality","normalized_ticks","previous_action",
          "observed_obstacle_dy10","forward_legal","side3_legal","side4_legal")
TARGETS=("object_dx","object_dy","pusher_dx","pusher_dy",
         "obstacle_dy","poststep_dwell250_fraction")
MIN_FIT=128
MIN_CAL=40
MIN_DIAG=40
MIN_FIT_WORLDS=20
MIN_CAL_WORLDS=8
MIN_DIAG_WORLDS=8
RIDGE_LAMBDA=.1
SCHEMA="junction.rokoko.v12.public-observed-action-conditioned-linear.v1"


def require(ok, message):
    if not ok:raise ValueError(message)


def public_inputs(observation,mask):
    require(len(observation)==OBS and len(mask)==ACTIONS and
            all(type(v) in (int,float) and math.isfinite(v) for v in observation) and
            all(type(m) in (bool,int) and m in (0,1) for m in mask) and any(mask),
            "V12_ONLY_FINITE_PUBLIC18D_AND_SEVEN_MASK")
    return observation,mask


def public_features(observation,mask,previous_observation=None):
    o,m=public_inputs(observation,mask)
    if previous_observation is not None:
        require(len(previous_observation)==OBS and all(type(v) in (int,float) and
                math.isfinite(v) for v in previous_observation),"V12_INVALID_PUBLIC_HISTORY")
    # Previous mover displacement uses only previously observed noisy obstacle
    # coordinates. Hidden physical mover amplitude, phase and frequency are
    # never consulted. The mask remains the independent actuator authority.
    trend=0. if previous_observation is None else 10.*(o[7]-previous_observation[7])
    return [1.,10.*(o[16]-o[0]),10.*(o[17]-o[1]),
            10.*(o[2]-o[0]),10.*(o[3]-o[1]),
            .1*o[4],.1*o[5],10.*(o[6]-o[0]),10.*(o[7]-o[1]),
            10.*o[8],o[9],o[13],o[14],trend,float(m[1]),float(m[3]),float(m[4])]


def target_from_executed_transition(step):
    o,n=step["observation"],step["next_observation"]
    public_inputs(o,step["mask"])
    require(len(n)==OBS and all(type(v) in (int,float) and math.isfinite(v) for v in n) and
            type(step["dwell_ticks_current"]) is int and
            step["dwell_ticks_current"]>=0 and
            type(step["cost"]) is int and step["cost"]>=0,
            "V12_ORIGINAL_POSTSTEP_LABELS_INVALID")
    # Original real physics can record 258/259 ticks on a successful option:
    # its inner integration loop finishes a servo substep after crossing 250.
    # Never rewrite original evidence or raise/relax the actual GOAL threshold.
    return [n[0]-o[0],n[1]-o[1],n[2]-o[2],n[3]-o[3],n[7]-o[7],
            min(250,step["dwell_ticks_current"])/250.]


def partition(seed):
    # This is preregistered by seed only, no reward, success or source run.
    return {0:"diagnostic",1:"calibration"}.get(seed%5,"fit")


def observed_samples(source_runs):
    """Generate genuine supervised rows, keeping individual world identity."""
    samples={action:{"fit":[],"calibration":[],"diagnostic":[]} for action in range(ACTIONS)}
    counts={run:{"legal":[0]*ACTIONS,"executed":[0]*ACTIONS,"unsafe":[0]*ACTIONS,
                 "actualGoal250Terminal":[0]*ACTIONS}
            for run in source_runs}
    world_sets={name:set() for name in ("fit","calibration","diagnostic")}
    action_worlds={run:[set() for _ in range(ACTIONS)] for run in source_runs}
    for run,data in source_runs.items():
        require(data["run"]==run and len(data["traces"])==800,
                "V12_EXPECT_FROZEN_800_REAL_TRIALS_PER_SOURCE")
        for (seed,strategy),trace in data["traces"].items():
            group=partition(seed)
            world_sets[group].add((run,seed))
            previous=None
            weight=1./len(trace)  # Equalize long failing and short successful episodes.
            for step in trace:
                action=step["action"]
                o,m=public_inputs(step["observation"],step["mask"])
                require(type(action) is int and 0<=action<ACTIONS and m[action]==1,
                        "V12_ORIGINAL_MASKED_ACTION_REQUIRED")
                for k,legal in enumerate(m):counts[run]["legal"][k]+=int(legal)
                counts[run]["executed"][action]+=1
                action_worlds[run][action].add(seed)
                counts[run]["unsafe"][action]+=int(step["cost"]>0)
                counts[run]["actualGoal250Terminal"][action]+=int(
                    step["success_info"] and step["dwell_ticks_current"]>=250 and
                    step["cost"]==0)
                samples[action][group].append((public_features(o,m,previous),
                                               target_from_executed_transition(step),
                                               weight,run,seed))
                previous=o
    # Public-observation-first cohort selection does not promise exactly equal
    # seed residue counts. The split is outcome-independent and world-disjoint;
    # source-fixed V10/V11 yield 185 FIT,65 CAL and70 DIAG worlds.
    require(sum(len(v) for v in world_sets.values())==320 and
            len(world_sets["fit"])>=150 and len(world_sets["calibration"])>=50 and
            len(world_sets["diagnostic"])>=50 and
            world_sets["fit"].isdisjoint(world_sets["calibration"]) and
            world_sets["fit"].isdisjoint(world_sets["diagnostic"]) and
            world_sets["calibration"].isdisjoint(world_sets["diagnostic"]),
            "V12_SOURCE_WORLDS_LEAKED_ACROSS_FIT_CAL_DIAG")
    require(sum(counts[r]["executed"][a] for r in counts for a in range(ACTIONS))==
            38569+34992,"V12_SOURCE_OPTION_COUNT_DRIFT")
    return samples,counts,world_sets,action_worlds


def quantile_ceil(values,p):
    require(bool(values) and 0<p<1,"V12_NONEMPTY_CALIBRATION_REQUIRED")
    ranked=sorted(float(x) for x in values)
    k=min(len(ranked)-1,math.ceil((len(ranked)+1)*p)-1)
    return ranked[k]


def predict(weights,x):
    return np.asarray(x,dtype=np.float64)@np.asarray(weights,dtype=np.float64)


def residuals(records,beta):
    if not records:return [],[]
    X=np.asarray([x for x,y,w,r,s in records],dtype=np.float64)
    Y=np.asarray([y for x,y,w,r,s in records],dtype=np.float64)
    predicted=X@beta
    return (np.linalg.norm((Y-predicted)[:,:2],axis=1).tolist(),
            np.abs((Y-predicted)[:,5]).tolist())


def world_max_residuals(records,beta):
    """A world, not its correlated option count, is one calibration unit."""
    pos,dwell=residuals(records,beta)
    grouped={}
    for (_,_,_,run,seed),p,d in zip(records,pos,dwell):
        key=(run,seed)
        if key not in grouped:grouped[key]=[0.,0.]
        grouped[key][0]=max(grouped[key][0],p)
        grouped[key][1]=max(grouped[key][1],d)
    return [v[0] for v in grouped.values()],[v[1] for v in grouped.values()]


def fit_action_models(source_runs):
    samples,counts,worlds,action_worlds=observed_samples(source_runs)
    models={}
    for action in range(ACTIONS):
        fit,cal,diag=(samples[action][part] for part in ("fit","calibration","diagnostic"))
        counts_split={k:len(samples[action][k]) for k in ("fit","calibration","diagnostic")}
        distinct_worlds={k:len({(run,seed) for x,y,w,run,seed in samples[action][k]})
                         for k in ("fit","calibration","diagnostic")}
        # Especially action 4 must never be hallucinated from an observed 3
        # examples out of ~49,000 legal opportunities. Action6 is an explicit
        # abstention/hold safety mechanism, not a learned motor action.
        if (action==6 or len(fit)<MIN_FIT or len(cal)<MIN_CAL or len(diag)<MIN_DIAG or
                distinct_worlds["fit"]<MIN_FIT_WORLDS or
                distinct_worlds["calibration"]<MIN_CAL_WORLDS or
                distinct_worlds["diagnostic"]<MIN_DIAG_WORLDS):
            models[str(action)]={"supported":False,"sourceObservedCounts":counts_split,
                                 "sourceDistinctWorldsBySplit":distinct_worlds,
                                 "reason":"ORIGINAL_ABSTAIN_NOT_MOTOR" if action==6 else
                                          "INSUFFICIENT_EXECUTED_ACTION_SUPPORT",
                                 "weights":None}
            continue
        X=np.asarray([x for x,y,w,r,s in fit],dtype=np.float64)
        Y=np.asarray([y for x,y,w,r,s in fit],dtype=np.float64)
        raww=np.asarray([w for x,y,w,r,s in fit],dtype=np.float64)
        weights=raww/(raww.mean())
        regularizer=np.eye(len(FEATURES))*RIDGE_LAMBDA
        regularizer[0,0]=0.
        beta=np.linalg.solve((X.T*weights)@X+regularizer,(X.T*weights)@Y)
        require(beta.shape==(len(FEATURES),len(TARGETS)) and np.all(np.isfinite(beta)),
                "V12_FIT_NONFINITE_ACTION_CONDITIONAL_MODEL")
        cal_pos,cal_dwell=residuals(cal,beta)
        diag_pos,diag_dwell=residuals(diag,beta)
        cal_world_pos,cal_world_dwell=world_max_residuals(cal,beta)
        diag_world_pos,diag_world_dwell=world_max_residuals(diag,beta)
        qpos=quantile_ceil(cal_pos,.95)
        qdwell=quantile_ceil(cal_dwell,.95)
        coverage=sum(v<=qpos for v in diag_pos)/len(diag_pos)
        qpos_world=quantile_ceil(cal_world_pos,.95)
        qdwell_world=quantile_ceil(cal_world_dwell,.95)
        world_coverage=sum(v<=qpos_world for v in diag_world_pos)/len(diag_world_pos)
        mean_pos=float(np.mean(diag_pos))
        true_object_delta=np.asarray([y[:2] for x,y,w,r,s in diag],dtype=np.float64)
        zero_model_error=float(np.mean(np.linalg.norm(true_object_delta,axis=1)))
        supported=bool(coverage>=.90 and world_coverage>=.90 and
                       math.isfinite(qpos_world) and qpos_world<.05 and
                       mean_pos<=zero_model_error*1.2)
        models[str(action)]={"supported":supported,"sourceObservedCounts":counts_split,
                            "sourceDistinctWorldsBySplit":distinct_worlds,
                            "weights":beta.tolist(),"calibration95PositionMeters":qpos,
                            "calibration95DwellFraction":qdwell,
                            "calibration95WorldMaxPositionMeters":qpos_world,
                            "calibration95WorldMaxDwellFraction":qdwell_world,
                            "diagnosticWorldMaxPositionCoverage":world_coverage,
                            "diagnosticWorldMaxPositionMeanMeters":float(np.mean(diag_world_pos)),
                            "diagnosticPositionCoverage":coverage,
                            "diagnosticPositionMAEMeters":mean_pos,
                            "diagnosticZeroMotionMAEMeters":zero_model_error,
                            "diagnosticDwellMAE":float(np.mean(diag_dwell)),
                            "reason":"PUBLIC_ACTION_DIAGNOSTIC_SUPPORTED" if supported else
                                     "PUBLIC_MODEL_DIAGNOSTIC_NO_GO"}
    return {"schema":SCHEMA,"featureNames":list(FEATURES),"targetNames":list(TARGETS),
            "worldDisjointSplits":{name:len(worlds[name]) for name in worlds},
            "sourceWorldSplitKeys":{name:[f"{run}:{seed}" for run,seed in sorted(worlds[name])]
                                    for name in worlds},
            "sourceWorldSplitSeedSha256":{name:hashlib.sha256(json.dumps(
              [f"{run}:{seed}" for run,seed in sorted(worlds[name])],
              separators=(",",":")).encode()).hexdigest() for name in worlds},
            "worldSplitRule":"seed%5: 0 diagnostic,1 calibration,2/3/4 FIT",
            "sourceActualExecutedActionCounts":counts,
            "sourceDistinctWorldsPerAction":{run:[len(s) for s in entries]
                                              for run,entries in action_worlds.items()},
            "models":models,"newMuJoCoPhysicsPerformed":False,
            "devCalTestOodOpened":False,"modelPromotionAuthorized":False}


def digest(model):
    return hashlib.sha256(json.dumps(model,sort_keys=True,separators=(",",":"),
                                     ensure_ascii=False,allow_nan=False).encode()).hexdigest()
