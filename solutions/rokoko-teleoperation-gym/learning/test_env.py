"""Focused real-physics smoke and fail-closed checks; no training claim."""
import unittest
import numpy as np
from env import ContactEnv, OBS_SIZE, heuristic


class PhysicsChecks(unittest.TestCase):
    def test_two_physics_episodes_and_seed_replay(self):
        snapshots = []
        for seed in (120001, 320001):
            env = ContactEnv(max_options=2)
            obs = env.reset(seed)
            snapshots.append(obs.copy())
            self.assertEqual(obs.shape, (OBS_SIZE,))
            self.assertTrue(np.isfinite(obs).all())
            done = False
            while not done:
                obs, reward, done, info = env.step(heuristic(obs, env.mask(obs)))
            self.assertGreater(info['physics_steps'], 0)
            self.assertFalse(info['unsafe'])
        self.assertFalse(np.array_equal(*snapshots))
        np.testing.assert_array_equal(ContactEnv().reset(120001), snapshots[0])
        with self.assertRaises(ValueError):
            ContactEnv().reset(800000)

    def test_hold_refuses_model_override_and_requires_ack(self):
        env = ContactEnv(max_options=3)
        env.reset(120002)
        env.release = 0
        env._sense()
        old = env.target.copy()
        self.assertTrue(env.held)
        self.assertFalse(env.mask()[2])
        env.step(2)  # an arbitrarily confident learned proposal is still rejected
        np.testing.assert_array_equal(env.target, old)
        self.assertGreater(env.refusals, 0)
        env.release = -1
        class NoAck:
            def random(self):
                return 1.
        env.ack_rng = NoAck()
        env._sense()
        self.assertTrue(env.held)  # healthy observations cannot auto-rearm
        env.drop_start, env.drop_len = 0, 100
        env._sense()
        self.assertTrue(env.held)
        self.assertFalse(env.mask()[0])
        env.drop_len = 0
        class Ack:
            def random(self):
                return 0.
        env.ack_rng = Ack()
        env._sense()
        self.assertFalse(env.held)
        self.assertEqual(env.acks, 1)


if __name__ == '__main__':
    unittest.main()
