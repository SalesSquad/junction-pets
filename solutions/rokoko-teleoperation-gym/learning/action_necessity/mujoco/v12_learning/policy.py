"""Unqualified V12 public-state, physics-goal-directed TRAIN hypotheses.

V5 is always the baseline. The *observed-only* world-disjoint fitted model
can arbitrate one bounded side/recovery rescue. It does not certify safety or
physical 250-tick goal success. The isolated RIGHT probe is TRAIN-only and is
explicitly NEVER treated as a trained action model.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable


MODEL_SCHEMA="junction.rokoko.v12.public-observed-action-conditioned-linear.v1"
PINNED_MODEL_SHA256="82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
V10_SOURCE_SHA="9cc583d3f0f24484b79c1929ba875c7a3b667806"
V11_SOURCE_SHA="ab6df4054ef6ed350b479469590a48046a0c0a68"
MOTOR=(0,1,2,3,4,5)
MAX_RESCUE_ROUNDS=1
MAX_RESCUE_OPTIONS=8


class V12ContractStop(ValueError):
    """Missing or inauthentic source, non-public state, illegal motor: STOP."""


def require(ok,reason):
    if not ok:raise V12ContractStop(reason)


def public_abi(observation,mask):
    try:
        obs=[v.item() if hasattr(v,"item") else v for v in observation]
        legal=[m.item() if hasattr(m,"item") else m for m in mask]
    except (ValueError,TypeError) as exc:
        raise V12ContractStop("V12_PUBLIC_ABI_NOT_ITERABLE") from exc
    require(len(obs)==18 and len(legal)==7 and
        all(type(v) in (float,int) and math.isfinite(v) for v in obs) and
        all(type(m) in (bool,int) and m in (0,1) for m in legal) and any(legal),
        "V12_ONLY_FINITE_PUBLIC18D_ORIGINAL_SEVEN_MASK")
    return tuple(float(v) for v in obs),tuple(int(m) for m in legal)


def checked_action(action,mask):
    # No numpy scalar bypass; external legacy original V5 returns Python int.
    require(type(action) is int and 0<=action<7 and mask[action]==1,
            "V12_ORIGINAL_SHIELD_ILLEGAL_ACTION_STOP")
    return action


def public_goal_distance(o):
    return math.hypot(o[16]-o[0],o[17]-o[1])


def gate_input(params,o,m,v5_action):
    require(params["kind"] in ("blocked_side","v5_abstain_side",
                "blocked_or_abstain_side","blocked_side_no_align"),
                "V12_FROZEN_GATE_KIND_CHANGED")
    if public_goal_distance(o)<=params["min_distance"] or abs(o[7])>=params["obstacle_limit"]:
        return False
    lateral=bool(m[3] or m[4])
    blocked=not(m[1] or m[2]) and lateral
    abstain=v5_action==6 and lateral
    if params["kind"]=="blocked_side":return blocked
    if params["kind"]=="v5_abstain_side":return abstain
    if params["kind"]=="blocked_or_abstain_side":return blocked or abstain
    return bool(blocked and not m[0])


def public_features(o,m,prev):
    # Exact frozen V12 fitted feature order. Previous *public* mover map only.
    trend=0. if prev is None else 10.*(o[7]-prev[7])
    return [1.,10.*(o[16]-o[0]),10.*(o[17]-o[1]),
      10.*(o[2]-o[0]),10.*(o[3]-o[1]),.1*o[4],.1*o[5],
      10.*(o[6]-o[0]),10.*(o[7]-o[1]),10.*o[8],o[9],o[13],o[14],
      trend,float(m[1]),float(m[3]),float(m[4])]


def load_frozen_model(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink==1,
            "V12_FROZEN_MODEL_FILE_MISSING_OR_UNSAFE")
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==PINNED_MODEL_SHA256,
            "V12_FROZEN_MODEL_SHA_CHANGED")
    m=json.loads(raw)
    require(m["schema"]==MODEL_SCHEMA and
        m["sourceEvidence"]["v10"]["sourceSha"]==V10_SOURCE_SHA and
        m["sourceEvidence"]["v11"]["sourceSha"]==V11_SOURCE_SHA and
        m["sourceOriginalRealMuJoCoTrials"]==1600 and
        m["sourceOriginalRealOptionTransitions"]==73561 and
        m["worldDisjointSplits"]=={"fit":185,"calibration":65,"diagnostic":70} and
        m["unseenOrUnsupportedActionsForbiddenAtInference"]==[0,4,6] and
        all(m["frozenV5WinningTrajectoryGateNoninterference"][r]["firedOnV5OriginalWinningWorlds"]==0
            for r in ("v10","v11")) and
        m["sourceActualExecutedActionCounts"]["v10"]["executed"][4]==3 and
        m["sourceActualExecutedActionCounts"]["v11"]["executed"][4]==0 and
        m["sourceDistinctWorldsPerAction"]["v10"][4]==1 and
        m["sourceDistinctWorldsPerAction"]["v11"][4]==0 and
        m["models"]["4"]["supported"] is False and
        m["models"]["4"]["weights"] is None and
        m["stateAndSafetyContract"]["originalShieldAlwaysFinal"] is True and
        m["modelPromotionAuthorized"] is False and
        m["newMuJoCoPhysicsPerformed"] is False and
        m["devCalTestOodOpened"] is False,
        "V12_FROZEN_PUBLIC_SOURCE_OR_ACTION4_PROVENANCE_DRIFT")
    # Validate model calibration and all numeric coefficients fail-closed.
    for a in range(7):
        d=m["models"][str(a)]
        if a in (0,4,6):
            require(d["supported"] is False,"V12_UNTRAINED_OR_DIAGNOSTIC_NO_GO_ACTION")
        else:
            weights=d["weights"]
            require(d["supported"] is True and len(weights)==17 and
              all(len(row)==6 and all(type(x) in (float,int) and math.isfinite(x)
                  for x in row) for row in weights) and
              .0<=d["calibration95WorldMaxPositionMeters"]<.05 and
              d["diagnosticWorldMaxPositionCoverage"]>=.90 and
              d["diagnosticPositionCoverage"]>=.90,
              "V12_SUPPORTED_ACTION_NOT_WORLD_CALIBRATED")
    return m


def model_score(o,m,prev,action,model,side_repetition):
    d=model["models"][str(action)]
    require(d["supported"] is True and action in MOTOR,
            "V12_UNSUPPORTED_ACTION_IN_MODEL_SCORE")
    feat=public_features(o,m,prev)
    pred=[sum(feat[i]*d["weights"][i][j] for i in range(17)) for j in range(6)]
    require(all(math.isfinite(p) for p in pred),"V12_NONFINITE_MODEL_OUTPUT_STOP")
    # Goal is physical 250tick CONTACT dwell, not 'forward reopens'. Model
    # dwell is an uncertain ranking *proxy*, never a success declaration.
    upper_dist=math.hypot(o[16]-o[0]-pred[0],o[17]-o[1]-pred[1])+d["calibration95WorldMaxPositionMeters"]
    lower_dwell=max(0.,min(1.,pred[5]-d["calibration95WorldMaxDwellFraction"]))
    penalty=0.004*side_repetition if action==3 else 0.
    return upper_dist-.01*lower_dwell+penalty


class BoundedV12DwellRescue:
    """Independent TRAIN-only hypothesis; V5 reset after any deviation."""
    def __init__(self,frozen_v5_factory:Callable,model:dict):
        require(callable(frozen_v5_factory),"V12_FROZEN_V5_FACTORY_REQUIRED")
        self.v5_factory=frozen_v5_factory
        self.v5=frozen_v5_factory()
        require(callable(self.v5),"V12_FROZEN_V5_POLICY_REQUIRED")
        self.model=model
        self.gate=model["frozenV11GateParameters"]
        self.gate_streak=0
        self.rescue_rounds=0
        self.rescue_active=False
        self.rescue_options=0
        self.previous_obs=None
        self.side_repetition=0
        self.mode_history=[]

    def _reset_v5(self):
        self.v5=self.v5_factory()
        require(callable(self.v5),"V12_FROZEN_V5_RESET_FAILED")
        self.rescue_active=False
        self.gate_streak=0
        self.rescue_options=0

    def _choose_supported(self,o,m):
        candidates=[a for a in MOTOR if m[a] and self.model["models"][str(a)]["supported"]]
        if not candidates:return None
        return min(candidates,key=lambda a:(model_score(o,m,self.previous_obs,a,self.model,
                                                    self.side_repetition),a))

    def __call__(self,observation,mask):
        o,m=public_abi(observation,mask)
        if self.rescue_active:
            if (m[1] or m[2] or public_goal_distance(o)<=.035 or
                    self.rescue_options>=MAX_RESCUE_OPTIONS):
                self._reset_v5()
            else:
                action=self._choose_supported(o,m)
                if action is not None:
                    checked_action(action,m)
                    self.rescue_options+=1
                    self.side_repetition=self.side_repetition+1 if action==3 else 0
                    self.previous_obs=o
                    self.mode_history.append("model_rescue_unqualified")
                    return action
                self._reset_v5()  # No model if only RIGHT4 legal; V5 decides.
        baseline=checked_action(self.v5(list(o),list(m)),m)
        eligible=gate_input(self.gate,o,m,baseline)
        self.gate_streak=self.gate_streak+1 if eligible else 0
        if self.rescue_rounds<MAX_RESCUE_ROUNDS and self.gate_streak>=self.gate["min_streak"]:
            action=self._choose_supported(o,m)
            if action is not None:
                checked_action(action,m)
                self.rescue_active=True
                self.rescue_rounds+=1
                self.rescue_options=1
                self.side_repetition=1 if action==3 else 0
                self.previous_obs=o
                self.mode_history.append("model_rescue_unqualified")
                return action
        self.previous_obs=o
        self.mode_history.append("frozen_v5")
        return baseline


class TrainOnlyRightAction4Probe:
    """One originally mask-legal RIGHT4 acquisition, never learned/promoted."""
    def __init__(self,frozen_v5_factory,gate):
        require(callable(frozen_v5_factory),"V12_RIGHT_TRAIN_BASELINE_REQUIRED")
        self.factory=frozen_v5_factory
        self.v5=self.factory()
        require(callable(self.v5),"V12_RIGHT_TRAIN_BASELINE_NOT_CALLABLE")
        self.gate=gate
        self.streak=0
        self.used=False
        self.reset_required=False
        self.mode_history=[]

    def __call__(self,observation,mask):
        o,m=public_abi(observation,mask)
        if self.reset_required:
            self.v5=self.factory()
            require(callable(self.v5),"V12_RIGHT_TRAIN_BASELINE_RESET_FAILED")
            self.reset_required=False
        v5_action=checked_action(self.v5(list(o),list(m)),m)
        eligible=not self.used and m[4]==1 and gate_input(self.gate,o,m,v5_action)
        self.streak=self.streak+1 if eligible else 0
        if self.streak>=self.gate["min_streak"]:
            self.used=True
            self.reset_required=True
            self.mode_history.append("UNTRAINED_RIGHT4_EXPLORATION_ONLY")
            return checked_action(4,m)
        self.mode_history.append("frozen_v5")
        return v5_action


def policy_factory(frozen_v5_factory:Callable,model_path):
    model=load_frozen_model(model_path)
    return lambda: BoundedV12DwellRescue(frozen_v5_factory,model)


def right4_train_only_factory(frozen_v5_factory:Callable,model_path):
    # This arm never calls model_score(4); data acquisition ONLY.
    gate=load_frozen_model(model_path)["frozenV11GateParameters"]
    return lambda: TrainOnlyRightAction4Probe(frozen_v5_factory,gate)
