"""Force lab v2: every scenario is driven by the simulated glove through fingertip retargeting."""
import mujoco,numpy as np,json,os,sys,imageio
from hand import *
from glove import Glove,apply,build_lut
import tasks
W_,H_,FPS=800,600,20
ORDER=['thumb','index','middle','ring','little']; FOUR=ORDER[1:]
BASE=np.array([0.16,0.17,0.2,1]); HOT=np.array([1.0,0.55,0.1,1])
class Tactile:
    """Fingertip force sensors as a real hand would have them: 100 Hz, 5 % gain error, 0.15 N noise, 0.05 N resolution."""
    def __init__(s,seed=0,ideal=False):
        s.rng=np.random.default_rng(seed); s.gain=1+0.05*s.rng.standard_normal(6); s.next=0; s.f=dict.fromkeys(ORDER+['palm'],0.0); s.sh=0.0; s.ideal=ideal
    def read(s,m,d,ob,axis=1):
        if d.time>=s.next:
            s.next+=0.01; tr=forces(m,d,ob); sh=abs(float(net_force(m,d,ob,tuple(ORDER+['palm']))[axis]))
            if s.ideal: s.f=tr; s.sh=sh
            else:
                for i,k in enumerate(ORDER+['palm']): s.f[k]=round(max(0,tr[k]*s.gain[i]+0.15*s.rng.standard_normal())/0.05)*0.05 if tr[k]>0 else max(0,round(0.15*s.rng.standard_normal()/0.05)*0.05)
                s.sh=max(0,sh*s.gain[0]+0.3*s.rng.standard_normal())
        return s.f
    def grip(s): return sum(s.f[k] for k in FOUR)
class Rec:
    def __init__(s,m,lookat,dist=0.40,az=215,el=-28,orbit=12,fscale=30,render=True):
        s.m=m; s.render=render and not os.environ.get('NORENDER'); s.fscale=fscale
        if s.render:
            s.r=mujoco.Renderer(m,H_,W_); s.cam=mujoco.MjvCamera(); s.cam.lookat[:]=lookat; s.cam.distance=dist; s.az=az; s.cam.elevation=el; s.orbit=orbit
            s.opt=mujoco.MjvOption(); s.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE]=True
        s.fg={f:[g for g in range(m.ngeom) if finger_of(m,m.geom_bodyid[g])==f and m.geom_contype[g]==0] for f in ORDER}
        for f in ORDER:
            for g in s.fg[f]: m.geom_matid[g]=-1; m.geom_rgba[g]=BASE
        s.frames=[]; s.data=[]; s.next=0.1; s.off=0.0
    def tick(s,d,T,ff=None,**row):
        if d.time<s.next: return
        s.next+=1/FPS
        if s.render:
            if ff is not None:
                for f,v in zip(ORDER,ff):
                    c=BASE+(HOT-BASE)*min(1,v/s.fscale)
                    for g in s.fg[f]: s.m.geom_rgba[g]=c
            s.cam.azimuth=s.az+s.orbit*np.sin(2*np.pi*d.time/T); s.r.update_scene(d,s.cam,s.opt); s.frames.append(s.r.render().copy())
        s.data.append(dict(t=round(d.time+s.off,3),fingers=ff,**row))
    def rebind(s,m,off):
        """continue recording on a fresh model (next phase)"""
        cam=(s.cam,s.az,s.orbit) if s.render else None; fr,da=s.frames,s.data
        if s.render: s.r.close()
        s.__init__(m,[0,0,0],fscale=s.fscale,render=s.render)
        if cam: s.cam,s.az,s.orbit=cam
        s.frames,s.data,s.off=fr,da,off
def pf(m,d,ob): f=forces(m,d,ob); return [round(f[k],2) for k in ORDER]
def r3(c): return [round(float(v),3) for v in c]
BAR=lambda R,free,mu=1.0,col="0.95 0.55 0.2 1": f'<body name="obj" pos="0.338 0 {0.013+R+0.004}">{"<freejoint/>" if free else ""}<geom name="obj" type="cylinder" size="{R} 0.07" quat="1 1 0 0" mass="0.2" rgba="{col}" friction="{mu} 0.01 0.003" priority="1" condim="4"/></body>'

