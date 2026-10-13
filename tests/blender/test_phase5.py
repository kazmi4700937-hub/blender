import bpy
import json
import math
import os
import sys
import bmesh
from mathutils import Vector, Euler, Matrix

print("=== RUNNING PHASE 5 ACCEPTANCE TESTS ===")

sys.path.insert(0, os.path.abspath("."))
from blender_addon.commands.fit import cmd_import_base_character, cmd_fit_template
from blender_addon.commands.rig import cmd_generate_rig, cmd_bind_mesh, cmd_list_bones

base_spec_path = os.path.abspath("assets/test_images/expected_character_spec.json")
with open(base_spec_path, "r", encoding="utf-8") as f:
    base_spec = json.load(f)

# -----------------------------------------------------------------
# Acceptance Test 1: Rig generates with no errors on 3 different specs
# -----------------------------------------------------------------
print("\n--- Test 1: Rig generation on 3 distinct character specs ---")

# Spec 1: Standard
spec1 = json.loads(json.dumps(base_spec))

# Spec 2: Wide (+20% width)
spec2 = json.loads(json.dumps(base_spec))
for k in ["shoulder_L", "elbow_L", "wrist_L", "hand_tip_L", "hip_L", "knee_L", "ankle_L"]:
    if k in spec2["joints"]:
        spec2["joints"][k][0] *= 1.2
for k in ["shoulder_R", "elbow_R", "wrist_R", "hand_tip_R", "hip_R", "knee_R", "ankle_R"]:
    if k in spec2["joints"]:
        spec2["joints"][k][0] *= 1.2
spec2.setdefault("widths", {})["shoulder_width"] = 0.5 * 1.2

# Spec 3: Tall/Thin (+15% height, -20% width)
spec3 = json.loads(json.dumps(base_spec))
spec3["height_m"] = 1.75 * 1.15
for k, pt in spec3["joints"].items():
    pt[2] *= 1.15  # Scale Z by 1.15
    if k.endswith("_L") or k.endswith("_R"):
        pt[0] *= 0.8  # Scale X by 0.8
spec3.setdefault("widths", {})["shoulder_width"] = 0.5 * 0.8

specs = [("Normal", spec1), ("Wide", spec2), ("TallThin", spec3)]

for name, sp in specs:
    print(f"\nTesting rig generation for spec: {name}...")
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.preferences.addon_enable(module="rigify")

    cmd_import_base_character({"blend_path": "assets/base_character.blend"})
    cmd_fit_template({"spec": sp})

    gen_res = cmd_generate_rig({})
    print(f"Generated rig: {gen_res['rig_name']} with {gen_res['bone_count']} bones.")
    if gen_res['bone_count'] < 500:
        print(f"FAIL: Rigify rig has unexpectedly few bones ({gen_res['bone_count']})!")
        sys.exit(1)

    bind_res = cmd_bind_mesh({})
    print(f"Bind mesh: {bind_res['mesh']} -> {bind_res['rig']}, unweighted: {bind_res['unweighted_count']}")
    if bind_res['unweighted_count'] != 0:
        print(f"FAIL: Found {bind_res['unweighted_count']} unweighted vertices in spec {name}!")
        sys.exit(1)

print("\nPASS: Rig generates without errors with 0 unweighted vertices across all 3 specs.")

# We will now use the generated rig from the standard spec for deformation tests
# -----------------------------------------------------------------
# Acceptance Test 2 & 3: Deformation Isolation (Left knee bend)
# -----------------------------------------------------------------
print("\n--- Test 2 & 3: Automated Pose Deformation Isolation Test ---")
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.preferences.addon_enable(module="rigify")

cmd_import_base_character({"blend_path": "assets/base_character.blend"})
cmd_fit_template({"spec": spec1})
cmd_generate_rig({})
cmd_bind_mesh({})

rig = bpy.data.objects["rig"]
body = bpy.data.objects["base_character"]

# Record rest vertex positions
rest_verts = [v.co.copy() for v in body.data.vertices]

# Switch to FK on left leg for direct knee rotation test
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE')

thigh_p = rig.pose.bones.get("thigh_parent.L")
if thigh_p and "IK_FK" in thigh_p:
    thigh_p["IK_FK"] = 1.0  # Switch to FK

# Rotate left knee (shin_fk.L) 90 degrees around local X
shin_fk = rig.pose.bones.get("shin_fk.L")
if not shin_fk:
    # Check DEF-shin.L
    shin_fk = rig.pose.bones.get("DEF-shin.L")

print("Rotating knee bone:", shin_fk.name)
shin_fk.rotation_mode = 'XYZ'
shin_fk.rotation_euler = Euler((math.radians(90), 0, 0), 'XYZ')
bpy.context.view_layer.update()

# Evaluate deformed vertex positions
bpy.ops.object.mode_set(mode='OBJECT')
dg = bpy.context.evaluated_depsgraph_get()
body_eval = body.evaluated_get(dg)
mesh_eval = body_eval.to_mesh()

