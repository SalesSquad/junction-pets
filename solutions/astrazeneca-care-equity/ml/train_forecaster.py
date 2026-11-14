"""Masked change-predicting transformer deep ensemble."""
import copy
import numpy as np
import torch
from torch import nn
from common import *
class Forecaster(nn.Module):
    def __init__(self,n,targets):
        super().__init__(); self.input=nn.Linear(n*2+1,128); self.category=nn.Embedding(3,128); self.position=nn.Parameter(torch.randn(8,128)*.02)
        layer=nn.TransformerEncoderLayer(128,4,256,.1,batch_first=True)
        self.encoder=nn.TransformerEncoder(layer,3); self.head=nn.Linear(128,targets*2*5); self.nt=targets
    def forward(self,x,cat,year):
        z=torch.cat([x,year[:,None,None].expand(-1,8,1)/30],-1)
        h=self.input(z)+self.category(cat)[:,None]+self.position
        return self.head(self.encoder(h).mean(1)).reshape(-1,self.nt,2,5).sort(-1).values

def loss(pred,y):
    mask=torch.isfinite(y); delta=torch.nan_to_num(y)[...,None]-pred
    q=torch.tensor(Q,device=pred.device,dtype=pred.dtype)
    return (torch.maximum(q*delta,(q-1)*delta)*mask[...,None]).sum()/(mask.sum().clamp(min=1)*5)
def tensors(w,y,meta,cats,targets,mean,std,device):
    mask=np.isfinite(w); z=np.where(mask,(w-mean)/std,0); inputs=np.concatenate([z,mask],-1).astype('float32')
    last=np.array([[last_value(a[:,j]) for j in targets] for a in w]); target=(y-last[:,:,None])/std[targets][None,:,None]
    return tuple(torch.as_tensor(a,device=device) for a in (inputs,cats[[m[0] for m in meta]].astype('int64'),np.array([m[1]-2000 for m in meta],dtype='float32'),target.astype('float32'))),last

def fit(w,y,meta,vw,vy,vm,cats,targets,a,epochs=None):
    # Statistics use only the training input windows, never validation/test observations.
    count=np.isfinite(w).sum((0,1)); mean=np.nansum(w,(0,1))/np.maximum(count,1); std=np.sqrt(np.nansum((w-mean)**2,(0,1))/np.maximum(count,1)); std=np.where(std>1e-6,std,1)
    train,_=tensors(w,y,meta,cats,targets,mean,std,a.device); valid,_=tensors(vw,vy,vm,cats,targets,mean,std,a.device)
    models=[]; histories=[]; total=epochs or a.epochs
    for s in range(a.seeds):
        seed(s); model=Forecaster(w.shape[-1],len(targets)).to(a.device); opt=torch.optim.AdamW(model.parameters(),lr=.0005); schedule=torch.optim.lr_scheduler.CosineAnnealingLR(opt,total); best=float('inf'); state=None; patience=0; history=[]
        for epoch in range(total):
            model.train(); order=torch.randperm(len(w),device=a.device)
            for idx in order.split(16 if a.smoke else 128):
                inp,cat,year,target=[t[idx] for t in train]; inp=inp.clone(); n=w.shape[-1]; hide=(torch.rand_like(inp[:,:,:n])<.15)&(inp[:,:,n:]>0); inp[:,:,:n].masked_fill_(hide,0); inp[:,:,n:].masked_fill_(hide,0)
                opt.zero_grad(); value=loss(model(inp,cat,year),target); value.backward(); nn.utils.clip_grad_norm_(model.parameters(),1); opt.step()
            schedule.step(); model.eval()
            with torch.no_grad(): val=float(loss(model(*valid[:3]),valid[3]))
            history.append(val)
            if val<best: best=val; state=copy.deepcopy(model.state_dict()); patience=0
            else: patience+=1
            if patience>=10: break
        model.load_state_dict(state); models.append({k:v.cpu() for k,v in model.state_dict().items()}); histories.append(history)
        print('seed',s,'epochs',len(history),'validation pinball',best,flush=True)
    return dict(models=models,mean=mean,std=std,histories=histories)
def predict(bundle,w,meta,cats,targets,device):
    t,last=tensors(w,np.full((len(w),len(targets),2),np.nan),meta,cats,targets,bundle['mean'],bundle['std'],device); out=[]
    for state in bundle['models']:
        m=Forecaster(w.shape[-1],len(targets)).to(device); m.load_state_dict(state); m.eval(); batches=[]
        with torch.no_grad():
            for start in range(0,len(w),256): batches.append(m(*(v[start:start+256] for v in t[:3])).cpu().numpy())
        out.append(np.concatenate(batches))
    return np.mean(out,0)*bundle['std'][targets][None,:,None,None]+last[:,:,None,None]
def main():
    a=args(); torch.set_num_threads(2); p,x,years,targets,cats=load(a.panel)
    w,y,m=windows(x,years,targets,[t for t in years if t<=2020]); y[np.array([t+2>2021 for _,t in m]),:,1]=np.nan
    # Training labels end in 2021; validation origin 2021 labels begin in 2022.
    vw,vy,vm=windows(x,years,targets,[2021]); bundle=fit(w,y,m,vw,vy,vm,cats,targets,a)
    Path(a.artifacts).mkdir(parents=True,exist_ok=True); torch.save(bundle,Path(a.artifacts)/'backtest.pt')
if __name__=='__main__': main()
