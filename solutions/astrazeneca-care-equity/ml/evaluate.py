"""Common-cell backtest and validation-only interval calibration/selection."""
from common import *
from train_forecaster import predict

def calibrate(pred,y):
    adjusted=pred.copy(); widths=np.zeros(pred.shape[1:3])
    for j in range(pred.shape[1]):
        for h in range(2):
            m=np.isfinite(y[:,j,h])&np.isfinite(pred[:,j,h]).all(1)
            if not m.any(): continue
            residual=np.maximum(pred[m,j,h,0]-y[m,j,h],y[m,j,h]-pred[m,j,h,4]); n=len(residual); rank=min(n,int(np.ceil((n+1)*.9)))
            widths[j,h]=max(0,float(np.sort(residual)[rank-1])); adjusted[:,j,h,0]-=widths[j,h]; adjusted[:,j,h,4]+=widths[j,h]
    return adjusted,widths

def summarize(pred,y,mask):
    if not mask.any(): return dict(mae=None,pinball=None,cov90=None,cov50=None,n=0)
    v=y[mask]; q=pred[mask]
    return dict(mae=float(np.mean(abs(q[:,2]-v))),pinball=float(pinball(q,v).mean()),cov90=float(np.mean((v>=q[:,0])&(v<=q[:,4]))),cov50=float(np.mean((v>=q[:,1])&(v<=q[:,3]))),n=int(len(v)))
def main():
    a=args(); p,x,years,targets,cats=load(a.panel); bundle=torch.load(Path(a.artifacts)/'backtest.pt',weights_only=False,map_location='cpu')
    w,y,m=windows(x,years,targets,[t for t in years if t<=2020],window=a.window); y[np.array([t+2>2021 for _,t in m]),:,1]=np.nan
    vw,vy,vm=windows(x,years,targets,[2021],window=a.window); tw,ty,tm=windows(x,years,targets,[2022,2023],window=a.window); ridge=fit_ridge(w,y,targets)
    vp={'transformer':predict(bundle,vw,vm,cats,targets,a.device)}; tp={'transformer':predict(bundle,tw,tm,cats,targets,a.device)}; offsets={}
    for method in METHODS[1:]:
        v=baseline(vw,targets,method,ridge); t=baseline(tw,targets,method,ridge); off=np.zeros((len(targets),2,5))
        for j in range(len(targets)):
            for h in range(2):
                e=vy[:,j,h]-v[:,j,h]; e=e[np.isfinite(e)]
                if len(e): off[j,h]=np.quantile(e,Q)
        # Persistence/drift/ridge median remains the actual baseline forecast.
        off[:,:,:2]=np.minimum(off[:,:,:2],0); off[:,:,2]=0; off[:,:,3:]=np.maximum(off[:,:,3:],0); offsets[method]=off
        vp[method]=v[...,None]+off; tp[method]=t[...,None]+off
    vcommon=np.isfinite(vy); common=np.isfinite(ty)
    for method in METHODS: vcommon &= np.isfinite(vp[method]).all(-1); common &= np.isfinite(tp[method]).all(-1)
    metrics={}; widths={}; validation={}; raw={method:value.copy() for method,value in tp.items()}; validation_horizons={}
    for method in METHODS:
        adjusted,width=calibrate(vp[method],np.where(vcommon,vy,np.nan)); widths[method]=width
        tpraw=tp[method].copy(); tp[method][...,0]-=width; tp[method][...,4]+=width
        validation[method]=[]; validation_horizons[method]=[]
        for j in range(len(targets)):
            validation_horizons[method].append({'h'+str(h+1):summarize(adjusted[:,j,h],vy[:,j,h],vcommon[:,j,h]) for h in range(2)})
            validation[method].append(summarize(adjusted[:,j].reshape(-1,5),vy[:,j].reshape(-1),vcommon[:,j].reshape(-1)))
    for j,k in enumerate(targets):
        key=p['indicators'][k]['key']; candidates={method:validation[method][j]['mae'] for method in METHODS}; available={k:v for k,v in candidates.items() if v is not None}; chosen=min(available,key=available.get) if available else 'persistence'
        item=dict(chosen=chosen,validationMAE=candidates)
        for group,category in [('county',1),('municipality',0)]:
            item[group]={}
            for h in range(2):
                mask=common[:,j,h]&(cats[[u for u,t in tm]]==category)
                item[group]['h'+str(h+1)]={method:summarize(tp[method][:,j,h],ty[:,j,h],mask) for method in METHODS}
        for group in ('county','municipality'):
            for h in range(2):
                category=1 if group=='county' else 0; mask=common[:,j,h]&(cats[[u for u,t in tm]]==category)
                for method in METHODS: item[group]['h'+str(h+1)][method]['cov90Raw']=summarize(raw[method][:,j,h],ty[:,j,h],mask)['cov90']
        item['validation']={method:validation_horizons[method][j] for method in METHODS}
        metrics[key]=item
    save(Path(a.artifacts)/'metrics.json',dict(split=dict(trainOriginsThrough=2020,trainLabelsThrough=2021,validationOrigins=[2021],testOrigins=[2022,2023]),metrics=metrics,validation=validation,limits=['Validation origin 2021 horizon 2 and test origin 2022 horizon 1 share target year 2023; training never sees test labels.','Coverage is empirical, not a population guarantee.'],configuration=vars(a),executedEpochs=[len(v) for v in bundle['histories']],panelSha256=__import__('hashlib').sha256(Path(a.panel).read_bytes()).hexdigest()))
    torch.save(dict(ridge=ridge,offsets=offsets,widths=widths),Path(a.artifacts)/'calibration.pt')
if __name__=='__main__': main()