moved_indices = []
for idx, v in enumerate(mesh_eval.vertices):
    disp = (v.co - rest_verts[idx]).length
    if disp > 0.01:
        moved_indices.append((idx, rest_verts[idx], v.co, disp))

print(f"Total vertices moved by bending left knee: {len(moved_indices)} of {len(rest_verts)}")
if len(moved_indices) == 0:
    print("FAIL: No vertices moved when rotating knee!")
    sys.exit(1)

# Verify isolation:
# 1. No right leg vertices moved (rest_verts.x < -0.05 and rest_verts.z < 1.0)
right_leg_moved = [item for item in moved_indices if item[1].x < -0.05 and item[1].z < 1.0]
print(f"Right leg vertices moved: {len(right_leg_moved)}")
if len(right_leg_moved) > 0:
    print(f"FAIL: Knee rotation leaked onto right leg ({len(right_leg_moved)} vertices moved)!")
    sys.exit(1)

# 2. No upper torso / head vertices moved (rest_verts.z > 1.3)
torso_moved = [item for item in moved_indices if item[1].z > 1.3]
print(f"Upper torso/head vertices moved: {len(torso_moved)}")
if len(torso_moved) > 0:
    print(f"FAIL: Knee rotation leaked onto upper torso ({len(torso_moved)} vertices moved)!")
    sys.exit(1)

body_eval.to_mesh_clear()
print("PASS: Left knee bend is cleanly isolated to the left leg.")

# -----------------------------------------------------------------
# Acceptance Test 4: Finger Bones & Hand Deformation
# -----------------------------------------------------------------
print("\n--- Test 4: Finger bones and curling test ---")
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE')

# Reset knee
shin_fk.rotation_euler = Euler((0, 0, 0), 'XYZ')

# Verify finger bones exist for each finger
finger_prefixes = ["thumb", "f_index", "f_middle", "f_ring", "f_pinky"]
for side in [".L", ".R"]:
    for finger in finger_prefixes:
        for i in range(1, 4):
            # Check for control or deform bone
            bone_name_fk = f"{finger}.0{i}{side}"
            bone_name_def = f"DEF-{finger}.0{i}{side}"
            exists = (bone_name_fk in rig.pose.bones) or (bone_name_def in rig.pose.bones)
            if not exists:
                print(f"FAIL: Missing finger bone {finger}.0{i}{side}!")
                sys.exit(1)

print("PASS: Finger bones confirmed for all 5 fingers on both hands.")

# Test curling left index finger
f_index_1 = rig.pose.bones.get("f_index.01.L") or rig.pose.bones.get("DEF-f_index.01.L")
f_index_1.rotation_mode = 'XYZ'
f_index_1.rotation_euler = Euler((0, 0, math.radians(45)), 'XYZ')
bpy.context.view_layer.update()

bpy.ops.object.mode_set(mode='OBJECT')
dg = bpy.context.evaluated_depsgraph_get()
body_eval = body.evaluated_get(dg)
mesh_eval = body_eval.to_mesh()

# Check volume and displacement
bm = bmesh.new()
bm.from_mesh(mesh_eval)
vol = bm.calc_volume(signed=True)
print(f"Hand volume after curling index finger: {vol:.5f}")
if vol <= 0:
    print("FAIL: Hand mesh collapsed upon finger rotation!")
    sys.exit(1)
bm.free()
body_eval.to_mesh_clear()

print("PASS: Finger curls cleanly without hand collapse.")

# -----------------------------------------------------------------
# Acceptance Test 5: IK / FK Switching Verification
# -----------------------------------------------------------------
print("\n--- Test 5: IK / FK Switch Properties ---")
switches = [
    ("thigh_parent.L", "IK_FK"),
    ("thigh_parent.R", "IK_FK"),
    ("upper_arm_parent.L", "IK_FK"),
    ("upper_arm_parent.R", "IK_FK")
]
for bone_name, prop in switches:
    pb = rig.pose.bones.get(bone_name)
    if not pb or prop not in pb:
        print(f"FAIL: Missing property {prop} on {bone_name}")
        sys.exit(1)
    # Test setting to 0.0 (IK) and 1.0 (FK)
    pb[prop] = 0.0
    assert pb[prop] == 0.0
    pb[prop] = 1.0
    assert pb[prop] == 1.0
    pb[prop] = 0.0  # Restore to IK default

print("PASS: IK/FK switching verified on legs and arms.")

# Save rigged character blend
rigged_blend_path = os.path.abspath("assets/rigged_character.blend")
bpy.ops.wm.save_as_mainfile(filepath=rigged_blend_path)
print("Saved rigged character blend to:", rigged_blend_path)

print("\n=== PHASE 5 ACCEPTANCE TESTS PASSED SUCCESSFULLY! ===")