def s_grip(render=True):
    m,d=load(BAR(0.019,False)); A=act(m); ob=m.body('obj').id; max_effort(m,20); rec=Rec(m,[0.33,0,0.03],fscale=60,render=render); g=Glove('power',1); T=8.0
    prof=lambda t: np.interp(t,[0,1.5,2.5,3.5,4.5,5.5,6.8,8],[0,0.55,0.55,0.75,0.75,1,1,0])
    while d.time<T:
        ctrl,c=g(d.time,float(prof(d.time))); apply(m,d,A,ctrl); mujoco.mj_step(m,d)
        rec.tick(d,T,ff=pf(m,d,ob),human=r3(c),sk=g.skeleton(c),total=round(float(np.linalg.norm(net_force(m,d,ob))),2))
    return rec,dict(id='grip')

def pinch_gauge():
    lut=build_lut('pinch'); m,d=load(''); v=dict(zip(lut['keys'],np.array(lut['v'])[int(len(lut['s'])*0.9)]))
    for k,x in v.items():
        if k.endswith('J0'):
            for j in '21': d.qpos[m.jnt_qposadr[m.joint('rh_'+k[:2]+'J'+j).id]]=x/2
        else: d.qpos[m.jnt_qposadr[m.joint('rh_'+k).id]]=x
    mujoco.mj_kinematics(m,d); tip=lambda b: d.body(b).xpos+d.body(b).xmat.reshape(3,3)@np.array([0,0,0.018])
    return tip('rh_ffdistal'),tip('rh_thdistal')
def s_pinch(render=True):
    """Pinch uses a grasp primitive: the glove's thumb/index closure drives a pre-found robot pinch pose; closing past contact becomes squeeze."""
    P=json.load(open('pinch_pose.json')); q=P['q']; pfp=np.array(P['pf']); ptp=np.array(P['pt']); mid=(pfp+ptp)/2; ax=(pfp-ptp)/np.linalg.norm(pfp-ptp); z=ax; x=np.cross(z,[0,0,1]); x/=np.linalg.norm(x); y=np.cross(z,x)
    Wd=f'<body name="obj" pos="{mid[0]} {mid[1]} {mid[2]}" xyaxes="{x[0]} {x[1]} {x[2]} {y[0]} {y[1]} {y[2]}"><geom type="box" size="0.012 0.012 0.005" rgba="0.95 0.55 0.2 1" friction="1 0.01 0.003" condim="4"/></body>'
    m,d=load(Wd); A=act(m); ob=m.body('obj').id; max_effort(m,20); rec=Rec(m,mid,dist=0.27,az=200,el=-35,orbit=10,fscale=25,render=render); g=Glove('pinch',2); T=7.0
    base={k:q[k] for k in ['THJ5','THJ4','THJ3','THJ2','THJ1','FFJ4','FFJ3']}; base['FFJ0']=q['FFJ2']+q['FFJ1']
    op=dict(base); op['THJ2']-=0.4; op['THJ1']-=0.3; op['FFJ3']-=0.4; sq={'THJ2':0.5,'THJ1':0.4,'FFJ3':0.5,'FFJ0':0.3}
    while d.time<T:
        s=float(np.interp(d.time,[0,1.0,2.0,3.0,4.0,5.2,6.2],[0,0.8,0.86,0.86,1,1,0])); _,c=g(d.time,s)
        for k in base:
            cl=c[0] if k[0]=='T' else c[1]; a_=float(np.clip(cl/0.8,0,1)); s_=float(np.clip((cl-0.8)/0.2,0,1))
            lo,hi=m.actuator_ctrlrange[A[k]]; d.ctrl[A[k]]=np.clip(op[k]+(base[k]-op[k])*a_+sq.get(k,0)*s_,lo,hi)
        mujoco.mj_step(m,d); th=float(net_force(m,d,ob,('thumb',))@ax); ix=float(-net_force(m,d,ob,('index',))@ax)
        rec.tick(d,T,ff=pf(m,d,ob),human=r3(c),sk=g.skeleton(c),total=round(max(min(th,ix),0),2))
    return rec,dict(id='pinch')

def contact_closure(R):
    m,d=load(BAR(R,False)); A=act(m); ob=m.body('obj').id; max_effort(m,4); g=Glove('power',0,noise_deg=0); s=0
    while s<1:
        apply(m,d,A,g.ctrl_for(np.full(5,s))); mujoco.mj_step(m,d); s+=0.0003
        if d.time<0.3: s=0; continue
        if sum(forces(m,d,ob)[k] for k in FOUR)>0.3: return s
    return 1.0
