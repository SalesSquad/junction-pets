"""Synthetic-only contract tests. Fake physics is never new-world outcome evidence."""
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


h = load('rokoko-mujoco-v13-original-qualification')
p = load('rokoko-mujoco-v13-original-retain-evidence')
v7 = load('rokoko-mujoco-v7-feasibility-qualification')
h.PLAN_SHA = 'b' * 64


def signature(env):
    return hashlib.sha256(str(env.seed).encode()).hexdigest()


class FakeEnv:
    def __init__(self, max_options=60):
        pass

    def reset(self, seed, ood):
        assert ood is False
        self.seed = seed
        self.done = False
        self.dwell = self.steps = self.physics_steps = self.contacts = 0
        self.obs = [0.] * 18
        self.obs[7] = .1 if seed - h.FIRST < 178 else .3
        return h.np.array(self.obs)

    def mask(self, obs):
        return h.np.ones(7, dtype=int)

    def step(self, action):
        self.done = True
        self.steps, self.physics_steps, self.contacts, self.dwell = 1, 100, 1, 251
        return h.np.array(self.obs), 1., True, dict(
            cost=0, contacts=1, success=True, unsafe=False, abstained=False, error=.01)


class Protocol:
    @staticmethod
    def derive_cohort(scans, plan):
        near = [r for r in scans if abs(r['observation'][7]) < .122][:40]
        clear = [r for r in scans if abs(r['observation'][7]) >= .122][:8]
        return [dict(seed=r['seed'], world_hash=r['world_hash'],
                     initial_public_obstacle_y=r['observation'][7], initial_mask=r['mask'],
                     observed_corridor=abs(r['observation'][7]) < .122)
                for r in sorted(near + clear, key=lambda r: r['seed'])]

    @staticmethod
    def paired_physical_goal_readout(trials, cohort, all_512_initial_public_worlds, plan):
        return dict(synthetic_only=True, count=len(trials))


FACTORIES = {a: (lambda action=(4 if a in h.ARMS[2:] else 0):
                  lambda: (lambda obs, mask: action))() for a in h.ARMS}


