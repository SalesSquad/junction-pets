"""Source-bound Monte Carlo experiments, using actual individual pathways.
Reference is an independent synthetic rest-of-country pool, reused across trials.
Probabilities are conditional on that pool; its sampling SE remains in tests.
D4 uses the core-stage detector for fair stage comparisons; its extra events
permit finer descriptive spans but do not create extra independent information.

Sample size is treated per core interval. calibrate() measures the standard
deviation of log-duration of each interval in a large simulated sample
(whole-day dates; a zero-day interval is logged as 0.5 day), the required n is
recomputed from those values, and sample_size_check() simulates the power at
exactly that n. Every gap between formula and simulation is reported, none is
tuned away.

Added after review: the detector uses Welch t quantiles and tests day-precision
pairs only (detect.py); the family-wise null is measured for month-precision
dates and population-proportional county sizes as well; repeated quarterly
looks are counted in the family (repeated_looks_null, early_warning); the
sample sizes are also given against the rest of the country as comparator
(rest_of_country_check); and the simulator's total pathway is compared with the
published cohort it was calibrated to (calibrate, cohort_check).
"""
import hashlib, json, re, time
from math import log as ln, sqrt
from pathlib import Path
import numpy as np
from .simulate import latent, observe, plant, populations, SIGMA, FAST_SHARE, DIAGNOSIS_FRACTION
from .detect import log_spans, moments, test_moments
from .power import analytic_power, sample_size, binomial_size, critical, min_detectable_ratio, IDEAL_SIGMA, ZERO_DAY, NORM, MIN_TEST_N
from .schema import INTERVALS, ENDPOINTS, D2_ENDPOINTS, PATHWAY_ORDER
from .aggregate import wilson
from .log import log as _log
DESIGNS=['D1','D2','D3','D4']
RATIOS=[1.1,1.2,1.3,1.5]
SIZES=[100,250,500,1000,2000]
CORE=INTERVALS[:3]
NATIONAL_CASES=37000      # assumption, not an observed incidence; the same figure simulate() uses
LOOKS=12                  # planned horizon of quarterly looks in the early-warning study
MONTH_SHARES=[0.,.5]

def published_cohort(path='data/evidence/literature-v1.json'):
    """Symptom-to-treatment mean and median of the cohort the step means come from, read from the
    project's evidence table (Kuitunen 2026). The top-level keys are the public route; 'fast' is the
    private/occupational route. implied_log_sd = sqrt(2 ln(mean/median)) is the log-SD of a single
    log-normal with that mean and median: a value computed from the cohort. The simulator's step
    log-SD (simulate.SIGMA) is an input; fast_and_public_both_differ_from_step_sigma says whether
    either route reproduces it."""
    from .simulate import SIGMA
    rows={r['id']:r for r in json.loads(Path(path).read_text())['rows']}
    unit=rows['kuitunen-2026-route-medians']['unit']
    mean=rows['kuitunen-2026-route-means']['milestones']['public'][-1]
    median=int(re.search(r'(\d+) public',unit).group(1))
    fast_mean=rows['kuitunen-2026-route-means']['milestones']['fast'][-1]
    fast_median=int(re.search(r'(\d+) private',unit).group(1))
    implied=sqrt(2*ln(mean/median)); fast_implied=sqrt(2*ln(fast_mean/fast_median))
    return dict(mean_days=mean,median_days=median,implied_log_sd=implied,
        fast=dict(mean_days=fast_mean,median_days=fast_median,implied_log_sd=fast_implied),
        step_sigma_in_simulator=SIGMA,
        fast_and_public_both_differ_from_step_sigma=bool(round(implied,2)!=SIGMA and round(fast_implied,2)!=SIGMA),
        doi=rows['kuitunen-2026-route-means']['doi'],evidence_ids=['kuitunen-2026-route-means','kuitunen-2026-route-medians'])

def county_layout(national=NATIONAL_CASES):
    """County sizes proportional to population (largest remainder), as simulate() allocates them."""
    _,pop=populations(); w=np.array(list(pop.values())); exact=national*w/w.sum()
    counts=np.floor(exact).astype(int); counts[np.argsort(-(exact-counts))[:national-counts.sum()]]+=1
    return list(pop),counts

def pathways(rng,shape):
    t,_=latent(rng,shape)
    return t+rng.integers(0,365,shape)[...,None]

def calibrate(rng,size,chunk=250_000):
    """Streamed large sample at day precision with no missing events.
    Returns per-interval moments of log-duration (pooled and by route) and the
    pooled (mean, variance, n) triple used as the national reference."""
    groups=['pooled','fast','public']
    raw={g:np.zeros((5,3)) for g in groups}; zero=np.zeros(3); days_sum=np.zeros(3)
    done=0; reversed_pairs=0; totals=[]; kept=0; fast_totals=[]; fast_kept=0
    while done<size:
        m=min(chunk,size-done); t,fast=latent(rng,(m,)); d=np.rint(t)
        reversed_pairs+=int((np.diff(d,axis=-1)<0).sum())
        spans=np.stack([d[:,b]-d[:,a] for a,b in ENDPOINTS[:3]],axis=-1)
        logs=log_spans(d)
        zero+=(spans==0).sum(axis=0); days_sum+=spans.sum(axis=0)
        if kept<2_000_000:      # symptom onset to treatment start on the public route, for the cohort check
            x=d[~fast,8]-d[~fast,0]; totals.append(x[:2_000_000-kept]); kept+=len(totals[-1])
        if fast_kept<2_000_000: # the same on the private/occupational route (bookkeeping only, no extra draws)
            x=d[fast,8]-d[fast,0]; fast_totals.append(x[:2_000_000-fast_kept]); fast_kept+=len(fast_totals[-1])
        for g,mask in [('pooled',np.ones(m,bool)),('fast',fast),('public',~fast)]:
            x=logs[mask]
            raw[g]+=np.stack([np.full(3,float(len(x))),x.sum(axis=0),(x**2).sum(axis=0),(x**3).sum(axis=0),(x**4).sum(axis=0)])
        done+=m
    def stats(r):
        n=r[0]; mu=r[1]/n; m2=r[2]/n-mu**2
        m4=r[4]/n-4*mu*r[3]/n+6*mu**2*r[2]/n-3*mu**4
        m3=r[3]/n-3*mu*r[2]/n+2*mu**3
        var=m2*n/(n-1); sd=np.sqrt(var)
        return n,mu,var,sd,np.sqrt(np.maximum(m4-m2**2,0)/n)/(2*sd),m3/m2**1.5
    n,mu,var,sd,se,skew=stats(raw['pooled'])
    by={g:stats(raw[g]) for g in ['fast','public']}
    intervals={}
    for k,name in enumerate(CORE):
        intervals[name]=dict(sd_log_duration=float(sd[k]),sd_standard_error=float(se[k]),mean_log_duration=float(mu[k]),
          skewness_log_duration=float(skew[k]),
          mean_days=float(days_sum[k]/n[k]),zero_day_share=float(zero[k]/n[k]),zero_day_episodes=int(zero[k]),
          by_route={g:dict(share=float(by[g][0][k]/n[k]),mean_log_duration=float(by[g][1][k]),sd_log_duration=float(by[g][3][k])) for g in by})
    total=np.concatenate(totals); published=published_cohort(); fast_total=np.concatenate(fast_totals)
    cohort=dict(route='public',interval='symptom onset to treatment start',episodes=int(len(total)),
        simulated_mean_days=float(total.mean()),simulated_median_days=float(np.median(total)),
        simulated_log_sd=float(np.log(np.maximum(total,ZERO_DAY)).std(ddof=1)),
        published_mean_days=published['mean_days'],published_median_days=published['median_days'],
        published_implied_log_sd=published['implied_log_sd'],doi=published['doi'],evidence_ids=published['evidence_ids'],
        fast=dict(route='private or occupational',episodes=int(len(fast_total)),simulated_mean_days=float(fast_total.mean()),
          simulated_median_days=float(np.median(fast_total)),simulated_log_sd=float(np.log(np.maximum(fast_total,ZERO_DAY)).std(ddof=1)),
          published_mean_days=published['fast']['mean_days'],published_median_days=published['fast']['median_days'],
          published_implied_log_sd=published['fast']['implied_log_sd']),
        step_sigma_in_simulator=published['step_sigma_in_simulator'],
        step_sigma_reproduced_by_cohort=not published['fast_and_public_both_differ_from_step_sigma'],
        sigma_sources=dict(step_sigma='input of the simulator (simulate.SIGMA), a modelling choice; computed from neither the cohort nor the simulator',
          per_interval='computed from the simulator: SD of log-duration of each interval in the calibration sample',
          cohort_implied='computed from the cohort: sqrt(2 ln(mean/median)) of the published symptom-to-treatment mean and median, per route'),
        reading='The simulator reproduces the published mean but not the published median: five independent steps sum to a total that is much less skewed than the cohort. Real intervals may be more spread than the simulated ones, which would raise every required n.')
    return dict(episodes=int(size),whole_day_chronology_violations=reversed_pairs,step_log_sd=SIGMA,fast_route_share_assumed=FAST_SHARE,zero_day_logged_as_days=ZERO_DAY,
      cohort_check=cohort,
      definition='Whole-day dates, no missing events, DAY precision. log-duration = log(days), a zero-day interval is logged as 0.5 day; positive intervals are unchanged.',
      intervals=intervals),(mu,var,n)

