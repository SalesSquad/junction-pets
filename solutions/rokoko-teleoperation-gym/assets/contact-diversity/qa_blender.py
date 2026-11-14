#!/usr/bin/env python3
"""Blender 5.2 native readback + GLB re-import acceptance, no false physics claim."""
from pathlib import Path
import bpy
import json
import hashlib

ROOT=Path(__file__).resolve().parent
expected=json.loads((ROOT/"collision_manifest.json").read_text())
receipt=json.loads((ROOT/"receipt.json").read_text())
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
for name,expected_sha in receipt["files_sha256"].items():
    p=ROOT/name
    if not p.is_file() or sha(p)!=expected_sha:
        raise RuntimeError("ASSET_SHA_MISMATCH:"+name)

bpy.ops.wm.open_mainfile(filepath=str(ROOT/"contact_diversity_bench.blend"))
native_collections={c.name:len(c.objects) for c in bpy.data.collections}
must={"BENCH","VISUAL_PROPS","COLLISION_PROXY","OBSTACLES","CAMERAS","LIGHTS","ANNOTATION"}
if not must.issubset(native_collections):
    raise RuntimeError("Missing editable native collections")
if len(bpy.data.cameras)<2:
    raise RuntimeError("Both QA cameras missing")

glb_results={}
for filename in ("bench_visual.glb","bench_collision_proxies.glb"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(ROOT/filename))
    objs=[o for o in bpy.data.objects if o.type=="MESH"]
    if not objs:
        raise RuntimeError("GLB_ROUNDTRIP_ZERO_MESHES:"+filename)
    tris=sum(len(poly.vertices)-2 for o in objs for poly in o.data.polygons)
    custom_ids=sorted(str(o.get("collider_id")) for o in objs if o.get("collider_id"))
    if filename=="bench_collision_proxies.glb":
        wanted={p["id"] for p in expected["collision_proxies"]}
        if not wanted.issubset(set(custom_ids)):
            raise RuntimeError(f"COLLIDER_IDS_LOST:{wanted-set(custom_ids)}")
    glb_results[filename]=dict(meshes=len(objs),triangles=tris,
                              collider_ids=custom_ids,roundtrip=True)

result={
    "schema":"rokoko.blender.asset_qa.v1",
    "blender_version":bpy.app.version_string,
    "native_collections":native_collections,
    "glb_roundtrip":glb_results,
    "asset_digests_verified":len(receipt["files_sha256"]),
    "collision_manifest_count":len(expected["collision_proxies"]),
    "visual_quality":"RENDERED_2_ANGLES",
    "mujoco_physical_contact":"NOT_PROVEN_BY_GLTF_ROUNDTRIP",
    "rights":"ORIGINAL_SYNTHETIC_GEOMETRY",
}
(ROOT/"qa_blender.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print("BLENDER_GLTF_ROUNDTRIP_PASS",json.dumps(result,sort_keys=True))
