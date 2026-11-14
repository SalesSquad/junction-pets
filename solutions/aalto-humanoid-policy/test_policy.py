import dataclasses
import unittest
from policy import HoldPolicy, destination
from replay import observation, replay


class PolicyTests(unittest.TestCase):
    def test_instruction_grammar(self):
        for color, side in [('red', 'left'), ('yellow', 'center'), ('blue', 'right')]:
            self.assertEqual(destination(f'Please place the {color} cube into the {side} bin.'), side)
        for text in ['put red block in right bin', 'red and blue', 'do not put red block in left bin',
                     'put red block in left bin then move blue', '', None]:
            self.assertIsNone(destination(text))

    def test_state_and_hold(self):
        p = HoldPolicy()
        first = p.step(observation())
        self.assertEqual(first.state, 'READY')
        for i, changes, state in [(1, {'head_depth': bytes(480*640*2)}, 'HOLD'),
                                  (2, {'instruction': 'unknown'}, 'ABSTAIN'),
                                  (3, {'arm_q': [0.8]*14}, 'READY'),
                                  (4, {'head_rgb': bytes(480*640*3)}, 'HOLD')]:
            result = p.step(observation(i/30, **changes))
            self.assertEqual(result.state, state)
            self.assertEqual(result.action(), first.action())

    def test_invalid_and_latched(self):
        for changes in ({'arm_q': [0]*13}, {'hand_q': [float('nan')]*14},
                        {'arm_dq': [float('inf')]*14}, {'arm_q': [True]*14},
                        {'head_rgb': b''}, {'head_depth': b''}, {'t': -1},
                        {'t': float('nan')}):
            with self.subTest(changes=str(changes)[:60]):
                p = HoldPolicy()
                bad = p.step(observation(**changes))
                self.assertEqual(bad.state, 'FAULT')
                with self.assertRaises(ValueError):
                    bad.action()
                self.assertEqual(p.step(observation(1)).state, 'FAULT')
                p.reset()
                self.assertEqual(p.step(observation()).state, 'READY')

    def test_stale_and_watchdog_gaps(self):
        for t, state in [(0, 'FAULT'), (-0.1, 'FAULT'), (0.2, 'HOLD'), (1.0, 'FAULT')]:
            p = HoldPolicy()
            initial = p.step(observation())
            result = p.step(observation(t))
            self.assertEqual(result.state, state)
            self.assertEqual(result.action(), initial.action())

    def test_mirrored_hands_preserve_wire_order(self):
        # Distinct left/right sentinels: never mirror, reverse or swap Dex3 slots.
        hand = [0.01*i for i in range(7)] + [-0.02*i for i in range(7)]
        result = HoldPolicy().step(observation(hand_q=hand))
        self.assertEqual(result.action()['hand_q_target'], hand)
        self.assertNotEqual(hand[:7], hand[7:])

    def test_trace_immutable_and_input_bound(self):
        p = HoldPolicy()
        p.step(observation())
        trace = p.trace
        with self.assertRaises(dataclasses.FrozenInstanceError):
            trace[0].digest = 'changed'
        p.step(observation(1/30))
        self.assertEqual(len(trace), 1)
        self.assertEqual(p.trace[1].previous, trace[0].digest)
        other = HoldPolicy()
        other.step(observation(instruction='different'))
        self.assertNotEqual(other.trace[0].digest, trace[0].digest)

    def test_replay_deterministic_limits_coverage(self):
        a = replay()
        self.assertEqual(a, replay())
        self.assertEqual(a['target_command_coverage_hz'], 30)
        self.assertEqual(a['failures'], 0)
        self.assertEqual(a['abstentions'], 30)
        self.assertEqual(a['max_arm_delta_rad_s'], 0)
        self.assertEqual(a['max_hand_delta_rad_s'], 0)
        self.assertFalse(a['official_rate_qualified'])


if __name__ == '__main__':
    unittest.main()
