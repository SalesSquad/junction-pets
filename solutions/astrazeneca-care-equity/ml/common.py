"""Shared windowing, baselines and quantile utilities."""
import argparse,json,random
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parent
Q=np.array([.05,.25,.5,.75,.95])
METHODS=['transformer','persistence','drift','ridge']
def save(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,allow_nan=False,indent=2))
def args(configure=None):
    p=argparse.ArgumentParser(); p.add_argument('--device',choices=['cpu','cuda'],default='cpu'); p.add_argument('--epochs',type=int,default=100); p.add_argument('--seeds',type=int,default=5); p.add_argument('--smoke',action='store_true'); p.add_argument('--panel',default=str(ROOT/'data/panel.json')); p.add_argument('--out',default=str(ROOT.parent/'data/ml/forecast-v1.json')); p.add_argument('--artifacts',default=str(ROOT/'artifacts')); p.add_argument('--d-model',type=int,default=128); p.add_argument('--layers',type=int,default=3); p.add_argument('--heads',type=int,default=4); p.add_argument('--window',type=int,default=8); p.add_argument('--lr',type=float,default=.0005); p.add_argument('--dropout',type=float,default=.1); p.add_argument('--mask-rate',type=float,default=.15); p.add_argument('--tag',default='')
    if configure: configure(p)
    a=p.parse_args()
    if min(a.d_model,a.layers,a.heads,a.window,a.seeds,a.epochs)<1 or a.window<3 or a.d_model%a.heads: p.error('positive dimensions required; window >=3 and d-model divisible by heads')
    if not 0<=a.dropout<1 or not 0<=a.mask_rate<=1 or a.lr<=0: p.error('invalid learning rate/dropout/mask rate')
    if a.tag:
        if Path(a.tag).is_absolute() or '..' in Path(a.tag).parts: p.error('tag must be a relative artifact subdirectory')
        a.artifacts=str(Path(a.artifacts)/a.tag)
    if a.smoke: a.seeds=1; a.epochs=2
    return a
def seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s); torch.use_deterministic_algorithms(True)
def load(path):
    p=json.loads(Path(path).read_text()); ids=[str(i['id']) for i in p['indicators']]; targets=[j for j,i in enumerate(p['indicators']) if i['isTarget']]; years=np.array(p['years']); x=np.full((len(p['units']),len(years),len(ids)),np.nan)
    for u,unit in enumerate(p['units']):
        for j,i in enumerate(ids):
            for y,v in p['values'].get(i,{}).get(unit['id'],{}).items():
                if int(y) in years: x[u,np.where(years==int(y))[0][0],j]=v
    cats=np.array([{'KUNTA':0,'HYVINVOINTIALUE':1,'MAA':2}[u['category']] for u in p['units']])
    return p,x,years,targets,cats
def windows(x,years,targets,origins,window=8,include_empty=False):
    xx=[]; yy=[]; meta=[]
    for u in range(len(x)):
        for t in origins:
            where=np.where(years==t)[0]
            if not len(where): continue
            k=where[0]; w=np.full((window,x.shape[2]),np.nan); start=max(0,k-window+1); w[-(k-start+1):]=x[u,start:k+1]
            last=np.array([last_value(w[:,j]) for j in targets]); y=np.full((len(targets),2),np.nan)
            for h in range(2):
                if k+h+1<len(years): y[:,h]=x[u,k+h+1,targets]
            if not include_empty and not np.isfinite(w).any(): continue
            xx.append(w); yy.append(y); meta.append((u,int(t)))
    return np.array(xx),np.array(yy),meta
def last_value(v):
    a=v[np.isfinite(v)]; return float(a[-1]) if len(a) else np.nan
def baseline(w,targets,method,ridge=None):
    out=np.full((len(w),len(targets),2),np.nan)
    for n,a in enumerate(w):
        for j,k in enumerate(targets):
            v=a[:,k]; last=last_value(v)
            if not np.isfinite(last): continue
            changes=np.diff(v); changes=changes[np.isfinite(changes)][-3:]; slope=changes.mean() if len(changes) else 0.
            recent=v[-3:]; recent=np.where(np.isfinite(recent),recent,last)
            for h in range(2): out[n,j,h]= last if method=='persistence' else last+(h+1)*slope if method=='drift' else np.r_[1.,recent]@ridge[j,h]
    return out
def fit_ridge(w,y,targets):
    coef=np.zeros((len(targets),2,4))
    for j,k in enumerate(targets):
        last=np.array([last_value(a[:,k]) for a in w]); recent=w[:,-3:,k]; recent=np.where(np.isfinite(recent),recent,last[:,None]); design=np.c_[np.ones(len(w)),recent]
        for h in range(2):
            m=np.isfinite(design).all(1)&np.isfinite(y[:,j,h])
            if m.any():
                a=design[m]; b=y[m,j,h]; penalty=np.diag([0,1,1,1]); coef[j,h]=np.linalg.solve(a.T@a+penalty+np.eye(4)*1e-8,a.T@b)
            else: coef[j,h,3]=1
    return coef
def probability(q,threshold): return float(np.clip(np.interp(threshold,np.asarray(q),Q,left=.02,right=.98),.02,.98))
def pinball(pred,y):
    error=y[...,None]-pred; return np.maximum(Q*error,(Q-1)*error)
