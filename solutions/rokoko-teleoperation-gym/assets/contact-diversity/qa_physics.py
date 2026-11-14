#!/usr/bin/env python3
"""Generate exact primitive MuJoCo proxy scene and verify gravity/contact.

Only low-dimensional primitive proxies are physically checked; Blender mesh
collisions, glove dynamics, fragile material damage, and real robots NOT tested.
"""
import math
import json
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import mujoco

ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/"collision_manifest.json").read_text())
pieces=manifest["collision_proxies"]
if manifest["units"]!="meters" or not manifest["z_up"]:
    raise RuntimeError("Wrong unit/coordinate convention")
ids=[p["id"] for p in pieces]
if len(ids)!=len(set(ids)) or len(ids)<7:
    raise RuntimeError("Duplicate/missing primitive collider IDs")
def f(values):
    return " ".join(f"{v:.6g}" for v in values)

model=ET.Element("mujoco",{"model":"rokoko_contact_diversity_primitive_proxies"})
ET.SubElement(model,"option",{"timestep":"0.002","gravity":"0 0 -9.81"})
world=ET.SubElement(model,"worldbody")
move=[]
for item in pieces:
    key=item["id"]
    shape=item["type"]
    xyz=item["position_m"]
    dims=item["dimensions_m"]
    mu=item["friction_mu"]
    mass=item["mass_kg"]
    if not all(math.isfinite(x) for x in [*xyz,*dims,mu,mass]):
        raise RuntimeError("Non-finite physics parameters")
    if shape=="box":
        sizes=[v/2 for v in dims]
    elif shape=="cylinder":
        sizes=[dims[0],dims[1]/2]
    elif shape=="sphere":
        sizes=[dims[0]]
    else:
        raise RuntimeError("Unknown physics shape")
    if mass<=0:
        ET.SubElement(world,"geom",{
            "name":"static_"+key,"type":shape,
            "pos":f(xyz),"size":f(sizes),
            "friction":f([mu,.02,.001]),"rgba":".8 .2 .2 1"})
    else:
        # Initial +4mm drop is a QA perturbation, not a manifest mutation.
        body=ET.SubElement(world,"body",{
            "name":key, "pos":f([xyz[0],xyz[1],xyz[2]+.004])})
        ET.SubElement(body,"freejoint")
        ET.SubElement(body,"geom",{
            "name":"geom_"+key,"type":shape,
            "size":f(sizes),"mass":str(mass),
            "friction":f([mu,.02,.001]),"rgba":".2 .6 .8 1"})
        move.append(key)
if set(move)!={"cube","mug_convex_body","fragile_ring_envelope"}:
    raise RuntimeError("Dynamic scene does not have expected three props")
# Save reusable synthetic MJCF bridge, not an asserted GLB physics conversion.
mjcf=ET.tostring(model,encoding="unicode")
(ROOT/"bench_primitive_proxies.xml").write_text(mjcf+"\n")
m=mujoco.MjModel.from_xml_string(mjcf)
d=mujoco.MjData(m)
ncontacts=0
for i in range(450):
    mujoco.mj_step(m,d)
    ncontacts+=d.ncon
    if not all(math.isfinite(x) for x in d.qpos):
        raise RuntimeError("DIVERGED_AT_STEP_"+str(i))
poses={}
for key in move:
    idx=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,key)
    xyz=list(map(float,d.xpos[idx]))
    poses[key]=xyz
    if not (0.0<=xyz[2]<=0.3):
        raise RuntimeError(f"Dynamic prop escaped table z: {key} {xyz}")
    if not (-.4<=xyz[0]<=.4 and -.3<=xyz[1]<=.3):
        raise RuntimeError("Dynamic prop escaped tabletop XY")
if ncontacts<3:
    raise RuntimeError("No actual native MuJoCo contacts")
report={
 "schema":"rokoko.blender.mujoco-proxy-smoke.v1",
 "mujoco_version":mujoco.__version__,
 "physics_steps":450,
 "timestep_s":float(m.opt.timestep),
 "dynamic_objects":move,
 "cumulative_contacts":ncontacts,
 "rest_positions_xyz_m":poses,
 "checked_source_sha256":hashlib.sha256(
    (ROOT/"collision_manifest.json").read_bytes()).hexdigest(),
 "mjcf_sha256":hashlib.sha256(
    (ROOT/"bench_primitive_proxies.xml").read_bytes()).hexdigest(),
 "scope":"ONLY_PRIMITIVE_SYNTHETIC_COLLISION_PROXIES",
 "actual_mesh_import_to_mujoco":"NOT_TESTED",
 "physical_calibration":"NOT_TESTED",
}
(ROOT/"qa_physics.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print("REAL_MUJOCO_PRIMITIVE_PROXY_QA_PASS",json.dumps(report,sort_keys=True))
