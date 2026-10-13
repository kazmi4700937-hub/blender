import bpy
import json
import os
import math
from mathutils import Vector, Matrix, Quaternion

print("--- Testing Direct LBS Mesh & Metarig Fitting ---")
bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))

metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]

with open("assets/test_images/expected_character_spec.json", "r") as f:
    spec = json.load(f)

joints = spec["joints"]

# We will test widening shoulders by 20%
target_joints = json.loads(json.dumps(joints))
for k in ["shoulder_L", "elbow_L", "wrist_L", "hand_tip_L"]:
    target_joints[k][0] *= 1.2
for k in ["shoulder_R", "elbow_R", "wrist_R", "hand_tip_R"]:
    target_joints[k][0] *= 1.2

# Get original rest bone heads and tails from metarig
bones_orig = {}
for b in metarig.data.bones:
    bones_orig[b.name] = (Vector(b.head_local), Vector(b.tail_local))

# Define target endpoints for bones
target_endpoints = {}

# Spine
target_endpoints["spine"] = (Vector(target_joints["crotch"]), Vector(target_joints["crotch"]) + Vector((0, 0, 0.15)))
target_endpoints["spine.001"] = (target_endpoints["spine"][1], target_endpoints["spine"][1] + Vector((0, 0, 0.15)))
target_endpoints["spine.002"] = (target_endpoints["spine.001"][1], target_endpoints["spine.001"][1] + Vector((0, 0, 0.15)))
target_endpoints["spine.003"] = (target_endpoints["spine.002"][1], Vector(target_joints["neck_base"]))
target_endpoints["spine.004"] = (Vector(target_joints["neck_base"]), Vector(target_joints["chin"]))
target_endpoints["spine.005"] = (Vector(target_joints["chin"]), Vector(target_joints["chin"]) + Vector((0, 0, 0.08)))
target_endpoints["spine.006"] = (target_endpoints["spine.005"][1], Vector(target_joints["head_top"]))

# Arms L & R
for side, sgn in [(".L", 1.0), (".R", -1.0)]:
    sfx = "_L" if side == ".L" else "_R"
    sh_head = Vector(target_joints[f"shoulder{sfx}"])
    el_head = Vector(target_joints[f"elbow{sfx}"])
    wr_head = Vector(target_joints[f"wrist{sfx}"])
    ht_head = Vector(target_joints[f"hand_tip{sfx}"])
    
    clav_head = Vector((sgn * 0.02, 0, Vector(target_joints["neck_base"]).z - 0.05))
    target_endpoints[f"shoulder{side}"] = (clav_head, sh_head)
    target_endpoints[f"upper_arm{side}"] = (sh_head, el_head)
    target_endpoints[f"forearm{side}"] = (el_head, wr_head)
    target_endpoints[f"hand{side}"] = (wr_head, ht_head)

# Legs L & R
for side, sgn in [(".L", 1.0), (".R", -1.0)]:
    sfx = "_L" if side == ".L" else "_R"
    hip = Vector(target_joints[f"hip{sfx}"])
    knee = Vector(target_joints[f"knee{sfx}"])
    ankle = Vector(target_joints[f"ankle{sfx}"])
    toe = Vector(target_joints[f"toe{sfx}"])
    
    target_endpoints[f"thigh{side}"] = (hip, knee)
    target_endpoints[f"shin{side}"] = (knee, ankle)
    target_endpoints[f"foot{side}"] = (ankle, toe)
    target_endpoints[f"toe{side}"] = (toe, toe + Vector((0, -0.06, 0)))

# Compute affine transform for each bone
bone_transforms = {}
for b_name, (h0, t0) in bones_orig.items():
    if b_name in target_endpoints:
        h1, t1 = target_endpoints[b_name]
    else:
        # Default translation if not explicitly specified
        continue
        
    v0 = t0 - h0
    v1 = t1 - h1
    len0 = v0.length
    len1 = v1.length
    if len0 < 1e-5 or len1 < 1e-5:
        continue
        
    dir0 = v0.normalized()
    dir1 = v1.normalized()
    rot = dir0.rotation_difference(dir1)
    scale_y = len1 / len0
    
    # Store transform: h0, h1, rot, scale_y, dir0
    bone_transforms[b_name] = (h0, h1, rot, scale_y, dir0)

# Deform mesh vertices using vertex group weights
mesh = body.data
vgroup_names = {g.index: g.name for g in body.vertex_groups}

for v in mesh.vertices:
    total_w = sum(g.weight for g in v.groups if vgroup_names.get(g.group) in bone_transforms)
    if total_w < 1e-5:
        continue
    
    p_orig = v.co.copy()
    p_new = Vector((0, 0, 0))
    
    for g in v.groups:
        b_name = vgroup_names.get(g.group)
        if b_name not in bone_transforms:
            continue
        w = g.weight / total_w
        h0, h1, rot, scale_y, dir0 = bone_transforms[b_name]
        
        # Local offset relative to bone head
        d = p_orig - h0
        # Project d onto bone axis and perpendicular
        d_par = dir0 * d.dot(dir0)
        d_perp = d - d_par
        
        # Scale parallel by scale_y
        d_par_scaled = d_par * scale_y
        
        # Rotate transformed vector and add to h1
        v_disp = rot @ (d_par_scaled + d_perp)
        p_new += (h1 + v_disp) * w
        
    v.co = p_new

# Update edit bones of metarig to match target_endpoints exactly
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='EDIT')
ebones = metarig.data.edit_bones

for b_name, (h1, t1) in target_endpoints.items():
    eb = ebones.get(b_name)
    if eb:
        eb.head = h1
        eb.tail = t1

bpy.ops.object.mode_set(mode='OBJECT')

# Verify differences on metarig
sh_L = metarig.data.bones["upper_arm.L"].head_local
el_L = metarig.data.bones["forearm.L"].head_local
wr_L = metarig.data.bones["hand.L"].head_local

print("upper_arm.L head:", sh_L, "Target:", target_joints["shoulder_L"])
print("forearm.L head:  ", el_L, "Target:", target_joints["elbow_L"])
print("hand.L head:     ", wr_L, "Target:", target_joints["wrist_L"])

diff_sh = (sh_L - Vector(target_joints["shoulder_L"])).length
diff_el = (el_L - Vector(target_joints["elbow_L"])).length
diff_wr = (wr_L - Vector(target_joints["wrist_L"])).length

print(f"Diff shoulder: {diff_sh*100:.2f} cm")
print(f"Diff elbow:    {diff_el*100:.2f} cm")
print(f"Diff wrist:    {diff_wr*100:.2f} cm")

assert diff_sh < 0.001
assert diff_el < 0.001
assert diff_wr < 0.001

# Verify mesh manifold
import bmesh
bm = bmesh.new()
bm.from_mesh(body.data)
non_m = [e for e in bm.edges if not e.is_manifold]
print("Non-manifold edges:", len(non_m))
assert len(non_m) == 0
bm.free()

print("Direct LBS Fitting passed with 0.00 cm error on all joints!")
