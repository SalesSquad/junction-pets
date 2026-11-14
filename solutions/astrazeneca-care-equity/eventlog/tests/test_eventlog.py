import json,math,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
import numpy as np
from eventlog.schema import pathway_events,events_table,EVENT_TYPES,PATHWAY_ORDER,ENDPOINTS,INTERVAL_EVENTS,INDEX
from eventlog.simulate import simulate,latent,observe,plant,FAST_MEANS,PUBLIC_MEANS
from eventlog.parquet_io import write_dataset,read_dataset
from eventlog.validate import validate
from eventlog.intervals import derive
from eventlog.aggregate import median_ci,wilson,summarize
from eventlog.power import sample_size,binomial_size,analytic_power,critical,min_detectable_ratio,required_information,IDEAL_SIGMA,ZERO_DAY,MIN_TEST_N
from eventlog.detect import log_spans,log_days,moments,test_moments,detect
from eventlog.design_study import (evaluate,structural,calibrate,sample_size_table,sample_size_check,county_layout,segment_moments,
    rest_of_country_flags,repeated_looks_null,published_cohort,small_county_month_null,v1_event_errors,v2_event_errors,
    V2_PREDICTIONS,V2_LABELS,SCRIBE_EVAL,CORE,RATIOS,NATIONAL_CASES,LOOKS)

ROOT=Path(__file__).resolve().parents[2]
SPECIFIED_ORDER=['SYMPTOM_ONSET_REPORTED','FIRST_CONTACT','PHYSICIAN_ASSESSMENT','REFERRAL_SENT','REFERRAL_RECEIVED',
                 'DIAGNOSIS','MDT_DECISION','SPECIALIST_VISIT','TREATMENT_START']

class EventlogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table,cls.roster=simulate(national_cases=100,seed=9)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            write_dataset(self.table,d,self.roster)
            got=read_dataset(d)
            self.assertTrue(got.schema.equals(pathway_events))
            key=lambda r:(r['episode_id'],r['event_type'])
            self.assertEqual(sorted(got.to_pylist(),key=key),sorted(self.table.to_pylist(),key=key))

    def test_invalid_physical_schema_returns_report(self):
        report=validate(self.table.drop(['event_date']))
        self.assertFalse(report.valid)
        self.assertTrue(report.schema_errors)
        self.assertTrue(all(v is None for v in report.missing_share.values()))

    def test_reversed(self):
        rows=self.table.to_pylist();rows[1]['event_date']=rows[0]['event_date']-timedelta(days=10)
        result=validate(events_table(rows),self.roster)
        self.assertFalse(result.valid);self.assertGreater(result.reversed_pairs,0)

    def test_bad_enum(self):
        rows=self.table.to_pylist();rows[0]['event_type']='NOT_AN_EVENT'
        self.assertTrue(validate(events_table(rows)).enum_errors)

    def test_duplicate(self):
        rows=self.table.to_pylist();rows.append(dict(rows[0]))
        self.assertEqual(validate(events_table(rows)).duplicates,1)

    def test_impossible_date(self):
        rows=self.table.to_pylist();rows[0]['event_date']=date(1800,1,1)
        self.assertEqual(validate(events_table(rows)).impossible_dates,1)

    # --- chronology: one pathway order for schema, simulator, validator and document

    def test_one_pathway_order(self):
        self.assertEqual(EVENT_TYPES,SPECIFIED_ORDER)
        self.assertEqual(PATHWAY_ORDER,' <= '.join(SPECIFIED_ORDER))
        self.assertEqual(INTERVAL_EVENTS['primary_care'],('FIRST_CONTACT','REFERRAL_SENT'))
        self.assertEqual(INTERVAL_EVENTS['diagnostic'],('REFERRAL_SENT','DIAGNOSIS'))
        self.assertEqual(INTERVAL_EVENTS['treatment'],('DIAGNOSIS','TREATMENT_START'))
        self.assertEqual(ENDPOINTS[:3],[(1,3),(3,5),(5,8)])
        self.assertEqual(validate(self.table,self.roster).pathway_order,PATHWAY_ORDER)
        doc=(ROOT/'DATA_COLLECTION.md').read_text()
        self.assertIn(PATHWAY_ORDER,' '.join(doc.replace('`','').split()))
        self.assertIn(', '.join(f'`{k}`' for k in SPECIFIED_ORDER),doc)

    def test_timing_rules(self):
        rng=np.random.default_rng(21)
        t,fast=latent(rng,(200000,))
        i=INDEX
        steps=np.stack([t[:,1],t[:,2]-t[:,1],t[:,3]-t[:,2],t[:,i['SPECIALIST_VISIT']]-t[:,3],t[:,8]-t[:,i['SPECIALIST_VISIT']]],axis=1)
        np.testing.assert_allclose(steps[fast].mean(axis=0),FAST_MEANS,rtol=.04)
        np.testing.assert_allclose(steps[~fast].mean(axis=0),PUBLIC_MEANS,rtol=.04)
        sent,received,diagnosis,mdt,specialist=(t[:,i[k]] for k in ['REFERRAL_SENT','REFERRAL_RECEIVED','DIAGNOSIS','MDT_DECISION','SPECIALIST_VISIT'])
        # DIAGNOSIS = REFERRAL_SENT + 0.6 x (referral-to-specialist step)
        np.testing.assert_allclose(diagnosis-sent,.6*(specialist-sent),rtol=1e-9,atol=1e-9)
        # REFERRAL_RECEIVED = REFERRAL_SENT + min(0-3 days, time to DIAGNOSIS)
        lag=received-sent
        self.assertTrue(np.all((lag>=0)&(lag<=3)&(lag<=diagnosis-sent+1e-9)))
        self.assertTrue(np.any(np.isclose(lag,diagnosis-sent)))          # the cap is really reached
        self.assertTrue(np.all((mdt>=diagnosis)&(mdt<=specialist)))        # MDT between DIAGNOSIS and SPECIALIST_VISIT
        self.assertTrue(np.all(t[:,8]>=specialist))                        # TREATMENT_START = SPECIALIST_VISIT + last step

    def test_zero_chronology_violations_latent_and_whole_days(self):
        rng=np.random.default_rng(22)
        t,_=latent(rng,(500000,))
        candidates=[t]+[plant(t,stage,ratio) for stage in range(3) for ratio in [1.1,1.5,3.]]
        candidates.append(latent(rng,(200000,),slowdowns=(1.5,1.3,2.))[0])
        for x in candidates:
            self.assertEqual(int((np.diff(x,axis=-1)<0).sum()),0)
            self.assertEqual(int((np.diff(np.rint(x),axis=-1)<0).sum()),0)
        # Ties exist in whole days and are allowed, not counted.
        self.assertGreater(int((np.diff(np.rint(t),axis=-1)==0).sum()),0)

    def test_zero_chronology_violations_in_validated_sample(self):
        cut=date(2026,12,31)
        for slowdowns in [None,{'HVA05':{'primary_care':1.5,'diagnostic':1.3,'treatment':2.}}]:
            table,roster=simulate(national_cases=4000,seed=31,data_cut=cut,slowdowns=slowdowns)
            report=validate(table,roster,cut)
            self.assertEqual(report.reversed_pairs,0)
            self.assertEqual(report.episodes_with_reversed_pair,0)
            self.assertEqual(report.reversed_by_pair,{})
            self.assertTrue(report.valid)
            self.assertTrue(all(r['days_'+k] is None or r['days_'+k]>=0 for r in derive(table,roster,cut).to_pylist() for k in ['primary_care','diagnostic','treatment','total']))

    def test_written_sample_has_zero_chronology_violations(self):
        out=ROOT/'data/eventlog'
        if not (out/'sample').exists(): self.skipTest('run python -m eventlog.run_all first')
        roster=json.loads((out/'sample-roster.json').read_text())
        report=validate(read_dataset(out/'sample'),roster,date(2026,12,31))
        self.assertEqual(report.reversed_pairs,0)
        self.assertTrue(report.valid)
        self.assertEqual(json.loads((out/'validation-report.json').read_text())['reversed_pairs'],0)

    def test_validator_uses_the_new_order(self):
        rows=self.table.to_pylist()
        episode=rows[0]['episode_id']
        mine={r['event_type']:r for r in rows if r['episode_id']==episode}
        # A diagnosis dated after the first treating-specialist visit breaks the order.
        mine['DIAGNOSIS']['event_date']=mine['SPECIALIST_VISIT']['event_date']+timedelta(days=5)
        result=validate(events_table(rows),self.roster)
        self.assertFalse(result.valid)
        self.assertEqual(result.episodes_with_reversed_pair,1)
        self.assertTrue(any(k.startswith('DIAGNOSIS > ') for k in result.reversed_by_pair))
        # A tie is not a violation.
        rows=self.table.to_pylist()
        mine={r['event_type']:r for r in rows if r['episode_id']==episode}
        for k in ['DIAGNOSIS','MDT_DECISION']: mine[k]['event_date']=mine['SPECIALIST_VISIT']['event_date']
        self.assertEqual(validate(events_table(rows),self.roster).reversed_pairs,0)

    def test_flag_mode_for_real_records(self):
        """The pathway order is the simulator's convention. For real records a reversed pair is
        flagged for review and does not make the file invalid; for simulator output it does."""
        rows=self.table.to_pylist()
        episode=rows[0]['episode_id']
        mine={r['event_type']:r for r in rows if r['episode_id']==episode}
        mine['SPECIALIST_VISIT']['event_date']=mine['DIAGNOSIS']['event_date']-timedelta(days=3)
        strict=validate(events_table(rows),self.roster)
        flag=validate(events_table(rows),self.roster,order='flag')
        self.assertFalse(strict.valid);self.assertEqual(strict.order_mode,'strict')
        self.assertTrue(flag.valid);self.assertEqual(flag.order_mode,'flag')
        self.assertEqual(flag.flagged_for_review,[episode]);self.assertEqual(strict.flagged_for_review,[episode])
        self.assertEqual(flag.reversed_pairs,strict.reversed_pairs);self.assertGreater(flag.reversed_pairs,0)
        # flag mode still rejects what is wrong for any data: a duplicate
        rows.append(dict(rows[0]))
        self.assertFalse(validate(events_table(rows),self.roster,order='flag').valid)
        with self.assertRaises(ValueError): validate(self.table,order='repair')

    # --- estimators

    def test_zero_day_interval_logged_as_half_day(self):
        got=log_days(np.array([0.,1.,7.,-2.,np.nan]))
        np.testing.assert_allclose(got[:3],[math.log(ZERO_DAY),0.,math.log(7)])
        self.assertTrue(np.isnan(got[3]) and np.isnan(got[4]))
        self.assertEqual(ZERO_DAY,.5)
        s=summarize([0,0,1,2,4],threshold=3)
        self.assertEqual(s['n_zero_day_logged_as_half_day'],2)
        self.assertAlmostEqual(s['mean_log_duration'],(2*math.log(.5)+math.log(2)+math.log(4))/5)

    def test_slowdown_estimator(self):
        rng=np.random.default_rng(10)
        baseline,_=latent(rng,(50000,));target,_=latent(rng,(50000,),slowdowns=(1.3,1.,1.))
        b=log_spans(baseline)[:,0];t=log_spans(target)[:,0]
        se=np.sqrt(b.var(ddof=1)/len(b)+t.var(ddof=1)/len(t))
        self.assertLess(abs((t.mean()-b.mean())-np.log(1.3)),3*se)

    def test_plant_scales_only_its_interval(self):
        rng=np.random.default_rng(11)
        t,_=latent(rng,(1000,))
        for stage,(a,b) in enumerate(ENDPOINTS[:3]):
            p=plant(t,stage,1.4)
            for other,(c,d) in enumerate(ENDPOINTS[:3]):
                np.testing.assert_allclose(p[:,d]-p[:,c],(t[:,d]-t[:,c])*(1.4 if other==stage else 1.),rtol=1e-9,atol=1e-9)
            same,_=latent(np.random.default_rng(11),(1000,),slowdowns=tuple(1.4 if k==stage else 1. for k in range(3)))
            np.testing.assert_allclose(p,same,rtol=1e-9,atol=1e-9)

    def test_formula_examples(self):
        self.assertEqual([sample_size(r) for r in RATIOS],[1809,495,239,100])
        self.assertEqual(binomial_size(),385)

    def test_empirical_null(self):
        """A small county with no slowdown: any of its three tests may reject in at most
        3 x 0.05/69 = 0.00217 of counties. 60,000 simulated counties of 50 episodes resolve that
        (binomial SE about 0.0002). The t quantile has to hold the rate; the normal quantile of the
        first implementation does not, which is why it was replaced."""
        rng=np.random.default_rng(12)
        ref,_=latent(rng,(1_000_000,));reference=moments(log_spans(np.rint(ref)))
        target,_=latent(rng,(60000,50))
        mean,var,n=moments(log_spans(np.rint(target)))
        flag,z,_=test_moments(mean,var,n,*reference)
        nominal=3*.05/69
        rate_t=float(flag.any(axis=-1).mean()); rate_z=float((np.abs(z)>critical()).any(axis=-1).mean())
        self.assertLess(rate_t,nominal+4*math.sqrt(nominal/60000))        # within 4 SE of the nominal bound
        self.assertGreater(rate_z,1.4*nominal)                             # the old threshold really was too loose
        self.assertLess(rate_t,rate_z)

    def test_t_quantile_and_looks_widen_the_threshold(self):
        z=critical()
        self.assertAlmostEqual(z,3.3801,places=3)
        self.assertGreater(float(critical(df=49)),z)                       # small county: larger critical value
        self.assertAlmostEqual(float(critical(df=1e9)),z,places=6)         # large df: the normal quantile
        self.assertGreater(critical(comparisons=69*LOOKS),z)               # repeated looks counted in the family
        mean=np.array([[.5,0.,0.]]);var=np.ones((1,3));n=np.full((1,3),40.)
        ref=(np.zeros(3),np.ones(3),np.full(3,1e6))
        flag,zz,_=test_moments(mean,var,n,*ref)                            # z = 0.5 / sqrt(1/40) = 3.16: below both thresholds
        self.assertAlmostEqual(float(zz[0,0]),.5/math.sqrt(1/40+1e-6),places=9)
        self.assertFalse(flag.any())
        mean=np.array([[.57,0.,0.]])                                       # z = 3.60 > 3.38 (normal) but below the t value 3.67 for df 39
        flag,zz,_=test_moments(mean,var,n,*ref)
        self.assertGreater(float(zz[0,0]),z);self.assertFalse(flag.any())
        mean=np.array([[.6,0.,0.]])                                        # z = 3.79: above the t threshold for one look ...
        self.assertTrue(test_moments(mean,var,n,*ref)[0][0,0])
        self.assertFalse(test_moments(mean,var,n,*ref,looks=LOOKS)[0][0,0])  # ... but not with twelve looks in the family

    def test_minimum_testable_episodes(self):
        mean=np.array([[5.,5.,5.]]);var=np.ones((1,3));ref=(np.zeros(3),np.ones(3),np.full(3,1e6))
        self.assertFalse(test_moments(mean,var,np.full((1,3),MIN_TEST_N-1.),*ref)[0].any())
        self.assertTrue(test_moments(mean,var,np.full((1,3),float(MIN_TEST_N)),*ref)[0].all())

    def test_month_precision_pairs_are_not_tested(self):
        rng=np.random.default_rng(13)
        t,_=latent(rng,(2000,))
        observed,month=observe(rng,t,0.,.5)
        logs=log_spans(observed,'D3',month)
        for k,(a,b) in enumerate(ENDPOINTS[:3]):
            inexact=month[:,a]|month[:,b]
            self.assertTrue(np.all(np.isnan(logs[inexact,k])))
            self.assertTrue(np.all(np.isfinite(logs[~inexact,k])))
            self.assertAlmostEqual(float((~inexact).mean()),.25,delta=.04)   # (1 - 0.5)^2 of the pairs remain
        # the derived table carries the flag and the table-based detector honours it
        table,roster=simulate(national_cases=3000,seed=14,month_share=.5)
        rows=derive(table,roster).to_pylist()
        flags=[r['day_precision_diagnostic'] for r in rows if r['days_diagnostic'] is not None]
        self.assertTrue(any(flags) and not all(flags))
        result=detect(derive(table,roster))
        tests=[x for c in result if not c.get('suppressed') for x in c['tests']]
        self.assertTrue(all(x['excluded_month_precision']>0 for x in tests if x['interval']=='diagnostic'))
        self.assertTrue(all((x['n']>=MIN_TEST_N)==x['tested'] for x in tests))

    def test_rest_of_country_sample_size(self):
        for r,sigma,national in [(1.1,.9383,37000),(1.2,.9773,9250),(1.5,.8035,9250)]:
            k=required_information(r,sigma); n=sample_size(r,sigma=sigma,national=national)
            self.assertGreaterEqual(n*(national-n)/national,k)
            self.assertLess((n-1)*(national-n+1)/national,k)                # and n - 1 is not enough
            self.assertGreater(n,sample_size(r,sigma=sigma))                # more than against an infinite reference
            self.assertAlmostEqual(analytic_power(r,n,sigma=sigma,reference_n=national-n),.8,delta=.005)
            self.assertLess(analytic_power(r,sample_size(r,sigma=sigma),sigma=sigma,reference_n=national-sample_size(r,sigma=sigma)),.8)
            self.assertLessEqual(min_detectable_ratio(n,sigma,national),r+1e-9)
        self.assertIsNone(sample_size(1.05,sigma=.98,national=9250))        # no county size reaches the power
        self.assertGreater(sample_size(1.2,comparisons=69*LOOKS),sample_size(1.2))

    def test_county_layout_and_segments(self):
        names,counts=county_layout()
        self.assertEqual(len(names),23);self.assertEqual(int(counts.sum()),NATIONAL_CASES)
        x=np.arange(24.).reshape(1,8,3)
        n,s1,s2=segment_moments(x,np.array([0,3,5]))
        np.testing.assert_allclose(n[0,:,0],[3,2,3]);np.testing.assert_allclose(s1[0,:,0],[0+3+6,9+12,15+18+21])

    def test_repeated_looks_inflate_and_family_correction_holds(self):
        rows=repeated_looks_null(np.random.default_rng(16),400)
        equal={r['threshold']:r['any_false_flag_by_look'] for r in rows if r['layout'].startswith('23 counties')}
        self.assertGreater(equal['single_look'][-1]['rate'],.15)           # twelve looks at the one-look threshold: far above 5%
        self.assertGreater(equal['single_look'][-1]['rate'],3*equal['single_look'][0]['rate'])
        self.assertLess(equal['looks_in_family'][-1]['rate'],.08)          # looks counted in the family: near 5% or below
        rates=[x['rate'] for x in equal['single_look']]
        self.assertEqual(rates,sorted(rates))                              # cumulative over looks

    def test_cohort_values_come_from_the_evidence_table(self):
        c=published_cohort()
        self.assertEqual((c['mean_days'],c['median_days']),(207,127))
        self.assertAlmostEqual(c['implied_log_sd'],math.sqrt(2*math.log(207/127)),places=12)
        self.assertEqual((c['fast']['mean_days'],c['fast']['median_days']),(123,76))
        self.assertAlmostEqual(c['fast']['implied_log_sd'],math.sqrt(2*math.log(123/76)),places=12)
        # the simulator's step value is an input: neither route's mean/median reproduces it
        self.assertEqual(c['step_sigma_in_simulator'],.96)
        self.assertTrue(c['fast_and_public_both_differ_from_step_sigma'])

    def test_measured_date_errors_enter_observation(self):
        rng=np.random.default_rng(17)
        t,_=latent(rng,(1000,))
        same,_=observe(np.random.default_rng(1),t,date_errors=[0])
        np.testing.assert_array_equal(same,np.rint(t))
        shifted,_=observe(np.random.default_rng(1),t,date_errors=[5])
        np.testing.assert_array_equal(shifted,np.rint(t)+5)          # every date gets one of the measured errors
        mixed,_=observe(np.random.default_rng(1),t,date_errors=[0,0,0,-40])
        share=float((mixed!=np.rint(t)).mean())
        self.assertAlmostEqual(share,.25,delta=.02)

    def test_measured_error_profiles_reproduce_the_scribe_metrics(self):
        needed=[ROOT/SCRIBE_EVAL,ROOT/V2_PREDICTIONS,*[ROOT/x for x in V2_LABELS.values()]]
        if not all(x.exists() for x in needed): self.skipTest('scribe evaluation files not present')
        import os
        here=os.getcwd(); os.chdir(ROOT)
        try:
            v1=v1_event_errors()
            v2=[v2_event_errors('test_nemotron'),v2_event_errors('test_haiku')]   # raises if recall differs from the stored metric
        finally: os.chdir(here)
        self.assertEqual((v1['true_events'],v1['events_with_type_found'],v1['exact_dates']),(479,440,295))   # scribe/RESULTS.md: 295 of 440
        self.assertEqual(v2[0]['true_events'],1251)
        for p in [v1,*v2]:
            self.assertEqual(len(p['date_errors_days']),p['events_with_type_found'])
            self.assertGreater(p['wrong_date_share'],.1)                   # far above the assumed rates of the first extraction study

    def test_month_precision_single_county_null(self):
        rng=np.random.default_rng(18)
        ref,_=latent(rng,(400_000,));reference=moments(log_spans(np.rint(ref)))
        rows={x['n']:x for x in small_county_month_null(rng,reference,4000,sizes=(30,250))}
        self.assertEqual(rows[30]['counties_with_a_test_share'],0.)        # about 7.5 testable pairs: never tested
        self.assertIsNone(rows[30]['false_positive_rate_among_tested'])
        self.assertEqual(rows[250]['counties_with_a_test_share'],1.)
        self.assertLess(rows[250]['false_positive_rate_t'],.01)

    def test_d2_structural_d3_localisation(self):
        rng=np.random.default_rng(15)
        ref,_=latent(rng,(100000,));baseline,_=latent(rng,(400,1000))
        ref=np.rint(ref)
        for stage in [0,1,2]:
            target=np.rint(plant(baseline,stage,1.5))
            d2,_,_=evaluate(target,moments(log_spans(ref,'D2')),'D2',stage)
            d3,_,_=evaluate(target,moments(log_spans(ref)),'D3',stage)
            self.assertIsNone(d2['stage_power'])
            self.assertEqual(d2['localisation'],'structurally_impossible')
            self.assertGreater(d3['stage_power'],.8)
        self.assertIsNone(structural()['county_power'])

    # --- sample size per interval

    def test_per_interval_sample_sizes_match_simulation(self):
        """The per-interval n is the idealised formula with the measured SD.
        (a) With that SD treated as known, as the formula assumes, simulated power
            at exactly that n equals the analytic power within Monte Carlo error
            (3.5 standard errors; binomial error of 4000 replications plus the
            sampling error of the reference mean). This test cannot see departures
            below about 0.02; the study's 200,000-replication check can, and
            reports them in RESULTS.md.
        (b) The detector as run estimates the variance in the county and uses
            Student t critical values, which the normal-approximation formula
            does not. Its power is therefore a little below the formula for
            small n (see RESULTS.md). Here it has to stay within 0.03 of the
            analytic power for n of at least 300, within 0.07 below that, and
            never more than 0.03 above it.
        (c) Negative control: the idealised n is too large for the treatment
            interval, so the idealised table does not match simulation there."""
        rng=np.random.default_rng(20261115)
        calibration,reference=calibrate(rng,8_000_000)
        self.assertEqual(calibration['whole_day_chronology_violations'],0)
        sds=[calibration['intervals'][k]['sd_log_duration'] for k in CORE]
        # Only the diagnostic interval is wider than one log-normal step.
        self.assertGreater(sds[1],IDEAL_SIGMA)
        self.assertLess(sds[0],IDEAL_SIGMA);self.assertLess(sds[2],sds[0])
        for k,s in zip(CORE,sds): self.assertLess(calibration['intervals'][k]['sd_standard_error'],.001)
        table=sample_size_table(sds)
        for row in table:
            self.assertEqual(row['idealised'],sample_size(row['slowdown']))
            for k,s in zip(CORE,sds): self.assertEqual(row[k],sample_size(row['slowdown'],sigma=s))
            self.assertGreater(row['diagnostic'],row['idealised'])
            self.assertLess(row['primary_care'],row['idealised']);self.assertLess(row['treatment'],row['primary_care'])
        check=sample_size_check(rng,sds,reference,4000)
        self.assertEqual(len(check),12)
        for c in check:
            where=f"{c['interval']} r={c['slowdown']} n={c['n']}"
            self.assertEqual(c['n'],next(r for r in table if r['slowdown']==c['slowdown'])[c['interval']])
            self.assertLess(abs(c['analytic_power']-.8),.01,where)
            self.assertLess(c['known_sd_gap_in_monte_carlo_se'],3.5,where)
            self.assertLess(c['absolute_gap'],.03 if c['n']>=300 else .07,where)
            self.assertLess(c['signed_gap'],.03,where)
        # (c) idealised n for a 20% treatment slowdown: far more power than 0.8.
        n=sample_size(1.2); t,_=latent(rng,(2000,n))
        mean,var,nn=moments(log_spans(np.rint(plant(t,2,1.2))))
        flag,_,_=test_moments(mean,var,nn,*reference)
        self.assertGreater(float(flag[:,2].mean()),.9)
        self.assertGreater(analytic_power(1.2,n,sigma=sds[2]),.9)

    def test_document_and_results_match_study(self):
        out=ROOT/'data/eventlog/design-study-v1.json'
        if not out.exists(): self.skipTest('run python -m eventlog.run_all first')
        from eventlog.audit import document_rows
        study=json.loads(out.read_text())
        doc=(ROOT/'DATA_COLLECTION.md').read_text()
        for line in document_rows(study): self.assertIn(line,doc)
        results=(ROOT/'eventlog/RESULTS.md').read_text()
        for finding in study['findings']: self.assertIn(finding,results)
        if 'measured_text_extraction' in study:
            from eventlog.audit import extraction_block
            self.assertIn(extraction_block(study),doc)
        self.assertEqual(study['pathway_order'],PATHWAY_ORDER)
        self.assertEqual(study['sample_validation']['chronology_violations'],0)

    # --- censoring, reproducibility, summaries

    def test_missing_not_censoring(self):
        table,roster=simulate(national_cases=10,seed=3,missingness={'DIAGNOSIS':1.})
        rows=derive(table,roster).to_pylist()
        self.assertTrue(all(r['days_diagnostic'] is None for r in rows))
        self.assertTrue(all(not r['censored_diagnostic'] for r in rows))

    def test_administrative_censor(self):
        cut=date(2025,6,1)
        table,roster=simulate(national_cases=100,seed=4,data_cut=cut)
        rows=derive(table,roster,cut).to_pylist()
        self.assertTrue(any(r['censored_total'] for r in rows))
        self.assertTrue(all(r['days_total'] is None or r['days_total']>=0 for r in rows))
        self.assertTrue(all(d<=cut for d in table['event_date'].to_pylist()))

    def test_reproducible(self):
        a,ra=simulate(national_cases=100,seed=6,month_share=.5,e_type=.1,e_date=.1,source='TEXT_EXTRACTED')
        b,rb=simulate(national_cases=100,seed=6,month_share=.5,e_type=.1,e_date=.1,source='TEXT_EXTRACTED')
        self.assertTrue(a.equals(b));self.assertEqual(ra,rb)

    def test_interval_summaries(self):
        self.assertEqual(median_ci([1,2,3,4,5]),[None,None])
        lo,hi=wilson(70,100);self.assertLess(lo,.7);self.assertGreater(hi,.7)

if __name__=='__main__': unittest.main()
