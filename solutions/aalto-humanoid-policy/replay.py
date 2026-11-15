"""Deterministic synthetic 30Hz hold replay. Never connects to a robot."""
import json
from policy import HoldPolicy, UPSTREAM, DATASET

RGB = b'\x01' * (480 * 640 * 3)
DEPTH = b'\x01\x00' * (480 * 640)


def observation(t=0.0, **overrides):
    obs = dict(head_rgb=RGB, head_depth=DEPTH, left_wrist_rgb=RGB,
               right_wrist_rgb=RGB, arm_q=[0.1] * 14, arm_dq=[0.0] * 14,
               hand_q=[0.1, 0.1, 0.2, -0.2, -0.2, -0.2, -0.2, 0.1, 0.1, -0.2, 0.2, 0.2, 0.2, 0.2], instruction='put the red block in the left bin', t=t)
    obs.update(overrides)
    return obs


def replay(frames=90, trace_path=None):
    if not isinstance(frames, int) or frames < 2:
        raise ValueError('at least two frames required')
    policy = HoldPolicy()
    emitted = failures = abstentions = 0
    previous = None
    max_arm = max_hand = 0.0
    states = {}
    for i in range(frames):
        instruction = 'put red block in left bin' if i % 3 else 'do something unseen'
        result = policy.step(observation(i / 30, instruction=instruction))
        states[result.state] = states.get(result.state, 0) + 1
        abstentions += result.state == 'ABSTAIN'
        try:
            action = result.action()
            if previous:
                max_arm = max(max_arm, max(abs(a-b)*30 for a,b in zip(
                    action['arm_q_target'], previous['arm_q_target'])))
                max_hand = max(max_hand, max(abs(a-b)*30 for a,b in zip(
                    action['hand_q_target'], previous['hand_q_target'])))
            previous = action
            emitted += 1
        except ValueError:
            failures += 1
    assert max_arm <= 1.0 and max_hand <= 3.0
    if trace_path:
        from dataclasses import asdict
        # Exclusive creation preserves prior evidence. Hash chains detect changes;
        # local files are not signed receipts or tamper-proof storage.
        with open(trace_path, 'x', encoding='utf-8') as stream:
            for entry in policy.trace:
                stream.write(json.dumps(asdict(entry), sort_keys=True) + '\n')
    return dict(status='ALL_OFFLINE_SYNTHETIC_HOLD_ONLY', upstream=UPSTREAM,
                dataset_revision=DATASET, frames=frames, scheduled_hz=30,
                target_command_coverage_hz=30 * emitted / frames,
                coverage_formula='30 * emitted / scheduled_frames; NOT measured throughput',
                meets_27hz_coverage_arithmetic=30 * emitted / frames >= 27,
                official_rate_qualified=False, failures=failures, abstentions=abstentions,
                states=states, max_arm_delta_rad_s=max_arm, max_hand_delta_rad_s=max_hand,
                clipping_operations=0, trace_digest=policy.trace[-1].digest)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', help='new JSONL path; refuses overwrite')
    args = parser.parse_args()
    print(json.dumps(replay(trace_path=args.trace), sort_keys=True))
