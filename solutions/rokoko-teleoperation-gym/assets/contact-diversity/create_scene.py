#!/usr/bin/env python3
"""Deterministic Blender 5.2 editable training props: VISUAL vs proxy colliders.

Original synthetic geometry. It does NOT qualify real mass/friction or robotics.
Run headless with: blender --background --factory-startup --python create_scene.py
"""
import bpy
import math
import json
import random
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
SEED = 3262026
random.seed(SEED)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for c in list(bpy.data.collections):
    if c.name == "Collection" and not c.objects:
        bpy.data.collections.remove(c)

def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c

COL = {x: collection(x) for x in
       ("BENCH", "VISUAL_PROPS", "COLLISION_PROXY", "OBSTACLES",
        "CAMERAS", "LIGHTS", "ANNOTATION")}
def put(obj, group):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COL[group].objects.link(obj)
    return obj

def material(name, rgb, metal=0.0, rough=0.45):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    if p is not None:
        p.inputs["Base Color"].default_value = (*rgb,1)
        p.inputs["Metallic"].default_value = metal
        p.inputs["Roughness"].default_value = rough
    return m

mat_dark = material("graphite_anodized_aluminium", (.055,.075,.11), .7,.27)
mat_top = material("ceramic_training_surface", (.08,.13,.21), .18,.46)
mat_blue = material("skill_blue", (.08,.29,.69), .1,.28)
mat_teal = material("safe_path_teal", (.06,.62,.47), .2,.34)
mat_amber = material("fragile_amber", (.94,.44,.12), .05,.28)
mat_red = material("obstacle_red", (.72,.1,.13),.35,.3)
mat_proxy = material("proxy_colliders_gray",(.4,.4,.4),0,.95)
mat_text = material("type_white",(.79,.86,.95),0,.8)
COLLIDERS = []

def cube(name, location, dimensions, group, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = put(bpy.context.object, group)
    o.name = name
    o.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m = o.modifiers.new("manufacturing_edge_radius","BEVEL")
        m.width = bevel
        m.segments = 3
        normal = o.modifiers.new("weighted_normals","WEIGHTED_NORMAL")
    o.data.materials.append(mat)
    return o

def cylinder(name, location, radius, depth, group, mat, verts=48, bevel=0):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts,radius=radius,depth=depth,location=location)
    o = put(bpy.context.object, group)
    o.name = name
    o.data.materials.append(mat)
    if bevel:
        b=o.modifiers.new("soft_edge","BEVEL")
        b.width=bevel
        b.segments=3
        o.modifiers.new("weighted_normals","WEIGHTED_NORMAL")
    return o

def physics_proxy(key,kind,xyz,dims,mass,friction,material_name,group="COLLISION_PROXY"):
    if kind=="box":
        o=cube("C_"+key,xyz,dims,group,mat_proxy)
    elif kind=="cylinder":
        o=cylinder("C_"+key,xyz,dims[0],dims[1],group,mat_proxy,24)
    elif kind=="sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=dims[0],location=xyz)
        o=put(bpy.context.object,group)
        o.name="C_"+key
        o.data.materials.append(mat_proxy)
    else:
        raise ValueError("unsupported collision geometry")
    o["collider_id"] = key
    o["shape"] = kind
    o["synthetic_mass_kg"] = mass
    o["synthetic_friction_mu"] = friction
    o["units"] = "m"
    o["source_label"] = "SYNTHETIC_NOT_CALIBRATED"
    o.hide_render = True
    COLLIDERS.append(dict(id=key,type=kind,position_m=list(xyz),
                          dimensions_m=list(dims),mass_kg=mass,
                          friction_mu=friction, material_id=material_name,
                          source="SYNTHETIC_UNCALIBRATED"))

# Bench top Z=0; visually appealing but a collision proxy is a plain box.
cube("tabletop_visual",(0,0,-.021),(.80,.60,.042),"BENCH",mat_top,.012)
for y in (-.285,.285):
    cube("side_rail_"+str(y),(0,y,-.004),(.80,.012,.010),"BENCH",mat_dark,.002)
for x in (-.39,.39):
    cube("end_rail_"+str(x),(x,0,-.004),(.012,.58,.010),"BENCH",mat_dark,.002)
physics_proxy("table_surface","box",(0,0,-.021),(.8,.6,.042),0.0,.65,"synthetic_workbench")