class Producer:
    MAX_OPTIONS = 60

    def __init__(self, fail_at=None, unsafe_at=None, readout=False):
        self.calls = []
        self.fail_at, self.unsafe_at = fail_at, unsafe_at

    def run_real_episode(self, env, seed, arm, factory, sig, deadline, source):
        obs = env.reset(seed, False).tolist()
        self.calls.append((seed, arm))
        unsafe = len(self.calls) == self.unsafe_at
        success = len(self.calls) != self.fail_at and not unsafe
        action = 4 if arm in h.ARMS[2:] else 0
        t = dict(observation=obs, next_observation=obs, mask=[1]*7, action=action,
                 reward=1., cost=int(unsafe), done=True, contacts_cumulative=1,
                 success_info=success, dwell_ticks_current=251 if success else 0,
                 dwell_ticks_cumulative=251 if success else 0)
        row = dict(seed=seed, strategy=arm, world_hash=sig(env), success=success,
                   unsafe=unsafe, abstained=False, contacts=1, final_error=.01,
                   dwell_ticks_final=251 if success else 0, physics_steps=100, full_transition_count=1, option_steps=1,
                   full_transition_sha256=h.digest([t]), transitions=[t])
        return row, [t]


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='v13-synthetic-',
                                               dir='/private/tmp' if Path('/private/tmp').is_dir() else None)
        self.root = Path(self.tmp.name)
        self.private = self.root / 'private'
        self.scans = h.scan_real_public_starts(FakeEnv(), signature)
        self.cohort = Protocol.derive_cohort(self.scans, {})
        self.survey = dict(selected_first40_near8_clear=[
            dict(seed=r['seed'], world_hash=r['world_hash'], near=r['observed_corridor'])
            for r in self.cohort])

    def test_science_requires_novel_burst_not_control_gain(self):
        def trial(arm, win, unsafe=False):
            return {'seed': 42, 'strategy': arm, 'success': win, 'unsafe': unsafe,
                    'abstained': False, 'contacts': 1,
                    'final_error': .01 if win else .1,
                    'terminal_dwell_ticks': 250 if win else 0}
        rows = {(42, arm): trial(arm, arm == h.ARMS[1]) for arm in h.ARMS}
        self.assertTrue(h.independent_science_gate(rows, 1).startswith('STOP'))
        rows[(42, h.ARMS[2])] = trial(h.ARMS[2], True)
        self.assertEqual(h.independent_science_gate(rows, 1),
                         'TRAIN_ONLY_SCIENCE_HYPOTHESIS_REQUIRES_NEW_REVIEW')
        self.assertTrue(h.independent_science_gate(rows, 0).startswith('STOP'))
        rows[(42, h.ARMS[3])] = trial(h.ARMS[3], False, unsafe=True)
        self.assertTrue(h.independent_science_gate(rows, 1).startswith('STOP'))

    def tearDown(self):
        self.tmp.cleanup()

    def run_original(self, fail=None, unsafe=None, protocol=Protocol):
        producer = Producer(fail, unsafe)
        result = h.run_pilot_originals(self.root, self.private, None, {}, None,
                   protocol, FACTORIES, producer, None, FakeEnv, signature, 'a'*40,
                   survey=self.survey)
        return result, producer

    def read_full(self):
        return h.verify_full_originals(self.private, 'a'*40, Protocol, {}, v7, self.survey)

    def qualify(self):
        self.run_original()
        training, manifest, readout, rows = self.read_full()
        replay = h.independent_true_physics_replay(
            self.private, training, rows, FACTORIES, v7, FakeEnv, signature)
        h.save_json_fresh(self.private / 'independent-qualification.json', {
            'schema': h.SCHEMA+'.independent-qualification', 'executed_head':'a'*40,
            'actual_trials':192, 'new_model_promotion_authorized':False,
            'dev_cal_test_ood_opened':False, 'original_sha256':manifest['file_sha256'],
            'full_192_real_episode_physics_replay': replay})
        return training, rows, replay

    def test_frozen_constants(self):
        self.assertEqual((h.FIRST,h.SCAN,h.EXPECTED),(519024,512,192))
        self.assertEqual(h.ARMS, ('frozen_v5','v12_phase_dwell_supported_actions',
                                'train_only_right4_burst2','train_only_right4_burst4'))
        self.assertEqual(h.MODEL_SHA, '82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e')

    def test_known_preflight(self):
        # Exact public survey from product source faec266; verify_preflight checks its frozen SHA.
        d = h.verify_preflight(HERE / 'fixtures' / 'rokoko-v13-world-survey.json')
        self.assertEqual(d['near_count'],178)

    def test_preflight_tamper(self):
        path=self.root/'survey.json'; path.write_text('{}')
        with self.assertRaisesRegex(AssertionError,'PREFLIGHT_SHA'):
            h.verify_preflight(path)

    def test_scan_512_public(self):
        self.assertEqual(self.scans[-1]['seed'],519535)
        self.assertEqual(sum(abs(r['observation'][7])<.122 for r in self.scans),178)
        h.verify_public_preflight(self.scans,self.cohort,self.survey)

    def test_cohort_order(self):
        self.assertTrue(h.independent_first_public_cohort(self.scans,self.cohort))
        with self.assertRaises(AssertionError):
            h.independent_first_public_cohort(self.scans,list(reversed(self.cohort)))

    def test_old_seed_refusal(self):
        self.scans[0]['seed']=518000
        with self.assertRaisesRegex(AssertionError,'CANONICAL_519024'):
            h.independent_first_public_cohort(self.scans,self.cohort)

    def test_invalid_520000_refusal(self):
        self.scans[0]['seed']=520000
        with self.assertRaises(AssertionError):
            h.independent_first_public_cohort(self.scans,self.cohort)

    def test_mask_legality(self):
        self.scans[0]['mask']=[0]*7
        with self.assertRaises(AssertionError):
            h.independent_first_public_cohort(self.scans,self.cohort)

    def test_goal_boolean_spoof(self):
        row=dict(success=True,unsafe=False,abstained=False)
        self.assertFalse(h.safe_goal(row))
        row.update(contacts=1, final_error=.01, terminal_dwell_ticks=251)
        self.assertTrue(h.safe_goal(row))
        for key,value in [('contacts',0),('final_error',.02),('terminal_dwell_ticks',249),
                          ('unsafe',True),('abstained',True)]:
            changed=dict(row);changed[key]=value
            self.assertFalse(h.safe_goal(changed))

    def test_first_unsafe_stop(self):
        result,producer=self.run_original(unsafe=1)
        self.assertEqual(result['completed_episodes'],1)
        self.assertEqual(len(producer.calls),1)
        self.assertFalse(result['complete'])
        p.publish_early_stop(self.private,self.root/'collector')

    def test_each_nonbaseline_loss_stops(self):
        for index in (2,3,4):
            with self.subTest(index=index):
                if self.private.exists():
                    self.private=self.root/str(index)
                result,producer=self.run_original(fail=index)
                self.assertEqual(result['completed_episodes'],index)
                self.assertEqual(result['reason'],'NONBASELINE_LOST_ACTUAL_FROZEN_V5_GOAL')

    def test_final_192nd_loss_lossless(self):
        result,producer=self.run_original(fail=192)
        self.assertEqual(result['completed_episodes'],192)
        archive=self.root/'collector'
        packed=p.publish_early_stop(self.private,archive)
        self.assertEqual(packed['original_sha256']['full_transitions.jsonl.gz'],
                         h.sha(self.private/'full_transitions.jsonl.gz'))
        with gzip.open(self.private/'full_transitions.jsonl.gz','rt') as f:
            rows=[json.loads(x) for x in f]
        self.assertEqual(len(rows),192)
        self.assertEqual(rows[-1]['strategy'],h.ARMS[-1])

    def test_readout_failure_192_preserved(self):
        class Bad(Protocol):
            @staticmethod
            def paired_physical_goal_readout(*args,**kwargs):
                raise ValueError('synthetic error')
        result,_=self.run_original(protocol=Bad)
        self.assertEqual(result['completed_episodes'],192)
        self.assertFalse(result['complete'])
        p.publish_early_stop(self.private,self.root/'collector')

    def test_full192_same_hash_replay(self):
        training,rows,replay=self.qualify()
        self.assertEqual(replay['exact_real_full_options_replayed'],192)
        self.assertTrue(replay['all_192_complete_real_episodes_replayed'])
        self.assertEqual(replay['untrained_right4_actual_legal_executions'],96)
        self.assertFalse(replay['promotion_authorized'])
        p.publish_qualified(self.private,self.root/'collector')

    def test_same_digest_does_not_replace_physics(self):
        self.run_original()
        training,_,_,rows=self.read_full()
        class Drift(FakeEnv):
            def step(self,action):
                obs,reward,done,info=super().step(action)
                self.dwell=250
                return obs,reward,done,info
        with self.assertRaisesRegex(AssertionError,'TRANSITION_DIVERGED'):
            h.independent_true_physics_replay(self.private,training,rows,FACTORIES,v7,Drift,signature)

    def test_wrong_policy_replay_rejected(self):
        self.run_original(); training,_,_,rows=self.read_full()
        factories={a:lambda:lambda obs,mask:6 for a in h.ARMS}
        with self.assertRaisesRegex(AssertionError,'POLICY_ACTION'):
            h.independent_true_physics_replay(self.private,training,rows,factories,v7,FakeEnv,signature)

    def test_raw_hash_tamper(self):
        self.run_original()
        with (self.private/'full_transitions.jsonl.gz').open('ab') as f: f.write(b'x')
        with self.assertRaisesRegex(AssertionError,'FILE_SHA'):
            self.read_full()

    def test_zip_tamper(self):
        self.run_original(fail=2); out=self.root/'collector'
        p.publish_early_stop(self.private,out)
        manifest=json.loads((out/'retention-manifest.json').read_text())
        archive=out/manifest['sources'][0]['parts'][0]['archive']
        with archive.open('ab') as f:f.write(b'x')
        with self.assertRaises(AssertionError):p.verify_reassembled(out,manifest)

    def test_source_symlink(self):
        self.run_original(fail=2)
        path=self.private/'partial_training.json'; outside=self.root/'outside'
        path.rename(outside);path.symlink_to(outside)
        with self.assertRaises(AssertionError):p.publish_early_stop(self.private,self.root/'collector')

    def test_collector_alias(self):
        self.run_original(fail=2);alias=self.root/'alias';alias.symlink_to(self.private)
        with self.assertRaises(AssertionError):p.publish_early_stop(self.private,alias/'collector')

    def test_no_promotion(self):
        self.qualify()
        path=self.private/'independent-qualification.json'
        doc=json.loads(path.read_text());doc['new_model_promotion_authorized']=True
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(AssertionError,'NOT_INDEPENDENTLY'):
            p.publish_qualified(self.private,self.root/'collector')

    def test_failure_archive(self):
        self.run_original()
        h.save_json_fresh(self.private/'failure.json',dict(schema=h.SCHEMA+'.qualification-failure',
                          executed_head='a'*40,promotion_authorized=False))
        p.publish_failure(self.private,self.root/'collector')
        doc=json.loads((self.root/'collector/retention-manifest.json').read_text())
        self.assertEqual(doc['status'],'UNQUALIFIED_FAILURE')

    def test_credit_cutoff_and_reserve(self):
        env=dict(CRACI_WORKLOAD='rokoko-mujoco-v13-pilot',CRACI_CREDIT_WINDOW_OPEN='true',
                 CRACI_CREDIT_REMAINING_SECONDS='7200',CRACI_MANUAL_SOURCE_REVIEWED='true')
        for stage in ('full', 'original'):
            h.admission(env,h.CUTOFF-7200,stage)
            with self.assertRaises(AssertionError):h.admission(env,h.CUTOFF-7199,stage)
        # A qualifying child that starts within the 60-minute job timeout
        # still clears the original one-hour gate at the exact boundary.
        h.admission(env,h.CUTOFF-3600,'qualify')
        with self.assertRaises(AssertionError):h.admission(env,h.CUTOFF-3599,'qualify')
        for key,value in [('CRACI_WORKLOAD','rokoko-mujoco-v13-original'),
                          ('CRACI_CREDIT_WINDOW_OPEN','false'),
                          ('CRACI_MANUAL_SOURCE_REVIEWED','false'),
                          ('CRACI_CREDIT_REMAINING_SECONDS','7199')]:
            with self.assertRaises(AssertionError):
                h.admission({**env,key:value},h.CUTOFF-7200,'full')
        with self.assertRaises(AssertionError):h.admission(env,h.CUTOFF-7200,'unknown')

    def test_missing_product_no_fallback(self):
        with self.assertRaises(AssertionError):h.load_module(self.root/'absent.py','missing')

    def test_full_prefix_baseline_order(self):
        self.run_original(fail=2)
        doc=json.loads((self.private/'partial_training.json').read_text())
        doc['complete_real_trial_rows'].reverse()
        with self.assertRaisesRegex(AssertionError,'PREFIX'):
            p.validate_original_rows(doc,doc['complete_real_trial_rows'],self.private)

    def test_original_v7_goal_threshold_250_exactly_matches_source(self):
        plan=dict(strategies=list(h.ARMS), expectedTrials=192,
                  trainSeedRangeInclusive=[519024,519535], modelPromotionAuthorized=False,
                  devCalTestOodOpened=False, trialFields=list(h.PROTOCOL_FIELDS),
                  contactGoal=dict(minimumActualContactDwellTicks=250))
        # The frozen V7 real physics gate is >=250, not >250; do NOT shift it.
        h.validate_plan_contract(plan)
        for wrong in (249, 251):
            plan['contactGoal']['minimumActualContactDwellTicks']=wrong
            with self.assertRaisesRegex(AssertionError,'V7_GOAL_MINIMUM_250'):
                h.validate_plan_contract(plan)

    def test_explicit_compact_protocol_projection(self):
        self.run_original(); training,_,_,_=self.read_full()
        compact=h.protocol_trials(training['trials'])
        self.assertEqual(set(compact[0]),set(h.PROTOCOL_FIELDS))
        self.assertEqual(compact[0]['contact_dwell_ticks'],251)
        self.assertEqual(compact[0]['final_error_m'],.01)
        self.assertIn('full_transition_sha256',training['trials'][0])

    def test_zip_symlink_entry_even_rehashed_rejected(self):
        self.run_original(fail=2); out=self.root/'collector'
        p.publish_early_stop(self.private,out)
        manifest=json.loads((out/'retention-manifest.json').read_text())
        part=manifest['sources'][0]['parts'][0]; archive=out/part['archive']
        with zipfile.ZipFile(archive) as z: raw=z.read(part['entry'])
        info=zipfile.ZipInfo(part['entry']);info.create_system=3
        info.external_attr=(0o120777 << 16)
        with zipfile.ZipFile(archive,'w') as z:z.writestr(info,raw)
        part['archive_bytes']=archive.stat().st_size
        part['archive_sha256']=h.sha(archive)
        with self.assertRaisesRegex(AssertionError,'ZIP_SYMLINK'):
            p.verify_reassembled(out,manifest)

    def test_source_hardlink_refused(self):
        self.run_original(fail=2)
        os.link(self.private/'partial_training.json',self.root/'alias.json')
        with self.assertRaisesRegex(AssertionError,'HARDLINK'):
            p.publish_early_stop(self.private,self.root/'collector')

    def test_old_cohort_refused_by_v13_retention(self):
        self.run_original(fail=2)
        path=self.private/'partial_training.json'
        data=json.loads(path.read_text());data['all_512_public_initial_scans'][0]['seed']=518000
        path.write_bytes(h.canonical(data))
        stop_path=self.private/'early_stop.json'
        stop=json.loads(stop_path.read_text());stop['raw_sha256']['partial_training.json']=h.sha(path)
        stop_path.write_bytes(h.canonical(stop))
        with self.assertRaisesRegex(AssertionError,'CANONICAL_519024'):
            p.publish_early_stop(self.private,self.root/'collector')

    def test_retention_manifest_symlink_rejected(self):
        self.run_original(fail=2); out=self.root/'collector'
        p.publish_early_stop(self.private,out)
        path=out/'retention-manifest.json'; manifest=json.loads(path.read_text())
        outside=self.root/'outside.json';path.rename(outside);path.symlink_to(outside)
        with self.assertRaisesRegex(AssertionError,'SYMLINK'):
            p.verify_reassembled(out,manifest)

    def test_full_run_cannot_ignore_stop_even_with_rehashed_rows(self):
        self.run_original()
        path=self.private/'training.json'; training=json.loads(path.read_text())
        training['trials'][1]['success']=False
        path.write_bytes(h.canonical(training))
        path=self.private/'manifest.json'; manifest=json.loads(path.read_text())
        manifest['file_sha256']['training.json']=h.sha(self.private/'training.json')
        path.write_bytes(h.canonical(manifest))
        with self.assertRaisesRegex(AssertionError,'IGNORED_IMMEDIATE_STOP'):
            self.read_full()


if __name__=='__main__':unittest.main()