def streamed_reference(rng,size,missing=0.,month=0.,chunk=500_000):
    """Rest-of-country moments of log-duration under one observation condition,
    accumulated in chunks so the pool can be large without holding it in memory."""
    acc={d:[0,0,0] for d in ['D2','D3']}; done=0
    while done<size:
        m=min(chunk,size-done)
        observed,mask=observe(rng,pathways(rng,(m,)),missing,month)
        for d in acc:
            l=log_spans(observed,d,mask); ok=np.isfinite(l); v=np.where(ok,l,0)
            acc[d]=[acc[d][0]+ok.sum(axis=0),acc[d][1]+v.sum(axis=0),acc[d][2]+(v*v).sum(axis=0)]
        done+=m
    out={}
    for d,(n,s1,s2) in acc.items():
        mean=s1/n; out[d]=(mean,(s2-n*mean**2)/(n-1),n)
    return out

def monte_carlo_se(a,ratio,n,sigma,reference_n,replications):
    """Binomial error of the replications plus the sampling error of the one
    fixed reference mean (delta method on the analytic power)."""
    delta=ln(ratio)/(sigma*sqrt(1/n+1/reference_n))
    binomial_se=sqrt(a*(1-a)/replications); reference_se=NORM.pdf(delta-critical())*sqrt(n/reference_n)
    return binomial_se,reference_se,sqrt(binomial_se**2+reference_se**2)

def evaluate(observed,reference,design,stage,month=None,looks=1):
    """month: mask of month-precision dates (those pairs are not tested); looks: planned repeated looks."""
    logs=log_spans(observed,design,month)
    mean,var,n=moments(logs)
    flag,z,located=test_moments(mean,var,n,*reference,looks=looks)
    hit=flag.any(axis=-1)
    own=flag[...,0 if design=='D2' else stage]
    return dict(county_power=float(hit.mean()),county_power_ci95=wilson(int(hit.sum()),len(hit)),
      planted_test_power=float(own.mean()),planted_test_power_ci95=wilson(int(own.sum()),len(own)),
      stage_power=float((located==stage).mean()) if design!='D2' else None,
      localisation='structurally_impossible' if design=='D2' else 'largest_positive_flagged_z',
      mean_complete_episodes=float(n.min(axis=-1).mean())),hit,located

def structural():
    return dict(county_power=None,planted_test_power=None,stage_power=None,localisation='structurally_impossible_no_patient_timestamps')

