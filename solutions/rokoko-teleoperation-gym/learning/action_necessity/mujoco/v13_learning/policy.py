"""V13 bounded continuation hypothesis for retrospective/fresh TRAIN only.

The V12 rescue returns to V5 as soon as either forward option is mask-legal.
A mask describes one decision, not a future trajectory or safe goal. Here the
already-started rescue can continue after reopening, but is limited by the
unchanged public ABI, current original shield, model action support and V12's
8-option/one-round caps. This is an unqualified experimental policy, never a
claim of safety, physical reachability, or improvement.
"""
from pathlib import Path
import importlib.util

_V12 = Path(__file__).resolve().parent.parent / "v12_learning" / "policy.py"
_spec = importlib.util.spec_from_file_location("rokoko_v12_policy", _V12)
if _spec is None or _spec.loader is None:
    raise ImportError("V12_POLICY_SOURCE_MISSING")
v12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v12)


class ContinueAfterReopen(v12.BoundedV12DwellRescue):
    """Only change V12's forward-reopening exit; keep all other bounds."""

    def __call__(self, observation, mask):
        o, m = v12.public_abi(observation, mask)
        if self.rescue_active:
            if (v12.public_goal_distance(o) <= .035 or
                    self.rescue_options >= v12.MAX_RESCUE_OPTIONS):
                self._reset_v5()
            else:
                action = self._choose_supported(o, m)
                if action is not None:
                    v12.checked_action(action, m)
                    self.rescue_options += 1
                    self.side_repetition = self.side_repetition + 1 if action == 3 else 0
                    self.previous_obs = o
                    self.mode_history.append("v13_continuation_unqualified")
                    return action
                self._reset_v5()
        baseline = v12.checked_action(self.v5(list(o), list(m)), m)
        eligible = v12.gate_input(self.gate, o, m, baseline)
        self.gate_streak = self.gate_streak + 1 if eligible else 0
        if (self.rescue_rounds < v12.MAX_RESCUE_ROUNDS and
                self.gate_streak >= self.gate["min_streak"]):
            action = self._choose_supported(o, m)
            if action is not None:
                v12.checked_action(action, m)
                self.rescue_active = True
                self.rescue_rounds += 1
                self.rescue_options = 1
                self.side_repetition = 1 if action == 3 else 0
                self.previous_obs = o
                self.mode_history.append("v13_continuation_unqualified")
                return action
        self.previous_obs = o
        self.mode_history.append("frozen_v5")
        return baseline


def policy_factory(frozen_v5_factory, model_path):
    model = v12.load_frozen_model(model_path)
    return lambda: ContinueAfterReopen(frozen_v5_factory, model)
