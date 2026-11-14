"""Fetch public THL observations using only the Python standard library."""
import hashlib,json,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
TARGETS=[(3621,'screen_breast'),(3620,'screen_cervix'),(6103,'screen_colorectal'),(6411,'gp_wait_over_7d'),(6410,'gp_wait_over_3m'),(3336,'specialist_wait_over_6m'),(13,'referral_handled_3d'),(5033,'referral_handled_over_21d')]
COVARIATES=[127,1068,180,181,3099,3126,5102,5641,5643,5659,326,3562,237,2475,3054,3051,3055,189,228]
def fetch(output=Path(__file__).parent/'data/panel.json'):
    manifest=[]
    def get(path):
        url='https://sotkanet.fi/rest/1.1/'+path
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
    for iid,key in TARGETS+[(i,str(i)) for i in COVARIATES]:
        try: rows=get('json?indicator='+str(iid)+''.join('&years='+str(y) for y in years)+'&genders=total')
        except Exception as e:
            skipped.append(dict(id=iid,reason=str(e))); continue
        cells={}
        for r in rows:
            uid=mapping.get(r['region']); v=r.get('value')
            if uid and isinstance(v,(int,float)) and r.get('gender')=='total': cells.setdefault(uid,{})[str(r['year'])]=v
        if not cells: skipped.append(dict(id=iid,reason='No observations in selected units')); continue
        values[str(iid)]=cells; indicators.append(dict(id=iid,key=key,isTarget=iid in dict(TARGETS)))
        print(iid,len(cells),flush=True)
    panel=dict(units=units,indicators=indicators,years=years,values=values,manifest=manifest,skippedIndicators=skipped)
    Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(panel,ensure_ascii=False))
    return panel
if __name__=='__main__': fetch()
