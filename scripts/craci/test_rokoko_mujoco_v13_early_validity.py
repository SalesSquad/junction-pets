"""Synthetic-only fail-closed row validation and forensic retention tests."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v13_synthetic_fixtures', HERE/'test_rokoko_mujoco_v13_harness.py')
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
h, p = f.h, f.p


class Producer(f.Producer):
    def __init__(self, mutate=None):
        super().__init__(); self.mutate = mutate

    def run_real_episode(self, env, seed, arm, factory, sig, deadline, source):
        row, trace = super().run_real_episode(env, seed, arm, factory, sig, deadline, source)
        row['dwell_ticks_final'] = trace[-1]['dwell_ticks_current']
        if self.mutate:
            self.mutate(len(self.calls), row, trace)
        return row, trace


class EarlyValidity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='v13-early-row-')
        self.root = Path(self.tmp.name); self.private = self.root/'private'
        self.scans = h.scan_real_public_starts(f.FakeEnv(), f.signature)
        self.portable_pin = patch.object(h, 'PORTABLE_PREFLIGHT_SHA',
                                        h.portable_scan_digest(self.scans))
        self.portable_pin.start()
        self.addCleanup(self.portable_pin.stop)
        cohort = f.Protocol.derive_cohort(self.scans, {})
        self.survey = dict(selected_first40_near8_clear=[
            dict(seed=r['seed'], world_hash=r['world_hash'], near=r['observed_corridor'])
            for r in cohort])

    def tearDown(self): self.tmp.cleanup()

    def run_mutation(self, mutate):
        producer = Producer(mutate)
        result = h.run_pilot_originals(self.root, self.private, None, {}, None,
                   f.Protocol, f.FACTORIES, producer, None, f.FakeEnv, f.signature,
                   'a'*40, survey=self.survey)
        return result, producer

    def check_forensic(self, result, count):
        self.assertFalse(result['complete'])
        self.assertEqual(result['completed_episodes'], count)
        self.assertTrue(result['reason'].startswith('SOURCE_OR_PHYSICS_EXCEPTION_UNQUALIFIED_'))
        self.assertTrue((self.private/'quarantine.json').is_file())
        stop = json.loads((self.private/'early_stop.json').read_text())
        self.assertEqual(stop['raw_sha256']['quarantine.json'], h.sha(self.private/'quarantine.json'))
        with gzip.open(self.private/'full_transitions.jsonl.gz', 'rt') as stream:
            self.assertEqual(len(list(stream)), count)
        out = self.root/'collector'; packed = p.publish_early_stop(self.private, out)
        self.assertEqual(packed['original_sha256']['quarantine.json'], h.sha(self.private/'quarantine.json'))
        manifest = json.loads((out/'retention-manifest.json').read_text())
        quarantine = next(x for x in manifest['sources'] if x['name'] == 'quarantine.json')
        parts = []
        for part in quarantine['parts']:
            with zipfile.ZipFile(out/part['archive']) as z: parts.append(z.read(part['entry']))
        self.assertEqual(b''.join(parts), (self.private/'quarantine.json').read_bytes())

    def test_nan_and_infinity_quarantined_before_any_next_episode(self):
        for val in (float('nan'), float('inf')):
            with self.subTest(value=val), tempfile.TemporaryDirectory(prefix='v13-case-') as tmp:
                self.root = Path(tmp); self.private = self.root/'private'
                result, producer = self.run_mutation(lambda n, row, trace: row.update(final_error=val))
                self.assertEqual(len(producer.calls), 1)
                self.check_forensic(result, 0)
                self.assertIn(b'NaN' if val != val else b'Infinity', (self.private/'quarantine.json').read_bytes())

    def test_missing_candidate_dwell_preserves_prior_baseline(self):
        def mutate(n,row,trace):
            if n == 2: del row['dwell_ticks_final']
        result, producer = self.run_mutation(mutate)
        self.assertEqual(len(producer.calls), 2)
        self.check_forensic(result, 1)
        self.assertNotIn('dwell_ticks_final', json.loads((self.private/'quarantine.json').read_text())['returned_row'])

    def test_false_success_hiding_real_goal_hard_stops(self):
        def mutate(n,row,trace):
            if n == 2:
                row['success'] = False; trace[-1]['success_info'] = False
                row['full_transition_sha256'] = h.digest(trace)
        result, producer = self.run_mutation(mutate)
        self.assertEqual(len(producer.calls), 2)
        self.check_forensic(result, 1)

    def test_trace_terminal_dwell_disagreement_hard_stops(self):
        def mutate(n,row,trace):
            if n == 2: row['dwell_ticks_final'] = 249
        result, producer = self.run_mutation(mutate)
        self.assertEqual(len(producer.calls), 2)
        self.check_forensic(result, 1)

    def test_normal_rows_are_accepted(self):
        result, producer = self.run_mutation(None)
        self.assertTrue(result['complete'])
        self.assertEqual(len(producer.calls),192)
        self.assertFalse((self.private/'quarantine.json').exists())

if __name__ == '__main__': unittest.main()
