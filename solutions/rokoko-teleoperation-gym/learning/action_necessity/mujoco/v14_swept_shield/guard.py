"""V14 research-only public-observation swept-obstacle motor-action veto.

Pure Python, no MuJoCo dependency.  This is a conservative *candidate* and
cannot qualify a robot or certify collision avoidance.  Nothing here can
change the original 7-action mask or the original physical unsafe predicate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Sequence


SOURCE_V13_SHA = "0751d78b93855bf70820b03b0a543e123d218baf"
ACTIONS = (
    "ALIGN", "PUSH_SLOW", "PUSH_MEDIUM", "APPROACH_LEFT",
    "APPROACH_RIGHT", "RETREAT", "ABSTAIN",
)
MOTOR_ACTIONS = tuple(range(6))
ABSTAIN = 6


@dataclass(frozen=True)
class Assumptions:
    """Public source bounds and deliberately conservative engineering choices.

    Global speed uses the maximum of the *source-level* training distribution,
    never a world's private amplitude, frequency, phase, or seed.  Gaussian
    noise has unbounded tails: 3 sigma is only a design assumption.
    """

    max_option_seconds: float = 0.2  # 10 servo ticks * 10 integration * .002 s
    # Use the published OOD envelope even for TRAIN.  The environment's
    # hidden `ood` flag never enters policy decisions; OOD efficacy is unknown.
    max_mover_amplitude_m: float = 0.045
    max_mover_frequency_hz: float = 1.0
    obstacle_box_half_width_m: float = 0.018
    object_radius_m: float = 0.020
    pusher_radius_m: float = 0.012
    mapped_obstacle_sigma_m: float = 0.005
    visible_object_sigma_m: float = 0.0015
    noise_sigma_multiple: float = 3.0
    object_motion_allowance_m: float = 0.020  # hypothesis, NOT a proven bound
    pusher_tracking_allowance_m: float = 0.005  # hypothesis, NOT a proven bound
    max_public_age_seconds: float = 0.1
    min_public_quality: float = 0.8

    @property
    def max_obstacle_speed_mps(self) -> float:
        return 2 * math.pi * self.max_mover_amplitude_m * self.max_mover_frequency_hz

    @property
    def obstacle_sweep_m(self) -> float:
        return self.max_obstacle_speed_mps * self.max_option_seconds

    @property
    def obstacle_disk_cover_radius_m(self) -> float:
        # Circumscribed radius of the XY cross-section of a square obstacle.
        return math.sqrt(2) * self.obstacle_box_half_width_m

    @property
    def object_clearance_m(self) -> float:
        return (
            self.obstacle_disk_cover_radius_m
            + self.object_radius_m
            + self.obstacle_sweep_m
            + self.noise_sigma_multiple
            * (self.mapped_obstacle_sigma_m + self.visible_object_sigma_m)
            + self.object_motion_allowance_m
        )

    @property
    def pusher_clearance_m(self) -> float:
        return (
            self.obstacle_disk_cover_radius_m
            + self.pusher_radius_m
            + self.obstacle_sweep_m
            + self.noise_sigma_multiple * self.mapped_obstacle_sigma_m
            + self.pusher_tracking_allowance_m
        )


@dataclass(frozen=True)
class ActionRisk:
    action: int
    name: str
    originally_allowed: bool
    veto: bool
    causes: tuple[str, ...]
    object_margin_m: float | None
    pusher_path_margin_m: float | None


@dataclass(frozen=True)
class Decision:
    """A *shadow verdict*, NEVER an executable command.

    `shadow_fallback_action` and `suggested_motor_actions` are counterfactual
    annotations only.  A caller cannot use this output as an actuator command.
    """

    requested_action: int
    would_veto_requested: bool
    shadow_fallback_action: int | None
    disposition: str
    cause: str
    original_mask7: tuple[int, ...]
    action_risks: tuple[ActionRisk, ...]
    suggested_motor_actions: tuple[int, ...]
    observed_obstacle_displacement_m: float | None
    history_consistent: bool
    max_obstacle_speed_mps: float
    global_max_amplitude_m: float
    global_max_frequency_hz: float
    obstacle_sweep_m: float
    object_clearance_m: float
    pusher_clearance_m: float
    evidence_origin: tuple[str, ...] = (
        "current_public18d",
        "optional_previous_public18d",
        "original_allowed_mask7",
        "source_global_mover_bounds_not_hidden_world_parameters",
        "geometric_candidate_not_physics_attestation",
        "gaussian_noise_tails_unbounded",
    )
    source_v13_sha: str = SOURCE_V13_SHA
    result_scope: str = "SOURCE_ONLY_SYNTHETIC_RESEARCH_CANDIDATE_NO_EFFICACY_CLAIM"

    def log_record(self) -> dict:
        """Small JSON-compatible provenance/uncertainty record; no private state."""
        return asdict(self)


@dataclass(frozen=True)
class OneForkProposal:
    """Advisory opt-in only at public live legal early V5 ABSTAIN decision.

    The default original V5 action is always returned unchanged.  An external
    independently reviewed experiment would need separate authority, budget,
    fresh original-mask admission, and explicit action selection before doing
    anything physical.  Nothing in this module executes or authorizes it.
    """

    baseline_action_unchanged: int
    source_public_trigger_valid: bool
    opted_in: bool
    experimental_action_advisory_only: int | None
    disposition: str
    risk: Decision | None
    experimental_original_physics_qualified: bool = False
    external_execution_authorized: bool = False
    per_world_max_candidate_forks: int = 1
    source_v13_sha: str = SOURCE_V13_SHA


def _public18d(raw: Sequence[float], label: str) -> tuple[float, ...]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 18:
        raise ValueError(f"{label}: expected public 18D observation")
    if not all(type(value) in (int, float) and math.isfinite(value) for value in raw):
        raise ValueError(f"{label}: nonfinite or nonnumeric public observation")
    out = tuple(float(v) for v in raw)
    if not (out[8] >= 0 and 0 <= out[9] <= 1 and 0 <= out[13] <= 1):
        raise ValueError(f"{label}: invalid age, quality or public time")
    for idx in (10, 11, 15):
        if out[idx] not in (0., 1.):
            raise ValueError(f"{label}: invalid boolean public state")
    return out


def _mask7(raw: Sequence[int]) -> tuple[int, ...]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 7:
        raise ValueError("original_mask7: expected seven original options")
    if any(type(v) not in (int, bool) or v not in (0, 1) for v in raw):
        raise ValueError("original_mask7: invalid original option bit")
    return tuple(int(v) for v in raw)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_segment_distance(p, start, end) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    if squared <= 1e-20:
        return _distance(p, start)
    t = min(1., max(0., ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / squared))
    return _distance(p, (start[0] + t * dx, start[1] + t * dy))


def _motor_target(action: int, obs: tuple[float, ...]):
    """Public geometric approximation to original desired option endpoints.

    Does not claim access to the hidden servo target or to the next true body
    state.  All directions derive from current public object and public goal.
    """
    obj, push = (obs[0], obs[1]), (obs[2], obs[3])
    # The goal is present in fields 16:18 of the original public 18D vector.
    toward = (obs[16] - obj[0], obs[17] - obj[1])
    norm = max(math.hypot(*toward), 1e-8)
    unit = (toward[0] / norm, toward[1] / norm)
    lateral = (-unit[1], unit[0])
    if action in (0, 1, 2):
        backoff = (0.041, 0.029, 0.0275)[action]
        return (obj[0] - backoff * unit[0], obj[1] - backoff * unit[1])
    if action in (3, 4):
        offset = 0.019 if action == 3 else -0.019
        return (obj[0] - .024 * unit[0] + offset * lateral[0],
                obj[1] - .024 * unit[1] + offset * lateral[1])
    if action == 5:
        return (push[0] - .035 * unit[0], push[1] - .035 * unit[1])
    raise ValueError("ABSTAIN has no motor endpoint")


def _history_status(current, previous, bounds: Assumptions):
    if previous is None:
        return None, True
    dt = (current[13] - previous[13]) * (10 * 60) * .02
    displacement = _distance((current[6], current[7]), (previous[6], previous[7]))
    if dt < -1e-5 or (dt < 1e-6 and displacement > 1e-6):
        return displacement, False
    # Observed map displacements contain unbounded Gaussian measurement noise.
    # This is an anomaly veto, not a claim that above-threshold motion is
    # impossible.  History never shrinks the base worst-case future tube.
    noise_allowance = bounds.noise_sigma_multiple * math.sqrt(2) * bounds.mapped_obstacle_sigma_m
    consistent = displacement <= bounds.max_obstacle_speed_mps * max(dt, 0) + noise_allowance
    return displacement, consistent


def decide(
    public18d: Sequence[float],
    original_mask7: Sequence[int],
    requested_action: int,
    *,
    previous_public18d: Sequence[float] | None = None,
) -> Decision:
    """Shadow-evaluate potential veto for an original-mask-legal motor option.

    No seeds, hidden obstacle pose or future observation enter the decision.
    Failure to validate public inputs raises ValueError (caller must issue NO
    motor command), rather than inventing an allowed action. No motor command
    is ever emitted by this function.
    """
    obs = _public18d(public18d, "public18d")
    previous = None if previous_public18d is None else _public18d(
        previous_public18d, "previous_public18d")
    mask = _mask7(original_mask7)
    if type(requested_action) is not int or not 0 <= requested_action <= 6:
        raise ValueError("requested_action: expected integer in original range 0..6")
    # No call-time bound overrides: do not tune the research guard to a known
    # unsafe world or unknowingly weaken it in one branch of an experiment.
    assumptions = _V14_ASSUMPTIONS

    displacement, history_ok = _history_status(obs, previous, assumptions)
    healthy = (bool(obs[10]) and bool(obs[11]) and not bool(obs[15])
               and obs[8] <= assumptions.max_public_age_seconds
               and obs[9] >= assumptions.min_public_quality)
    obj = (obs[0], obs[1])
    push = (obs[2], obs[3])
    obstacle = (obs[6], obs[7])
    obj_margin = _distance(obj, obstacle) - assumptions.object_clearance_m
    risks = []
    for action in range(7):
        allowed = bool(mask[action])
        if action == ABSTAIN:
            risks.append(ActionRisk(action, ACTIONS[action], allowed, not allowed,
                                    () if allowed else ("original_mask_forbids",), None, None))
            continue
        target = _motor_target(action, obs)
        pusher_margin = (_point_segment_distance(obstacle, push, target)
                         - assumptions.pusher_clearance_m)
        reasons = []
        if not allowed:
            reasons.append("original_mask_forbids")
        if not healthy:
            reasons.append("public_deadman_quality_age_or_hold_unhealthy")
        if not history_ok:
            reasons.append("previous_public_obstacle_map_inconsistent")
        if obj_margin <= 0:
            reasons.append("object_within_predictive_swept_obstacle_tube")
        if pusher_margin <= 0:
            reasons.append("pusher_option_path_within_predictive_swept_obstacle_tube")
        risks.append(ActionRisk(action, ACTIONS[action], allowed, bool(reasons),
                                tuple(reasons), obj_margin, pusher_margin))

    selected = risks[requested_action]
    if selected.veto:
        fallback = ABSTAIN if mask[ABSTAIN] else None
        disposition = "SHADOW_VETO_NOT_EXECUTED"
        cause = "+".join(selected.causes)
    else:
        fallback = None
        disposition = "SHADOW_ORIGINAL_ABSTAIN" if requested_action == ABSTAIN else "SHADOW_PASS_NOT_EXECUTED"
        cause = "originally_allowed_and_no_candidate_veto"
    # Advisory alternatives are re-requested later, never auto-selected here.
    suggestions = tuple(a for a in (3, 4, 5) if not risks[a].veto and a != requested_action)
    return Decision(
        requested_action=requested_action,
        would_veto_requested=selected.veto,
        shadow_fallback_action=fallback,
        disposition=disposition,
        cause=cause,
        original_mask7=mask,
        action_risks=tuple(risks),
        suggested_motor_actions=suggestions,
        observed_obstacle_displacement_m=displacement,
        history_consistent=history_ok,
        max_obstacle_speed_mps=assumptions.max_obstacle_speed_mps,
        global_max_amplitude_m=assumptions.max_mover_amplitude_m,
        global_max_frequency_hz=assumptions.max_mover_frequency_hz,
        obstacle_sweep_m=assumptions.obstacle_sweep_m,
        object_clearance_m=assumptions.object_clearance_m,
        pusher_clearance_m=assumptions.pusher_clearance_m,
    )


def propose_one_fork(
    public18d: Sequence[float],
    original_mask7: Sequence[int],
    baseline_action: int,
    *,
    opt_in: bool = False,
    experimental_action: int | None = None,
    previous_public18d: Sequence[float] | None = None,
) -> OneForkProposal:
    """One advisory *TRAIN research* fork; baseline V5 remains unchanged.

    Source V13 frozen_first_fork's public EARLY_LIVE_ABSTAIN predicate:
    original V5 would ABSTAIN(6) although live=1, held=0 and some original
    motor option is legal. No seed, outcome, private world label, or future
    observation is consulted. This is a proposal, not action replacement.
    """
    obs = _public18d(public18d, "public18d")
    mask = _mask7(original_mask7)
    if type(baseline_action) is not int or not 0 <= baseline_action <= 6 or not mask[baseline_action]:
        raise ValueError("baseline_action: original-mask-legal integer required")
    if type(opt_in) is not bool:
        raise ValueError("opt_in: explicit boolean research consent required")
    if experimental_action is not None and (type(experimental_action) is not int
                                            or not 0 <= experimental_action < 6):
        raise ValueError("experimental_action: only a single motor option 0..5")
    if not opt_in and experimental_action is not None:
        raise ValueError("experimental_action: cannot propose without opt-in")
    # Validate previous public input also when no research is enabled.
    if previous_public18d is not None:
        _public18d(previous_public18d, "previous_public18d")
    trigger = bool(baseline_action == ABSTAIN and obs[10] == 1 and obs[15] == 0
                   and any(mask[:6]))
    status = "BASELINE_V5_UNCHANGED_NO_RESEARCH"
    proposed = None
    risk = None
    if opt_in:
        if not trigger:
            status = "BASELINE_V5_UNCHANGED_PUBLIC_TRIGGER_ABSENT"
        elif experimental_action is None:
            status = "BASELINE_V5_UNCHANGED_NO_EXPERIMENT_ACTION"
        else:
            risk = decide(obs, mask, experimental_action,
                          previous_public18d=previous_public18d)
            if risk.would_veto_requested:
                status = "BASELINE_V5_UNCHANGED_EXPERIMENT_VETOED"
            else:
                # A reviewed host must separately authorize/execute this; the
                # original baseline remains unaffected by this source-only API.
                proposed = experimental_action
                status = "BASELINE_V5_UNCHANGED_ADVISORY_FORK_ONLY"
    return OneForkProposal(
        baseline_action_unchanged=baseline_action,
        source_public_trigger_valid=trigger,
        opted_in=opt_in,
        experimental_action_advisory_only=proposed,
        disposition=status,
        risk=risk,
    )


_V14_ASSUMPTIONS = Assumptions()
