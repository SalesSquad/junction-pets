"""Individual-level synthetic episodes and explicit observation errors.

Every episode is built from non-negative gaps between consecutive events of the
one pathway order in schema.EVENT_TYPES, so latent times are chronological by
construction and stay so after rounding to whole days (rounding is monotone;
ties are allowed). Timing rules, per route:

  five log-normal steps (means FAST_MEANS / PUBLIC_MEANS, log-SD SIGMA):
    symptom onset -> first contact -> physician assessment -> referral sent
    -> first visit to the treating specialist -> treatment start
  REFERRAL_RECEIVED = REFERRAL_SENT + min(U(0,3) days, time to DIAGNOSIS)
  DIAGNOSIS         = REFERRAL_SENT + 0.6 x (referral-to-specialist step)
  MDT_DECISION      = uniform between DIAGNOSIS and SPECIALIST_VISIT
  SPECIALIST_VISIT  = REFERRAL_SENT + (referral-to-specialist step)
  TREATMENT_START   = SPECIALIST_VISIT + last step

A slowdown multiplies every gap inside one core interval (primary care,
diagnostic, treatment) and shifts all later events; order is preserved.
"""
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from .schema import EVENT_TYPES, AGE_BANDS, CANCER_SITES, ENDPOINTS, events_table
SIGMA = .96
FAST_SHARE = .45
FAST_MEANS = np.array([42,1,34,41,5.])
PUBLIC_MEANS = np.array([72,22,53,57,3.])
DIAGNOSIS_FRACTION = .6
# Gap j is the time from event j-1 to event j; a core interval (a,b) owns gaps a+1..b.
STAGE_GAPS = [list(range(a+1,b+1)) for a,b in ENDPOINTS[:3]]

def latent(rng, shape, slowdowns=(1.,1.,1.)):
    if any(r<=0 for r in slowdowns): raise ValueError('slowdown ratios must be positive')
    fast = rng.random(shape) < FAST_SHARE
    means = np.where(fast[...,None],FAST_MEANS,PUBLIC_MEANS)
    steps = rng.lognormal(np.log(means)-SIGMA**2/2,SIGMA)
    to_diagnosis = DIAGNOSIS_FRACTION*steps[...,3]
    to_specialist = steps[...,3]-to_diagnosis
    received = np.minimum(rng.uniform(0,3,shape),to_diagnosis)
    mdt = rng.uniform(0,1,shape)*to_specialist
    gaps = np.zeros((*shape,9))
    gaps[...,1] = steps[...,0]            # symptom onset -> FIRST_CONTACT
    gaps[...,2] = steps[...,1]            # -> PHYSICIAN_ASSESSMENT
    gaps[...,3] = steps[...,2]            # -> REFERRAL_SENT
    gaps[...,4] = received                # -> REFERRAL_RECEIVED
    gaps[...,5] = to_diagnosis-received   # -> DIAGNOSIS
    gaps[...,6] = mdt                     # -> MDT_DECISION
    gaps[...,7] = to_specialist-mdt       # -> SPECIALIST_VISIT
    gaps[...,8] = steps[...,4]            # -> TREATMENT_START
    for stage,ratio in enumerate(slowdowns):
        if ratio!=1: gaps[...,STAGE_GAPS[stage]] *= ratio
    return np.cumsum(gaps,axis=-1), fast

def plant(t, stage, ratio):
    """Slow one core interval of existing pathways: its gaps are multiplied by
    ratio and every later event shifts. Same mechanism as latent(slowdowns=...)."""
    if ratio<=0: raise ValueError('slowdown ratio must be positive')
    gaps = np.diff(t,axis=-1)
    gaps[...,[j-1 for j in STAGE_GAPS[stage]]] *= ratio
    return np.concatenate([t[...,:1],t[...,:1]+np.cumsum(gaps,axis=-1)],axis=-1)

