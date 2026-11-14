"""Fetch public THL observations using only the Python standard library."""
import argparse,hashlib,json,math,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
TARGETS=[(3621,'screen_breast'),(3620,'screen_cervix'),(6103,'screen_colorectal'),(6411,'gp_wait_over_7d'),(6410,'gp_wait_over_3m'),(3336,'specialist_wait_over_6m'),(13,'referral_handled_3d'),(5033,'referral_handled_over_21d')]
COVARIATES=[127,1068,180,181,3099,3126,5102,5641,5643,5659,326,3562,237,2475,3054,3051,3055,189,228]
def fetch(output=Path(__file__).parent/'data/panel.json',extra_indicators=0):
    manifest=[]
    def get(path):
        url='https://sotkanet.fi/rest/1.1/'+path
        time.sleep(.2)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'care-equity-navigator/1.0','Accept':'application/json'}),timeout=90) as r: raw=r.read()
                result=json.loads(raw)
                manifest.append(dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),retrievedAt=datetime.now(timezone.utc).isoformat()))
                return result
            except Exception:
                if attempt==3: raise
                time.sleep(2**attempt)
    regions=get('regions'); units=[]; mapping={}
    for r in regions:
        cat=r['category']; code=r['code']
        if cat not in ('KUNTA','HYVINVOINTIALUE','MAA'): continue
        if cat=='MAA' and code not in ('358',): continue
        uid={'KUNTA':'KU'+code,'HYVINVOINTIALUE':'HVA'+code,'MAA':'FI'}[cat]
        mapping[r['id']]=uid; units.append(dict(id=uid,category=cat,name=r['title'].get('fi',str(code))))
    years=list(range(2000,2026)); values={}; skipped=[]; indicators=[]
    base=TARGETS+[(i,str(i)) for i in COVARIATES]
    candidates=[]
    if extra_indicators:
        for item in sorted(get('indicators'),key=lambda i:int(i['id'])):
            iid=int(item['id'])
            if iid in dict(base): continue
            regions=item.get('classifications',{}).get('region',{}).get('values',[])
            if 'Kunta' not in regions:
                skipped.append(dict(id=iid,reason='No municipality classification')); continue
            candidates.append((iid,str(iid)))
    added=0
    for iid,key in base+candidates:
        extra=iid not in dict(base)
        if extra and added>=extra_indicators: break
        try: rows=get('json?indicator='+str(iid)+''.join('&years='+str(y) for y in years)+'&genders=total')
        except Exception as e:
            skipped.append(dict(id=iid,reason=str(e))); continue
        cells={}
        for r in rows:
            uid=mapping.get(r['region']); v=r.get('value')
            if uid and isinstance(v,(int,float)) and math.isfinite(v) and r.get('gender')=='total' and 2000<=int(r['year'])<=2025: cells.setdefault(uid,{})[str(r['year'])]=v
        if not cells: skipped.append(dict(id=iid,reason='No observations in selected units')); continue
        if extra:
            reason=coverage_failure(cells)
            if reason:
                skipped.append(dict(id=iid,reason=reason)); continue
            added+=1
        values[str(iid)]=cells; indicators.append(dict(id=iid,key=key,isTarget=iid in dict(TARGETS)))
        print(iid,len(cells),flush=True)
    panel=dict(units=units,indicators=indicators,years=years,values=values,manifest=manifest,skippedIndicators=skipped,extraIndicatorsRequested=extra_indicators,extraIndicatorsAdded=added)
    Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(panel,ensure_ascii=False))
    return panel
def coverage_failure(cells):
    by_year={}; latest=None
    for uid,values in cells.items():
        for year,value in values.items():
            if 2000<=int(year)<=2025 and math.isfinite(value): latest=max(latest or 2000,int(year))
        if uid.startswith('KU'):
            for year,value in values.items():
                if 2000<=int(year)<=2025 and math.isfinite(value):
                    by_year.setdefault(int(year),set()).add(uid)
    if len(by_year)<15: return 'Fewer than 15 municipality observation years in 2000-2025'
    if len(by_year.get(latest,set()))<250: return 'Fewer than 250 municipalities in latest observed year'
    return None

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--extra-indicators',type=int,default=0)
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'data/panel.json')
    a=parser.parse_args()
    if a.extra_indicators<0: parser.error('extra-indicators must be nonnegative')
    fetch(a.out,a.extra_indicators)
