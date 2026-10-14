"""Phase 9c acceptance test: rig a mesh that is NOT the template body.

The test makes a character mesh with different proportions (tall and thin), exports it as .glb
with no vertex groups and no armature (so it is just a shape, like a generated model), imports it
back through the generated-mesh importer, and then places and generates a Rigify rig on it from a
character spec. It also checks that joints can be read from a Mixamo style skeleton.

Run with:  blender -b --python tests/blender/test_phase9c.py
"""

import json
import math
import os
import sys
import tempfile

import bpy
from mathutils import Euler, Vector

print("=== RUNNING PHASE 9C ACCEPTANCE TESTS ===")

sys.path.insert(0, os.path.abspath("."))
from blender_addon.commands.fit import cmd_import_base_character, cmd_fit_template
from blender_addon.commands.geometry import cmd_import_generated_mesh
from blender_addon.commands.fit_mesh import cmd_rig_generated_mesh
from blender_addon.commands.skeleton import cmd_skeleton_to_spec

TMP = tempfile.mkdtemp(prefix="phase9c_")


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def check(cond, msg):
    if not cond:
        fail(msg)
    print("PASS:", msg)


def fresh():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.preferences.addon_enable(module="rigify")


with open(os.path.abspath("assets/test_images/expected_character_spec.json"), "r", encoding="utf-8") as f:
    base_spec = json.load(f)

# A tall, thin character: not the template's proportions.
spec = json.loads(json.dumps(base_spec))
for name, pt in spec["joints"].items():
    pt[2] *= 1.15
    if name.endswith("_L") or name.endswith("_R"):
        pt[0] *= 0.8
spec["height_m"] = spec["joints"]["head_top"][2]

# -------------------------------------------------------------
print("\n--- Test 1: joints are read from a Mixamo style skeleton ---")


