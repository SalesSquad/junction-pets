"""Adapter for Rokoko Studio Live custom streaming, JSON v3 (one ASCII JSON frame per UDP datagram).
Public format notes: https://support.rokoko.com/hc/en-us/articles/4410416376977-Custom-Streaming
Reads the right-hand finger joint rotations (world-space quaternions x,y,z,w) and turns them into per-digit
closure 0..1, which is what the Shadow Hand retargeting in glove.py consumes.
STATUS: tested only against frames this file generates itself (synthetic_frame). Not yet run on a real Rokoko stream;
finger joint key names follow the v3 humanoid naming (rightIndexProximal ...) and should be confirmed on real data."""
import json, math, socket, sys
import numpy as np
from glove import POSES, D2R, F, human_finger, human_thumb
DIGITS=['Thumb','Index','Middle','Ring','Little']
LZ4_MAGIC=b'\x04\x22\x4d\x18'
def _q(j): r=j['rotation']; return np.array([r['x'],r['y'],r['z'],r['w']],float)
def _rel_angle(qa,qb):
    """angle (rad) of the rotation taking orientation a to orientation b"""
    w=abs(float(np.dot(qa,qb))); return 2*math.acos(min(1.0,w))
def _joint(body,side,digit,seg):
    for name in (f'{side}{digit}{seg}', f'{side}{digit}{"Intermediate" if seg=="Medial" else seg}'):
        if name in body: return body[name]
    return None
def span(kind,digit):
    P=POSES[kind]
    if digit=='Thumb': return sum(P['t'])*D2R
    f=P['f'][digit.lower()] if isinstance(P['f'],dict) else P['f']; return sum(f)*D2R
def parse_frame(payload,kind='power',side='right',actor=0):
    """bytes/str/dict -> dict(closure=[thumb,index,middle,ring,little], timestamp, has_glove) or raises ValueError"""
    if isinstance(payload,(bytes,bytearray)):
        if payload[:4]==LZ4_MAGIC: raise ValueError('LZ4-framed stream: select plain "JSON v3" in Rokoko Studio custom streaming')
        payload=payload.decode('ascii')
    fr=json.loads(payload) if isinstance(payload,str) else payload
    actors=fr.get('scene',{}).get('actors') or []
    if not actors: raise ValueError('no actors in frame (JSON v4 fills scene.newtons instead; this adapter reads JSON v3)')
    a=actors[actor]; body=a.get('body',{}); meta=a.get('meta',{})
    hand=body.get(f'{side}Hand')
    if hand is None: raise ValueError(f'frame has no {side}Hand joint')
    qh=_q(hand); out=[]
    for dg in DIGITS:
        chain=[_joint(body,side,dg,s) for s in ('Proximal','Medial','Distal')]
        if chain[2] is None: raise ValueError(f'frame has no {side}{dg}Distal joint')
        qs=[qh]+[_q(j) for j in chain if j is not None]      # summing per-segment angles keeps each step under 180 degrees
        ang=sum(_rel_angle(a,b) for a,b in zip(qs[:-1],qs[1:]))
        out.append(float(np.clip(ang/span(kind,dg),0,1)))
    return dict(closure=out,timestamp=fr.get('scene',{}).get('timestamp'),has_glove=bool(meta.get(f'has{side.capitalize()}Glove',meta.get('hasGloves',False))))
def _quat_x(a): return dict(x=math.sin(a/2),y=0.0,z=0.0,w=math.cos(a/2))
def synthetic_frame(closure,t=0.0,kind='power'):
    """Build a JSON v3-shaped frame from per-digit closure using the simulated human hand (for tests and offline demos)."""
    body={'rightHand':dict(position=dict(x=0,y=1.0,z=0),rotation=_quat_x(0))}; P=POSES[kind]
    for i,dg in enumerate(DIGITS):
        if dg=='Thumb': ang=np.array(P['t'])*D2R*closure[0]; pts=human_thumb(P['opp']*D2R*min(1,1.6*closure[0]),ang)
        else:
            f=P['f'][dg.lower()] if isinstance(P['f'],dict) else P['f']; ang=np.array(f)*D2R*closure[i]; pts=human_finger(dg.lower(),ang)
        acc=0
        for seg,a,p in zip(['Proximal','Medial','Distal'],ang,pts[:3]):
            acc+=float(a); body[f'right{dg}{seg}']=dict(position=dict(x=float(p[0]),y=1.0+float(p[2]),z=float(-p[1])),rotation=_quat_x(acc))
    return dict(version='3,0',fps=60.0,scene=dict(timestamp=t,actors=[dict(name='SimulatedOperator',meta=dict(hasGloves=True,hasLeftGlove=False,hasRightGlove=True,hasBody=False,hasFace=False),body=body)],newtons=[],props=[]))
def listen(port=14043,host='0.0.0.0',kind='power'):
    """Yield parsed frames from a live Rokoko Studio custom stream (UDP, JSON v3, uncompressed)."""
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind((host,port))
    while True:
        data,_=s.recvfrom(1<<16)
        try: yield parse_frame(data,kind)
        except ValueError as e: print('skipped frame:',e,file=sys.stderr)
def replay(path,kind='power'):
    for line in open(path):
        if line.strip(): yield parse_frame(line,kind)
if __name__=='__main__':
    # round-trip self test + write a sample stream file
    rng=np.random.default_rng(0); worst=0
    for _ in range(200):
        c=rng.uniform(0,1,5); got=parse_frame(json.dumps(synthetic_frame(c)))['closure']; worst=max(worst,float(np.abs(np.array(got)-c).max()))
    assert worst<1e-6,worst
    try: parse_frame(LZ4_MAGIC+b'xx'); raise SystemExit('lz4 not rejected')
    except ValueError: pass
    try: parse_frame(json.dumps(dict(scene=dict(actors=[],newtons=[{}])))); raise SystemExit('v4 not rejected')
    except ValueError: pass
    with open('sample_stream_v3.jsonl','w') as f:
        for k in range(360):
            t=k/60; s=float(np.interp(t,[0,1.5,2.5,3.5,4.5,5.2,6],[0,0.6,0.6,1,1,0,0])); c=np.clip(s+0.004*np.sin(2*np.pi*9*t+np.arange(5)),0,1)
            f.write(json.dumps(synthetic_frame(c,t))+'\n')
    print('round trip ok, worst closure error',worst,'; wrote sample_stream_v3.jsonl (360 frames, simulated)')