def sample_size_table(sds,cohort_sigma=None):
    """idealised and per-interval columns: infinite reference, one look. rest_of_country: the same
    with the other episodes of the period as comparator (a year or a quarter of NATIONAL_CASES).
    cohort_spread: one step with the log-SD implied by the published cohort's mean and median."""
    rows=[]
    for r in RATIOS:
        row=dict(slowdown=r,idealised=sample_size(r),**{k:sample_size(r,sigma=s) for k,s in zip(CORE,sds)})
        if cohort_sigma: row['cohort_spread']=sample_size(r,sigma=cohort_sigma)
        row['rest_of_country']={period:{k:sample_size(r,sigma=s,national=n) for k,s in zip(CORE,sds)}
            for period,n in [('year',NATIONAL_CASES),('quarter',NATIONAL_CASES//4)]}
        row['with_planned_looks']={k:sample_size(r,sigma=s,comparisons=69*LOOKS) for k,s in zip(CORE,sds)}
        rows.append(row)
    return rows

def segment_moments(logs,starts):
    """Per-county (count, sum, sum of squares) along axis -2 for counties stored as consecutive blocks."""
    ok=np.isfinite(logs); v=np.where(ok,logs,0)
    return np.add.reduceat(ok,starts,axis=-2).astype(float),np.add.reduceat(v,starts,axis=-2),np.add.reduceat(v*v,starts,axis=-2)

def rest_of_country_flags(n,s1,s2,looks=1):
    """Each county against all other counties of the same array. n, s1, s2: (..., counties, tests)."""
    mean=s1/np.maximum(n,1); var=(s2-n*mean**2)/np.maximum(n-1,1)
    rn=n.sum(axis=-2,keepdims=True)-n; r1=s1.sum(axis=-2,keepdims=True)-s1; r2=s2.sum(axis=-2,keepdims=True)-s2
    rmean=r1/np.maximum(rn,1); rvar=(r2-rn*rmean**2)/np.maximum(rn-1,1)
    return test_moments(mean,var,n,rmean,rvar,rn,looks=looks)[0]

def familywise_null(rng,replications,chunk=50):
    """No slowdown anywhere; every county is tested against the rest of the country. Share of
    replications with at least one false flag, by county layout and date precision."""
    names,proportional=county_layout(); out=[]
    layouts=[('23 counties x 250',np.full(23,250)),
             (f'population-proportional, {NATIONAL_CASES//4} episodes (one quarter)',county_layout(NATIONAL_CASES//4)[1]),
             (f'population-proportional, {NATIONAL_CASES} episodes (one year)',proportional)]
    for label,sizes in layouts:
        starts=np.concatenate([[0],np.cumsum(sizes)[:-1]]); total=int(sizes.sum())
        for month in MONTH_SHARES:
            hits={d:0 for d in ['D2','D3']}; untested={d:0 for d in ['D2','D3']}; done=0
            while done<replications:
                m=min(chunk,replications-done)
                observed,mask=observe(rng,pathways(rng,(m,total)),0.,month)
                for d in hits:
                    n,s1,s2=segment_moments(log_spans(observed,d,mask),starts)
                    hits[d]+=int(rest_of_country_flags(n,s1,s2).any(axis=(1,2)).sum())
                    untested[d]+=int((n<MIN_TEST_N).sum())
                done+=m
            for d in ['D2','D3','D4']:
                k=hits['D3' if d=='D4' else d]
                out.append(dict(design=d,layout=label,county_count=23,smallest_county=int(sizes.min()),largest_county=int(sizes.max()),
                  episodes=total,month_share=month,replications=replications,
                  familywise_false_positive_rate=k/replications,ci95=wilson(k,replications),
                  county_tests_below_min_n_share=untested['D3' if d=='D4' else d]/(replications*23*(1 if d=='D2' else 3))))
    return out

def repeated_looks_null(rng,replications,quarters=LOOKS,window=4,chunk=25):
    """No slowdown anywhere, quarterly looks on a rolling window, every county against the rest of
    the country at each look. Share of replications with at least one false flag by look L, with the
    single-look threshold (a = 0.05/69) and with the looks counted in the family (a = 0.05/(69 L))."""
    out=[]
    for label,sizes in [('23 counties x 250 per quarter',np.full(23,250)),
                        (f'population-proportional, {NATIONAL_CASES//4} per quarter',county_layout(NATIONAL_CASES//4)[1])]:
        starts=np.concatenate([[0],np.cumsum(sizes)[:-1]]); total=int(sizes.sum())
        first={k:np.zeros(quarters,int) for k in ['single_look','looks_in_family']}; done=0
        while done<replications:
            m=min(chunk,replications-done)
            l=log_spans(np.rint(pathways(rng,(m,quarters,total))))
            n,s1,s2=segment_moments(l,starts)                       # (m, quarters, counties, 3)
            seen={k:np.zeros(m,bool) for k in first}
            for q in range(quarters):
                sl=slice(max(0,q-window+1),q+1)
                a,b,c=n[:,sl].sum(axis=1),s1[:,sl].sum(axis=1),s2[:,sl].sum(axis=1)
                for k,looks in [('single_look',1),('looks_in_family',quarters)]:
                    seen[k]|=rest_of_country_flags(a,b,c,looks=looks).any(axis=(1,2))
                    first[k][q]+=int(seen[k].sum())
            done+=m
        for k in first:
            out.append(dict(layout=label,threshold=k,comparisons=69*(1 if k=='single_look' else quarters),quarters=quarters,window_quarters=window,
              replications=replications,design='D3',
              any_false_flag_by_look=[dict(look=q+1,rate=int(first[k][q])/replications,ci95=wilson(int(first[k][q]),replications)) for q in range(quarters)]))
    return out

def rest_of_country_check(rng,sds,replications=2000,chunk_episodes=4_000_000):
    """Power when the comparator is the rest of the country in the same period, fully simulated:
    N episodes, the first n are the county with the planted slowdown. Two county sizes per cell:
    the n of the infinite-reference table and the n of the two-sample formula."""
    rows=[]
    for period,national,ratio in [('quarter',NATIONAL_CASES//4,1.2),('year',NATIONAL_CASES,1.1)]:
        for stage,name in enumerate(CORE):
            for kind,n in [('infinite_reference_n',sample_size(ratio,sigma=sds[stage])),('rest_of_country_n',sample_size(ratio,sigma=sds[stage],national=national))]:
                hits=0; done=0
                while done<replications:
                    m=min(max(1,chunk_episodes//national),replications-done)
                    t,_=latent(rng,(m,national)); t[:,:n]=plant(t[:,:n],stage,ratio)
                    l=log_spans(np.rint(t))[...,stage]
                    a=l[:,:n]; b=l[:,n:]
                    flag,_,_=test_moments(a.mean(axis=1)[:,None],a.var(axis=1,ddof=1)[:,None],np.full((m,1),float(n)),
                        b.mean(axis=1)[:,None],b.var(axis=1,ddof=1)[:,None],np.full((m,1),float(national-n)),counties=69)
                    hits+=int(flag.sum()); done+=m
                a=analytic_power(ratio,n,sigma=sds[stage],reference_n=national-n)
                rows.append(dict(period=period,national_episodes=national,interval=name,slowdown=ratio,county_n_kind=kind,n=n,replications=replications,
                  analytic_power_two_sample=a,analytic_power_infinite_reference=analytic_power(ratio,n,sigma=sds[stage]),
                  empirical_power=hits/replications,empirical_power_ci95=wilson(hits,replications),signed_gap=hits/replications-a))
    return rows

def small_county_null(rng,reference,replications=200_000,sizes=(30,50,100,250,1000),budget=3_000_000):
    """One county with no slowdown against the large calibration reference, whole-day dates:
    share of replications in which any of its three tests rejects, with the detector's t quantiles
    and, for comparison, with the normal quantile the first implementation used. The nominal rate
    for three tests at a = 0.05/69 each is at most 3 x 0.05/69."""
    rows=[]; zc=critical()
    for n in sizes:
        t_hits=0; z_hits=0; done=0
        while done<replications:
            m=min(max(1,budget//n),replications-done)
            t,_=latent(rng,(m,n)); mean,var,nn=moments(log_spans(np.rint(t)))
            flag,z,_=test_moments(mean,var,nn,*reference)
            t_hits+=int(flag.any(axis=-1).sum()); z_hits+=int((np.abs(z)>zc).any(axis=-1).sum()); done+=m
        rows.append(dict(n=n,replications=replications,nominal_at_most=3*.05/69,
          false_positive_rate_t=t_hits/replications,ci95_t=wilson(t_hits,replications),
          false_positive_rate_normal_quantile=z_hits/replications,ci95_normal_quantile=wilson(z_hits,replications)))
    return rows

def county_detectability(sds):
    """For each county under the NATIONAL_CASES assumption: the smallest slowdown that reaches power
    0.8 in each interval, for one look at a quarter and one look at a year, rest of the country as
    comparator, a = 0.05/69. A planning aid built from assumed case counts, not an observation."""
    names,counts=county_layout(); rows=[]
    for name,annual in zip(names,counts):
        row=dict(county=name,assumed_annual_cases=int(annual),assumed_cases_per_quarter=float(annual/4))
        for period,n,national in [('quarter',annual/4,NATIONAL_CASES/4),('year',float(annual),float(NATIONAL_CASES))]:
            row[f'min_detectable_slowdown_{period}']={k:min_detectable_ratio(n,s,national) for k,s in zip(CORE,sds)}
        rows.append(row)
    return rows

def sample_size_check(rng,sds,reference,replications,budget=600_000):
    """Simulated power at exactly the per-interval n, for whole-day complete
    episodes against the calibration sample as national reference. Two tests:
    known_sd, the formula's own setting (z-test of the mean log-duration with the
    measured SD treated as known), and detector, the Wald test as actually run
    (variance estimated in the county)."""
    reference_n=float(reference[2].min()); rows=[]; zc=critical()
    for stage,name in enumerate(CORE):
        for ratio in RATIOS:
            n=sample_size(ratio,sigma=sds[stage]); hits=0; known=0; shift=0.; done=0
            while done<replications:
                m=min(max(1,budget//n),replications-done)
                t,_=latent(rng,(m,n)); d=np.rint(plant(t,stage,ratio))
                mean,var,nn=moments(log_spans(d))
                flag,_,_=test_moments(mean,var,nn,*reference)
                diff=mean[:,stage]-reference[0][stage]
                hits+=int(flag[:,stage].sum()); shift+=float(diff.sum()); done+=m
                known+=int((np.abs(diff/(sds[stage]*sqrt(1/n+1/reference_n)))>zc).sum())
            a=analytic_power(ratio,n,sigma=sds[stage],reference_n=reference_n)
            binomial_se,reference_se,se=monte_carlo_se(a,ratio,n,sds[stage],reference_n,replications)
            p=hits/replications; pk=known/replications
            rows.append(dict(interval=name,slowdown=ratio,sd_log_duration=sds[stage],n=n,replications=replications,
              analytic_power=a,binomial_se=binomial_se,reference_se=reference_se,monte_carlo_se=se,
              known_sd_power=pk,known_sd_power_ci95=wilson(known,replications),known_sd_gap=abs(pk-a),known_sd_gap_in_monte_carlo_se=abs(pk-a)/se,
              empirical_power=p,empirical_power_ci95=wilson(hits,replications),absolute_gap=abs(p-a),signed_gap=p-a,gap_in_monte_carlo_se=abs(p-a)/se,
              log_ratio=ln(ratio),mean_observed_log_shift=shift/replications))
    return rows

def gap_summary(tables):
    """Like-for-like gaps of the D3 cells (D4 repeats D3) by observation condition."""
    out=[]
    for missing in [0.,.2]:
        for month in [0.,.5]:
            cells=[x for x in tables if x['design']=='D3' and x['missingness']==missing and x['month_share']==month]
            worst=max(cells,key=lambda x:x['empirical_analytic_gap'])
            out.append(dict(missingness=missing,month_share=month,cells=len(cells),
              largest_gap=worst['empirical_analytic_gap'],largest_gap_cell={k:worst[k] for k in ['n','slowdown','stage','planted_test_power','analytic_power']},
              mean_gap=float(np.mean([x['empirical_analytic_gap'] for x in cells])),
              cells_with_analytic_power_between_0_02_and_0_98=sum(x['gap_in_monte_carlo_se'] is not None for x in cells),
              cells_beyond_3_monte_carlo_se=sum(x['gap_in_monte_carlo_se'] is not None and x['gap_in_monte_carlo_se']>3 for x in cells),
              largest_idealised_gap=max(x['idealised_gap'] for x in cells)))
    return out

def run(replications=1000,seed=20261114,reference_size=4_000_000,calibration_size=50_000_000,check_replications=200_000,two_sample_replications=2000,small_null_replications=200_000,log_steps=True):
    if replications<400: raise ValueError('At least 400 replications required')
    started=time.monotonic(); rng=np.random.default_rng(seed)
    log=_log if log_steps else (lambda *a,**k:None)      # smoke runs do not write to the run log
    calibration,national=calibrate(rng,calibration_size)
    sds=[calibration['intervals'][k]['sd_log_duration'] for k in CORE]
    cohort=calibration['cohort_check']
    sizes=sample_size_table(sds,cohort['published_implied_log_sd'])
    log('calibrate_interval_log_sd','python -m eventlog.run_all',metrics=dict(episodes=calibration_size,
        sd_log_duration=dict(zip(CORE,sds)),elapsed_seconds=time.monotonic()-started))
    check=sample_size_check(rng,sds,national,check_replications)
    log('sample_size_check','python -m eventlog.run_all',metrics=dict(replications=check_replications,
        largest_gap=max(x['absolute_gap'] for x in check),elapsed_seconds=time.monotonic()-started))
    print('sample-size check done',flush=True)
    two_sample=rest_of_country_check(rng,sds,two_sample_replications)
    log('rest_of_country_check','python -m eventlog.run_all',metrics=dict(cells=len(two_sample),replications=two_sample[0]['replications'],
        lowest_power_at_infinite_reference_n=min(x['empirical_power'] for x in two_sample if x['county_n_kind']=='infinite_reference_n'),
        lowest_power_at_rest_of_country_n=min(x['empirical_power'] for x in two_sample if x['county_n_kind']=='rest_of_country_n'),elapsed_seconds=time.monotonic()-started))
    print('rest-of-country check done',flush=True)
    small_null=small_county_null(rng,national,small_null_replications)
    log('small_county_null','python -m eventlog.run_all',metrics=dict(replications=small_null_replications,
        rate_t={x['n']:x['false_positive_rate_t'] for x in small_null},rate_normal_quantile={x['n']:x['false_positive_rate_normal_quantile'] for x in small_null},
        nominal_at_most=small_null[0]['nominal_at_most'],elapsed_seconds=time.monotonic()-started))
    refs={(missing,month):streamed_reference(rng,reference_size,missing,month) for missing in [0.,.2] for month in [0.,.5]}
    log('reference_pools','python -m eventlog.run_all',metrics=dict(episodes_per_condition=reference_size,conditions=len(refs),elapsed_seconds=time.monotonic()-started))
    tables=[]; nulls=[]
    for n in SIZES:
        truth=pathways(rng,(replications,n))
        for missing in [0.,.2]:
            for month in [0.,.5]:
                observed,mask=observe(rng,truth,missing,month)
                null_result={}
                for d in ['D2','D3']:
                    stats,hit,_=evaluate(observed,refs[(missing,month)][d],d,0,mask)
                    null_result[d]=float(hit.mean())
                nulls.extend([dict(design=d,n=n,missingness=missing,month_share=month,
                    county_false_positive_rate=null_result.get('D3' if d=='D4' else d),
                    structural=d=='D1') for d in DESIGNS])
                for stage in range(3):
                    for ratio in RATIOS:
                        planted=plant(truth,stage,ratio)
                        observed,mask=observe(rng,planted,missing,month)
                        result={}
                        for d in ['D2','D3']:
                            result[d]=evaluate(observed,refs[(missing,month)][d],d,stage,mask)[0]
                        # an interval is usable when both dates are present and both are known to the day
                        keep=(1-missing)**2*(1-month)**2
                        analytic=analytic_power(ratio,n*keep,sigma=sds[stage],reference_n=reference_size*keep)
                        ideal=analytic_power(ratio,n*keep,reference_n=reference_size*keep)
                        se=monte_carlo_se(analytic,ratio,n*keep,sds[stage],reference_size*keep,replications)[2]
                        for d in DESIGNS:
                            stats=structural() if d=='D1' else dict(result['D3' if d=='D4' else d])
                            core=d in ['D3','D4']; gap=abs(stats['planted_test_power']-analytic) if core else None
                            tables.append(dict(design=d,n=n,slowdown=ratio,stage=INTERVALS[stage],missingness=missing,
                              month_share=month,expected_testable_episodes=n*keep,**stats,analytic_power=analytic if core else None,
                              analytic_power_idealised=ideal if core else None,
                              empirical_analytic_gap=gap,monte_carlo_se=se if core else None,
                              gap_in_monte_carlo_se=gap/se if core and .02<=analytic<=.98 else None,
                              idealised_gap=abs(stats['county_power']-ideal) if core else None))
        log('design_grid_size','python -m eventlog.run_all',metrics={'n':n,'completed_cells':len(tables),'elapsed_seconds':time.monotonic()-started})
        print(f'design grid: n={n}, rows={len(tables)}',flush=True)
    # Family-wise null experiments: every county actually sampled and tested against the rest of
    # the country; no synthetic independent p-values substituted for durations.
    family_null=familywise_null(rng,replications)
    log('familywise_null','python -m eventlog.run_all',metrics=dict(rows=len(family_null),
        largest=max(x['familywise_false_positive_rate'] for x in family_null),elapsed_seconds=time.monotonic()-started))
    looks_null=repeated_looks_null(rng,replications)
    log('repeated_looks_null','python -m eventlog.run_all',metrics=dict(rows=len(looks_null),
        by_final_look={f"{x['layout']} | {x['threshold']}":x['any_false_flag_by_look'][-1]['rate'] for x in looks_null},elapsed_seconds=time.monotonic()-started))
    print('null experiments done',flush=True)
    # Controlled log-normal formula check separates stage-sum/route mixture
    # effects from Monte Carlo error in the specified power formula.
    calibration_check=[]
    for ratio in RATIOS:
        n=sample_size(ratio)
        x=rng.normal(np.log(ratio),IDEAL_SIGMA,(replications,n))
        z=x.mean(axis=1)/(IDEAL_SIGMA/np.sqrt(n))
        p=float((np.abs(z)>critical()).mean())
        calibration_check.append(dict(ratio=ratio,n=n,empirical_power=p,analytic_power=analytic_power(ratio,n),absolute_gap=abs(p-analytic_power(ratio,n))))
    early=early_warning(rng,replications,refs[(0.,0.)])
    counties=county_detectability(sds)
    extraction=extraction_study(rng,replications,pathways(rng,(100_000,)))
    # Added after the second review, each with its own random stream so that every earlier
    # experiment keeps exactly the draws of the previous run.
    month_null=small_county_month_null(np.random.default_rng([seed,1]),national,small_null_replications)
    log('small_county_month_null','python -m eventlog.run_all',metrics=dict(replications=small_null_replications,month_share=.5,
        rate_t={x['n']:x['false_positive_rate_t'] for x in month_null},rate_among_tested={x['n']:x['false_positive_rate_among_tested'] for x in month_null},
        nominal_at_most=month_null[0]['nominal_at_most'],elapsed_seconds=time.monotonic()-started))
    measured=measured_extraction_study(np.random.default_rng([seed,2]),replications)
    log('measured_extraction_study','python -m eventlog.run_all',inputs=sorted({k for p in measured['profiles'] for k in p['sources']}),metrics=dict(
        profiles={p['profile']:dict(wrong_date_share=p['wrong_date_share'],missing_share=p['missing_share'],check=p['check']) for p in measured['profiles']},
        stage_power={f"{x['condition']} {x['profile']} n={x['n']} {x['stage']}":x['stage_power'] for x in measured['rows'] if x['kind']=='planted'},
        null_rate={f"{x['condition']} {x['profile']} n={x['n']}":x['county_false_positive_rate'] for x in measured['rows'] if x['kind']=='null'},
        elapsed_seconds=time.monotonic()-started))
    gaps=gap_summary(tables)
    clean=gaps[0]; worst=max(gaps,key=lambda x:x['largest_gap'])
    def side(power,gap,z):
        w=max(check,key=lambda x:x[gap])
        return dict(min_power=min(x[power] for x in check),max_power=max(x[power] for x in check),largest_gap=w[gap],
          largest_gap_in_monte_carlo_se=w[z],largest_gap_cell=dict(interval=w['interval'],slowdown=w['slowdown'],n=w['n']),
          cells_beyond_3_monte_carlo_se=sum(x[z]>3 for x in check))
    check_summary=dict(cells=len(check),replications=check_replications,target_power=.8,
      monte_carlo_se='sqrt(binomial variance of the replications + variance from the sampling error of the one fixed reference mean)',
      known_sd=side('known_sd_power','known_sd_gap','known_sd_gap_in_monte_carlo_se'),
      detector=side('empirical_power','absolute_gap','gap_in_monte_carlo_se'),
      detector_mean_signed_gap_by_interval={k:float(np.mean([x['signed_gap'] for x in check if x['interval']==k])) for k in CORE})
    report=dict(schemaVersion='1.1',seed=seed,replications=replications,synthetic=True,
      pathway_order=PATHWAY_ORDER,
      settings=dict(step_log_sd=SIGMA,idealised_sigma=IDEAL_SIGMA,reference_episodes=reference_size,counties=23,core_comparisons=69,
        n_definition='Latent complete episodes before independent event-level missingness; observed n reported per cell.',
        missingness='Independent per timestamp; endpoint completeness is (1-m)^2, not (1-m).',
        precision='MONTH dates are stored at the Gregorian month midpoint and flagged; pairs with a MONTH endpoint are excluded from the test. Negative measured spans excluded, zero-day spans logged as 0.5 day, effective n reported.',
        observation='MONTH dates are interval-valued; they are kept in the data but carry no weight in the mean-log test.',
        reference='Design grid and early warning: independent fixed synthetic rest-of-country pool per observation condition, conditional Monte Carlo; finite reference SE retained. Null experiments and the rest-of-country check: each county against the other episodes of the same simulated country. The two text-extraction experiments use their own pools of 100000 episodes. The single-county null experiments use the calibration sample as reference.',
        test='Welch test of mean log-duration with Student t critical values (Welch-Satterthwaite degrees of freedom); a county is tested in an interval only with at least %d complete day-precision episodes.'%MIN_TEST_N,
        month_precision='A date known to the month only is not used in the test: an interval is testable when both of its dates are present and known to the day.',
        family='One look: 23 counties x 3 intervals = 69 comparisons (a = 0.05/69). The early-warning study counts its %d planned quarterly looks in the family (a = 0.05/(69 x %d)), a Bonferroni upper bound for overlapping rolling windows. Cancer-site strata are not in the family; each stratum analysed separately multiplies it again.'%(LOOKS,LOOKS),
        national_cases='%d new cases a year is an assumption used for county sizes; it is not an observed incidence.'%NATIONAL_CASES,
        monte_carlo_se='Binomial error of the replications plus the sampling error of the one fixed reference mean (delta method on the analytic power); gap_in_monte_carlo_se is only given where the analytic power is between 0.02 and 0.98.',
        intermediate_events='One pathway order. REFERRAL_RECEIVED = REFERRAL_SENT + min(U(0,3) days, time to DIAGNOSIS); DIAGNOSIS = REFERRAL_SENT + %s x (referral-to-specialist step), an unsourced modelling constant that sets the diagnostic and treatment columns; MDT_DECISION uniform between DIAGNOSIS and SPECIALIST_VISIT, also a modelling choice; TREATMENT_START = SPECIALIST_VISIT + last step. Latent times are cumulative sums of non-negative gaps.'%DIAGNOSIS_FRACTION,
        slowdown='A planted slowdown multiplies every gap inside one core interval and shifts all later events.',
        stage_dependence='Diagnostic span is 0.6 x the referral-to-specialist step; treatment span is 0.4 x that step plus the last step, so the two are positively correlated but not identical.',
        log_duration='log(days) on whole-day intervals; a zero-day interval is logged as 0.5 day; positive intervals are unchanged.',
        analytic_power='Normal approximation for the planted interval own two-sided test at Bonferroni 0.05/69, with the measured per-interval log-SD, testable n = n(1-m)^2(1-q)^2 (m: share of dates missing, q: share of dates known to the month only) and the finite reference. The detector uses t quantiles and a minimum n, which the formula does not.',
        empirical_power='planted_test_power: share of replications where the planted interval own test rejects. county_power (any of the three tests rejects) is kept as a separate outcome.',
        assumptions='National case count, routes, route shares, distributions, thresholds, censor cutoff and simulated effects are assumptions, not Finnish observations.'),
      interval_log_sd=calibration,
      sample_sizes=dict(formula='n >= s^2 (z_{1-a/2} + z_power)^2 / (ln r)^2, a = 0.05/69, power 0.8',idealised_sigma=IDEAL_SIGMA,
        sigma_by_interval=dict(zip(CORE,sds)),cohort_implied_sigma=cohort['published_implied_log_sd'],national_cases_assumed=NATIONAL_CASES,planned_looks=LOOKS,
        rest_of_country_formula='n (N - n) / N >= s^2 (z_{1-a/2} + z_power)^2 / (ln r)^2, N = episodes in the country in the period',
        n_relative_standard_error_from_sd={k:2*calibration['intervals'][k]['sd_standard_error']/calibration['intervals'][k]['sd_log_duration'] for k in CORE},
        rows=sizes),
      sample_size_check=check,sample_size_check_summary=check_summary,rest_of_country_check=two_sample,binomial_n=binomial_size(),
      repeated_looks_null=looks_null,small_county_null=small_null,small_county_null_month=month_null,county_detectability=counties,county_population_year=populations()[0],minimum_testable_episodes=MIN_TEST_N,
      design_grid=tables,null_by_cell=nulls,familywise_null=family_null,analytic_calibration=calibration_check,
      power_gap_by_condition=gaps,
      largest_absolute_power_gap=worst['largest_gap'],
      largest_power_gap_day_precision_complete=clean['largest_gap'],
      largest_sample_size_check_gap=check_summary['detector']['largest_gap'],
      largest_idealised_power_gap=max(x['largest_idealised_gap'] for x in gaps),
      largest_calibrated_absolute_gap=max(r['absolute_gap'] for r in calibration_check),
      early_warning=early,text_extraction=extraction,measured_text_extraction=measured,findings=[])
    I=calibration['intervals']; K=check_summary['known_sd']; W=check_summary['detector']; M=check_summary['detector_mean_signed_gap_by_interval']
    representative=[x for x in tables if x['design']=='D3' and x['n']==500 and x['slowdown']==1.2 and x['missingness']==0 and x['month_share']==0]
    row=lambda r:next(x for x in sizes if x['slowdown']==r)
    wc=worst['largest_gap_cell']; cc=clean['largest_gap_cell']
    pct=lambda r:round((r-1)*100); name=lambda k:k.replace('_',' ')
    where=lambda c:f"{name(c['interval'])}, {pct(c['slowdown'])}% slowdown, n = {c['n']}"
    fam=lambda layout,month:next(x for x in family_null if x['design']=='D3' and x['layout']==layout and x['month_share']==month)
    lk=lambda layout,thr:next(x for x in looks_null if x['layout']==layout and x['threshold']==thr)['any_false_flag_by_look']
    L0=looks_null[0]['layout']; L1=looks_null[2]['layout']
    ro=lambda period,kind:[x for x in two_sample if x['period']==period and x['county_n_kind']==kind]
    small=[c for c in counties if c['assumed_cases_per_quarter']<MIN_TEST_N]
    reach=lambda period,r:sum(1 for c in counties if all(v is not None and v<=r for v in c[f'min_detectable_slowdown_{period}'].values()))
    untest=[x for x in tables if x['design']=='D3' and x['expected_testable_episodes']<MIN_TEST_N]
    report['findings']=[
      f"One pathway order is used by simulator, validator and document: {PATHWAY_ORDER}. In {calibration['episodes']} simulated episodes rounded to whole days it is violated {calibration['whole_day_chronology_violations']} times.",
      f"The design grid contains {len(tables)} design cells with {replications} replications per cell.",
      f"Measured standard deviation of log-duration in {calibration['episodes']} simulated episodes (whole days, zero-day intervals logged as {ZERO_DAY} day): "
        +", ".join(f"{name(k)} {I[k]['sd_log_duration']:.4f}" for k in CORE)+f"; the idealised single-step value is {IDEAL_SIGMA}. Wider than idealised: {', '.join(name(k) for k in CORE if I[k]['sd_log_duration']>IDEAL_SIGMA) or 'none'}; narrower: {', '.join(name(k) for k in CORE if I[k]['sd_log_duration']<=IDEAL_SIGMA) or 'none'}.",
      "By route (fast, public) the standard deviation of log-duration is: "+"; ".join(f"{name(k)} {I[k]['by_route']['fast']['sd_log_duration']:.4f}, {I[k]['by_route']['public']['sd_log_duration']:.4f}" for k in CORE)+".",
      "Share of zero-day intervals in that sample: "+", ".join(f"{name(k)} {I[k]['zero_day_share']:.6f}" for k in CORE)+".",
      f"Cohort check, public route, symptom onset to treatment start ({cohort['episodes']} simulated episodes): simulated mean {cohort['simulated_mean_days']:.1f} days, median {cohort['simulated_median_days']:.1f}, log-SD {cohort['simulated_log_sd']:.3f}; published mean {cohort['published_mean_days']}, median {cohort['published_median_days']}, implied log-SD {cohort['published_implied_log_sd']:.3f}. The simulator matches the published mean, not the published median.",
      f"Idealised sizing (s = {IDEAL_SIGMA}) requires {row(1.1)['idealised']}, {row(1.2)['idealised']}, {row(1.3)['idealised']} and {row(1.5)['idealised']} complete episodes for 10%, 20%, 30% and 50% slowdowns; with the cohort-implied spread (s = {cohort['published_implied_log_sd']:.4f}) it requires {row(1.1)['cohort_spread']}, {row(1.2)['cohort_spread']}, {row(1.3)['cohort_spread']} and {row(1.5)['cohort_spread']}.",
      *[f"Per-interval sizing for {name(k)} (s = {I[k]['sd_log_duration']:.4f}) requires {row(1.1)[k]}, {row(1.2)[k]}, {row(1.3)[k]} and {row(1.5)[k]} complete episodes for 10%, 20%, 30% and 50% slowdowns." for k in CORE],
      f"With the rest of the country as comparator ({NATIONAL_CASES} episodes a year, an assumption) a 10% slowdown requires "+", ".join(f"{name(k)} {row(1.1)['rest_of_country']['year'][k]}" for k in CORE)
        +f"; against one quarter ({NATIONAL_CASES//4} episodes) a 20% slowdown requires "+", ".join(f"{name(k)} {row(1.2)['rest_of_country']['quarter'][k]}" for k in CORE)+".",
      f"Formula check at exactly the per-interval n ({check_replications} replications in each of {len(check)} cells), with the measured SD treated as known as the formula assumes: simulated power ranges from {K['min_power']:.4f} to {K['max_power']:.4f}; the largest gap to the analytic power is {K['largest_gap']:.4f} ({where(K['largest_gap_cell'])}), {K['largest_gap_in_monte_carlo_se']:.2f} Monte Carlo standard errors; {K['cells_beyond_3_monte_carlo_se']} of {len(check)} cells are beyond 3 standard errors.",
      f"Same cells with the detector as run (variance estimated in each county, t quantiles): simulated power ranges from {W['min_power']:.4f} to {W['max_power']:.4f}; the largest gap to the analytic power is {W['largest_gap']:.4f} ({where(W['largest_gap_cell'])}), {W['largest_gap_in_monte_carlo_se']:.2f} Monte Carlo standard errors; {W['cells_beyond_3_monte_carlo_se']} of {len(check)} cells are beyond 3 standard errors.",
      "Mean signed gap of the detector (simulated minus analytic power) by interval: "+", ".join(f"{name(k)} {M[k]:+.4f} (skewness of log-duration {I[k]['skewness_log_duration']:+.3f})" for k in CORE)+".",
      f"Rest-of-country comparator, fully simulated ({two_sample[0]['replications']} replications per cell): at the infinite-reference n the power is {min(x['empirical_power'] for x in ro('quarter','infinite_reference_n')):.3f} to {max(x['empirical_power'] for x in ro('quarter','infinite_reference_n')):.3f} for a 20% slowdown against one quarter and {min(x['empirical_power'] for x in ro('year','infinite_reference_n')):.3f} to {max(x['empirical_power'] for x in ro('year','infinite_reference_n')):.3f} for a 10% slowdown against one year; at the two-sample n it is {min(x['empirical_power'] for x in ro('quarter','rest_of_country_n')):.3f} to {max(x['empirical_power'] for x in ro('quarter','rest_of_country_n')):.3f} and {min(x['empirical_power'] for x in ro('year','rest_of_country_n')):.3f} to {max(x['empirical_power'] for x in ro('year','rest_of_country_n')):.3f}.",
      f"In the design grid at day precision without missing events the largest gap between the planted interval's simulated power and its per-interval analytic power is {clean['largest_gap']:.4f} ({name(cc['stage'])}, n = {cc['n']}, {pct(cc['slowdown'])}% slowdown; {clean['cells_beyond_3_monte_carlo_se']} of the {clean['cells_with_analytic_power_between_0_02_and_0_98']} cells with analytic power between 0.02 and 0.98 are beyond 3 Monte Carlo standard errors).",
      "Largest gap by observation condition (missingness, month-precision share), with month-precision pairs left out of the test and counted out of n in the formula: "+"; ".join(f"({g['missingness']}, {g['month_share']}) {g['largest_gap']:.4f}" for g in gaps)+".",
      f"The largest gap over all observation conditions is {worst['largest_gap']:.4f} (missingness {worst['missingness']}, month-precision share {worst['month_share']}, {name(wc['stage'])}, n = {wc['n']}, {pct(wc['slowdown'])}% slowdown: simulated {wc['planted_test_power']:.4f} against analytic {wc['analytic_power']:.4f}).",
      f"Month precision costs episodes instead of validity: with half of the dates known to the month only, a quarter of the intervals are testable. {len(untest)} of the {len([x for x in tables if x['design']=='D3'])} D3 cells expect fewer than {MIN_TEST_N} testable episodes and are not tested at all.",
      f"Under the first implementation's definition (any of the three tests rejects, s = {IDEAL_SIGMA}) the largest gap is {report['largest_idealised_power_gap']:.4f}.",
      f"The binomial target comparison requires {binomial_size()} episodes.",
      f"D3 county power at n=500 and a 20% slowdown without observation loss ranges from {min(x['county_power'] for x in representative):.4f} to {max(x['county_power'] for x in representative):.4f} across planted stages.",
      f"The matched log-normal calibration has a largest absolute power gap of {report['largest_calibrated_absolute_gap']:.4f}.",
      "Family-wise false-positive rate with no slowdown anywhere (D3, each county against the rest of the country, one look; day precision / half of the dates month precision): "
        +"; ".join(f"{lay}: {fam(lay,0.)['familywise_false_positive_rate']:.3f} / {fam(lay,.5)['familywise_false_positive_rate']:.3f}" for lay in dict.fromkeys(x['layout'] for x in family_null))+".",
      "One county against a large reference, no slowdown, any of the three tests rejecting (nominal at most %.5f): "%small_null[0]['nominal_at_most']
        +"; ".join(f"n = {x['n']}: {x['false_positive_rate_t']:.5f} with t quantiles, {x['false_positive_rate_normal_quantile']:.5f} with the normal quantile" for x in small_null)+".",
      f"The maximum measured family-wise null false-positive rate over timestamp designs, layouts and precisions is {max(x['familywise_false_positive_rate'] for x in family_null):.4f}.",
      f"Repeated quarterly looks with no slowdown anywhere ({L0}; rolling four-quarter window): with the single-look threshold at least one false flag appears in {lk(L0,'single_look')[-1]['rate']:.3f} of replications within {LOOKS} looks ({lk(L0,'single_look')[0]['rate']:.3f} at the first look); with the {LOOKS} looks counted in the family it is {lk(L0,'looks_in_family')[-1]['rate']:.3f}. Population-proportional counties: {lk(L1,'single_look')[-1]['rate']:.3f} and {lk(L1,'looks_in_family')[-1]['rate']:.3f}.",
      f"Early warning with the {LOOKS} looks counted in the family: the largest pre-onset false-alarm rate of a single county over 4 looks is {max(x['pre_onset_false_alarm_rate'] for x in early if x['design']!='D1'):.4f}.",
      f"County sizes under the assumption of {NATIONAL_CASES} cases a year range from {min(c['assumed_annual_cases'] for c in counties)} to {max(c['assumed_annual_cases'] for c in counties)}; {reach('quarter',1.2)} of {len(counties)} counties can detect a 20% slowdown in every interval within one quarter, {reach('year',1.2)} within one year, and {reach('year',1.1)} can detect 10% within one year. {len(small)} counties have fewer than {MIN_TEST_N} assumed cases a quarter.",
      f"D1 has {len([x for x in tables if x['design']=='D1'])} structurally unidentifiable cells; D2 also cannot localise among the three core stages.",
      f"Where each s comes from: computed from the cohort (sqrt(2 ln(mean/median)) of the published symptom-to-treatment figures) it is {cohort['published_implied_log_sd']:.3f} on the public route and {cohort['fast']['published_implied_log_sd']:.3f} on the private or occupational route; "
        f"computed from the simulator it is the per-interval value above; the simulator's step value {SIGMA} is an input that {'neither route reproduces' if not cohort['step_sigma_reproduced_by_cohort'] else 'one route reproduces'}.",
      "One county with half of its dates at month precision (those pairs not tested), no slowdown, against a large reference: "
        +"; ".join(f"n = {x['n']}: any test rejects in {x['false_positive_rate_t']:.5f} of counties, "+(f"{x['false_positive_rate_among_tested']:.5f} among the {x['counties_with_a_test_share']:.3f} with at least one test" if x['false_positive_rate_among_tested'] is not None else 'no county is tested') for x in month_null)
        +f" (nominal at most {month_null[0]['nominal_at_most']:.5f}).",
      *[(lambda E,P,N:f"Measured per-event error, {E['system']} ({E['wrong_date_share']:.3f} of the found events with a wrong date, up to {E['largest_absolute_error_days']} days; {E['missing_share']:.3f} of true events not found), drawn independently per date: "
        +"; ".join(f"in a county of {n} episodes a 30% slowdown is located in its interval in "+", ".join(f"{P(E['profile'],n,k):.3f}" for k in CORE)+" of runs (primary care, diagnostic, treatment) against "+", ".join(f"{P(None,n,k):.3f}" for k in CORE)+" with every event confirmed" for n in sorted({x['n'] for x in measured['rows']}))
        +". With no slowdown, a county whose dates are extracted while the rest of the country uses structured dates is flagged in "+" and ".join(f"{N(E['profile'],n):.3f} (n = {n})" for n in sorted({x['n'] for x in measured['rows']}))+" of runs.")(
        E,lambda prof,n,k:next(x['stage_power'] for x in measured['rows'] if x['kind']=='planted' and x['profile']==prof and x['n']==n and x['stage']==k),
        lambda prof,n:next(x['county_false_positive_rate'] for x in measured['rows'] if x['kind']=='null' and x['condition']=='measured_county_only' and x['profile']==prof and x['n']==n))
        for E in measured['profiles']]
    ]
    return report

def early_warning(rng,reps,refs):
    """A slowdown starts in quarter 5 of 12; each quarter the last four quarters of one county are
    tested against the reference. The 12 planned looks are counted in the Bonferroni family
    (a = 0.05/(69 x 12)), so the false-alarm probability over the whole horizon stays near 5%."""
    n=250; records=[]
    for stage in range(3):
        for ratio in RATIOS:
            truth=pathways(rng,(reps,12,n))
            truth[:,4:]=plant(truth[:,4:],stage,ratio)
            obs,_=observe(rng,truth)
            for d in DESIGNS:
                base=dict(design=d,stage=INTERVALS[stage],slowdown=ratio,n_per_quarter=n,quarters=12,onset_quarter=5,window_quarters=4,
                    looks_in_family=LOOKS,comparisons=69*LOOKS)
                if d=='D1': records.append(dict(base,median_quarters_to_detection=None,localisation='structurally_impossible'));continue
                first=np.full(reps,99); pre=np.zeros(reps,bool)
                for q in range(12):
                    window=obs[:,max(0,q-3):q+1].reshape(reps,-1,9)
                    _,hit,_=evaluate(window,refs['D3' if d=='D4' else d],d,stage,looks=LOOKS)
                    if q<4: pre|=hit
                    else: first=np.where((first==99)&hit,q-3,first)
                detected=first<99; rate=float(detected.mean())
                records.append(dict(base,detected_by_quarter12=rate,pre_onset_false_alarm_rate=float(pre.mean()),
                  median_quarters_to_detection=float(np.sort(first)[int(np.ceil(reps*.5))-1]) if rate>=.5 else None,
                  conditional_median_quarters=float(np.median(first[detected])) if detected.any() else None,
                  undetected_right_censored=int((~detected).sum()),localisation='structurally_impossible' if d=='D2' else 'core_stages'))
    return records

def extraction_study(rng,reps,reference_truth):
    records=[]; n=500; ratio=1.3
    truth=pathways(rng,(reps,n))
    errors=[0.,.02,.05,.1]
    # The reference is observed once per error setting, with the same error process as the county.
    references={}
    for et in errors:
        for ed in errors:
            ref,_=observe(rng,reference_truth,e_type=et,e_date=ed)
            references[(et,ed)]={d:moments(log_spans(ref,'D2' if d=='D2' else 'D3')) for d in ['D2','D3','D4']}
    for stage in range(3):
        a,b=ENDPOINTS[stage]
        target=plant(truth,stage,ratio)
        true_med=np.median(target[...,b]-target[...,a],axis=1)
        baseline={}
        for et in errors:
            for ed in errors:
                obs,_=observe(rng,target,e_type=et,e_date=ed)
                for d in ['D2','D3','D4']:
                    stats,_,_=evaluate(obs,references[(et,ed)][d],d,stage)
                    if et==0 and ed==0: baseline[d]=stats['stage_power']
                    if d!='D2':
                        spans=obs[...,b]-obs[...,a]
                        measured=np.nanmedian(np.where(spans>=0,spans,np.nan),axis=1)
                        bias=float(np.nanmean(measured-true_med))
                    else:
                        composite=obs[...,D2_ENDPOINTS[1]]-obs[...,D2_ENDPOINTS[0]]
                        measured=np.nanmedian(np.where(composite>=0,composite,np.nan),axis=1)
                        bias=float(np.nanmean(measured-np.median(target[...,D2_ENDPOINTS[1]]-target[...,D2_ENDPOINTS[0]],axis=1)))
                    records.append(dict(design=d,source='TEXT_EXTRACTED',stage=INTERVALS[stage],slowdown=ratio,n=n,
                      e_type=et,e_date=ed,median_bias_days=bias,median_estimand='referral_received_to_treatment' if d=='D2' else INTERVALS[stage],**stats,
                      localisation_power_loss=baseline[d]-stats['stage_power'] if d!='D2' else None,
                      error_policy='Wrong-type collisions and missing endpoints abstain; negative spans are excluded; no chronology repair. Same error process in target and country.'))
    return records

SCRIBE_EVAL='data/scribe/eval-v1.json'
V2_PREDICTIONS='data/scribe/v3/student/v2-selected/A-270m-lora-r16--test_nemotron+test_haiku--off.json'
V2_LABELS={'test_nemotron':'data/scribe/v2/dataset/test_nemotron.parquet','test_haiku':'data/scribe/v2/dataset/test_haiku.parquet'}

def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _summary(errors,true_events,**extra):
    return dict(true_events=true_events,events_with_type_found=len(errors),exact_dates=sum(1 for x in errors if x==0),
      wrong_date_share=sum(1 for x in errors if x!=0)/len(errors),missing_share=1-len(errors)/true_events,
      largest_absolute_error_days=max(abs(x) for x in errors),date_errors_days=errors,**extra)

def v1_event_errors(path=SCRIBE_EVAL):
    """Version-1 adapter (Gemma 3 1B, LoRA, MLX) on its 200 held-out SYNTHETIC test notes: the signed
    date errors of the true events whose type was found, as computed by the scribe's own evaluator."""
    a=json.loads(Path(path).read_text())['test']['adapter']
    return _summary([int(x) for x in a['date_errors_days']],int(a['recall']['n']),profile='v1_1b_nemotron_notes',
      system='version-1 adapter, Gemma 3 1B LoRA (MLX), 200 Nemotron-written test notes',sources={path:_sha(path)},
      check='date errors as stored by the scribe evaluator',extra_predicted_events=None)

def v2_event_errors(split,predictions=V2_PREDICTIONS):
    """Selected version-2 adapter (Gemma 3 270M, LoRA r16, unconstrained greedy decoding) on one test
    split: each true event is matched to the predicted events of the same type; it is found when one
    exists with a readable date, its error is 0 if any of them has the exact date and otherwise the
    error of the first. Extra predicted events of a type the note does not have are counted, not
    modelled. The recall this gives must equal the evaluator's stored event recall."""
    import ast
    from datetime import date
    import pyarrow.parquet as pq
    run=json.loads(Path(predictions).read_text())['splits'][split]
    gold={r['id']:r for r in pq.read_table(V2_LABELS[split]).to_pylist()}
    errors=[]; true_events=0; extra=0; exact_found=0
    for r in run['records']:
        g=gold[r['id']]['events']; g=g if isinstance(g,list) else ast.literal_eval(g)
        pred=((r.get('prediction') or {}).get('events')) or []
        types={e['type'] for e in g}; extra+=sum(1 for e in pred if e['type'] not in types)
        for e in g:
            true_events+=1; days=[]
            for q in pred:
                if q['type']!=e['type']: continue
                try: days.append((date.fromisoformat(q['date'])-date.fromisoformat(e['date'])).days)
                except (TypeError,ValueError): pass
            if days: errors.append(0 if 0 in days else days[0]); exact_found+=0 in days
    stored=run['metrics']['event_recall']
    if not (stored['n']==true_events and abs(stored['value']-exact_found/true_events)<1e-12):
        raise ValueError(f'{split}: recomputed recall {exact_found}/{true_events} differs from the stored {stored}')
    writer='Nemotron' if 'nemotron' in split else 'Haiku'
    return _summary(errors,true_events,profile=f'v2_270m_{writer.lower()}_notes',
      system=f'selected version-2 adapter, Gemma 3 270M LoRA r16, {len(run["records"])} {writer}-written test notes',
      sources={predictions:_sha(predictions),V2_LABELS[split]:_sha(V2_LABELS[split])},
      check=f'recomputed event recall {exact_found}/{true_events} equals the stored {stored["value"]:.4f}',extra_predicted_events=extra)

def measured_extraction_errors():
    return [v2_event_errors('test_nemotron'),v2_event_errors('test_haiku'),v1_event_errors()]

def measured_extraction_study(rng,reps,reference_size=100_000,sizes=(500,2000),ratio=1.3):
    """The text-extraction experiment with the measured error of the scribe instead of assumed rates,
    one run per measured error profile. Every date gets a signed error drawn independently from the
    profile's measured errors (zeros included) and every event is lost with the measured share whose
    type was not found. D3 detector (D4 uses the same one). Conditions:
      confirmed            every extracted event checked by a person; assumed to remove the error,
      measured_everywhere  county and rest of the country both extracted with the measured error,
      measured_county_only the county extracted, the rest of the country from structured fields
                           (null rows only: does a different data source alone raise flags?).
    Real errors are not independent within a note (a note with a relative date has all its dates
    wrong), and extra predicted events are not modelled; how either changes these figures was not
    measured."""
    profiles=measured_extraction_errors()
    ref_truth=pathways(rng,(reference_size,))
    clean_ref=moments(log_spans(np.rint(ref_truth)))
    rows=[]
    for n in sizes:
        truth=pathways(rng,(reps,n)); targets=[plant(truth,stage,ratio) for stage in range(3)]
        def planted(condition,profile,observe_fn,ref):
            for stage in range(3):
                a,b=ENDPOINTS[stage]; target=targets[stage]; obs=observe_fn(target)
                true_med=np.median(target[...,b]-target[...,a],axis=1)
                stats,_,_=evaluate(obs,ref,'D3',stage)
                spans=obs[...,b]-obs[...,a]
                measured=np.nanmedian(np.where(spans>=0,spans,np.nan),axis=1)
                rows.append(dict(kind='planted',condition=condition,profile=profile,n=n,stage=INTERVALS[stage],slowdown=ratio,replications=reps,**stats,
                  median_bias_days=float(np.nanmean(measured-true_med)),true_median_days=float(np.mean(true_med)),
                  negative_span_share=float(np.mean(spans<0))))
        def null(condition,profile,obs,ref):
            stats,hit,_=evaluate(obs,ref,'D3',0)
            rows.append(dict(kind='null',condition=condition,profile=profile,n=n,replications=reps,county_false_positive_rate=float(hit.mean()),
              county_false_positive_rate_ci95=wilson(int(hit.sum()),len(hit)),nominal_at_most=3*.05/69,mean_complete_episodes=stats['mean_complete_episodes']))
        planted('confirmed',None,np.rint,clean_ref)
        null('confirmed',None,np.rint(truth),clean_ref)
        for p in profiles:
            errors=np.array(p['date_errors_days'],float); miss=p['missing_share']
            noisy=lambda t:observe(rng,t,missingness=miss,date_errors=errors)[0]
            noisy_ref=moments(log_spans(noisy(ref_truth)))
            planted('measured_everywhere',p['profile'],noisy,noisy_ref)
            null('measured_everywhere',p['profile'],noisy(truth),noisy_ref)
            null('measured_county_only',p['profile'],noisy(truth),clean_ref)
    return dict(profiles=[{k:v for k,v in p.items() if k!='date_errors_days'} for p in profiles],reference_episodes=reference_size,rows=rows,
      error_model='Each date: signed error drawn independently from the measured list of its profile; each event: lost with the measured missing share. Negative spans are excluded, never repaired.',
      limits=['The measured errors come from synthetic notes written and labelled by language models, not from clinical text.',
        'Errors are drawn independently per date; real errors cluster within a note. Extra predicted events are not modelled.',
        'The confirmed condition assumes that a person removes every error; that was not measured.'])

def small_county_month_null(rng,reference,replications=200_000,sizes=(30,50,100,250,1000),month=.5,budget=3_000_000):
    """One county with no slowdown and a share `month` of its dates known to the month only (those
    pairs are not tested, as in the detector), against the large day-precision calibration reference.
    The month mask is independent of the durations, so the reference needs no month precision of its
    own. Reports the share of counties in which any of the three tests rejects, the same among the
    counties with at least one test, and the share of interval tests skipped (fewer than MIN_TEST_N
    day-precision pairs)."""
    rows=[]
    for n in sizes:
        hits=0; skipped=0; tested=0; done=0
        while done<replications:
            m=min(max(1,budget//n),replications-done)
            t,_=latent(rng,(m,n)); mask=rng.random((m,n,9))<month
            mean,var,nn=moments(log_spans(np.rint(t),'D3',mask))
            flag,_,_=test_moments(mean,var,nn,*reference)
            hits+=int(flag.any(axis=-1).sum()); skipped+=int((nn<MIN_TEST_N).sum()); tested+=int((nn>=MIN_TEST_N).any(axis=-1).sum()); done+=m
        rows.append(dict(n=n,month_share=month,replications=replications,nominal_at_most=3*.05/69,expected_testable_episodes=n*(1-month)**2,
          false_positive_rate_t=hits/replications,ci95_t=wilson(hits,replications),
          counties_with_a_test_share=tested/replications,false_positive_rate_among_tested=hits/tested if tested else None,
          ci95_among_tested=wilson(hits,tested) if tested else None,interval_tests_skipped_share=skipped/(3*replications)))
    return rows
