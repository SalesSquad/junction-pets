"""Actual contact, determinism, and deliberately damaging impact: no graphics."""
import json
from pathlib import Path
import mujoco as mj
import numpy as np
from experiment import HERE, DT, IMPULSE_LIMIT, run


def main():
    a = run(104, 'object_centered', False, [0,0.5,1])
    b = run(104, 'object_centered', False, [0,0.5,1])
    assert a == b, 'Same-source fixed-seed determinism failure'
    assert a['pusher_object_contact_steps'] > 0 and a['max_step_impulse_ns'] > 0
    m = mj.MjModel.from_xml_path(str(HERE/'scene.xml'))
    d = mj.MjData(m)
    # Deliberate negative test: violent pusher impact must trip the fragility proxy.
    d.qvel[6] = 2.0
    d.ctrl[:] = [0.2,0]
    og = mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'object_geom')
    pg = mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'pusher_geom')
    force = np.zeros(6)
    peak = 0.0
    for _ in range(200):
        mj.mj_step(m,d)
        for c in range(d.ncon):
            if {d.contact[c].geom1,d.contact[c].geom2} == {og,pg}:
                mj.mj_contactForce(m,d,c,force)
                peak = max(peak,float(np.linalg.norm(force[:3]))*DT)
    assert peak > IMPULSE_LIMIT, 'Negative impact did not trip fragility threshold'
    print(json.dumps(dict(source_kind='SYNTHETIC_MUJOCO',determinism='PASS',
                         contact_steps=a['pusher_object_contact_steps'],
                         max_step_impulse_ns=a['max_step_impulse_ns'],
                         negative_impact_ns=peak,fragility_threshold_ns=IMPULSE_LIMIT)))


if __name__ == '__main__':
    main()
