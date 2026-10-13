import bpy
import json
import math
import os
import sys
import bmesh
from mathutils import Vector

print("=== RUNNING PHASE 4 ACCEPTANCE TESTS ===")

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath("."))
from blender_addon.commands.fit import cmd_import_base_character, cmd_fit_template

spec_file = os.path.abspath("assets/test_images/expected_character_spec.json")
with open(spec_file, "r", encoding="utf-8") as f:
    orig_spec = json.load(f)

# -------------------------------------------------------------
# Test 1: Round-trip test (fitting template to its own spec)
# -------------------------------------------------------------
print("\n--- Test 1: Round-trip test to own spec ---")
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.preferences.addon_enable(module="rigify")

cmd_import_base_character({"blend_path": "assets/base_character.blend"})
res = cmd_fit_template({"spec": orig_spec})
print("Fit template result:", res)

metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]

bones = metarig.data.bones
joints = orig_spec["joints"]

check_pairs = [
    ("upper_arm.L", "shoulder_L"),
    ("forearm.L", "elbow_L"),
    ("hand.L", "wrist_L"),
    ("thigh.L", "hip_L"),
    ("shin.L", "knee_L"),
    ("foot.L", "ankle_L")
]

for b_name, j_name in check_pairs:
    b_head = bones[b_name].head_local
    j_pos = Vector(joints[j_name])
    diff = (b_head - j_pos).length
    print(f"Bone {b_name} head vs {j_name}: diff = {diff*100:.2f} cm")
    if diff > 0.01:
        print(f"FAIL: Difference {diff*100:.2f} cm exceeds 1 cm for {b_name}!")
        sys.exit(1)

print("PASS: Round-trip joint positions match own spec within 1 cm.")

# -------------------------------------------------------------
# Test 2: Fitting to 20% wider shoulders
# -------------------------------------------------------------
print("\n--- Test 2: Fitting with 20% wider shoulders ---")
wide_spec = json.loads(json.dumps(orig_spec))

# Widen shoulders and arms by 20%
for key in ["shoulder_L", "elbow_L", "wrist_L", "hand_tip_L"]:
    if key in wide_spec["joints"]:
        wide_spec["joints"][key][0] *= 1.2
for key in ["shoulder_R", "elbow_R", "wrist_R", "hand_tip_R"]:
    if key in wide_spec["joints"]:
        wide_spec["joints"][key][0] *= 1.2

wide_spec.setdefault("widths", {})["shoulder_width"] = 0.42 * 1.2

bpy.ops.wm.read_homefile(use_empty=True)
cmd_import_base_character({"blend_path": "assets/base_character.blend"})
cmd_fit_template({"spec": wide_spec})

metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]
bones = metarig.data.bones

sh_L_head = bones["upper_arm.L"].head_local
sh_R_head = bones["upper_arm.R"].head_local
sh_width_fitted = (sh_L_head - sh_R_head).length
orig_sh_width = (Vector(orig_spec["joints"]["shoulder_L"]) - Vector(orig_spec["joints"]["shoulder_R"])).length

print(f"Fitted shoulder width: {sh_width_fitted:.4f}m vs original: {orig_sh_width:.4f}m")
expected_sh_width = orig_sh_width * 1.2
diff_sh = abs(sh_width_fitted - expected_sh_width)
if diff_sh > 0.015:
    print(f"FAIL: Shoulder width {sh_width_fitted:.4f} does not match expected {expected_sh_width:.4f}")
    sys.exit(1)

print("PASS: 20% wider shoulders confirmed on rig.")

# -------------------------------------------------------------
# Test 3: Symmetry check (all joint positions symmetric about X=0 within 1cm)
# -------------------------------------------------------------
print("\n--- Test 3: Symmetry check ---")
sym_pairs = [
    ("upper_arm.L", "upper_arm.R"),
    ("forearm.L", "forearm.R"),
    ("hand.L", "hand.R"),
    ("thigh.L", "thigh.R"),
    ("shin.L", "shin.R"),
    ("foot.L", "foot.R")
]

for b_l, b_r in sym_pairs:
    hl = bones[b_l].head_local
    hr = bones[b_r].head_local
    x_asym = abs(hl.x + hr.x)
    z_asym = abs(hl.z - hr.z)
    print(f"Pair {b_l} / {b_r}: X asymmetry = {x_asym*100:.2f} cm, Z asymmetry = {z_asym*100:.2f} cm")
    if x_asym > 0.01:
        print(f"FAIL: X asymmetry {x_asym*100:.2f} cm exceeds 1 cm for {b_l}/{b_r}")
        sys.exit(1)
    if z_asym > 0.01:
        print(f"FAIL: Z asymmetry {z_asym*100:.2f} cm exceeds 1 cm for {b_l}/{b_r}")
        sys.exit(1)

print("PASS: All joint positions are symmetric about X = 0 within 1 cm.")

# -------------------------------------------------------------
# Test 4: Mesh manifold and outward normals check
# -------------------------------------------------------------
print("\n--- Test 4: Mesh manifold and normals check ---")
bm = bmesh.new()
bm.from_mesh(body.data)

non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
print("Non-manifold edges count:", len(non_manifold_edges))
if len(non_manifold_edges) > 0:
    print(f"FAIL: Mesh has {len(non_manifold_edges)} non-manifold edges!")
    sys.exit(1)

# Check for zero or negative area faces (inverted or collapsed)
collapsed_faces = [f for f in bm.faces if f.calc_area() <= 1e-6]
print("Collapsed/degenerate faces count:", len(collapsed_faces))
if len(collapsed_faces) > 0:
    print(f"FAIL: Mesh has {len(collapsed_faces)} degenerate faces!")
    sys.exit(1)

# Outward normals and watertight geometry check via signed volume
volume = bm.calc_volume(signed=True)
print("Mesh signed volume:", volume)
if volume <= 0:
    print(f"FAIL: Inverted normals! Signed volume is {volume} <= 0")
    sys.exit(1)

bm.free()
print("PASS: Mesh is manifold with zero non-manifold edges and outward-facing normals.")

# Save fitted character blend file
fitted_blend_path = os.path.abspath("assets/fitted_character.blend")
bpy.ops.wm.save_as_mainfile(filepath=fitted_blend_path)
print("Saved fitted character blend to:", fitted_blend_path)

print("\n=== PHASE 4 ACCEPTANCE TESTS PASSED SUCCESSFULLY! ===")
