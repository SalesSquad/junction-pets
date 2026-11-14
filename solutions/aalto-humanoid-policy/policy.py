"""Offline-only hold baseline. No perception, trajectory planner, or robot control."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
from numbers import Real

UPSTREAM = '36daf5b44dad46b8f448a5124ded7faa9947be1e'
DATASET = '04046a85586feb5727f991adee3367176015cab0'
SOURCE = f'https://github.com/zupermiez/aaltonomous-humanoid/tree/{UPSTREAM}'
COLORS = {'red': 'left', 'yellow': 'center', 'blue': 'right'}


def destination(instruction):
    """Deliberately narrow grammar; unseen or competing clauses abstain."""
    if not isinstance(instruction, str):
        return None
    words = instruction.lower().strip().rstrip('.!')
    match = re.fullmatch(
        r'(?:please )?(?:put|place|move|sort) (?:the )?'
        r'(red|yellow|blue) (?:object|item|block|cube) '
        r'(?:in|into|to) (?:the )?(?:(left|center|right) )?bin(?: please)?', words)
    if not match:
        return None
    color, side = match.groups()
    expected = COLORS[color]
    return expected if side in (None, expected) else None


def vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 14:
        raise ValueError(name + ': expected 14 numbers')
    if any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x)
           for x in value):
        raise ValueError(name + ': nonfinite/nonnumeric')
    return tuple(float(x) for x in value)


@dataclass(frozen=True)
class Result:
    state: str
    reason: str
    arm: tuple | None
    hand: tuple | None
    destination: str | None

    def action(self):
        if self.arm is None:
            raise ValueError('explicit fault: no safe target; reset required')
        return {'arm_q_target': list(self.arm), 'hand_q_target': list(self.hand)}


@dataclass(frozen=True)
class Trace:
    index: int
    upstream: str
    dataset: str
    input_digest: str
    result: Result
    previous: str
    digest: str


class HoldPolicy:
    """READY means validated input only. Every emitted target is a fixed hold.

    First valid measured pose seeds the hold. No synthetic perception ever moves
    it. FAULT latches until reset; a prior safe hold remains available on errors.
    Time-gap checks are observation-time checks, not a wall-clock watchdog.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self._arm = self._hand = self._t = None
        self._fault = False
        self._trace = ()

    @property
    def trace(self):
        return self._trace

    def step(self, obs):
        target = None
        try:
            if self._fault:
                raise ValueError('latched fault; reset required')
            if not isinstance(obs, dict):
                raise ValueError('observation must be a mapping')
            arm = vector(obs.get('arm_q'), 'arm_q')
            vector(obs.get('arm_dq'), 'arm_dq')
            hand = vector(obs.get('hand_q'), 'hand_q')
            t = obs.get('t')
            if isinstance(t, bool) or not isinstance(t, Real) or not math.isfinite(t) or t < 0:
                raise ValueError('invalid time')
            gap = 0 if self._t is None else t - self._t
            if self._t is not None and gap <= 0:
                raise ValueError('stale/nonmonotonic observation')
            if gap >= 1.0:
                raise ValueError('safe-stop gap >=1s')
            for key in ('head_rgb', 'left_wrist_rgb', 'right_wrist_rgb'):
                if not isinstance(obs.get(key), bytes) or len(obs[key]) != 480 * 640 * 3:
                    raise ValueError(key + ': expected uint8 480x640x3 bytes')
            depth = obs.get('head_depth')
            if not isinstance(depth, bytes) or len(depth) != 480 * 640 * 2:
                raise ValueError('head_depth: expected uint16 480x640 bytes')
            if not all(any(obs[key]) for key in ('head_rgb', 'left_wrist_rgb', 'right_wrist_rgb')):
                state, reason = 'HOLD', 'blank camera frame; no perception performed'
            elif not any(depth):
                state, reason = 'HOLD', 'no valid depth; no perception performed'
            else:
                target = destination(obs.get('instruction'))
                state, reason = ('READY', 'validated input; hold-only baseline') if target else (
                    'ABSTAIN', 'ambiguous or unseen instruction')
            if gap >= 0.2:
                state, reason = 'HOLD', 'observation gap >=0.2s'
            if self._arm is None:
                self._arm, self._hand = arm, hand
            self._t = float(t)
        except ValueError as exc:
            self._fault = True
            state, reason = 'FAULT', str(exc)
        result = Result(state, reason, self._arm, self._hand, target)
        # Hash sensor bytes and exact scalar input, without retaining image data.
        def canonical(x):
            if isinstance(x, bytes):
                return {'bytes': len(x), 'sha256': hashlib.sha256(x).hexdigest()}
            if isinstance(x, dict):
                return {str(k): canonical(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [canonical(v) for v in x]
            if isinstance(x, Real):
                return repr(x)
            if x is None or isinstance(x, str):
                return x
            return {'invalid_type': type(x).__name__}
        incoming = hashlib.sha256(json.dumps(canonical(obs), sort_keys=True).encode()).hexdigest()
        previous = self._trace[-1].digest if self._trace else '0' * 64
        payload = json.dumps([len(self._trace), UPSTREAM, DATASET, incoming,
                              result.__dict__, previous], sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        self._trace += (Trace(len(self._trace), UPSTREAM, DATASET, incoming,
                              result, previous, digest),)
        return result
