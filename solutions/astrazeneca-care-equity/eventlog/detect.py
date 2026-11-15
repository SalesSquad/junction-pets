"""Two-sided Welch test of mean log-duration; rest-of-country comparator.
The comparator excludes the target county, avoiding overlap covariance.
Bonferroni family is counties x three core stages (or counties x one D2 span),
times the number of planned looks when the same test is repeated over time.

The critical value is a Student t quantile with Welch-Satterthwaite degrees of
freedom, because the county variance is estimated from the county's own
episodes. A normal quantile is too small for small counties.

Only intervals whose two dates are both known to the day are tested. A date
known to the month is an interval, not a point; taking its midpoint adds error
that this test does not model, so those pairs are left out of the test (they
remain in the data). A county needs MIN_TEST_N such episodes to be tested.

Log-duration convention (one definition for the detector, the measured
standard deviations and the sample-size table): dates are whole days, so an
interval can be zero days. A zero-day interval is logged as ZERO_DAY (0.5 day),
every positive interval as log(days) unchanged. Negative spans can only come
from observation error and are excluded, never repaired.
"""
import numpy as np
from .power import critical, ZERO_DAY, MIN_TEST_N
from .schema import ENDPOINTS, D2_ENDPOINTS

def log_days(spans):
    spans=np.asarray(spans,float)
    with np.errstate(invalid='ignore',divide='ignore'):
        return np.where(spans>0,np.log(np.where(spans>0,spans,1)),np.where(spans==0,np.log(ZERO_DAY),np.nan))

def log_spans(observed, design='D3', month=None):
    """Log-durations of the design's intervals. month: boolean array like observed,
    True where a date is known to the month only; such pairs become nan (not tested)."""
    if design=='D1': return np.empty((*observed.shape[:-1],0))
    pairs=[D2_ENDPOINTS] if design=='D2' else ENDPOINTS[:3]
    logs=log_days(np.stack([observed[...,b]-observed[...,a] for a,b in pairs],axis=-1))
    if month is not None:
        logs=np.where(np.stack([month[...,a]|month[...,b] for a,b in pairs],axis=-1),np.nan,logs)
    return logs

def moments(logs,axis=-2):
    ok=np.isfinite(logs); n=ok.sum(axis=axis)
    s=np.where(ok,logs,0).sum(axis=axis)
    mean=s/np.maximum(n,1)
    diff=np.where(ok,logs-np.expand_dims(mean,axis),0)
    var=(diff**2).sum(axis=axis)/np.maximum(n-1,1)
    return mean,var,n

def welch_df(var,n,reference_var,reference_n):
    a=var/np.maximum(n,1); b=reference_var/np.maximum(reference_n,1)
    with np.errstate(invalid='ignore',divide='ignore'):
        df=(a+b)**2/(a**2/np.maximum(n-1,1)+b**2/np.maximum(reference_n-1,1))
    return np.where(np.isfinite(df)&(df>=1),df,1.)

def test_moments(mean,var,n,reference_mean,reference_var,reference_n,counties=23,looks=1,min_n=MIN_TEST_N):
    """looks: planned number of repeated looks sharing the family-wise 5%."""
    se=np.sqrt(var/np.maximum(n,1)+reference_var/np.maximum(reference_n,1))
    z=(mean-reference_mean)/np.maximum(se,1e-12)
    crit=critical(comparisons=counties*mean.shape[-1]*looks,df=welch_df(var,n,reference_var,reference_n))
    flagged=(np.abs(z)>crit) & (n>=min_n) & (reference_n>=min_n)
    # Stage is selected among flagged positive delays only.
    eligible=flagged & (z>0)
    stage=np.where(eligible.any(axis=-1),np.argmax(np.where(eligible,z,-np.inf),axis=-1),-1)
    return flagged,z,stage

def detect(interval_table):
    """County-vs-rest-of-country core tests from derived interval rows.
    Zero-day intervals enter as log(0.5) and their count is reported.
    Negative spans are excluded and counted; missing/censored spans are
    excluded; spans with a month-precision endpoint are counted and not tested;
    no imputation or clipping is performed. Counties with fewer than
    MIN_TEST_N testable episodes in an interval are not tested in it.
    """
    from .schema import INTERVALS
    rows=interval_table.to_pylist();counties=sorted({r['county'] for r in rows})
    result=[]
    for county in counties:
        means=[];variances=[];sizes=[];rmeans=[];rvars=[];rns=[];zeros=[];excluded=[];inexact=[]
        for stage in INTERVALS[:3]:
            local=[];rest=[];zero=0;bad=0;month=0
            for r in rows:
                x=r['days_'+stage]
                if r['censored_'+stage] or x is None: continue
                if r.get('day_precision_'+stage) is False:
                    if r['county']==county: month+=1
                    continue
                if x<0:
                    if r['county']==county: bad+=1
                    continue
                if x==0 and r['county']==county: zero+=1
                (local if r['county']==county else rest).append(float(log_days(x)))
            for vals,ms,vs,ns in [(local,means,variances,sizes),(rest,rmeans,rvars,rns)]:
                ms.append(float(np.mean(vals)) if vals else 0.)
                vs.append(float(np.var(vals,ddof=1)) if len(vals)>1 else 0.)
                ns.append(len(vals))
            zeros.append(zero);excluded.append(bad);inexact.append(month)
        if min(rns)<MIN_TEST_N:
            result.append(dict(county=county,suppressed=True,reason=f'reference n < {MIN_TEST_N}'));continue
        flags,z,stage=test_moments(*map(np.array,[means,variances,sizes,rmeans,rvars,rns]),counties=len(counties))
        result.append(dict(county=county,tests=[dict(interval=k,n=n,zero_day_logged_as_half_day=zero,excluded_negative=bad,
          excluded_month_precision=month,tested=n>=MIN_TEST_N,
          flagged=bool(f) if n>=MIN_TEST_N else None,z=float(zz) if n>=MIN_TEST_N else None)
          for k,n,zero,bad,month,f,zz in zip(INTERVALS[:3],sizes,zeros,excluded,inexact,flags,z)],
          located_stage=INTERVALS[int(stage)] if stage>=0 else None))
    return result
