"""Arm + hand tasks driven by the simulated glove (operator intent -> glove stream -> retarget -> robot)."""
import mujoco,numpy as np,json,os,sys
from hand import *
from glove import Glove,apply
ORDER=['thumb','index','middle','ring','little']
def setarm(m,d,A,x=0,y=0,z=0,roll=0,pitch=0,yaw=0):
    for k,v in zip(['ARMX','ARMY','ARMZ','ARMROLL','ARMPITCH','ARMYAW'],[x,y,z,roll,pitch,yaw]): d.ctrl[A[k]]=v
def initarm(m,d,**kw):
    for k,v in kw.items(): d.qpos[m.jnt_qposadr[m.joint('arm_'+k).id]]=v
def cup_task(rec=None,grip_target=30.0,mass=0.3,mu=1.0,verbose=False,R=0.022):
    Wd=f'<body name="obj" pos="0.338 {0.017+R+0.070+0.003} 0.0"><freejoint/><geom name="obj" type="cylinder" size="{R} 0.07" mass="{mass}" rgba="0.92 0.9 0.84 1" friction="{mu} 0.01 0.003" condim="4"/></body>'
    m,d=load(Wd,arm=True,floor=-0.0705); A=act(m); ob=m.body('obj').id; max_effort(m,6); g=Glove('power',seed=3)
    roll0=-1.5708; initarm(m,d,roll=roll0); mujoco.mj_forward(m,d); T=14.5; s=0.0; filt=0.0; log=[]
    wp=lambda t,ts,vs: float(np.interp(t,ts,vs))
    while d.time<T:
        t=d.time
        y=wp(t,[0,0.5,2.0,12.2,13.6],[0,0,0.070,0.070,0.0]); z=wp(t,[4.6,6.0,10.0,11.2],[0,0.12,0.12,0.003]); x=wp(t,[6.0,7.0],[0,0.12])
        roll=roll0+wp(t,[7.2,8.2,8.8,9.8],[0,-1.0,-1.0,0]); setarm(m,d,A,x=x,y=y,z=z,roll=roll)
        tgt=grip_target if 2.2<t<11.5 else 0.0
        F=sum(forces(m,d,ob)[k] for k in ['index','middle','ring','little']); filt+=0.02*(F-filt)
        s=float(np.clip(s+(0.0004*np.tanh((tgt-filt)/10.0) if tgt>0 else -0.0015),0,1))
        ctrl,c=g(t,s); apply(m,d,A,ctrl); mujoco.mj_step(m,d)
        o=d.body('obj'); up=o.xmat.reshape(3,3)[:,2]; tilt=float(np.degrees(np.arccos(np.clip(up[2],-1,1))))
        row=dict(human=[round(float(v),3) for v in c],fingers=[round(forces(m,d,ob)[k],2) for k in ORDER],total=round(filt,2),height=round(float(o.xpos[2])*1000,1),tilt=round(tilt,1),ox=round(float(o.xpos[0])*1000,1))
        if rec: rec.tick(d,T,g=g,c=c,**row)
        elif int(t*1000)%500==0: log.append((round(t,1),row['total'],row['height'],row['tilt'],row['ox']))
    o=d.body('obj'); res=dict(final_height_mm=float(o.xpos[2])*1000,final_tilt=tilt,moved_x_mm=float(o.xpos[0]-0.338)*1000)
    if verbose: print(log)
    return res
if __name__=='__main__': print(cup_task(verbose=True))
