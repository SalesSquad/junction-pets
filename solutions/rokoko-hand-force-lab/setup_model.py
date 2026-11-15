"""Fetch the Shadow Hand model (MuJoCo Menagerie, Apache-2.0, pinned commit) and derive the 6-axis carriage variant.
The model is not vendored in this repository. Run once: python3 setup_model.py"""
import os,subprocess
HERE=os.path.dirname(os.path.abspath(__file__)); M=os.path.join(HERE,'menagerie'); COMMIT='370c43965323c0944b433b202aac5058b5f907a9'
if not os.path.isdir(M):
    subprocess.check_call(['git','clone','--filter=blob:none','--sparse','https://github.com/google-deepmind/mujoco_menagerie',M])
    subprocess.check_call(['git','-C',M,'sparse-checkout','set','shadow_hand']); subprocess.check_call(['git','-C',M,'checkout','-q',COMMIT])
p=os.path.join(M,'shadow_hand','')
x=open(p+'right_hand.xml').read()
x=x.replace('<body name="rh_forearm" childclass="right_hand" quat="0 1 0 1">','''<body name="arm" pos="0 0 0"><inertial pos="0 0 0" mass="1.0" diaginertia="0.01 0.01 0.01"/>
      <joint name="arm_x" type="slide" axis="1 0 0" damping="5" armature="0.5" range="-0.5 0.5"/><joint name="arm_y" type="slide" axis="0 1 0" damping="5" armature="0.5" range="-0.5 0.5"/><joint name="arm_z" type="slide" axis="0 0 1" damping="5" armature="0.5" range="-0.5 0.5"/>
      <joint name="arm_roll" type="hinge" axis="1 0 0" damping="1" armature="0.05" range="-3.2 3.2"/><joint name="arm_pitch" type="hinge" axis="0 1 0" damping="1" armature="0.05" range="-1.6 1.6"/><joint name="arm_yaw" type="hinge" axis="0 0 1" damping="1" armature="0.05" range="-1.6 1.6"/>
    <body name="rh_forearm" childclass="right_hand" quat="0 1 0 1">''',1)
assert x.count('</worldbody>')==1 and '<body name="arm"' in x
x=x.replace('</worldbody>','</body></worldbody>')
acts=''.join(f'<position name="rh_A_ARM{n.upper()}" joint="arm_{n}" kp="{kp}" kv="{kv}" ctrlrange="{lo} {hi}" forcerange="-{fr} {fr}"/>' for n,kp,kv,lo,hi,fr in [('x',20000,900,-0.5,0.5,200),('y',20000,900,-0.5,0.5,200),('z',20000,900,-0.5,0.5,200),('roll',600,40,-3.2,3.2,40),('pitch',600,40,-1.6,1.6,40),('yaw',600,40,-1.6,1.6,40)])
open(p+'right_hand_arm.xml','w').write(x.replace('</actuator>',acts+'</actuator>')); print('model ready at',p)
