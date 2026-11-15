"""Simulated motion-capture glove + fingertip retargeting to the Shadow Hand.
Human hand: simple kinematic model (segment lengths are typical adult values, assumed).
Stream: 60 Hz sample-and-hold, 35 ms latency, joint noise 0.8 deg rms, 9 Hz tremor.
Retargeting: each robot fingertip follows the human fingertip vector (knuckle->tip), scaled by finger length."""
import numpy as np, mujoco, json, os
from scipy.optimize import least_squares
from hand import load
D2R=np.pi/180
F=['index','middle','ring','little']
HK={'index':(0.030,0,0.095),'middle':(0.008,0,0.099),'ring':(-0.013,0,0.093),'little':(-0.032,0,0.082)}
HL={'index':(0.045,0.026,0.022),'middle':(0.050,0.030,0.023),'ring':(0.046,0.028,0.023),'little':(0.036,0.020,0.020)}
RK={'index':(0.033,0,0.095),'middle':(0.011,0,0.099),'ring':(-0.011,0,0.095),'little':(-0.033,0,0.0865)}
RL=(0.045,0.025,0.026); RP={'index':'FF','middle':'MF','ring':'RF','little':'LF'}
HTB=np.array([0.030,-0.008,0.028]); HTL=(0.046,0.035,0.028); RTB=np.array([0.034,-0.0086,0.029])
def dirv(a): return np.array([0.0,-np.sin(a),np.cos(a)])
def human_finger(f,ang):
    """ang=(mcp,pip,dip) rad -> joint positions (knuckle, pip, dip, tip) in palm frame"""
    k=np.array(HK[f]); L=HL[f]; p=[k]; a=0
    for l,q in zip(L,ang): a+=q; p.append(p[-1]+l*dirv(a))
    return np.array(p)
def rot(axis,a):
    axis=axis/np.linalg.norm(axis); K=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]]); return np.eye(3)+np.sin(a)*K+(1-np.cos(a))*K@K
def human_thumb(opp,ang):
    """opp rad (rotation in front of palm), ang=(cmc,mcp,ip) flex rad"""
    Rz=rot(np.array([0,0,1.0]),-opp); u=Rz@np.array([np.sin(45*D2R),0,np.cos(45*D2R)])
    v=np.array([-0.5,-0.6,0.3]); v=v-(v@u)*u; v/=np.linalg.norm(v); n=np.cross(u,v)
    p=[HTB.copy()]; a=0
    for l,q in zip(HTL,ang): a+=q; p.append(p[-1]+l*(rot(n,a)@u))
    return np.array(p)
POSES={ # closed-hand targets for the simulated operator (deg): fingers (mcp,pip,dip), thumb opp + (cmc,mcp,ip)
 'power':dict(f=(85,100,60),opp=70,t=(25,45,55)),
 'pinch':dict(f={'index':(52,58,32),'middle':(8,10,5),'ring':(8,10,5),'little':(8,10,5)},opp=78,t=(38,30,28)),
}
def _fit_thumb(kind,target):
    r=least_squares(lambda x:np.r_[human_thumb(x[0],x[1:])[-1]-target,0.002*(x-np.array([1.0,0.4,0.4,0.4]))],[1.0,0.4,0.4,0.4],bounds=([0,0,0,0],[1.6,0.9,1.1,1.2]))
    POSES[kind]['opp']=float(r.x[0]/D2R); POSES[kind]['t']=tuple(float(v/D2R) for v in r.x[1:]); return float(np.linalg.norm(human_thumb(r.x[0],r.x[1:])[-1]-target))
def human_pose(kind,s,st=None):
    P=POSES[kind]; st=s if st is None else st; out={}
    for i,f in enumerate(F):
        a=P['f'][f] if isinstance(P['f'],dict) else P['f']; lead=[0.0,0.03,0.06,0.09][i]
        out[f]=np.array(a)*D2R*np.clip(s*(1+lead),0,1)
    out['opp']=P['opp']*D2R*min(1,1.6*st); out['thumb']=np.array(P['t'])*D2R*st
    return out
_e1=_fit_thumb('power',np.array([0.012,-0.052,0.082]))
_it=human_finger('index',np.array(POSES['pinch']['f']['index'])*D2R)[-1]; _e2=_fit_thumb('pinch',_it+np.array([0.0,0.004,-0.012]))
# ---------- retargeting ----------
def robot_finger_solve(f,target,x0=(0.3,0.6)):
    k=np.array(RK[f])
    def tip(x): a,b=x; return k+RL[0]*dirv(a)+RL[1]*dirv(a+b/2)+RL[2]*dirv(a+b)
    r=least_squares(lambda x:(tip(x)-target)[1:],x0,bounds=([-0.26,0],[1.57,3.14]))
    return r.x,float(np.linalg.norm(tip(r.x)-target))
_m=None
def _thumb_model():
    global _m,_d,_J,_pal
    if _m is None:
        _m,_d=load(''); _J=[_m.jnt_qposadr[_m.joint('rh_THJ%d'%i).id] for i in (5,4,3,2,1)]
    return _m,_d,_J
def robot_thumb_tip(q):
    m,d,J=_thumb_model(); d.qpos[:]=0
    for a,v in zip(J,q): d.qpos[a]=v
    mujoco.mj_kinematics(m,d); P=d.body('rh_palm'); R=P.xmat.reshape(3,3); b=d.body('rh_thdistal')
    return R.T@(b.xpos+b.xmat.reshape(3,3)@np.array([0,0,0.0275])-P.xpos)
