"""Tests for the event-log extension and the county worklist join. SYNTHETIC data only."""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds

from eventlog import schema
from safetynet import extension, worklist

ROOT = Path(__file__).resolve().parents[2]
T = date(2025, 12, 1)
# Wording the project never uses; assembled from parts so repository text scans do not match this guard.
FORBIDDEN = tuple(' '.join(p).replace(' - ', '-') for p in (('auto', '-', 'confirmed'), ('skips', 'review'),
                                                             ('clinically', 'accurate'), ('works on', 'real notes')))


def write_log(root: Path, episodes):
    """episodes: list of (episode_id, county, route, age_band, {event_type: date})."""
    rows = []
    for eid, county, route, band, events in episodes:
        for et, d in events.items():
            rows.append(dict(episode_id=eid, event_type=et, event_date=d, date_precision='DAY', county=county,
                             entry_route=route, cancer_site='lung', age_band=band, source='STRUCTURED_FIELD',
                             extraction_confidence=None, verified_by_human=False, synthetic=True))
    t = schema.events_table(rows)
    t = t.append_column('year', pa.array([2025] * t.num_rows, pa.int16()))
    t = t.set_column(t.schema.get_field_index('county'), 'county', pa.array([str(x) for x in t['county'].to_pylist()]))
    part = ds.partitioning(pa.schema([('year', pa.int16()), ('county', pa.string())]), flavor='hive')
    ds.write_dataset(t, str(root), format='parquet', partitioning=part)


def ref(sent, dx=None, county='HVA06', eid='E1', band='70-74'):
    return dict(loop_kind='suspected_cancer_referral', loop_id=eid, county=county, entry_route='PUBLIC_PRIMARY',
                age_band=band, cancer_site='lung', referral_sent=sent, diagnosis=dx, synthetic=True)


def img(report, outcome='DUE_DATE', due=None, done=None, county='HVA06', lid='L1'):
    return dict(loop_id=lid, county=county, entry_route='PUBLIC_PRIMARY', age_band='60-64', contact_language='fi',
                interpreter=False, report_line_id='X', report_date=report, report_text='SYNTHETIC',
                rule_outcome=outcome, rule_reason='interval', rule_due_date=due, recommendation_copied='Kontrolli-TT 3 kk kuluttua.',
                gold_outcome=outcome, gold_due_date=due, followup_done_date=done, synthetic=True)


class ReferralClock(unittest.TestCase):
    def test_states(self):
        self.assertIsNone(worklist.referral_state(ref(T + timedelta(days=1)), T))
        s = worklist.referral_state(ref(T - timedelta(days=50)), T)
        self.assertEqual((s['open'], s['overdue'], s['days_overdue'], s['clock_passed']), (True, True, 8, True))
        s = worklist.referral_state(ref(T - timedelta(days=42)), T)
        self.assertEqual((s['open'], s['overdue']), (True, False))
        s = worklist.referral_state(ref(T - timedelta(days=60), T - timedelta(days=30)), T)
        self.assertEqual((s['open'], s['closed_by_threshold']), (False, True))
        s = worklist.referral_state(ref(T - timedelta(days=60), T - timedelta(days=5)), T)
        self.assertEqual((s['open'], s['overdue'], s['closed_by_threshold']), (False, False, False))
        # A diagnosis dated after the replay date has not happened yet.
        s = worklist.referral_state(ref(T - timedelta(days=60), T + timedelta(days=5)), T)
        self.assertEqual((s['open'], s['overdue']), (True, True))
        self.assertTrue(worklist.referral_state(ref(T - timedelta(days=95)), T, 90)['overdue'])


