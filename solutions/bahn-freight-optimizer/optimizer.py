"""Deterministic, network-free Spread decision laboratory. Python 3.10+."""
import argparse
import hashlib
import json
import random
from pathlib import Path

LABEL = 'SYNTHETIC_OFFLINE'
BASE = 'a33f525171b6424d39dfc4c889b63e0fc5cb459e'
RULES = '657c44f88e36d2dab3e0b0ea28d552bdfb9796cfd61ce49634a9e3a6dd10cdbc'
MAX = 2**53 - 1  # interoperable JSON integer; Python arithmetic itself is unbounded
TRAIN = (11, 29, 47)
HOLDOUT = (101, 211, 307)  # frozen before evaluation


def integer(x, low=0, high=MAX):
    if type(x) is not int or not low <= x <= high:
        raise ValueError('integer outside accepted range')
    return x


def keys(x, required):
    if not isinstance(x, dict) or set(x) != set(required.split()):
        raise ValueError('unexpected or missing schema fields')


def ident(x):
    if not isinstance(x, str) or not x or len(x) > 80 or not all(c.isalnum() or c in '_-' for c in x):
        raise ValueError('unsafe identifier')


def validate(s):
    keys(s, 'format now level requests drivers')
    if s['format'] != 'spread-offline-mapping-v1':
        raise ValueError('explicit mapping required; raw DeskSnapshot is not accepted')
    integer(s['now'], 0, 20000); integer(s['level'], 1, 8)
    if not isinstance(s['requests'], list) or len(s['requests']) > 1000 or not isinstance(s['drivers'], list) or len(s['drivers']) > 1000:
        raise ValueError('bounded arrays required')
    seen = set()
    for d in s['drivers']:
        keys(d, 'id rating100 completedGigs manualLicence availableAt reliabilityBps')
        ident(d['id'])
        if d['id'] in seen: raise ValueError('duplicate driver')
        seen.add(d['id'])
        integer(d['rating100'], 0, 500); integer(d['completedGigs']); integer(d['availableAt'], 0, 20000)
        integer(d['reliabilityBps'], 0, 10000)
        if type(d['manualLicence']) is not bool: raise ValueError('licence bool required')
    seen = set()
    for r in s['requests']:
        keys(r, 'id respondBy referenceFeeCents options legs note status revision')
        ident(r['id'])
        if r['id'] in seen: raise ValueError('duplicate request')
        seen.add(r['id']); integer(r['respondBy'], 0, 20000); integer(r['referenceFeeCents'], 1, MAX//10000); integer(r['revision'])
        if r['status'] not in ('pending', 'cancelled'): raise ValueError('invalid status')
        if not isinstance(r['note'], str) or len(r['note']) > 2000: raise ValueError('bounded note required')
        if not isinstance(r['options'], dict) or not 1 <= len(r['options']) <= 3: raise ValueError('options required')
        for name, o in r['options'].items():
            if name not in ('same_day', 'next_day', 'within_3_days'): raise ValueError('unknown option')
            keys(o, 'deadline listPriceCents'); integer(o['deadline'], 0, 20000); integer(o['listPriceCents'], 1, MAX//10000)
        if not isinstance(r['legs'], list) or not 1 <= len(r['legs']) <= 2: raise ValueError('one or two legs required')
        for l in r['legs']:
            keys(l, 'pickup delivery roadMinutes km premium manualGearbox electric chargePercent needsPlates releasedAt snow')
            for place in ('pickup', 'delivery'):
                p = l[place]; keys(p, 'placeId window open private'); ident(p['placeId'])
                for field in ('window', 'open'):
                    w = p[field]
                    if not isinstance(w, list) or len(w) != 2: raise ValueError('interval required')
                    integer(w[0], 0, 20000); integer(w[1], w[0], 20000)
                if type(p['private']) is not bool: raise ValueError('private bool required')
            for f in ('premium', 'manualGearbox', 'electric', 'needsPlates', 'snow'):
                if type(l[f]) is not bool: raise ValueError('bool required')
            integer(l['roadMinutes'], 1, 2000); integer(l['km'], 1, 2000); integer(l['chargePercent'], 0, 100)
            if l['releasedAt'] is not None: integer(l['releasedAt'], 0, 20000)
    return s


def ceildiv(a, b): return (a+b-1)//b


def release_fee(fee_cents, minutes_to_pickup, started=False, driver_late=False):
    integer(fee_cents, 0, MAX//100); integer(minutes_to_pickup, -20000, 20000)
    if started: raise ValueError('Cannot release after gig_started')
    if driver_late: return 0
    # Boundary ambiguity resolved conservatively: exactly 24h uses 50%.
    percent = 100 if minutes_to_pickup < 120 else 50 if minutes_to_pickup <= 1440 else 25
    return ceildiv(fee_cents*percent,100)


def plan(s, r, o, high):
    """Conservative synthetic lower score, NOT calibrated probability or guarantee."""
    if r['note'].strip(): return None, 'Unparsed dealer note: manual verification required'
    eligible = [d for d in s['drivers'] if
                (not any(l['premium'] for l in r['legs']) or (d['rating100'] >= 480 and d['completedGigs'] >= 50))
                and (not any(l['manualGearbox'] for l in r['legs']) or d['manualLicence'])]
    if not eligible: return None, 'No eligible driver evidence'
    d = min(eligible, key=lambda x: (x['availableAt'], -x['reliabilityBps'], x['id']))
    # Home/working position and transit are hidden: reserve a synthetic 60-minute access buffer.
    t = max(s['now']+60, d['availableAt']); stops=[]; drive=0
    for i,l in enumerate(r['legs']):
        if l['releasedAt'] is None: return None, 'Payment/readiness release unknown'
        if l['snow']: return None, 'Snow/tyre truth unresolved'
        p,later = l['pickup'],l['delivery']
        charging = l['electric'] and l['chargePercent'] < 30 and l['km'] > 200
        t=max(t, p['window'][0], p['open'][0], l['releasedAt'])
        t += 30*int(l['needsPlates'])
        if t > min(p['window'][1], p['open'][1]): return None, 'Pickup window/release infeasible'
        stops.append({'leg':i,'kind':'pickup','at':t,'withPlates':l['needsPlates'],'withCharging':charging})
        drive += l['roadMinutes']
        t += ceildiv(l['roadMinutes']*120,100)+40*int(charging)
        t=max(t,later['window'][0],later['open'][0])
        deadline=min(o['deadline'],later['window'][1]+(30 if later['private'] else 0),later['open'][1])
        if t+60 > deadline: return None, 'Delivery deadline lacks 60-minute reserve'
        stops.append({'leg':i,'kind':'delivery','at':t})
    # Explicit mapping permits only connected trade-in legs; no invented inter-stop roads.
    if len(r['legs']) == 2 and r['legs'][0]['delivery']['placeId'] != r['legs'][1]['pickup']['placeId']:
        return None, 'Missing inter-leg road: split/re-map required'
    split = drive > 720 and len(r['legs']) > 1
    if split: return None, 'Trade-in exceeds 12h: separate gig/driver evidence required'
    fee=ceildiv(r['referenceFeeCents']*(150 if s['level']>=7 else 110),100) if high else ceildiv(r['referenceFeeCents']*80,100)
    score=d['reliabilityBps']-(100 if high else 1400)-(200 if s['level']>=7 else 0)-(100 if len(r['legs'])==2 else 0)
    # Minimum per-leg evidence uses a union bound, avoiding independence assumptions.
    score=max(0,10000-len(r['legs'])*(10000-score))
    return {'driverId':d['id'],'finishAt':t,'feeCents':fee,'lowerSafetyBps':score,
            'stops':stops,'schedule':[{'at':s['now'],'feeCents':fee}] if s['level']==1 else
            [{'at':s['now'],'feeCents':fee},{'at':s['now']+30,'feeCents':ceildiv(fee*110,100)}]}, None


def recommend(snapshot):
    s=validate(json.loads(json.dumps(snapshot)))
    rows=[]
    for r in sorted(s['requests'],key=lambda x:(x['respondBy'],x['id'])):
        row={'requestId':r['id'],'revision':r['revision'],'decision':'ABSTAIN','reasons':[],'alternatives':[]}
        rows.append(row)
        if r['status']=='cancelled' or s['now']>=r['respondBy']:
            row['reasons']=['Cancelled or response deadline reached']; continue
        options=list(r['options'].items())[:1] if s['level']<=3 else sorted(r['options'].items())
        for name,o in options:
            for high in (False,True):
                p,reason=plan(s,r,o,high)
                if not p: row['reasons'].append(reason); continue
                price=o['listPriceCents'] if s['level']<=3 else ceildiv(o['listPriceCents']*(120 if s['level']>=7 else 96),100)
                # Reserve the maximum scheduled fee plus 10% refund contingency.
                margin=price-max(x['feeCents'] for x in p['schedule'])-ceildiv(price,10)
                row['alternatives'].append({'option':name,'highFee':high,'priceCents':price,'reservedMarginCents':margin,**p})
        safe=[p for p in row['alternatives'] if p['lowerSafetyBps']>=9000 and p['reservedMarginCents']>0]
        if safe:
            p=max(safe,key=lambda x:(x['reservedMarginCents'],x['lowerSafetyBps']))
            row.update(decision='QUOTE',recommendation=p)
            # Conservative reservation prevents concurrent requests claiming one driver.
            next(d for d in s['drivers'] if d['id']==p['driverId'])['availableAt']=p['finishAt']+60
        else: row['reasons'].append('No positive-margin plan at >=90% synthetic lower safety score')
        row['reasons']=sorted(set(row['reasons']))
        row['idempotencyKey']=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
    return {'mode':LABEL,'baseCommit':BASE,'rulesSha256':RULES,'signed':False,
            'safety':'Heuristic synthetic lower score; no real 90% guarantee; no executable sponsor actions', 'rows':rows}


class Book:
    """Replay-only event reducer. Sequence dedup survives JSON checkpoint/restart."""
    def __init__(self,state=None):
        self.state=state or {'seen':[],'orders':{},'offers':{},'openOffers':{}}
    def event(self,e):
        keys(e,'seq kind orderId revision'); integer(e['seq']); ident(e['orderId']); integer(e['revision'])
        if e['kind'] not in ('order_won','order_changed','order_cancelled','release','gig_expired','gig_started','gig_dropped','no_show'): raise ValueError('unknown event')
        if e['seq'] in self.state['seen']: return False
        o=self.state['orders'].setdefault(e['orderId'],{'revision':-1,'status':'new','repost':False})
        self.state['seen'].append(e['seq'])
        if e['revision']<o['revision'] or o['status']=='cancelled': return False
        o['revision']=e['revision']
        if e['kind']=='order_cancelled': o.update(status='cancelled',repost=False)
        elif e['kind']=='gig_started': o.update(status='started',repost=False)
        elif e['kind']=='order_changed': o.update(status='review_changed',repost=False)
        elif e['kind'] in ('gig_expired','gig_dropped','no_show'): o.update(status='needs_replan',repost=True)
        elif e['kind']=='release': o.update(status='ready_replan',repost=True)
        else: o.update(status='won',repost=True)
        return True
    def offer(self,driver,gig,now,level):
        ident(driver);ident(gig);integer(now,0,20000);integer(level,1,8)
        day=now//1440; k=f'{driver}:{day}'
        active=[t for t in self.state['openOffers'].get(gig,[]) if t>now]
        if level<3 or not 420<=now%1440<1380 or self.state['offers'].get(k,0)>=3 or len(active)>=3: return False
        self.state['offers'][k]=self.state['offers'].get(k,0)+1
        self.state['openOffers'][gig]=active+[now+10]
        return True


def scenario(seed,level=8,count=40):
    rng=random.Random(seed); requests=[]
    def place(id,a,b): return {'placeId':id,'window':[a,b],'open':[a,b],'private':False}
    for i in range(count):
        now=480+i*45; minutes=rng.choice([60,120,240,420]); tight=rng.random()<.25
        legs=[{'pickup':place('A',now,now+700),'delivery':place('B',now,now+(200 if tight else 1100)),
               'roadMinutes':minutes,'km':minutes*2,'premium':rng.random()<.2,'manualGearbox':rng.random()<.3,
               'electric':rng.random()<.3,'chargePercent':20,'needsPlates':rng.random()<.1,'releasedAt':now,'snow':False}]
        requests.append({'id':f'R{i}','respondBy':now+15,'referenceFeeCents':rng.randrange(6000,18000),
                         'options':{'same_day':{'deadline':now+(200 if tight else 1100),'listPriceCents':40000}},
                         'legs':legs,'note':'payment later' if rng.random()<.1 else '', 'status':'pending','revision':0})
    drivers=[{'id':f'D{i}','rating100':490,'completedGigs':70,'manualLicence':True,'availableAt':480,'reliabilityBps':9900} for i in range(6)]
    return {'format':'spread-offline-mapping-v1','now':480,'level':level,'requests':requests,'drivers':drivers}


def simulate(seed,policy):
    s=scenario(seed); rng=random.Random(seed+900000); won=on=gm=0; failures={}; ledger=[]
    # Synthetic demand/acceptance outcomes are intentionally independent of policy safety score.
    for r in s['requests']:
        s['now']=r['respondBy']-15
        demand, cancellation, booking, delay = [rng.random() for _ in range(4)]
        if policy=='optimizer':
            row=recommend({**s,'requests':[r]})['rows'][0]
            if row['decision']!='QUOTE': continue
            p=row['recommendation']; price=p['priceCents']; fee=max(x['feeCents'] for x in p['schedule'])
            d=next(d for d in s['drivers'] if d['id']==p['driverId']); d['availableAt']=p['finishAt']+60
        else:
            price=40000;fee=r['referenceFeeCents']*80//100
        if demand > max(.1, .95-(price-40000)/80000): continue
        if cancellation<.04: continue  # cancelled orders excluded
        won+=1
        l=r['legs'][0]
        capacity = fee*100 >= r['referenceFeeCents']*(70+int(booking*95))
        actual_finish = s['now']+60+l['roadMinutes']+(90 if delay<.04 else 20)
        if l['electric'] and l['km']>200 and l['chargePercent']<30: actual_finish+=40 if policy=='optimizer' else 130
        success=capacity and booking<.98 and actual_finish<=min(l['delivery']['window'][1],r['options']['same_day']['deadline']) and not r['note']
        if success: on+=1; revenue=price
        else:
            revenue=price*75//100
            reason='synthetic_delay_or_drop' if policy=='optimizer' else 'underfunding_or_unread_constraint'
            failures[reason]=failures.get(reason,0)+1
        gm+=revenue-fee;ledger.append({'requestId':r['id'],'revenueCents':revenue,'driverFeeCents':fee,'onTime':success})
    return {'seed':seed,'policy':policy,'wonOrders':won,'onTimeOrders':on,'onTimeBps':on*10000//won if won else None,
            'ranked':ranked(won,on),'grossMarginCents':gm,'failureModes':failures,'ledger':ledger}


def ranked(won,on):
    integer(won); integer(on,0,won)
    return won>0 and on*10>=won*9


def comparison():
    return {'mode':LABEL,'thresholdFrozenBps':9000,'modelLimit':'Toy stochastic outcomes, not the official simulator or calibrated validation',
            'fixedSeeds':list(TRAIN),'heldOutSeeds':list(HOLDOUT),'runs':[{'split':split,**simulate(seed,p)} for split,seeds in [('fixed',TRAIN),('held_out',HOLDOUT)] for seed in seeds for p in ('baseline','optimizer')]}


def main():
    ap=argparse.ArgumentParser(description=LABEL+' — no network, no dispatch')
    ap.add_argument('command',choices=['demo','recommend','compare']);ap.add_argument('--input');ap.add_argument('--output');ap.add_argument('--seed',type=int,default=11);ap.add_argument('--level',type=int,choices=range(1,9),default=8)
    a=ap.parse_args()
    if a.command=='recommend':
        if not a.input: ap.error('--input required')
        path=Path(a.input)
        if path.stat().st_size>2_000_000: raise ValueError('input too large')
        result=recommend(json.loads(path.read_text()))
    elif a.command=='compare': result=comparison()
    else: result=recommend(scenario(a.seed,a.level))
    out=json.dumps(result,indent=2,allow_nan=False)
    if a.output: Path(a.output).write_text(out+'\n')
    else: print(out)

if __name__=='__main__': main()
