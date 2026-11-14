"""Validation-only config selection; test scoring starts after winners are frozen."""
import argparse
import copy
import hashlib
from datetime import datetime, timezone
from common import *
from train_forecaster import fit, predict
from evaluate import calibrate, summarize

def configure(p):
    p.set_defaults(seeds=3)
    p.add_argument('--extended-panel',default=str(ROOT/'data/panel-extended.json'))
    p.add_argument('--grid',help='JSON list of config overrides; useful for bounded smoke runs')

def default_grid(base,extended):
    # Seven paired architectures isolate the contribution of extra covariates.
    shapes=[(5,64,2),(8,64,3),(12,64,2),(5,128,3),
            (8,128,3),(12,128,2),(8,256,3)]
    return [dict(panel=panel,window=w,d_model=d,layers=l)
            for panel in (base,extended) for w,d,l in shapes]

def select_validation(scores):
    """Only validation summaries enter this API. Stable ties prefer baselines."""
    available={k:v for k,v in scores.items() if v is not None and np.isfinite(v)}
    return min(available,key=available.get) if available else None

def score(pred,y,mask):
    return summarize(pred,y,mask)

def aggregate(horizons):
    cells=[v for v in horizons.values() if v['n']]
    return sum(v['mae']*v['n'] for v in cells)/sum(v['n'] for v in cells) if cells else None

def baseline_quantiles(vw,vy,targets,ridge):
    predictions={}; offsets={}
    for method in METHODS[1:]:
        v=baseline(vw,targets,method,ridge); off=np.zeros((len(targets),2,5))
        for j in range(len(targets)):
            for h in range(2):
                e=vy[:,j,h]-v[:,j,h]; e=e[np.isfinite(e)]
                if len(e): off[j,h]=np.quantile(e,Q)
        off[:,:,:2]=np.minimum(off[:,:,:2],0); off[:,:,2]=0
        off[:,:,3:]=np.maximum(off[:,:,3:],0)
        predictions[method]=v[...,None]+off; offsets[method]=off
    return predictions,offsets