class ImagingClock(unittest.TestCase):
    def test_states(self):
        r = T - timedelta(days=120)
        self.assertIsNone(worklist.imaging_state(img(T + timedelta(days=1), due=T + timedelta(days=90)), T))
        self.assertIsNone(worklist.imaging_state(img(r, outcome='NONE'), T))
        s = worklist.imaging_state(img(r, due=T - timedelta(days=10)), T)
        self.assertEqual((s['open'], s['overdue'], s['days_overdue'], s['due_passed'], s['done_by_due']), (True, True, 10, True, False))
        s = worklist.imaging_state(img(r, due=T - timedelta(days=10), done=T + timedelta(days=3)), T)
        self.assertTrue(s['overdue'])
        s = worklist.imaging_state(img(r, due=T - timedelta(days=10), done=T - timedelta(days=12)), T)
        self.assertEqual((s['open'], s['overdue'], s['done_by_due']), (False, False, True))
        s = worklist.imaging_state(img(r, due=T + timedelta(days=30)), T)
        self.assertEqual((s['open'], s['overdue'], s['due_passed']), (True, False, False))
        s = worklist.imaging_state(img(T - timedelta(days=3), outcome='PERSON'), T)
        self.assertEqual((s['kind'], s['awaiting_person'], s['overdue']), ('recommendation_needs_person', True, False))
        self.assertFalse(worklist.imaging_state(img(T - timedelta(days=30), outcome='PERSON'), T)['open'])


class CountyPanel(unittest.TestCase):
    def test_counts_then_three_rows(self):
        refs = [ref(T - timedelta(days=60), eid='A'), ref(T - timedelta(days=50), eid='B', band='0-4'),
                ref(T - timedelta(days=80), T - timedelta(days=70), eid='C'), ref(T - timedelta(days=10), eid='D'),
                ref(T - timedelta(days=70), county='HVA05', eid='E')]
        imgs = [img(T - timedelta(days=200), due=T - timedelta(days=20), lid='I1'),
                img(T - timedelta(days=200), due=T - timedelta(days=20), done=T - timedelta(days=25), lid='I2'),
                img(T - timedelta(days=2), outcome='PERSON', lid='I3'),
                img(T - timedelta(days=10), due=T + timedelta(days=80), lid='I4')]
        p = worklist.county_panel('HVA06', refs, imgs, T)
        c = p['counts']
        self.assertEqual(c['referral'], dict(open=3, overdue=2, overdue_at_sensitivity_days=0, clock_passed=3,
                                             diagnosed_by_threshold=1, share_diagnosed_by_threshold=round(1 / 3, 4)))
        self.assertEqual((c['imaging']['open'], c['imaging']['overdue'], c['imaging']['due_passed'],
                          c['imaging']['done_by_due'], c['imaging']['awaiting_person']), (2, 1, 2, 1, 1))
        self.assertEqual((c['open_loops'], c['overdue']), (6, 3))
        ex = p['examples']
        self.assertLessEqual(len(ex), 3)
        self.assertEqual([e['loop_kind'] for e in ex], ['imaging_follow_up', 'suspected_cancer_referral', 'recommendation_needs_person'])
        self.assertEqual(ex[1]['episode_code'], 'A')  # most overdue adult referral; B is age 0-4
        self.assertEqual([e['status'] for e in ex], ['nurse confirms', 'nurse confirms', 'needs editing'])
        for e in ex:
            self.assertTrue(e['synthetic'])
            for k in ('episode_code', 'age_band', 'route', 'days_overdue', 'missing_step', 'owner_role', 'status', 'contact_language', 'interpreter'):
                self.assertIn(k, e)
        self.assertEqual(sum(r['open'] for r in p['by_route']), 6)
        self.assertEqual(sum(r['open'] for r in p['by_language']), 6)


