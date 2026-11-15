"""Numbers behind the page: operator feedback trials, friction sweep with noisy sensors, learned policy."""
import numpy as np,json,sys,mujoco
from lab import *
from sklearn.neural_network import MLPRegressor
out={}
def feedback():
    res={}
    for mode in ['blind','feedback','limiter']:
        rows=[]
        for i in range(12):
            R=[0.017,0.019,0.021,0.023][i%4]; r=fragile_phase(mode,R=R,seed=100+i); rows.append(dict(R=R,**r)); print(mode,i,R,round(r['steady'],1),round(r['peak'],1),r['broken'],flush=True)
        res[mode]=dict(n=len(rows),broken=sum(r['broken'] for r in rows),steady=[r['steady'] for r in rows],peak=[r['peak'] for r in rows])
    return res
def friction():
    res=[]
    for mu in [0.5,0.8,1.0]:
        a=slip_run(False,mu=mu,seed=7,maxpull=60); b=slip_run(True,mu=mu,seed=7,maxpull=60); c=slip_run(True,mu=mu,seed=7,maxpull=60,ideal=True)
        res.append(dict(mu=mu,no_reflex=a,reflex=b,reflex_ideal=c)); print(res[-1],flush=True)
    return res
def episode(R,tgt,policy=None,seed=0,T=4.0):
    m,d=load(BAR(R,False)); A=act(m); ob=m.body('obj').id; max_effort(m,4); g=Glove('power',seed,noise_deg=0); tac=Tactile(seed); s=0.0; X=[];Y=[];F=[]
    while d.time<T:
        tac.read(m,d,ob)
        if int(round(d.time*1000))%20==0:
            obs=[tgt/50,s]+[tac.f[k]/20 for k in ORDER]+[tac.grip()/50]
            a=0.008*np.tanh((tgt-tac.grip())/10.0) if policy is None else float(policy.predict([obs])[0])
            X.append(obs);Y.append(a); s=float(np.clip(s+a,0,1))
        apply(m,d,A,g.ctrl_for(np.full(5,s))); mujoco.mj_step(m,d)
        if d.time>0.3: F.append(float(np.linalg.norm(net_force(m,d,ob))))
    return X,Y,dict(R=R,target=tgt,final=float(np.mean(F[-800:])),peak=float(max(F)))
def learn():
    X=[];Y=[]
    for R in [0.016,0.018,0.020,0.022,0.024]:
        for tgt in [5,12,20,30]:
            x,y,r=episode(R,tgt,seed=int(R*1e4)+tgt); X+=x;Y+=y; print('demo',r,flush=True)
    pol=MLPRegressor(hidden_layer_sizes=(48,48),max_iter=3000,random_state=0,learning_rate_init=2e-3).fit(np.array(X),np.array(Y)*100); 
    class P:
        def predict(s,o): return pol.predict(o)/100
    tests=[]
    for R in [0.017,0.019,0.021,0.023]:
        for tgt in [8,16,25]:
            _,_,r=episode(R,tgt,policy=P(),seed=999); r['ok']=bool(abs(r['final']-tgt)<=0.2*tgt and r['peak']<=1.6*tgt); tests.append(r); print('test',r,flush=True)
    import pickle; pickle.dump(pol,open('policy.pkl','wb'))
    return dict(demos=20,samples=len(X),tests=tests,success=sum(t['ok'] for t in tests),n=len(tests))
for name in sys.argv[1:]:
    out[name]=dict(feedback=feedback,friction=friction,learn=learn)[name](); json.dump(out[name],open(f'results/exp_{name}.json','w'),default=float)
