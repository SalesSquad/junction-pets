"""Synthetic regressions on exact V12 original raw, no CRACI dispatch or physics rerun."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from core import (ARTIFACT_SHA, FUTURE_START, FUTURE_END, SOURCE, HARNESS,
                  EvidenceRejected, ARMS, canonical, compile_decision,
                  read_original_hosted, sha, validate_historical_safety,
                  verify_raw)


class V3FeedbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deliberately supplied via env/runner or scratch: the original
        # GitHub artifact is NOT bundled or committed with this source.
        import os
        artifact = os.environ.get('CRACI_V12_ORIGINAL_ZIP')
        if not artifact:
            raise RuntimeError('CRACI_V12_ORIGINAL_ZIP is required for these source-bound tests')
        cls.path = Path(artifact)
        cls.bundle = read_original_hosted(cls.path)

    def test_original_zip_full_raw_and_source_identity(self):
        self.assertEqual(sha(self.path.read_bytes()), ARTIFACT_SHA)
        result = verify_raw(self.bundle)
        self.assertEqual((result['real_episodes'],result['full_real_options']), (144,4228))
        self.assertEqual((result['baseline_goal250'],result['candidate_goal250'],
                          result['exploration_goal250']), (12,12,12))
        self.assertEqual((result['candidate_novel'],result['candidate_lost'],
                          result['candidate_unsafe'],result['exploration_unsafe']), ([],[],[],[]))
        self.assertEqual((result['right4_executed'],result['right4_distinct_worlds']), (31,31))

    def test_hosted_zip_sha_tamper_rejected(self):
        contents = bytearray(self.path.read_bytes())
        contents[len(contents)//3] ^= 0x01
        with tempfile.TemporaryDirectory(prefix='craci-v3-tamper-') as tmp:
            path = Path(tmp)/'tampered.zip'
            path.write_bytes(contents)
            with self.assertRaisesRegex(EvidenceRejected,'HOSTED_ZIP_SHA_DRIFT'):
                read_original_hosted(path)

    def test_fake_goal250_rejected_even_with_recomputed_transition_sha(self):
        fake = deepcopy(self.bundle)
        target = next(row for row in fake['training']['trials']
                      if row['seed'] == 518003 and row['strategy'] == ARMS[1])
        stream = next(row for row in fake['transitions']
                      if row['seed'] == 518003 and row['strategy'] == ARMS[1])
        self.assertFalse(target['success'])
        self.assertLess(stream['transitions'][-1]['dwell_ticks_cumulative'],250)
        target['success'] = True
        stream['transitions'][-1]['success_info'] = True
        target['full_transition_sha256'] = sha(canonical(stream['transitions']))
        target['transitions'] = [stream['transitions'][index] for index in target['sparse_transition_indices']]
        with self.assertRaisesRegex(EvidenceRejected,'FAKE_GOAL250_WITHOUT_REAL_CONTACT_DWELL'):
            verify_raw(fake)

    def test_tampered_world_hash_or_public_cohort_refused(self):
        fake = deepcopy(self.bundle)
        fake['training']['cohort'][0]['world_hash'] = '0'*64
        with self.assertRaisesRegex(EvidenceRejected,'COHORT_PUBLIC_WORLD_DRIFT'):
            verify_raw(fake)

    def test_old_v10_safety_regression_stays_blocking(self):
        old = deepcopy(self.bundle['old_feedback'])
        old['paired_goal250']['unsafe'] = 1
        with self.assertRaisesRegex(EvidenceRejected,'HISTORICAL_V10_V11_SAFETY_REGRESSION'):
            validate_historical_safety(old)
        old = deepcopy(self.bundle['old_feedback'])
        old['paired_goal250']['lost'] = 1
        with self.assertRaisesRegex(EvidenceRejected,'HISTORICAL_V10_V11_SAFETY_REGRESSION'):
            validate_historical_safety(old)

    def test_sealed_split_test_ood_and_promotion_refused(self):
        for field,value in [('no_dev_test_ood',False),('model_promotion_authorized',True)]:
            fake = deepcopy(self.bundle)
            fake['training'][field] = value
            with self.assertRaisesRegex(EvidenceRejected,'FORBIDDEN_SPLIT_OR_PROMOTION'):
                verify_raw(fake)

    def test_frozen_v13_train_seeds_obey_original_guard(self):
        decision = compile_decision(self.bundle)
        cohort = decision['next_training_decision']['frozen_new_train_cohort']
        self.assertEqual((cohort['first_seed'],cohort['last_seed_inclusive']),
                         (FUTURE_START,FUTURE_END))
        self.assertEqual((FUTURE_START,FUTURE_END),(519024,519535))
        self.assertEqual(FUTURE_END-FUTURE_START+1,512)
        self.assertLess(FUTURE_END,520000)
        self.assertTrue(cohort['original_contact_env_guard_unchanged'])
        self.assertTrue(decision['next_training_decision']['no_dispatch_authorization'])
        self.assertFalse(decision['dispatch_authorized'])
        self.assertFalse(decision['model_promotion_authorized'])
        self.assertEqual(decision['evidence']['source_sha'],SOURCE)
        self.assertEqual(decision['evidence']['harness_sha'],HARNESS)
        self.assertEqual(decision['decision'],'SCIENCE_STOP_NO_PROMOTION')

    def test_ranked_witnesses_bind_to_original_seed_world_hash_action(self):
        decision = compile_decision(self.bundle)
        scans = {row['seed']:row for row in self.bundle['training']['cohort']}
        cases=decision['next_training_decision']['ranked_hypotheses']
        self.assertEqual([row['rank'] for row in cases],[1,2,3,4])
        for hypothesis in cases:
            self.assertFalse(hypothesis['counterfactual_effect_observed'])
            self.assertTrue(hypothesis['requires_new_real_physics_intervention'])
            for witness in hypothesis['observed_train_witnesses']:
                self.assertIn(witness['seed'],scans)
                self.assertEqual(witness['world_hash'],scans[witness['seed']]['world_hash'])
                self.assertTrue(1<=witness['option']<=60)
                self.assertTrue(0<=witness['action']<=6)
                self.assertEqual(witness['mask_legal'],1)
                self.assertEqual(len(witness['transition_sha256']),64)

    def test_original_replay_decision_is_byte_deterministic(self):
        first = canonical(compile_decision(self.bundle)) + b'\n'
        second = canonical(compile_decision(self.bundle)) + b'\n'
        self.assertEqual(first,second)
        self.assertEqual(sha(first),sha(second))
        self.assertEqual(compile_decision(self.bundle)['evidence']['actual_spend_eur'],None)
        self.assertEqual(compile_decision(self.bundle)['evidence']['signed_provider_attestation'],False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