class JoinWithEventLog(unittest.TestCase):
    def test_read_mini_log_and_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            eps = [(f'SYNTHETIC-T-HVA06-{i}', 'HVA06', 'PUBLIC_PRIMARY' if i % 2 else 'OCCUPATIONAL', '60-64',
                    dict(SYMPTOM_ONSET_REPORTED=date(2025, 3, 1), REFERRAL_SENT=date(2025, 4, 1),
                         **({'DIAGNOSIS': date(2025, 4, 20)} if i % 3 else {}))) for i in range(8)]
            eps += [(f'SYNTHETIC-T-HVA05-{i}', 'HVA05', 'PRIVATE', '50-54', dict(SYMPTOM_ONSET_REPORTED=date(2025, 3, 1))) for i in range(4)]
            write_log(Path(tmp), eps)
            episodes = extension.read_event_log(Path(tmp))
            self.assertEqual(len(episodes), 12)
            refs = extension.referral_loops(episodes)
            self.assertEqual(len(refs), 8)
            self.assertEqual(sum(r['diagnosis'] is None for r in refs), 3)
            cohort = extension.imaging_cohort(episodes, T)
            self.assertEqual(sum(x['county'] == 'HVA06' for x in cohort), 2)
            self.assertEqual(sum(x['county'] == 'HVA05' for x in cohort), 1)
            self.assertEqual({x['entry_route'] for x in cohort if x['county'] == 'HVA05'}, {'PRIVATE'})
            self.assertTrue(all(x['synthetic'] and x['report_date'] <= T for x in cohort))
            self.assertEqual(cohort, extension.imaging_cohort(episodes, T))
            table = extension.imaging_table(cohort)
            self.assertEqual(table.schema, extension.imaging_loops_schema)

    def test_real_sample_join(self):
        episodes = extension.read_event_log(ROOT / 'data/eventlog/sample')
        self.assertEqual(len(episodes), 20000)
        refs = extension.referral_loops(episodes)
        self.assertEqual(len(refs), 19792)  # REFERRAL_SENT events in data/eventlog/sample
        self.assertTrue(all(r['diagnosis'] is None or r['diagnosis'] >= r['referral_sent'] for r in refs))

    def test_schema_untouched(self):
        self.assertEqual(len(schema.EVENT_TYPES), 9)
        self.assertFalse(set(extension.EXT_EVENT_TYPES) & set(schema.EVENT_TYPES))


class BuiltPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = ROOT / 'data/safetynet/safetynet-v1.json'
        if not p.exists():
            raise unittest.SkipTest('run python -m safetynet.build first')
        cls.text = p.read_text()
        cls.data = json.loads(cls.text)

    def test_shape_and_labels(self):
        d = self.data
        self.assertTrue(d['synthetic'])
        self.assertEqual(d['dataClass'], 'SYNTHETIC')
        self.assertEqual(d['pilotRegionId'], 'HVA06')
        self.assertEqual(len(d['counties']), 23)
        for c in d['counties']:
            self.assertLessEqual(len(c['examples']), 3)
            self.assertTrue(all(e['synthetic'] for e in c['examples']))
        self.assertEqual(d['national']['open_loops'], sum(c['counts']['open_loops'] for c in d['counties']))
        self.assertEqual(d['national']['overdue'], sum(c['counts']['overdue'] for c in d['counties']))
        self.assertIn('PLACEHOLDER', {t['label'] for t in d['thresholds']})
        self.assertTrue(all('DESIGN' in k['target'] for k in d['kpis']))
        self.assertIn('Scope for pathway timing to be confirmed with STM/THL', d['text']['legal'])
        self.assertIn('1 June 2026', d['text']['legal'])

    def test_cohort_rule_errors_only_in_the_safe_direction(self):
        c = self.data['cohort']['imaging_loops']
        e = c['errors']
        self.assertEqual((e['wrong_due_date'], e['invented_date_for_person_line'], e['invented_date_for_none_line'],
                          e['missed_recommendation']), (0, 0, 0, 0))
        self.assertEqual(sum(c['due_line_sent_to_person_reasons'].values()), e['due_line_sent_to_person'])
        self.assertEqual(c['rule_matches_gold'] + e['due_line_sent_to_person'], c['loops'])

    def test_forbidden_wording_absent(self):
        low = self.text.lower()
        for w in FORBIDDEN:
            self.assertNotIn(w, low)


if __name__ == '__main__':
    unittest.main()
