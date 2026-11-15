"""Drive the simulated Shadow Hand from a Rokoko JSON v3 stream file (or live UDP with --udp PORT) and report grip force."""
import sys,numpy as np,mujoco
from hand import *
from glove import Glove,apply
import rokoko_v3
from lab import BAR,FOUR
def run(frames,fps=60.0):
    m,d=load(BAR(0.019,False)); A=act(m); ob=m.body('obj').id; max_effort(m,20); g=Glove('power',0,noise_deg=0); peak=0; filt=np.zeros(5); n=0
    for fr in frames:
        c=np.array(fr['closure']); n+=1
        for _ in range(int(round(1000/fps))):
            filt+=0.06*(c-filt); apply(m,d,A,g.ctrl_for(filt)); mujoco.mj_step(m,d)
        if d.time>0.3: peak=max(peak,float(np.linalg.norm(net_force(m,d,ob))))
    return dict(frames=n,sim_seconds=round(d.time,2),peak_grip_N=round(peak,1))
if __name__=='__main__':
    src=rokoko_v3.listen(int(sys.argv[2])) if len(sys.argv)>2 and sys.argv[1]=='--udp' else rokoko_v3.replay(sys.argv[1] if len(sys.argv)>1 else 'sample_stream_v3.jsonl')
    print(run(src))