# Cube
cube("cube_skill_object",(-.19,-.08,.05),(.10,.10,.10),"VISUAL_PROPS",mat_blue,.009)
physics_proxy("cube","box",(-.19,-.08,.05),(.10,.10,.10),.085,.37,"synthetic_polymer")

# Cup body and lip; visual is hollow, but deliberately label collision as convex cylinder
cylinder("mug_shell",(-.055,-.14,.038),.039,.076,"VISUAL_PROPS",mat_teal,64,.004)
cylinder("mug_outer_rim",(-.055,-.14,.078),.041,.005,"VISUAL_PROPS",mat_dark,64,.001)
# Hollow visual inset is cosmetic, not part of collision proxy
cylinder("mug_interior",(-.055,-.14,.080),.033,.003,"VISUAL_PROPS",mat_dark,64)
curve=bpy.data.curves.new("mug_handle_curve","CURVE")
curve.dimensions="3D"
curve.resolution_u=20
curve.bevel_depth=.005
curve.bevel_resolution=3
spline=curve.splines.new("BEZIER")
spline.bezier_points.add(3)
for b,co in zip(spline.bezier_points,[
    (-.014,-.14,.059),(.008,-.14,.073),(.018,-.14,.034),(-.014,-.14,.026)]):
    b.co=co
    b.handle_left_type="AUTO"
    b.handle_right_type="AUTO"
handle=bpy.data.objects.new("mug_handle_visual",curve)
COL["VISUAL_PROPS"].objects.link(handle)
curve.materials.append(mat_teal)
physics_proxy("mug_convex_body","cylinder",(-.055,-.14,.038),(.041,.076),.14,.38,"synthetic_ceramic")

# Thin fragile ring: visual torus but proxy deliberately conservative sphere.
bpy.ops.mesh.primitive_torus_add(major_segments=64,minor_segments=12,
     location=(.14,-.14,.035),major_radius=.043,minor_radius=.007)
ring=put(bpy.context.object,"VISUAL_PROPS")
ring.name="fragile_ring_visual"
ring.data.materials.append(mat_amber)
physics_proxy("fragile_ring_envelope","sphere",(.14,-.14,.055),(.051,),.035,.46,"synthetic_fragile_material")

# Removable obstacle pegs along controlled route; proxies are simple cylinders.
for i,(x,y) in enumerate(((.055,.015),(.13,.07),(.20,-.04)),start=1):
    cylinder("obstacle_peg_visual_"+str(i),(x,y,.037),.016,.074,"OBSTACLES",mat_red,32,.003)
    physics_proxy("obstacle_peg_"+str(i),"cylinder",(x,y,.037),(.016,.074),0.0,.62,
                  "synthetic_fixed_peg")
# Explicit approach lane rails and target marker
cube("blue_start_pad",(-.30,.16,.003),(.12,.11,.006),"BENCH",mat_blue,.006)
cube("teal_goal_pad",(.29,.16,.003),(.12,.11,.006),"BENCH",mat_teal,.006)
for y in (-.028,.028):
    cube("approach_rail_" + str(y),(-.07,y,.001),(.17,.005,.002),"BENCH",mat_amber,.001)

# Two physically distinct virtual pusher fingers = non-actuating stage prop.
for y in (-.011,.011):
    cube("pusher_finger_"+str(y),(-.30,y,.024),(.060,.012,.040),
         "VISUAL_PROPS",mat_dark,.003)

def text_label(body,location,size=.014):
    cv=bpy.data.curves.new("text_"+body,"FONT")
    cv.body=body
    cv.size=size
    cv.extrude=.0004
    ob=bpy.data.objects.new("label_"+body,cv)
    COL["ANNOTATION"].objects.link(ob)
    ob.location=location
    cv.materials.append(mat_text)
    return ob
text_label("START / TEACH",(-.36,.245,.010),.018)
text_label("OBJECT SKILL BENCH",(-.16,.25,.010),.022)
text_label("SAFE GOAL",(.22,.245,.010),.018)

def aim(obj,target):
    q=(Vector(target)-obj.location).to_track_quat("-Z","Y")
    obj.rotation_euler=q.to_euler()
def camera(name,at,target):
    cam=bpy.data.cameras.new(name)
    o=bpy.data.objects.new(name,cam)
    COL["CAMERAS"].objects.link(o)
    o.location=at
    aim(o,target)
    cam.type="PERSP"
    cam.lens=45
    return o
