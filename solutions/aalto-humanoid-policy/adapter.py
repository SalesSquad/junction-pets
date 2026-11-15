"""Thin optional official-server adapter; live compatibility is not qualified."""
try:
    import numpy as np
    from aaltonomous.deploy.policy_server import Policy, serve
except ImportError as exc:
    raise SystemExit('Optional dependency unavailable: install the pinned official '
                     'aaltonomous package and its server dependencies, plus numpy. '
                     f'Original import error: {exc}') from exc

from policy import HoldPolicy


class ConservativePolicy(Policy):
    name = "aalto-m320-offline-hold"
    action_horizon = 1

    def __init__(self):
        self.core = HoldPolicy()

    def reset(self, instruction="", task=None, seed=None):
        self.core.reset()

    def act(self, obs):
        converted = dict(obs)
        try:
            for key, shape, dtype in (
                ('head_rgb', (480, 640, 3), np.uint8),
                ('left_wrist_rgb', (480, 640, 3), np.uint8),
                ('right_wrist_rgb', (480, 640, 3), np.uint8),
                ('head_depth', (480, 640), np.uint16),
                ('arm_q', (14,), np.float32), ('arm_dq', (14,), np.float32),
                ('hand_q', (14,), np.float32)):
                value = obs[key]
                if not isinstance(value, np.ndarray) or value.shape != shape or value.dtype != dtype:
                    raise ValueError(f'{key}: wrong dtype or shape')
                converted[key] = value.tobytes() if value.ndim > 1 else value.tolist()
        except (KeyError, TypeError, ValueError):
            converted = {}  # core latches FAULT, preserving a previous hold
        result = self.core.step(converted)
        action = result.action()  # no invented zero target when no safe pose exists
        return {key: np.asarray(value, dtype=np.float32) for key, value in action.items()}



if __name__ == '__main__':
    serve(ConservativePolicy(), port=8000)
