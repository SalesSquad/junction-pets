"""Synthetic GOOD/BAD contracts only; source fixtures are never physics evidence."""
import copy
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v12_harness_contract', HERE / 'rokoko-mujoco-v12-pilot-qualification.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class HostContract(unittest.TestCase):
    def test_live_hour_credit_and_manual_exact_source_required(self):
        env = dict(CRACI_CREDIT_WINDOW_OPEN='true', CRACI_WINDOW_END='2026-11-15T17:00:00Z',
                   CRACI_SOURCE_SHA=h.SOURCE_SHA, CRACI_WORKLOAD='rokoko-mujoco-v12-pilot',
                   GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ATTEMPT='1')
        h.admission(env, datetime(2026, 11, 15, 16, tzinfo=timezone.utc))
        for key, value in [('CRACI_CREDIT_WINDOW_OPEN','false'), ('CRACI_SOURCE_SHA','a'*40),
                           ('GITHUB_EVENT_NAME','push'), ('GITHUB_RUN_ATTEMPT','2'),
                           ('CRACI_WINDOW_END','2027-01-01T00:00:00Z')]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                h.admission({**env, key:value}, datetime(2026, 11, 15, 15, tzinfo=timezone.utc))
        with self.assertRaises(AssertionError):
            h.admission(env, datetime(2026, 11, 15, 16, 0, 1, tzinfo=timezone.utc))

    def test_physical_terminal_never_forward_proxy(self):
        row = dict(option_steps=1, full_transition_count=1, success=True, unsafe=False,
                   dwell_ticks_final=250, contacts=1, final_error=.019)
        trace = [dict(action=1, mask=[0,1,0,0,0,0,1], done=True, success_info=True,
                      dwell_ticks_current=250)]
        h.verify_terminal(row, trace)
        for key, value in [('dwell_ticks_final',249), ('contacts',0), ('final_error',.02),
                           ('unsafe',True), ('option_steps',2)]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                h.verify_terminal({**row, key:value}, trace)
        with self.assertRaises(AssertionError):
            h.verify_terminal(row, [{**trace[0], 'action':4}])

    def test_lossless_red_and_incomplete_retention_uses_v11_parts(self):
        for complete in (False, True):
            with self.subTest(complete=complete), tempfile.TemporaryDirectory() as td:
                private = Path(td) / 'private'; private.mkdir()
                # >6MiB original requires multiple bounded binary parts.
                raw = (b'actual-original-synthetic-contract-bytes\n' * 180000)
                (private/'full_transitions.jsonl.gz').write_bytes(raw)
                h.write(private/'training.json', {'fixtureOnly':True})
                h.write(private/'qualification.json', {'experiment_complete':complete, 'science_gate':'RED'})
                h.write(private/'paired-readout.json', {'hostScienceRed':True})
                h.write(private/'manifest.json', dict(schema=h.SCHEMA+'.manifest',
                    executed_head=h.SOURCE_SHA, file_sha256={p.name:h.sha(p) for p in private.iterdir()}))
                before = {p.name:h.sha(p) for p in private.iterdir()}
                published = Path(td)/'collector'
                result = h.publish(private, published, HERE.parents[1])
                self.assertEqual(result['exact_source_sha'], h.SOURCE_SHA)
                self.assertEqual(before, {p.name:h.sha(p) for p in private.iterdir()})
                report = json.loads((published/'retention-manifest.json').read_text())
                src = next(s for s in report['sources'] if s['name']=='full_transitions.jsonl.gz')
                rebuilt = b''
                for part in src['parts']:
                    self.assertLessEqual((published/part['archive']).stat().st_size, 6*1024*1024)
                    with zipfile.ZipFile(published/part['archive']) as z:
                        rebuilt += z.read(part['entry'])
                self.assertEqual(rebuilt, raw)
                self.assertGreater(len(src['parts']), 1)
                (private/'training.json').write_text('changed')
                with self.assertRaisesRegex(AssertionError, 'SHA_MISMATCH'):
                    h.publish(private, Path(td)/'bad', HERE.parents[1])


