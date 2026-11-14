"""Refit selected methods and export county predictive quantiles."""
from common import *
from train_forecaster import fit,predict

def export(a):
    torch.set_num_threads(2); p,x,years,targets,cats=load(a.panel); metrics=json.loads((Path(a.artifacts)/'metrics.json').read_text())['metrics']; cal=torch.load(Path(a.artifacts)/'calibration.pt',weights_only=False)
    w,y,m=windows(x,years,targets,years[:-1],window=a.window); ridge=fit_ridge(w,y,targets)
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
            index=valid[-1]; origin=int(years[index]); fw,fy,fm=windows(x,years,targets,[origin],window=a.window); n=next((i for i,v in enumerate(fm) if v[0]==u),None)
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
def export_sweep(a):
    """Refit each selected configuration once; combine only its selected indicators."""
    import copy
    root=Path(a.artifacts)
    sweep=json.loads((root/'sweep.json').read_text())
    import hashlib
    for config in sweep['configs'].values():
        path=Path(config['configuration']['panel'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=config['panelSha256']:
            raise ValueError(f'Panel changed since sweep: {path}')
    if hashlib.sha256(Path(sweep['configuration']['panel']).read_bytes()).hexdigest()!=sweep['basePanelSha256']:
        raise ValueError('Base panel changed since sweep')
    groups={}
    for key,chosen in sweep['chosen'].items():
        groups.setdefault(chosen if chosen and chosen.startswith('config-') else 'baselines',[]).append(key)
    combined=None; choices={}
    for group,keys in groups.items():
        c=copy.copy(a)
        if group!='baselines':
            for name,value in sweep['configs'][group]['configuration'].items(): setattr(c,name,value)
        else:
            c.panel=sweep['configuration']['panel']; c.window=8
        c.device=a.device
        c.artifacts=str(root/'export'/group); c.out=str(Path(c.artifacts)/'forecast.json')
        Path(c.artifacts).mkdir(parents=True,exist_ok=True)
        p,x,years,targets,cats=load(c.panel)
        metrics={}; offsets={name:np.zeros((len(targets),2,5)) for name in METHODS[1:]}
        widths={name:np.zeros((len(targets),2)) for name in METHODS}
        for j,k in enumerate(targets):
            key=p['indicators'][k]['key']
            record=json.loads((root/f'selected-{key}.json').read_text())
            selected=record['chosen']
            method='transformer' if selected and selected.startswith('config-') else (selected or 'persistence')
            # Unowned targets are ignored after export and need no transformer refit.
            if key not in keys: method='persistence'
            test=record['test']['methods']
            scores={('transformer' if name.startswith('config-') else name):hs for name,hs in test.items()}
            metrics[key]=dict(chosen=method,county={f'h{h+1}':{name:hs[f'h{h+1}'] for name,hs in scores.items()} for h in range(2)})
            for name,off in record['offsets'].items(): offsets[name][j]=off
            for name,width in record['widths'].items():
                widths['transformer' if name.startswith('config-') else name][j]=width
        # The legacy exporter expects county metrics. Sweep cells pool all unit categories;
        # they are labeled as such in the merged product below, never as county scores.
        save(Path(c.artifacts)/'metrics.json',dict(metrics=metrics))
        torch.save(dict(offsets=offsets,widths=widths),Path(c.artifacts)/'calibration.pt')
        if group!='baselines':
            bundle=torch.load(Path(sweep['configs'][group]['configuration']['artifacts'])/'backtest.pt',weights_only=False,map_location='cpu')
            torch.save(bundle,Path(c.artifacts)/'backtest.pt')
        export(c)
        output=json.loads(Path(c.out).read_text())
        if combined is None:
            combined=copy.deepcopy(output); combined['metrics']={}; combined['forecasts']={}
        for key in keys:
            combined['forecasts'][key]=output['forecasts'][key]
            chosen=sweep['chosen'][key]
            configuration=sweep['configs'][chosen] if chosen and chosen.startswith('config-') else dict(method=chosen or 'persistence',panel=sweep['configuration']['panel'],panelSha256=sweep['basePanelSha256'],window=8)
            choices[key]=configuration
            combined['metrics'][key]=dict(chosen='transformer' if chosen and chosen.startswith('config-') else chosen or 'persistence',
                chosenConfig=configuration,validation=sweep['validation'][key],test=sweep['test'][key],evaluationUnits='all panel categories pooled',
                **{f'h{h+1}':{('transformer' if name.startswith('config-') else name):hs[f'h{h+1}']
                             for name,hs in sweep['test'][key]['methods'].items()} for h in range(2)})
    combined['trainedOn']=dict(device=a.device,selection=sweep['selection'],chosenConfigs=choices,
        seeds=sweep['configuration']['seeds'],epochs=sweep['configuration']['epochs'],
        transformerRefitted=any(k.startswith('config-') for k in groups))
    save(a.out,combined)

def configure(p):
    p.add_argument('--grid',help=argparse.SUPPRESS)
    p.add_argument('--extended-panel',help=argparse.SUPPRESS)
    p.add_argument('--sweep',action='store_true',help='Refit/export validation-selected sweep winners')

if __name__=='__main__':
    a=args(configure)
    if a.sweep: export_sweep(a)
    else: export(a)

