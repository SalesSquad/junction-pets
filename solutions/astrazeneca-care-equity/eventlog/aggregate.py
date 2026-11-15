"""Complete-case summaries; censored lower bounds never enter naive estimates."""
from collections import defaultdict
from math import comb, sqrt
import numpy as np
from .schema import INTERVALS
from .power import NORM, ZERO_DAY

def median_ci(values, confidence=.95):
    x=np.sort(values); n=len(x)
    # Invert Binomial(n,.5). Exact symmetric distribution-free coverage >=95%.
    tail=(1-confidence)/2; cumulative=0.; k=0
    # Stable recurrence avoids overflowing 2**n for large cells.
    import math
    for j in range(n//2+1):
        mass=math.exp(math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)-n*math.log(2))
        cumulative+=mass
        if cumulative>tail: break
        k=j+1
    return [float(x[k-1]) if k else None,float(x[n-k]) if k else None]

def wilson(success,n,confidence=.95):
    if not n: return [None,None]
    z=NORM.inv_cdf((1+confidence)/2); p=success/n; den=1+z*z/n
    mid=(p+z*z/(2*n))/den; half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [mid-half,mid+half]

def summarize(values,threshold):
    x=np.asarray(values,float); n=len(x)
    if n<5: return dict(n=n,suppressed=True)
    # Same convention as detect.log_days: a zero-day interval is logged as 0.5 day.
    logs=np.log(np.where(x>0,x,ZERO_DAY))
    return dict(n=n,suppressed=False,median=float(np.median(x)),median_ci95=median_ci(x),
      n_positive=int((x>0).sum()),n_zero_day_logged_as_half_day=int((x==0).sum()),mean_log_duration=float(logs.mean()) if len(logs) else None,
      sd_log_duration=float(logs.std(ddof=1)) if len(logs)>1 else None,
      se_log_duration=float(logs.std(ddof=1)/sqrt(len(logs))) if len(logs)>1 else None,
      threshold_days=threshold,share_within=float((x<=threshold).mean()),wilson_ci95=wilson(int((x<=threshold).sum()),n))

def aggregate(table,thresholds=None):
    thresholds=thresholds or dict(primary_care=90,diagnostic=60,treatment=30,total=180)
    groups=defaultdict(list); censored=defaultdict(int); missing=defaultdict(int)
    for r in table.to_pylist():
        for k in INTERVALS:
            key=(r['county'],k); x=r['days_'+k]
            groups[key]
            if r['censored_'+k]: censored[key]+=1
            elif x is None: missing[key]+=1
            elif x<0: raise ValueError(f'Negative duration in {key}; validate first')
            else: groups[key].append(x)
    return [dict(county=c,interval=k,**summarize(v,thresholds[k]),n_censored=censored[(c,k)],n_missing=missing[(c,k)]) for (c,k),v in sorted(groups.items())]