BREAK=15.0
def fragile_phase(mode,R=0.019,seed=0,rec=None,sc=None,T=5.0,goal=5.0,limit=3.0):
    """mode: 'blind' operator closes by eye; 'feedback' operator sees/hears force (180 ms delay, 10 % perception noise); 'limiter' operator slams shut, hand limits force."""
    rng=np.random.default_rng(seed); m,d=load(BAR(R,False,col="0.96 0.93 0.85 1")); A=act(m); ob=m.body('obj').id; max_effort(m,4); gid=m.geom('obj').id
    if rec is not None: rec.rebind(m,rec.data[-1]['t']+1/FPS if rec.data else 0); rec.next=0.05
    g=Glove('power',seed); tac=Tactile(seed); s=0.0; lim=0.0; broken=False; peak=0; hist=[]; seen=0.0
    sc=contact_closure(R) if sc is None else sc; blind_goal=sc+rng.uniform(0.03,0.14)
    while d.time<T:
        t=d.time; tac.read(m,d,ob); F=tac.grip(); hist.append(F)
        if int(t*1000)%100==0: seen=hist[max(0,len(hist)-180)]*(1+0.10*rng.standard_normal())      # operator perceives a delayed, noisy force
        active=0.4<t<T-0.9
        if mode=='blind': s=float(np.interp(t,[0.4,1.6,T-0.9,T-0.2],[0,blind_goal,blind_goal,0]))
        elif mode=='feedback': s=float(np.clip(s+(0.0003*np.tanh((goal-seen)/6.0) if active else -0.0015),0,1))
        else: s=float(np.interp(t,[0.4,1.2,T-0.9,T-0.2],[0,1,1,0]))
        ctrl,c=g(t,s)
        if mode=='limiter':
            lim=float(np.clip(lim+(0.0012*np.tanh((limit-F)/10.0) if active else -0.0015),0,1)); ctrl=g.ctrl_for(np.minimum(c,lim))
        apply(m,d,A,ctrl); mujoco.mj_step(m,d)
        true=float(np.linalg.norm(net_force(m,d,ob))) if t>0.3 else 0.0; peak=max(peak,true)
        if true>BREAK and not broken: broken=True; m.geom_rgba[gid]=[0.9,0.15,0.15,1]
        if rec is not None: rec.tick(d,T,ff=pf(m,d,ob),human=r3(c),sk=g.skeleton(c),total=round(true,2),flag={'blind':'EI PALAUTETTA','feedback':'VOIMAPALAUTE','limiter':'KÄDEN VOIMARAJA'}[mode]+(' · RIKKI' if broken else ''))
    steady=float(np.mean(hist[int((T-1.9)*1000):int((T-0.9)*1000)]))
    return dict(broken=broken,peak=peak,steady=steady)
def s_fragile(render=True):
    m,d=load(''); rec=Rec(m,[0.33,0,0.03],fscale=15,render=render); out={}; sc=contact_closure(0.019)
    for i,mode in enumerate(['blind','feedback','limiter']): out[mode]=fragile_phase(mode,seed=[101,12,13][i],rec=rec,sc=sc)
    return rec,dict(id='fragile',**out)

def slip_run(reflex,mu=1.0,seed=0,rec=None,ideal=False,T=10.0,maxpull=45.0):
    m,d=load(BAR(0.019,True,mu)); A=act(m); ob=m.body('obj').id; max_effort(m,6)
    if rec is not None: rec.rebind(m,rec.data[-1]['t']+1/FPS if rec.data else 0); rec.next=0.05
    g=Glove('power',seed); tac=Tactile(seed,ideal); s=0.0; add=0.0; slipped=None; p0=None; pull=0.0
    while d.time<T:
        t=d.time; tac.read(m,d,ob); F=tac.grip()
        if t<3.0: s=float(np.clip(s+(0.0012 if F<1 else 0.0004*np.tanh((12.0-F)/10.0)),0,1))           # operator settles a light 12 N grip, then holds still
        else:
            if p0 is None: p0=d.body('obj').xpos.copy(); m.opt.gravity[:]=0
            pull=float(np.interp(t,[3,9],[0,maxpull])) if slipped is None else 0.0
            add=float(np.clip(add+0.0008*np.tanh(((max(12.0,2.2*tac.sh+6.0) if reflex else 12.0)-F)/10.0),-0.3,1))   # hand holds grip force itself; reflex raises the target with sensed shear
        d.xfrc_applied[ob,:3]=[0,pull,0]; ctrl,c=g(t,s); ctrl=g.ctrl_for(np.clip(c+add,0,1)); apply(m,d,A,ctrl); mujoco.mj_step(m,d)
        disp=0.0 if p0 is None else float(np.linalg.norm(d.body('obj').xpos-p0))
        if slipped is None and disp>0.010: slipped=pull
        if rec is not None: rec.tick(d,T,ff=pf(m,d,ob),human=r3(c),sk=g.skeleton(c),total=round(sum(forces(m,d,ob)[k] for k in FOUR),2),load=round(pull if slipped is None else slipped,2),flag=('REFLEKSI' if reflex else 'EI REFLEKSIÄ')+(' · LUISTI' if slipped is not None else ''))
    return slipped
