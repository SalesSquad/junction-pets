"""Refit selected methods and export county predictive quantiles."""
from common import *
from train_forecaster import fit,predict

def main():
    a=args(); torch.set_num_threads(2); p,x,years,targets,cats=load(a.panel); metrics=json.loads((Path(a.artifacts)/'metrics.json').read_text())['metrics']; cal=torch.load(Path(a.artifacts)/'calibration.pt',weights_only=False)
    w,y,m=windows(x,years,targets,years[:-1]); ridge=fit_ridge(w,y,targets)
    # Full-data refit uses the backtest-selected epoch count, without a new future holdout.
    selected=any(v['chosen']=='transformer' for v in metrics.values()); bundle=None
    if selected:
        old=torch.load(Path(a.artifacts)/'backtest.pt',weights_only=False); epochs=max(1,int(np.median([len(h) for h in old['histories']]))); bundle=fit(w,y,m,w,y,m,cats,targets,a,epochs); torch.save(bundle,Path(a.artifacts)/'refit.pt')
    forecasts={}; outputmetrics={}
    for j,k in enumerate(targets):
        key=p['indicators'][k]['key']; method=metrics[key]['chosen']; forecasts[key]={}; outputmetrics[key]=dict(chosen=method,**metrics[key]['county'])
        for u,unit in enumerate(p['units']):
            if cats[u]!=1: continue
            valid=np.where(np.isfinite(x[u,:,k]))[0]
            if not len(valid): continue
            index=valid[-1]; origin=int(years[index]); fw,fy,fm=windows(x,years,targets,[origin]); n=next((i for i,v in enumerate(fm) if v[0]==u),None)
            if n is None: continue
            if method=='transformer': q=predict(bundle,fw[n:n+1],fm[n:n+1],cats,targets,a.device)[0,j]
            else: q=baseline(fw[n:n+1],targets,method,ridge)[0,j,:,None]+cal['offsets'][method][j]
            q[:,0]-=cal['widths'][method][j]; q[:,4]+=cal['widths'][method][j]; q=np.sort(q,axis=-1); last=float(x[u,index,k]); item=dict(lastYear=origin,lastValue=last,pBelowThreshold={} if key.startswith('screen_') else None,pWorse={})
            for h in range(2):
                label='h'+str(h+1); item[label]=dict(year=origin+h+1,**dict(zip(['q05','q25','q50','q75','q95'],map(float,q[h])))); below=probability(q[h],last)
                higher=key.startswith('screen_') or key=='referral_handled_3d'; item['pWorse'][label]=below if higher else 1-below
                if item['pBelowThreshold'] is not None: item['pBelowThreshold'][label]=probability(q[h],80)
            forecasts[key][unit['id']]=item
    from datetime import datetime,timezone
    save(a.out,dict(schemaVersion='care-equity-forecast-v1',generatedAt=datetime.now(timezone.utc).isoformat(),trainedOn=dict(device=a.device,seeds=a.seeds,epochs=a.epochs,transformerRefitted=selected),skippedIndicators=p.get('skippedIndicators',[]),metrics=outputmetrics,forecasts=forecasts))
if __name__=='__main__': main()