@unittest.skipUnless(os.environ.get('CRACI_SOURCE_ROOT'), 'set CRACI_SOURCE_ROOT to exact V12 source fixture')
class PinnedProtocolContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(os.environ['CRACI_SOURCE_ROOT']).resolve()
        cls.protocol, cls.policy, cls.plan, cls.frozen = h.source_contract(cls.source)

    def scans(self):
        rows=[]
        for seed in range(518000,518512):
            obs=[0.]*18; obs[7]=0. if seed%3 else .13
            rows.append(dict(seed=seed,world_hash=f'fixture-world-{seed}',observation=obs,mask=[1]*7))
        return rows

    def fixture(self):
        scans=self.scans(); cohort=self.protocol.derive_cohort(scans,self.plan,'pilot')
        trials=[dict(seed=w['seed'],world_hash=w['world_hash'],strategy=a,success=False,
                     unsafe=False,abstained=False) for w in cohort for a in h.ARMS]
        # A novel nonexploratory goal: GOOD synthetic contract, not simulator evidence.
        trials[1]['success']=True
        return scans,cohort,trials

    def test_good_exact_matrix_and_no_training_action4_model(self):
        scans,cohort,trials=self.fixture()
        self.assertFalse(h.matrix_readout(self.protocol,self.plan,scans,cohort,trials)['hostScienceRed'])
        model=self.policy.load_frozen_model(self.frozen/'model.json')
        self.assertFalse(model['models']['4']['supported'])
        self.assertIsNone(model['models']['4']['weights'])
        self.assertEqual(len(cohort),48)
        self.assertEqual(sum(w['observed_corridor'] for w in cohort),40)

    def test_bad_duplicate_missing_extra_world_arm_and_plan(self):
        scans,cohort,trials=self.fixture()
        mutations=[trials[:-1],trials+[trials[-1]],trials[:-1]+[trials[0]],
                   [{**trials[0],'strategy':'invented'}]+trials[1:],
                   [{**trials[0],'world_hash':'other-world'}]+trials[1:]]
        for bad in mutations:
            with self.subTest(bad=bad[0]), self.assertRaises(ValueError):
                h.matrix_readout(self.protocol,self.plan,scans,cohort,bad)
        for bad_scan in (scans[:-1], scans+[scans[-1]], scans[::-1]):
            with self.assertRaises(ValueError):
                h.matrix_readout(self.protocol,self.plan,bad_scan,cohort,trials)
        changed=copy.deepcopy(self.plan); changed['pilotCohort']['near']=39
        with self.assertRaises(ValueError):
            h.matrix_readout(self.protocol,changed,scans,cohort,trials)

    def test_bad_unsafe_lost_v5_and_zero_novel_stay_red(self):
        scans,cohort,trials=self.fixture()
        for index in (0,1,2):
            bad=copy.deepcopy(trials); bad[index]['unsafe']=True
            self.assertTrue(h.matrix_readout(self.protocol,self.plan,scans,cohort,bad)['hostScienceRed'])
        no_novel=copy.deepcopy(trials); no_novel[1]['success']=False
        self.assertTrue(h.matrix_readout(self.protocol,self.plan,scans,cohort,no_novel)['hostScienceRed'])
        lost=copy.deepcopy(trials); lost[3]['success']=True
        self.assertTrue(h.matrix_readout(self.protocol,self.plan,scans,cohort,lost)['hostScienceRed'])

    def test_raw_matrix_hash_and_trace_tampering_rejected(self):
        scans,cohort,trials=self.fixture()
        # Synthetic complete original byte layout, explicitly NOT a physics run.
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)
            docs=[]
            for row in trials:
                success=row['success']
                trace=[dict(observation=[0.]*18,next_observation=[0.]*18,
                    mask=[1]*7,action=1,done=True,success_info=success,
                    dwell_ticks_current=250 if success else 0)]
                canonical=json.dumps(trace,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
                row.update(option_steps=1,full_transition_count=1,contacts=1 if success else 0,
                    dwell_ticks_final=250 if success else 0,final_error=.019 if success else .2,
                    full_transition_sha256=h.hashlib.sha256(canonical).hexdigest())
                docs.append(dict(seed=row['seed'],strategy=row['strategy'],transitions=trace))
            h.write(out/'training.json',dict(executed_head=h.SOURCE_SHA,stage='pilot',training_only=True,
                model_promotion_authorized=False,all_512_public_initial_scans=scans,cohort=cohort,trials=trials))
            h.write(out/'paired-readout.json',h.matrix_readout(self.protocol,self.plan,scans,cohort,trials))
            def freeze(raw):
                with gzip.open(out/'full_transitions.jsonl.gz','wt') as f:
                    for doc in raw: f.write(json.dumps(doc)+'\n')
                (out/'manifest.json').unlink(missing_ok=True)
                h.write(out/'manifest.json',dict(schema=h.SCHEMA+'.manifest',executed_head=h.SOURCE_SHA,
                    file_sha256={n:h.sha(out/n) for n in
                        ('training.json','paired-readout.json','full_transitions.jsonl.gz')}))
            freeze(docs)
            h.verify_raw(out,self.protocol,self.plan)
            for bad in (docs[:-1],docs+[docs[0]],docs[:-1]+[docs[0]]):
                freeze(bad)
                with self.assertRaises(AssertionError): h.verify_raw(out,self.protocol,self.plan)
            bad=copy.deepcopy(docs);bad[0]['transitions'][0]['action']=4
            freeze(bad)
            with self.assertRaisesRegex(AssertionError,'TRACE_SHA'):
                h.verify_raw(out,self.protocol,self.plan)
            freeze(docs)
            (out/'paired-readout.json').write_text('{}')
            with self.assertRaisesRegex(AssertionError,'HASH'):
                h.verify_raw(out,self.protocol,self.plan)

    def test_bad_action_support_and_plan_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            model=json.loads((self.frozen/'model.json').read_text())
            model['models']['4']['supported']=True
            p=Path(td)/'model.json'; h.write(p,model)
            with self.assertRaises(ValueError): self.policy.load_frozen_model(p)
            p=Path(td)/'plan.json'; h.write(p,self.plan)
            with self.assertRaises(ValueError): self.protocol.verified_plan(p)


if __name__ == '__main__': unittest.main()