def run(a):
    a.panel=str(Path(a.panel).resolve()); a.extended_panel=str(Path(a.extended_panel).resolve())
    torch.set_num_threads(2)
    root=Path(a.artifacts); root.mkdir(parents=True,exist_ok=True)
    grid=json.loads(Path(a.grid).read_text()) if a.grid else default_grid(a.panel,a.extended_panel)
    if not grid: raise ValueError('empty grid')
    allowed={'panel','window','d_model','layers','heads','lr','dropout','mask_rate'}
    configs=[]; valpred={}; data=None
    for i,overrides in enumerate(grid):
        if set(overrides)-allowed: raise ValueError('unsupported config fields')
        c=copy.copy(a)
        for key,value in overrides.items(): setattr(c,key,value)
        if c.window<3 or c.d_model%c.heads: raise ValueError('invalid window/heads')
        c.panel=str(Path(c.panel).resolve()); c.artifacts=str(root/f'config-{i:02d}')
        Path(c.artifacts).mkdir(parents=True,exist_ok=True)
        p,x,years,targets,cats=load(c.panel)
        w,y,m=windows(x,years,targets,[t for t in years if t<=2020],window=c.window)
        y[np.array([t+2>2021 for _,t in m]),:,1]=np.nan
        vw,vy,vm=windows(x,years,targets,[2021],window=c.window,include_empty=True)
        identity=([u['id'] for u in p['units']], [p['indicators'][k]['key'] for k in targets],vm)
        if data is None:
            data=(identity,vy)
        elif identity!=data[0] or not np.array_equal(vy,data[1],equal_nan=True):
            raise ValueError('panels must have identical units, targets, validation labels and origins')
        bundle=fit(w,y,m,vw,vy,vm,cats,targets,c)
        torch.save(bundle,Path(c.artifacts)/'backtest.pt')
        valpred[f'config-{i:02d}']=predict(bundle,vw,vm,cats,targets,c.device)
        configs.append(c)
        save(Path(c.artifacts)/'configuration.json',dict(configuration=vars(c),panelSha256=hashlib.sha256(Path(c.panel).read_bytes()).hexdigest()))
    # Baselines use the unchanged base panel, eight-year window and same target cells.
    b=copy.copy(a); b.window=8
    p,x,years,targets,cats=load(b.panel)
    w,y,m=windows(x,years,targets,[t for t in years if t<=2020])
    y[np.array([t+2>2021 for _,t in m]),:,1]=np.nan
    vw,vy,vm=windows(x,years,targets,[2021],include_empty=True)
    if ([u['id'] for u in p['units']],[p['indicators'][k]['key'] for k in targets],vm)!=data[0] or not np.array_equal(vy,data[1],equal_nan=True):
        raise ValueError('base panel target alignment differs')
    ridge=fit_ridge(w,y,targets)
    bp,offsets=baseline_quantiles(vw,vy,targets,ridge)
    valpred={**bp,**valpred}
    common=np.isfinite(vy)
    for prediction in valpred.values(): common &= np.isfinite(prediction).all(-1)
    validation={}; winners={}; transformer_winners={}; baseline_winners={}
    for j,k in enumerate(targets):
        key=p['indicators'][k]['key']
        validation[key]={name:{f'h{h+1}':score(pred[:,j,h],vy[:,j,h],common[:,j,h]) for h in range(2)} for name,pred in valpred.items()}
        scores={name:aggregate(hs) for name,hs in validation[key].items()}
        winners[key]=select_validation(scores)
        transformer_winners[key]=select_validation({name:s for name,s in scores.items() if name.startswith('config-')})
        baseline_winners[key]=select_validation({name:s for name,s in scores.items() if name in METHODS[1:]})
    # Persist the selection before loading any test windows.
    result=dict(basePanelSha256=hashlib.sha256(Path(a.panel).read_bytes()).hexdigest(),createdAt=datetime.now(timezone.utc).isoformat(),configuration=vars(a),
                configs={f'config-{i:02d}':json.loads((Path(c.artifacts)/'configuration.json').read_text()) for i,c in enumerate(configs)},
                validation=validation,chosen=winners,bestTransformer=transformer_winners,
                bestBaseline=baseline_winners,
                selection='Lowest pooled validation MAE over both horizons and all units; baseline-first stable ties.',
                limits=['Validation h2 and test h1 overlap in calendar year 2023.',
                        'Seed spread is max-minus-min single-seed test MAE, not a confidence interval.',
                        f'{len(grid)} configs share one validation origin; selection can overfit validation.'])
    save(root/'selection.json',result)
    # Only the validation-best transformer per indicator receives a test score.
    tw,ty,tm=windows(x,years,targets,[2022,2023],include_empty=True)
    test_base={name:baseline(tw,targets,name,ridge)[...,None]+offsets[name] for name in METHODS[1:]}
    result['test']={}; result['verdicts']={}
    for j,k in enumerate(targets):
        key=p['indicators'][k]['key']; winner=transformer_winners[key]
        predictions={name:pred[:,j] for name,pred in test_base.items()}
        single=[]; width_map={}
        if winner:
            c=configs[int(winner.split('-')[1])]
            cp,cx,cy,ct,cc=load(c.panel)
            ctw,cty,ctm=windows(cx,cy,ct,[2022,2023],window=c.window,include_empty=True)
            if ctm!=tm or not np.array_equal(cty,ty,equal_nan=True): raise ValueError('test panel alignment differs')
            bundle=torch.load(Path(c.artifacts)/'backtest.pt',weights_only=False,map_location='cpu')
            predictions[winner]=predict(bundle,ctw,ctm,cc,ct,c.device)[:,j]
            for state in bundle['models']:
                one=dict(bundle,models=[state])
                single.append(predict(one,ctw,ctm,cc,ct,c.device)[:,j])
        mask=np.isfinite(ty[:,j])
        for pred in predictions.values(): mask &= np.isfinite(pred).all(-1)
        report={}
        for name,pred in predictions.items():
            v=valpred[name][:,j:j+1]
            _,width=calibrate(v,np.where(common[:,j:j+1],vy[:,j:j+1],np.nan))
            pred=pred.copy(); pred[...,0]-=width[0]; pred[...,4]+=width[0]
            width_map[name]=width[0]
            report[name]={f'h{h+1}':score(pred[:,h],ty[:,j,h],mask[:,h]) for h in range(2)}
        seed_scores=[aggregate({f'h{h+1}':score(pred[:,h],ty[:,j,h],mask[:,h]) for h in range(2)}) for pred in single]
        seed_scores=[v for v in seed_scores if v is not None]
        spread=max(seed_scores)-min(seed_scores) if len(seed_scores)>1 else None
        best_base=baseline_winners[key]
        model_mae=aggregate(report[winner]) if winner else None
        base_mae=aggregate(report[best_base]) if best_base else None
        delta=base_mae-model_mae if model_mae is not None and base_mae is not None else None
        result['test'][key]=dict(methods=report,seedMAE=seed_scores,seedSpread=spread,seedMAEByHorizon={f'h{h+1}':[score(pred[:,h],ty[:,j,h],mask[:,h])['mae'] for pred in single] for h in range(2)},baselineMinusTransformerMAE=delta,
                                 improvementExceedsSeedSpread=(delta>spread) if delta is not None and spread is not None else None)
        result['verdicts'][key]=(f"{winner} {'beats' if delta>0 else 'does not beat'} validation-best baseline {best_base}: baseline minus transformer MAE {delta:.6g}; seed range {spread:.6g}; improvement exceeds range: {delta>spread}." if delta is not None and spread is not None else 'Insufficient common observations; no winner claim.')
        # Export consumes only the selected method's validation calibration and config.
        chosen=winners[key]
        save(root/f'selected-{key}.json',dict(chosen=chosen,transformer=winner,
            config=vars(configs[int(winner.split('-')[1])]) if winner else None,
            offsets={name:off[j].tolist() for name,off in offsets.items()},
            widths={name:width.tolist() for name,width in width_map.items()},
            validation=validation[key],test=result['test'][key]))
    save(root/'sweep.json',result)
    lines=['# Validation-selected sweep','',result['selection'],'',
           'Test MAE is reported only for the pooled-validation-best transformer and the three baselines. Horizon scores are descriptive; selection pools both horizons.','']
    for key,entries in validation.items():
        lines += [f'## {key}',f"Selected overall: {winners[key]}; transformer: {transformer_winners[key]}; baseline: {baseline_winners[key]}.",'',
                  '| Method/config | Validation h1 MAE (n) | Validation h2 MAE (n) |','|---|---|---|']
        for name,hs in entries.items(): lines.append('| '+name+' | '+' | '.join(f"{v['mae']} ({v['n']})" for v in hs.values())+' |')
        lines += ['','| Selected transformer / baseline | Test h1 MAE (n) | Test h2 MAE (n) |','|---|---|---|']
        for name,hs in result['test'][key]['methods'].items(): lines.append('| '+name+' | '+' | '.join(f"{v['mae']} ({v['n']})" for v in hs.values())+' |')
        lines += ['',result['verdicts'][key],'']
    lines += ['## Limits','',*result['limits']]
    (root/'SWEEP_REPORT.md').write_text('\n'.join(lines)+'\n')
    return result

if __name__=='__main__': run(args(configure))
