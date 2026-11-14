"""Tests for the forward-phrase rule (safetynet.rule) and its 60-line SYNTHETIC evaluation."""
import hashlib
import json
import unittest
from datetime import date
from pathlib import Path

from safetynet import rule
from safetynet.measure import evaluate
from safetynet.reports import render

ROOT = Path(__file__).resolve().parents[2]
R = date(2025, 1, 31)


def read(text, d=R):
    return rule.read(text, d)


class DueDates(unittest.TestCase):
    def check(self, text, due, d=R):
        r = read(text, d)
        self.assertEqual(r['outcome'], rule.DUE_DATE, (text, r))
        self.assertEqual(r['due_date'], due, text)
        s, e = r['span']
        self.assertEqual(text[s:e], r['matched_phrase'])
        self.assertIn(r['recommendation_text'], text)

    def test_digits_months_clamped_to_month_end(self):
        self.check('Suositellaan kontrolli-TT 3 kk kuluttua.', '2025-04-30')
        self.check('Kontrolli-TT 1 kk kuluttua.', '2025-02-28')
        self.check('Kontrolli-TT 1 kk kuluttua.', '2024-02-29', date(2024, 1, 31))

    def test_word_forms(self):
        self.check('Kontrolli-TT kuuden kuukauden kuluttua.', '2025-07-31')
        self.check('Seuranta-TT kahdentoista kuukauden kuluttua.', '2026-01-31')
        self.check('Uusinta-TT vuoden kuluttua.', '2026-01-31')
        self.check('Seuranta-TT kahden vuoden päästä.', '2027-01-31')
        self.check('Kontrolli-TT puolen vuoden kuluttua.', '2025-07-31')
        self.check('Kontrolli-TT 6 kk:n päästä.', '2025-07-31')

    def test_weeks_and_attributive_and_calendar(self):
        self.check('Kontrollikuvaus 4 viikon kuluttua.', '2025-02-28')
        self.check('Suositellaan 3 kk:n kontrolli-TT.', '2025-04-30')
        self.check('Kontrolli-TT 15.3.2026.', '2026-03-15')

    def test_backward_phrases_and_past_dates_are_ignored(self):
        self.check('Kyhmy ennallaan verrattuna 12 kk sitten otettuun TT:hen. Kontrolli-TT 6 kk kuluttua.', '2025-07-31')
        self.check('Kasvanut verrattuna 3.10.2024 tutkimukseen. Kontrolli-TT 3 kk kuluttua.', '2025-04-30')

    def test_en_dash_normalisation_keeps_offsets(self):
        text = 'Löydös – ei muutoksia. Kontrolli-TT 3 kk kuluttua.'
        r = read(text)
        self.assertEqual(text[r['span'][0]:r['span'][1]], '3 kk kuluttua')


class ToPerson(unittest.TestCase):
    def test_person(self):
        cases = {
            'Kontrolli-TT 3–6 kk kuluttua.': 'range',
            'Kontrolli-TT 3-6 kk kuluttua.': 'range',
            'Seuranta-TT kolmen tai kuuden kuukauden kuluttua.': 'range',
            'Kontrolli-TT noin 3 kk kuluttua.': 'vague_or_conditional',
            'Kontrolli-TT n. 6 kk kuluttua.': 'vague_or_conditional',
            'Kontrolli harkinnan mukaan.': 'vague_or_conditional',
            'Seuranta-TT myöhemmin.': 'vague_or_conditional',
            'Kontrolli-TT parin kuukauden kuluttua.': 'vague_or_conditional',
            'Mikäli kliinisesti aiheellista, kontrolli-TT 3 kk kuluttua.': 'vague_or_conditional',
            'Jos oireet jatkuvat, uusintakuvaus.': 'vague_or_conditional',
            'Kontrolli-TT maaliskuussa 2026.': 'month_without_day',
            'Kontrolli-TT 1,5 v kuluttua.': 'decimal_interval',
            'Kontrolli-TT 3 kk kuluttua ja ultraäänitutkimus 6 kk kuluttua.': 'several_time_expressions',
            'Suositellaan kontrolli-TT:tä.': 'recommendation_without_time',
            'Ei jatkotoimia. Kontrolli-TT 3 kk kuluttua.': 'no_followup_and_followup_both_written',
            'Edellinen 3 kk:n kontrolli-TT oli normaali.': 'backward_reference',
            'Kontrolli-TT 31.2.2026.': 'invalid_calendar_date',
        }
        for text, reason in cases.items():
            r = read(text)
            self.assertEqual((r['outcome'], r['reason']), (rule.PERSON, reason), text)
            self.assertIsNone(r['due_date'], text)


class NoFollowUp(unittest.TestCase):
    def test_none(self):
        for text in ['Ei jatkotoimia.', 'Ei kontrollitarvetta.', 'Kontrollia ei tarvita.', 'Ei seurantatarvetta.',
                     'Kalkkeutunut granulooma, ennallaan verrattuna 12 kk sitten otettuun TT:hen. Ei jatkotoimia.']:
            r = read(text)
            self.assertEqual((r['outcome'], r['reason']), (rule.NONE, 'explicit_no_followup'), text)
        self.assertEqual(read('Keuhkot normaalit.')['reason'], 'no_recommendation_found')


class SixtyLines(unittest.TestCase):
    def test_sixty_synthetic_lines(self):
        lines = render()
        self.assertEqual(len(lines), 60)
        self.assertEqual(len({x['line_id'] for x in lines}), 60)
        self.assertTrue(all(x['synthetic'] and x['language'] == 'fi' for x in lines))
        self.assertEqual({g: sum(x['gold_outcome'] == g for x in lines) for g in rule.OUTCOMES},
                         dict(DUE_DATE=30, PERSON=20, NONE=10))
        self.assertEqual(render(), lines)

    def test_frozen_rule_result(self):
        m = evaluate()['metrics']
        self.assertEqual((m['exact_due_date']['k'], m['exact_due_date']['n']), (30, 30))
        self.assertEqual((m['sent_to_person_when_gold_person']['k'], m['sent_to_person_when_gold_person']['n']), (20, 20))
        self.assertEqual(m['errors'], dict(wrong_due_date=0, invented_date_for_person_line=0, invented_date_for_none_line=0,
                                           missed_recommendation=0, due_line_sent_to_person=0))
        self.assertEqual(m['copied_verbatim']['k'], 60)

    def test_rule_file_matches_frozen_hash(self):
        frozen = [json.loads(l) for l in (ROOT / 'runs/ship-safetynet.jsonl').read_text().splitlines()
                  if l.strip() and json.loads(l).get('step') == '1-rule-frozen']
        self.assertTrue(frozen, 'no frozen-rule receipt')
        self.assertEqual(hashlib.sha256((ROOT / 'safetynet/rule.py').read_bytes()).hexdigest(), frozen[0]['sha256'])


if __name__ == '__main__':
    unittest.main()