def build_mixamo_armature(src_spec, swap_sides=False, prefix="mixamorig:"):
    j = {k: Vector(v) for k, v in src_spec["joints"].items()}
    if swap_sides:   # a skeleton built with its Left on the -X side
        for base in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle", "toe", "hand_tip"):
            j[base + "_L"], j[base + "_R"] = j[base + "_R"], j[base + "_L"]
    arm_data = bpy.data.armatures.new("Skel")
    arm = bpy.data.objects.new("Skel", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")

    def add(name, head, tail):
        eb = arm_data.edit_bones.new(prefix + name)
        eb.head, eb.tail = head, tail

    off = Vector((0, 0, 0.02))
    add("Hips", j["crotch"], j["neck_base"])
    add("Neck", j["neck_base"], j["chin"])
    add("Head", j["chin"], j["head_top"])
    add("HeadTop_End", j["head_top"], j["head_top"] + off)
    for side, sgn in (("L", "Left"), ("R", "Right")):
        add(f"{sgn}Arm", j[f"shoulder_{side}"], j[f"elbow_{side}"])
        add(f"{sgn}ForeArm", j[f"elbow_{side}"], j[f"wrist_{side}"])
        add(f"{sgn}Hand", j[f"wrist_{side}"], j[f"hand_tip_{side}"])
        add(f"{sgn}HandMiddle4", j[f"hand_tip_{side}"], j[f"hand_tip_{side}"] + off)
        add(f"{sgn}UpLeg", j[f"hip_{side}"], j[f"knee_{side}"])
        add(f"{sgn}Leg", j[f"knee_{side}"], j[f"ankle_{side}"])
        add(f"{sgn}Foot", j[f"ankle_{side}"], j[f"toe_{side}"])
        add(f"{sgn}ToeBase", j[f"toe_{side}"], j[f"toe_{side}"] + Vector((0, -0.05, 0)))
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def max_joint_error(a, b):
    return max((Vector(a[k]) - Vector(b[k])).length for k in a if k in b)


fresh()
build_mixamo_armature(spec)
res = cmd_skeleton_to_spec({})
err = max_joint_error(res["joints"], spec["joints"])
check(err < 1e-3, f"every joint is recovered within 1 mm (worst {err * 1000:.3f} mm)")
check(abs(res["height_m"] - spec["height_m"]) < 1e-3, "height comes from the head-top bone")

fresh()
build_mixamo_armature(spec, swap_sides=True)
res = cmd_skeleton_to_spec({})
err = max_joint_error(res["joints"], spec["joints"])
check(err < 1e-3 and res["warnings"], f"a skeleton with left and right swapped is corrected and reported (worst {err * 1000:.3f} mm)")

fresh()
build_mixamo_armature(spec, prefix="")
check(max_joint_error(cmd_skeleton_to_spec({})["joints"], spec["joints"]) < 1e-3, "names without the mixamorig prefix also work")

fresh()
arm_data = bpy.data.armatures.new("Odd")
odd = bpy.data.objects.new("Odd", arm_data)
bpy.context.scene.collection.objects.link(odd)
bpy.context.view_layer.objects.active = odd
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones.new("root")
eb.head, eb.tail = (0, 0, 0), (0, 0, 1)
bpy.ops.object.mode_set(mode="OBJECT")
try:
    cmd_skeleton_to_spec({})
    fail("a skeleton with unknown names was accepted")
except ValueError as e:
    check("Mixamo" in str(e) and "Missing" in str(e), "unknown bone names are refused, and the missing names are listed")

# -------------------------------------------------------------
print("\n--- Test 2: a generated mesh with different proportions is rigged ---")
fresh()
cmd_import_base_character({"blend_path": "assets/base_character.blend"})
cmd_fit_template({"spec": spec})
body = bpy.data.objects["base_character"]
body.vertex_groups.clear()
for mod in list(body.modifiers):
    body.modifiers.remove(mod)
bpy.data.objects.remove(bpy.data.objects["metarig"], do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.context.view_layer.objects.active = body
glb = os.path.join(TMP, "tall_thin.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True)

fresh()
imp = cmd_import_generated_mesh({"path": glb, "target_height_m": spec["height_m"]})
mesh_name = imp["mesh_objects"][0]
print("Imported:", mesh_name, "vertices", imp["vertices"], "height", imp["height_m"])
check(len(bpy.data.objects[mesh_name].vertex_groups) == 0, "the imported mesh has no vertex groups (it is just a shape)")

res = cmd_rig_generated_mesh({"mesh_name": mesh_name, "spec": spec})
for w in res["warnings"]:
    print("  warning:", w)
check(res["bone_count"] >= 500, f"a full Rigify rig was generated ({res['bone_count']} bones)")
check(res["unweighted_count"] == 0, "every vertex has a weight")
empty = [n for n, c in res["key_bone_vertex_counts"].items() if c < 3]
check(not empty, f"every key deform bone controls vertices (smallest: {min(res['key_bone_vertex_counts'].values())})")
check(res["bones_following_an_ancestor"] > 50, f"{res['bones_following_an_ancestor']} bones without a joint of their own followed their parent")

metarig = bpy.data.objects["metarig"]
sh = Vector(res["joints_used"]["shoulder_L"])
head = metarig.data.bones["upper_arm.L"].head_local
check((head - sh).length < 1e-3, "the upper arm bone starts at the shoulder joint")
tip = Vector(spec["joints"]["hand_tip_L"])
finger_end = metarig.data.bones["f_middle.03.L"].tail_local
check((finger_end - tip).length < 0.12, f"finger bones follow the hand ({(finger_end - tip).length * 100:.1f} cm from the hand tip)")
check(all(abs(a - b) < 0.03 for a, b in zip(res["joints_used"]["knee_L"][:1] + res["joints_used"]["knee_L"][2:],
                                            spec["joints"]["knee_L"][:1] + spec["joints"]["knee_L"][2:])),
      "refining the depth did not move a joint sideways or up and down")

# Deformation isolation: bend the left knee and see what moves.
rig = bpy.data.objects[res["rig"]]
body = bpy.data.objects[mesh_name]
rest = [v.co.copy() for v in body.data.vertices]
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
thigh_p = rig.pose.bones.get("thigh_parent.L")
if thigh_p and "IK_FK" in thigh_p:
    thigh_p["IK_FK"] = 1.0
shin = rig.pose.bones.get("shin_fk.L") or rig.pose.bones.get("DEF-shin.L")
shin.rotation_mode = "XYZ"
shin.rotation_euler = Euler((math.radians(90), 0, 0), "XYZ")
bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode="OBJECT")
mesh_eval = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
moved = [(i, rest[i]) for i, v in enumerate(mesh_eval.vertices) if (v.co - rest[i]).length > 0.01]
hip_z = spec["joints"]["hip_L"][2]
right_leg = [m for m in moved if m[1].x < -0.05 and m[1].z < hip_z]
torso = [m for m in moved if m[1].z > spec["height_m"] * 0.66]
print(f"  bending the left knee moved {len(moved)} of {len(rest)} vertices")
check(len(moved) > 20, "bending the left knee moves the left leg")
check(len(right_leg) == 0, "no right leg vertex moved")
check(len(torso) == 0, "no torso or head vertex moved")

print("\n--- Test 3: bad input is refused with a readable error ---")
for params, text in (({"mesh_name": "nothing", "spec": spec}, "not found"),
                     ({"mesh_name": mesh_name}, "spec")):
    try:
        cmd_rig_generated_mesh(params)
        fail(f"{params.keys()} was accepted")
    except ValueError as e:
        check(text in str(e), f"refused: {e}")

print("\n=== ACCEPTANCE TESTS PASSED ===")
