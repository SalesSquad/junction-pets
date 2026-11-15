import copy
import json
from pathlib import Path
import sys
import tempfile
import subprocess
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from split_policy import split_manifest, validate_manifest, horizon_evidence, valid_quantiles
from common import windows, split_windows, training_support, probability, np
from export_forecasts import export, panel_digest


class SplitPolicyTests(unittest.TestCase):
    def test_old_overlap_and_forged_target_sets_are_rejected(self):
        fixed = split_manifest(range(2000, 2026))
        self.assertEqual(fixed['targetYears']['validation'], [2022, 2023])
        self.assertEqual(fixed['targetYears']['test'], [2024, 2025])
        old = copy.deepcopy(fixed)
        old['testOrigins'] = [2022, 2023]
        old['targetYears']['test'] = [2023, 2024, 2025]
        with self.assertRaisesRegex(ValueError, 'leakage'):
            validate_manifest(old)
        old['targetYears']['test'] = [2024, 2025]
        with self.assertRaisesRegex(ValueError, 'do not match'):
            validate_manifest(old)
        with self.assertRaisesRegex(ValueError, 'historical'):
            validate_manifest(None)

    def test_calendar_gaps_and_training_cutoff(self):
        years = np.array([2020, 2022, 2023])
        x = years[None, :, None].astype(float)
        w, y, _ = windows(x, years, [0], [2020], window=3)
        self.assertTrue(np.isnan(y[0, 0, 0]))
        self.assertEqual(y[0, 0, 1], 2022)
        w, _, _ = windows(x, years, [0], [2022], window=3)
        self.assertTrue(np.isnan(w[0, 1, 0]))
        _, train, _ = split_windows(x, years, [0], 'train')
        self.assertTrue(np.isnan(train).all())
        for bad in [np.array([2020, 2020, 2021]), np.array([2022, 2020, 2021])]:
            with self.assertRaisesRegex(ValueError, 'sorted unique'):
                windows(x, bad, [0], [2020])

    def test_late_targets_have_no_effective_training_deltas(self):
        w = np.array([[[np.nan]], [[10.]]])
        y = np.array([[[20., 21.]], [[11., np.nan]]])
        np.testing.assert_array_equal(training_support(w, y, [0]), [[1, 0]])
        np.testing.assert_array_equal(training_support(np.empty((0, 3, 1)), np.empty((0, 1, 2)), [0]), [[0, 0]])

    def test_null_and_unsupported_horizons_stay_unavailable(self):
        scores = {'persistence': {'h1': {'n': 3, 'mae': 1.}, 'h2': {'n': 0, 'mae': None}}}
        null = horizon_evidence(None, scores, scores, {})
        self.assertIsNone(null['chosen'])
        self.assertTrue(all(h['status'] == 'WITHHELD' for h in null['horizons'].values()))
        baseline = horizon_evidence('persistence', scores, scores, {})
        self.assertEqual(baseline['horizons']['h1']['status'], 'ELIGIBLE')
        self.assertEqual(baseline['horizons']['h2']['status'], 'WITHHELD')
        trained = {'transformer': scores['persistence']}
        unknown = horizon_evidence('transformer', trained, trained, {})
        self.assertEqual(unknown['horizons']['h1']['status'], 'WITHHELD')

    def test_invalid_quantiles_abstain(self):
        for q in [[1]*5, [1, 2, 3, 2, 5], [float('nan'), 2, 3, 4, 5]]:
            self.assertFalse(valid_quantiles(q))
            self.assertIsNone(probability(q, 3))
        self.assertTrue(valid_quantiles([1, 2, 3, 4, 5]))
        self.assertEqual(probability([1, 2, 3, 4, 5], 3), .5)

    def test_linear_fit_exports_abstention_with_a_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            years = list(range(2000, 2026))
            panel = dict(years=years, units=[dict(id='HVA01', category='HYVINVOINTIALUE')],
                         indicators=[dict(id=1, key='screen_breast', isTarget=True)],
                         values={'1': {'HVA01': {str(y): 50 + (y-2000)*.5 for y in years}}})
            (root / 'panel.json').write_text(json.dumps(panel))
            source = Path(__file__).resolve().parents[1]
            for script in ('train_forecaster.py', 'evaluate.py', 'export_forecasts.py'):
                subprocess.run([sys.executable, str(source / script), '--smoke', '--d-model', '8',
                                '--layers', '1', '--heads', '2', '--panel', str(root / 'panel.json'),
                                '--artifacts', str(root / 'artifacts'), '--out', str(root / 'forecast.json')],
                               check=True, capture_output=True, text=True)
            result = json.loads((root / 'forecast.json').read_text())
            self.assertEqual(result['forecasts'], {})
            evidence = result['evaluation']['indicators']['screen_breast']
            self.assertEqual(evidence['chosen'], 'drift')
            self.assertEqual(evidence['horizons']['h1']['status'], 'ELIGIBLE')
            self.assertEqual(evidence['export']['status'], 'WITHHELD')
            self.assertEqual(evidence['export']['horizons']['h1']['withheld'], 1)
            self.assertIn('INVALID_OR_COLLAPSED_QUANTILES', evidence['export']['horizons']['h1']['reasons'])

    def test_all_abstained_export_needs_no_fabricated_model_or_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel = root / 'panel.json'
            panel.write_text(json.dumps(dict(
                years=list(range(2000, 2026)), units=[dict(id='HVA01', category='HYVINVOINTIALUE')],
                indicators=[dict(id=1, key='screen_colorectal', isTarget=True)], values={})))
            metrics = dict(
                split=split_manifest(range(2000, 2026)), panelSha256=panel_digest(panel), trainingSupport={},
                metrics={'screen_colorectal': dict(chosen=None, validation={}, county={'h1': {}, 'h2': {}})})
            (root / 'metrics.json').write_text(json.dumps(metrics))
            args = SimpleNamespace(device='cpu', panel=str(panel), artifacts=str(root),
                                   out=str(root / 'forecast.json'), window=8, seeds=1, epochs=1)
            export(args)
            result = json.loads((root / 'forecast.json').read_text())
            self.assertEqual(result['forecasts'], {})
            self.assertIsNone(result['metrics']['screen_colorectal']['chosen'])
            self.assertFalse(result['trainedOn']['transformerRefitted'])
            self.assertEqual(result['evaluation']['indicators']['screen_colorectal']['export']['status'], 'WITHHELD')
            self.assertEqual(result['evaluation']['indicators']['screen_colorectal']['horizons']['h1']['status'], 'WITHHELD')


if __name__ == '__main__':
    unittest.main()
