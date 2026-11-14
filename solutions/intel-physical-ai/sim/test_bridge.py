"""Targeted tests. Physics logs/camera bytes are caller-supplied external evidence."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from bridge import (Bridge, ROOT, load, sha, validate_model, verify_camera_bytes,
                    verify_episode)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Path(os.environ['M8_MODEL_ROOT'])
        cls.evidence = Path(os.environ['M8_EPISODE'])
        cls.camera = Path(os.environ['M8_HISTORICAL_CAMERA'])
        cls.genuine_sha = os.environ['M8_HISTORICAL_CAMERA_SHA256']

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.episode = Path(self.tmp.name) / 'episode'
        shutil.copytree(self.evidence, self.episode)
        self.manifest = load(self.episode / 'manifest.json')
        self.rows = [json.loads(x) for x in (self.episode / 'trace.jsonl').read_text().splitlines()]

    def save(self):
        (self.episode / 'trace.jsonl').write_text(''.join(json.dumps(r, allow_nan=True)+'\n' for r in self.rows))
        self.manifest['trace_sha256'] = sha(self.episode / 'trace.jsonl')
        (self.episode / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_genuine_historical_frame_hash(self):
        verify_camera_bytes(self.camera, self.genuine_sha, 320, 256)

    def test_complete_replay_with_genuine_saved_bytes_fixture(self):
        # Protocol fixture assembled from historical bytes, not 180 fresh captures.
        self.manifest.update(scenario='nominal', capture_state='required')
        self.manifest['capture'] = {'camera': 'wrist_cam', 'width': 320, 'height': 256, 'every_frame': True}
        for i, row in enumerate(self.rows):
            relative = f'frames/{i:04d}.ppm'
            shutil.copyfile(self.camera, self.episode / relative)
            row['camera'].update(present=True, path=relative, sha256=self.genuine_sha)
            row['injection']['fault'] = None
            row['bridge'] = Bridge().observe(row['camera'], i, row['physics_time_s'], row['injection'])
            row['command_emitted'] = True
        self.save()
        self.assertTrue(verify_episode(self.episode, self.model)['sensor_replay_accepted'])
        image = self.episode / 'frames/0000.ppm'
        image.write_bytes(image.read_bytes()[:-1] + b'X')
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_genuine_frame_tamper(self):
        p = Path(self.tmp.name) / 'tamper.ppm'
        p.write_bytes(self.camera.read_bytes()[:-1] + b'X')
        with self.assertRaises(ValueError):
            verify_camera_bytes(p, self.genuine_sha, 320, 256)

    def test_missing_camera_rejected_and_latched(self):
        result = verify_episode(self.episode, self.model)
        self.assertFalse(result['sensor_replay_accepted'])
        self.assertTrue(result['global_stop_latched'])
        self.assertEqual(result['routing'], 'REFUSED_HOLD')

    def test_duplicate_frame(self):
        self.rows[2] = copy.deepcopy(self.rows[1]); self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_nonmonotonic_time(self):
        self.rows[2]['physics_time_s'] = self.rows[1]['physics_time_s']; self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_nonfinite(self):
        self.rows[2]['qpos'][0] = float('nan'); self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_truncated(self):
        p = self.episode / 'trace.jsonl'; p.write_bytes(p.read_bytes()[:-1])
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_missing_frame_even_with_updated_hash(self):
        self.rows.pop(); self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_missing_hash(self):
        self.rows[0]['camera']['present'] = True
        del self.rows[0]['camera']['sha256']; self.save()
        with self.assertRaises((KeyError, ValueError, TypeError)): verify_episode(self.episode, self.model)

    def test_path_traversal(self):
        self.rows[0]['camera'].update(present=True, path='../outside.ppm', sha256=self.genuine_sha); self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_invalid_model_pin(self):
        model = Path(self.tmp.name) / 'model'; model.mkdir()
        for p in self.model.iterdir(): (model / p.name).symlink_to(p)
        (model / 'scene_box.xml').unlink()
        (model / 'scene_box.xml').write_text('<mujoco/>')
        with self.assertRaises(ValueError): validate_model(model)

    def test_command_after_stop(self):
        self.rows[1]['command_emitted'] = True; self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_changed_servo_after_stop(self):
        self.rows[1]['servo_target'][0] += .01; self.save()
        with self.assertRaises(ValueError): verify_episode(self.episode, self.model)

    def test_output_never_overwrites(self):
        before = sha(self.episode / 'trace.jsonl')
        p = subprocess.run([sys.executable, str(ROOT / 'run.py'), '--model-root', str(self.model),
                            '--output-dir', str(self.episode), '--capture', 'disabled'], capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(before, sha(self.episode / 'trace.jsonl'))

    def test_sensor_identity_staleness_and_global_latch(self):
        good = {'identity': 'wrist_cam:1', 'frame_index': 1, 'present': True,
                'captured_at_s': 1, 'source': 'SIM_PHYSICS_RENDER'}
        clean = {'source': 'SYNTHETIC_FAULT_INJECTION', 'fault': None}
        for change in ({'identity': 'other:1'}, {'captured_at_s': 0}, {'present': False},
                       {'captured_at_s': float('nan')}):
            b = Bridge(); rejected = b.observe({**good, **change}, 1, 1, clean)
            self.assertEqual(rejected['reason'], 'INVALID_OR_ABSENT_SENSOR')
            self.assertFalse(rejected['command_allowed'])
            self.assertFalse(b.observe(good, 1, 1, clean)['command_allowed'])
        b = Bridge()
        stopped = b.observe(good, 1, 1, {**clean, 'fault': 'operator_global_stop'})
        self.assertFalse(stopped['command_allowed'])
        self.assertFalse(b.observe(good, 1, 1, clean)['command_allowed'])
        self.assertFalse(hasattr(b, 'rearm'))

    def test_no_quality_score_unknown_evidence_always_hold(self):
        good = {'identity': 'wrist_cam:0', 'frame_index': 0, 'present': True,
                'captured_at_s': 0, 'source': 'SIM_PHYSICS_RENDER'}
        result = Bridge().observe(good, 0, 0, {'source': 'SYNTHETIC_FAULT_INJECTION', 'fault': None})
        self.assertEqual(result['route'], 'HOLD')
        self.assertFalse(result['sorting_allowed'])
        self.assertEqual(result['reason'], 'NO_REAL_CALIBRATED_DEFECT_SOURCE')


if __name__ == '__main__': unittest.main()