def robot_thumb_solve(target,x0):
    lo=[-1.05,0,-0.21,-0.7,-0.26]; hi=[1.05,1.22,0.21,0.7,1.57]
    r=least_squares(lambda x:np.r_[robot_thumb_tip(x)-target,0.004*(x-x0)],np.clip(x0,lo,hi),bounds=(lo,hi),diff_step=1e-3)
    return r.x,float(np.linalg.norm(robot_thumb_tip(r.x)-target))
def retarget_pose(hp,x0=None):
    """human pose dict -> robot actuator targets dict + per-finger tip error (m)"""
    out={};err={};x0=x0 or {}
    for f in F:
        hpts=human_finger(f,hp[f]); sc=sum(RL)/sum(HL[f]); tgt=np.array(RK[f])+sc*(hpts[-1]-hpts[0])
        x,e=robot_finger_solve(f,tgt,x0.get(f,(0.3,0.6))); out[RP[f]+'J3']=x[0]; out[RP[f]+'J0']=x[1]; err[f]=e; x0[f]=x
    ht=human_thumb(hp['opp'],hp['thumb']); sc=0.0975/sum(HTL); tgt=RTB+sc*(ht[-1]-ht[0])
    x,e=robot_thumb_solve(tgt,x0.get('thumb',np.array([0.0,0.6,0,0.2,0.3]))); x0['thumb']=x; err['thumb']=e
    for n,v in zip(['THJ5','THJ4','THJ3','THJ2','THJ1'],x): out[n]=v
    return out,err,x0
def build_lut(kind,n=41):
    """Precompute robot targets over operator closure s (and thumb closure) for fast simulation."""
    p=f'lut_{kind}.json'
    if os.path.exists(p): return json.load(open(p))
    S=np.linspace(0,1,n); rows=[];errs=[];x0=None
    for s in S:
        out,err,x0=retarget_pose(human_pose(kind,s),x0); rows.append(out); errs.append(err)
    lut=dict(s=S.tolist(),keys=list(rows[0]),v=[[r[k] for k in rows[0]] for r in rows],err=[[e[k] for k in ['thumb']+F] for e in errs]); json.dump(lut,open(p,'w')); return lut
class Glove:
    """Simulated glove stream for one grasp type. call(t, intent s in 0..1) -> robot ctrl dict, human skeleton, closure seen by robot."""
    def __init__(s,kind,seed=0,rate=60,latency=0.035,noise_deg=0.8):
        s.kind=kind; s.lut=build_lut(kind); s.S=np.array(s.lut['s']); s.V=np.array(s.lut['v']); s.rng=np.random.default_rng(seed)
        s.dt=1/rate; s.lat=latency; s.noise=noise_deg; s.buf=[]; s.next=0; s.cur=np.zeros(5); s.filt=np.zeros(5); s.fullspan=np.array(POSES[kind]['f'] if not isinstance(POSES[kind]['f'],dict) else POSES[kind]['f']['index']).sum()
    def __call__(s,t,intent):
        if t>=s.next:
            s.next+=s.dt; trem=0.004*np.sin(2*np.pi*9*t+np.arange(5)); n=s.rng.standard_normal(5)*s.noise/ s.fullspan*1.7
            s.buf.append((t+s.lat,np.clip(intent+trem+n,0,1)))      # per-digit closure as measured by the glove
        while s.buf and s.buf[0][0]<=t: s.cur=s.buf.pop(0)[1]
        s.filt+=0.06*(s.cur-s.filt)                                   # receiver-side smoothing
        return s.ctrl_for(s.filt),s.filt.copy()
    def ctrl_for(s,c):
        ctrl={}
        for i,k in enumerate(s.lut['keys']):
            dig=0 if k.startswith('TH') else 1+['FF','MF','RF','LF'].index(k[:2]); ctrl[k]=float(np.interp(c[dig],s.S,s.V[:,i]))
        return ctrl
    def skeleton(s,c):
        hp=human_pose(s.kind,1.0); pts=[]
        for i,f in enumerate(F):
            a=(np.array(POSES[s.kind]['f'][f] if isinstance(POSES[s.kind]['f'],dict) else POSES[s.kind]['f'])*D2R)*c[i+1]; pts.append(human_finger(f,a))
        P=POSES[s.kind]; th=human_thumb(P['opp']*D2R*min(1,1.6*c[0]),np.array(P['t'])*D2R*c[0])
        return [np.round(th*1000,1).tolist()]+[np.round(p*1000,1).tolist() for p in pts]
def apply(m,d,A,ctrl):
    for k,v in ctrl.items():
        lo,hi=m.actuator_ctrlrange[A[k]]; d.ctrl[A[k]]=min(max(v,lo),hi)
if __name__=='__main__':
    print('human thumb fit err mm',round(_e1*1000,2),round(_e2*1000,2),POSES['power']['opp'],POSES['power']['t'],POSES['pinch']['opp'],POSES['pinch']['t'])
    for kind in POSES:
        if os.path.exists(f'lut_{kind}.json'): os.remove(f'lut_{kind}.json')
        l=build_lut(kind); e=np.array(l['err'])*1000
        print(kind,'tip error mm mean per digit',e.mean(0).round(2),'max',e.max().round(2)); print({k:round(v,2) for k,v in zip(l['keys'],l['v'][-1])})
        ht=human_thumb(POSES[kind]['opp']*D2R,np.array(POSES[kind]['t'])*D2R)[-1]; hi=human_finger('index',np.array(POSES[kind]['f']['index'] if isinstance(POSES[kind]['f'],dict) else POSES[kind]['f'])*D2R)[-1]
        print(' human thumb tip',ht.round(3),'index tip',hi.round(3),'gap mm',round(float(np.linalg.norm(ht-hi))*1000,1))
