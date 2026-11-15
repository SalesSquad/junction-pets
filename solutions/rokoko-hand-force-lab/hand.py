"""Shared helpers: Shadow Hand (MuJoCo Menagerie, Apache-2.0) force tests."""
import mujoco, numpy as np, os
HERE=os.path.dirname(os.path.abspath(__file__))
HAND=os.path.join(HERE,'menagerie/shadow_hand/right_hand.xml')
FINGERS={'ff':'index','mf':'middle','rf':'ring','lf':'little','th':'thumb','pa':'palm'}
def scene(extra_world, extra='', arm=False, floor=-0.1):
    return f'''<mujoco model="handforce">
  <include file="{"right_hand_arm.xml" if arm else "right_hand.xml"}"/>
  <option timestep="0.001"/>
  <statistic extent="0.3"/>
  <visual><global offwidth="1280" offheight="960"/><quality shadowsize="4096"/><map force="0.0004"/><scale forcewidth="0.06" contactwidth="0.05" contactheight="0.01"/><rgba contactforce="1 0.62 0.15 1" contactpoint="1 0.62 0.15 1"/><headlight ambient="0.55 0.55 0.6" diffuse="0.7 0.7 0.75"/></visual>
  <asset><texture type="skybox" builtin="gradient" rgb1="0.16 0.19 0.26" rgb2="0.04 0.05 0.07" width="256" height="1536"/>
  <texture type="2d" name="g" builtin="checker" rgb1="0.20 0.22 0.27" rgb2="0.17 0.19 0.24" width="300" height="300"/>
  <material name="g" texture="g" texuniform="true" texrepeat="6 6" reflectance="0.25"/></asset>
  <worldbody><light pos="0.3 0 1.2" dir="0 0 -1" directional="true"/><light pos="0.1 -0.5 0.6" diffuse="0.5 0.6 0.9"/><light pos="0.6 0.4 0.5" diffuse="0.9 0.6 0.4"/>
  <geom name="floor" pos="0 0 {floor}" size="0 0 0.05" type="plane" material="g"/>
  {extra_world}</worldbody>{extra}</mujoco>'''
def load(extra_world, extra='', arm=False, floor=-0.1):
    p=os.path.join(os.path.dirname(HAND),'_scene_%d.xml'%os.getpid())
    open(p,'w').write(scene(extra_world,extra,arm,floor))
    try: m=mujoco.MjModel.from_xml_path(p)
    finally: os.remove(p)
    return m,mujoco.MjData(m)
def act(m): return {m.actuator(i).name[5:]:i for i in range(m.nu)}
def finger_of(m,b):
    n=m.body(b).name
    return FINGERS.get(n[3:5]) if n.startswith('rh_') else None
def forces(m,d,obj_body):
    """Normal contact force [N] per finger on body obj_body, from the solver."""
    out={f:0.0 for f in FINGERS.values()}; f6=np.zeros(6)
    for i in range(d.ncon):
        c=d.contact[i]; b1=m.geom_bodyid[c.geom1]; b2=m.geom_bodyid[c.geom2]
        if obj_body not in (b1,b2): continue
        f=finger_of(m,b2 if b1==obj_body else b1)
        if f is None: continue
        mujoco.mj_contactForce(m,d,i,f6); out[f]+=max(f6[0],0.0)
    return out
def saturation(m,d):
    """|actuator force| / limit for every actuator (1.0 = motor at its real limit)."""
    return {m.actuator(i).name[5:]:abs(d.actuator_force[i])/m.actuator_forcerange[i,1] for i in range(m.nu)}

def net_force(m,d,obj_body,groups=('index','middle','ring','little')):
    """World-frame net force vector [N] that the given fingers apply to obj_body."""
    tot=np.zeros(3); f6=np.zeros(6)
    for i in range(d.ncon):
        c=d.contact[i]; b1=m.geom_bodyid[c.geom1]; b2=m.geom_bodyid[c.geom2]
        if obj_body not in (b1,b2): continue
        f=finger_of(m,b2 if b1==obj_body else b1)
        if f not in groups: continue
        mujoco.mj_contactForce(m,d,i,f6)
        fw=c.frame.reshape(3,3).T@f6[:3]   # force on geom2 from geom1, world frame
        tot+= fw if b2==obj_body else -fw
    return tot

def max_effort(m,g=20.0):
    """Stiffen the position servos so they run into the model's own force limits (forcerange unchanged)."""
    for i in range(m.nu):
        if 'ARM' in m.actuator(i).name: continue
        m.actuator_gainprm[i,0]*=g; m.actuator_biasprm[i,1]*=g