def observe(rng, t, missingness=0., month_share=0., e_type=0., e_date=0., date_errors=None):
    """MONTH is represented by its month midpoint; precision is never hidden.
    Month observation uses a fixed Gregorian origin for study arrays.
    Wrong types are reassigned, not silently corrected; duplicates stay invalid.
    e_date shifts a share of dates by 1 to 30 days (an assumed error model).
    date_errors, if given, is a measured list of signed date errors in days
    (zeros included); every date gets one of them, drawn independently.
    """
    a = np.rint(t).copy()
    month = rng.random(a.shape)<month_share
    origin = np.datetime64('2020-01-01','D')
    dates = origin + a.astype('timedelta64[D]')
    starts = dates.astype('datetime64[M]').astype('datetime64[D]')
    ends = (dates.astype('datetime64[M]')+np.timedelta64(1,'M')).astype('datetime64[D]')
    mids = starts + ((ends-starts).astype(int)//2).astype('timedelta64[D]')
    a[month] = (mids-origin).astype(int)[month]
    shifted = rng.random(a.shape)<e_date
    a += shifted*rng.integers(1,31,a.shape)*rng.choice([-1,1],a.shape)
    if date_errors is not None:
        a += rng.choice(np.asarray(date_errors,float),a.shape)
    missing = rng.random(a.shape)<missingness
    if e_type:
        wrong = rng.random(a.shape)<e_type
        labels = np.broadcast_to(np.arange(9),a.shape).copy()
        labels[wrong] = (labels[wrong]+rng.integers(1,9,wrong.sum()))%9
        out = np.full_like(a,np.nan)
        for k in range(9):
            matches = (labels==k)&~missing
            count = matches.sum(axis=-1)
            out[...,k] = np.where(count==1,np.where(matches,a,0).sum(axis=-1),np.nan)
        a = out
    else:
        a[missing] = np.nan
    return a, month

def populations(snapshot='data/snapshot/public-v1.json'):
    v = json.loads(Path(snapshot).read_text())['indicators']['population']['values']
    year = max(int(y) for values in v.values() for y in values)
    return year, {c:float(values[str(year)]) for c,values in sorted(v.items()) if str(year) in values}

def simulate(national_cases=37000, seed=20261114, year=None, slowdowns=None,
             missingness=None, month_share=0., e_type=0., e_date=0.,
             data_cut=date(2030,12,31), source='STRUCTURED_FIELD'):
    """Case count is an assumption, not an observed cancer incidence.
    Largest-remainder allocation yields exactly national_cases episodes.
    Returns events and an episode roster so zero-event episodes remain visible.
    """
    rng = np.random.default_rng(seed)
    population_year,pop = populations()
    year = year or population_year
    counties = list(pop)
    weights = np.array(list(pop.values())); exact = national_cases*weights/weights.sum()
    counts = np.floor(exact).astype(int)
    counts[np.argsort(-(exact-counts))[:national_cases-counts.sum()]] += 1
    rows,roster = [],[]
    missingness = missingness or {}; slowdowns = slowdowns or {}
    for county,n in zip(counties,counts):
        factors = slowdowns.get(county,{})
        t,fast = latent(rng,(int(n),),tuple(factors.get(k,1.) for k in ['primary_care','diagnostic','treatment']))
        starts = [date(year,1,1)+timedelta(days=int(x)) for x in rng.integers(0,365,n)]
        for i in range(n):
            episode = f'SYNTHETIC-{seed}-{year}-{county}-{i}'
            route = rng.choice(['OCCUPATIONAL','PRIVATE']) if fast[i] else 'PUBLIC_PRIMARY'
            age,site = rng.choice(AGE_BANDS),rng.choice(CANCER_SITES)
            roster.append(dict(episode_id=episode,county=county,entry_route=route,year=year,synthetic=True,administratively_censored=[EVENT_TYPES[j] for j in range(9) if starts[i]+timedelta(days=int(round(t[i,j])))>data_cut]))
            for j,event in enumerate(EVENT_TYPES):
                d = starts[i]+timedelta(days=int(round(t[i,j])))
                if d>data_cut or rng.random()<missingness.get(event,0.): continue
                precision = 'MONTH' if rng.random()<month_share else 'DAY'
                if precision=='MONTH': d = d.replace(day=15)
                if source=='TEXT_EXTRACTED':
                    if rng.random()<e_type: event = EVENT_TYPES[(j+int(rng.integers(1,9)))%9]
                    if rng.random()<e_date: d += timedelta(days=int(rng.integers(1,31))*int(rng.choice([-1,1])))
                rows.append(dict(episode_id=episode,event_type=event,event_date=d,date_precision=precision,county=county,entry_route=route,cancer_site=site,age_band=age,source=source,extraction_confidence=.9 if source=='TEXT_EXTRACTED' else None,verified_by_human=False,synthetic=True))
    return events_table(rows),roster