hero=camera("HERO_ISOMETRIC",(.90,-.90,.73),(0,0,0))
side=camera("SIDE_INSPECTION",(.0,-1.08,.31),(0,0,0))
for name,location,power,scale in (
    ("softbox_main",(.55,-.50,.95),180,1.3),
    ("softbox_rim",(-.55,.35,.82),125,1.1)):
    light=bpy.data.lights.new(name,"AREA")
    light.energy=power
    light.shape="DISK"
    light.size=scale
    o=bpy.data.objects.new(name,light)
    COL["LIGHTS"].objects.link(o)
    o.location=location
    aim(o,(0,0,0))
sc=bpy.context.scene
sc.render.engine="BLENDER_EEVEE"
sc.render.resolution_x=1024
sc.render.resolution_y=640
sc.render.resolution_percentage=100
sc.render.image_settings.file_format="PNG"
sc.render.film_transparent=False
sc.world.color=(.025,.035,.055)
sc.view_settings.exposure=-.30
sc.view_settings.view_transform="AgX"

# Render visual objects; proxy colliders never appear in final renders.
for coll in COL["COLLISION_PROXY"].objects:
    coll.hide_render=True
sc.camera=hero
sc.render.filepath=str(ROOT/"bench_hero.png")
bpy.ops.render.render(write_still=True)
sc.camera=side
sc.render.filepath=str(ROOT/"bench_side.png")
bpy.ops.render.render(write_still=True)

# Export separate visual and collision GLBs; selected/hidden state explicitly restored.
def export_glb(name,groups):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        select=bool(any(obj in COL[g].objects[:] for g in groups)) and obj.type=="MESH"
        obj.select_set(select)
        if select:
            obj.hide_render=False
    bpy.ops.export_scene.gltf(filepath=str(ROOT/name),export_format="GLB",
                               use_selection=True,export_apply=False,
                               export_extras=True)
    for coll in COL["COLLISION_PROXY"].objects:
        coll.hide_render=True
export_glb("bench_visual.glb",("BENCH","VISUAL_PROPS","OBSTACLES"))
export_glb("bench_collision_proxies.glb",("COLLISION_PROXY",))
sc.camera=hero
bpy.ops.object.select_all(action="DESELECT")
# Save .blend last, preserving editable meshes/proxy collections/cameras.
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"contact_diversity_bench.blend"))

# 24 non-rendered, seed-pinned challenge configurations; not 24 hardware trials.
variants=[]
for i in range(24):
    rng=random.Random(SEED+i)
    variants.append(dict(
      id="variant_%02d"%i, seed=SEED+i,
      cube_y_m=round(rng.uniform(-.17,.16),4),
      cup_yaw_deg=round(rng.uniform(-45,45),2),
      ring_x_m=round(rng.uniform(.08,.22),4),
      friction_mu=round(rng.uniform(.18,.75),3),
      hypothetical_camera_occlusion=round(rng.uniform(0,.3),3),
      planned_only=True))
(ROOT/"collision_manifest.json").write_text(json.dumps(dict(
    schema="rokoko.blender.contact.diversity.v1",
    units="meters",z_up=True,scene_seed=SEED,
    collision_proxies=COLLIDERS,
    note="Blender geometry is NOT a MuJoCo/JAX/Isaac trained collision model. No physics qualification or actual Rokoko hardware."),
    indent=2,sort_keys=True)+"\n")
(ROOT/"variants.json").write_text(json.dumps(variants,indent=2)+"\n")

def hashfile(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assets=["contact_diversity_bench.blend","bench_visual.glb",
        "bench_collision_proxies.glb","bench_hero.png","bench_side.png",
        "collision_manifest.json","variants.json"]
triangles=0
for ob in bpy.data.objects:
    if ob.type=="MESH":
        triangles += sum(max(1,len(face.vertices)-2) for face in ob.data.polygons)
receipt=dict(
    schema="rokoko.blender.render_receipt.v1",
    blender_version=bpy.app.version_string,
    source_file="create_scene.py",source_sha256=hashfile(ROOT/"create_scene.py"),
    seed=SEED,visual_triangles_approx_total=triangles,
    source_label="SYNTHETIC_GEOMETRY_NOT_CALIBRATED",
    rendered_angles=["HERO_ISOMETRIC","SIDE_INSPECTION"],
    files_sha256={name:hashfile(ROOT/name) for name in assets},
    consumer_mujoco_import="NOT_TESTED",
    blender_glb_export="EXECUTED",
    blender_glb_reimport="NOT_TESTED")
(ROOT/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
print("ROKOKO_BLENDER_CREATED",json.dumps(receipt,sort_keys=True))