def s_slip(render=True):
    m,d=load(''); rec=Rec(m,[0.33,0.01,0.03],orbit=8,fscale=30,render=render); out={}
    out['slip_at']=slip_run(False,seed=5,rec=rec); out['slip_at_reflex']=slip_run(True,seed=5,rec=rec)
    return rec,dict(id='slip',**out)

def s_ball(render=True):
    Wd='<body name="obj" pos="0.345 -0.005 0.054"><freejoint/><geom name="obj" type="sphere" size="0.03" mass="0.15" rgba="0.2 0.75 0.6 1" friction="1 0.01 0.003" condim="4"/></body>'
    m,d=load(Wd); A=act(m); ob=m.body('obj').id; max_effort(m,6); rec=Rec(m,[0.33,0,0.04],fscale=12,render=render); T=9.0; s=0.0; q0=d.qpos[-7:].copy(); g=Glove('power',4); tac=Tactile(4)
    while d.time<T:
        tgt=float(np.interp(d.time,[0,0.3,1.5,8,8.8],[0,0,10,10,0]))
        if d.time<3.2: d.qpos[-7:]=q0; d.qvel[-6:]=0
        tac.read(m,d,ob); F=sum(tac.f[k] for k in ORDER)
        s=float(np.clip(s+(0.0006*np.tanh((tgt-F)/10.0) if tgt>0 else -0.0006),0,1)); ctrl,c=g(d.time,s); apply(m,d,A,ctrl)
        if 4.2<d.time<7.2: d.ctrl[A['WRJ1']]=0.35*np.sin(2*np.pi*1.5*d.time); d.ctrl[A['WRJ2']]=-0.15+0.15*np.sin(2*np.pi*1.0*d.time)
        else: d.ctrl[A['WRJ1']]=0; d.ctrl[A['WRJ2']]=0
        mujoco.mj_step(m,d); pal=d.body('rh_palm'); rel=pal.xmat.reshape(3,3).T@(d.body('obj').xpos-pal.xpos)
        rec.tick(d,T,ff=pf(m,d,ob),human=r3(c),sk=g.skeleton(c),total=round(sum(forces(m,d,ob)[k] for k in ORDER),2),rel=[round(float(v)*1000,1) for v in rel])
    return rec,dict(id='ball')

class CupRec:
    def __init__(s,render): s.rec=None; s.render=render
    def tick(s,d,T,g=None,c=None,**row):
        if s.rec is None: s.rec=Rec(s.m,[0.42,0.06,0.03],dist=0.62,az=140,el=-22,orbit=10,fscale=20,render=s.render)
        ff=row.pop('fingers'); row.pop('human'); s.rec.tick(d,T,ff=ff,human=r3(c),sk=g.skeleton(c),**row)
def s_cup(render=True):
    cr=CupRec(render); _l=tasks.load
    def L(*a,**k):
        m,d=_l(*a,**k); cr.m=m; return m,d
    tasks.load=L; res=tasks.cup_task(rec=cr); tasks.load=_l
    return cr.rec,dict(id='cup',**res)
S=dict(grip=s_grip,pinch=s_pinch,fragile=s_fragile,slip=s_slip,ball=s_ball,cup=s_cup)
if __name__=='__main__':
    os.makedirs('out',exist_ok=True)
    for n in sys.argv[1:]:
        rec,meta=S[n]()
        if rec.frames:
            imageio.mimwrite(f'out/{n}.mp4',rec.frames,fps=FPS,codec='libx264',quality=7,macro_block_size=8,pixelformat='yuv420p'); imageio.imwrite(f'out/{n}_mid.png',rec.frames[len(rec.frames)*2//3])
        json.dump(dict(meta=meta,data=rec.data),open(f'out/{n}.json','w'),default=float)
        tot=[r['total'] for r in rec.data]; print(n,len(rec.data),'rows max',max(tot),{k:(v if not isinstance(v,float) else round(v,2)) for k,v in meta.items()},[ (r['t'],r['total']) for r in rec.data[::25]],flush=True)
