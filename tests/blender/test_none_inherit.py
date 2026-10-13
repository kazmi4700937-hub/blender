import bpy
import json
import os
from mathutils import Vector, Matrix

print("--- Testing Fit with inherit_scale = 'NONE' ---")
bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))
metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]

with open("assets/test_images/expected_character_spec.json", "r") as f:
    spec = json.load(f)

joints = spec["joints"]

# Disable inherit scale on all bones
for b in metarig.data.bones:
    b.inherit_scale = 'NONE'

# Enter pose mode
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')

def set_bone(b_name, head_pt, tail_pt):
    pb = metarig.pose.bones[b_name]
    ref = metarig.data.bones[b_name].matrix_local
    rest_len = metarig.data.bones[b_name].length
    v = tail_pt - head_pt
    sy = v.length / rest_len if rest_len > 1e-4 else 1.0
    y_dir = v.normalized()
    ref_y = ref.to_3x3().col[1].normalized()
    rot = ref_y.rotation_difference(y_dir)
    x_dir = (rot @ ref.to_3x3().col[0]).normalized()
    z_dir = (rot @ ref.to_3x3().col[2]).normalized()

    mat = Matrix.Identity(4)
    mat.col[0] = x_dir.to_4d()
    mat.col[1] = y_dir.to_4d() * sy
    mat.col[2] = z_dir.to_4d()
    mat.col[3] = head_pt.to_4d()
    mat[3][3] = 1.0
    pb.matrix = mat
    bpy.context.view_layer.update()

# Set upper_arm.L and forearm.L
sh_head = Vector(joints["shoulder_L"])
el_head = Vector(joints["elbow_L"])
wr_head = Vector(joints["wrist_L"])

set_bone("upper_arm.L", sh_head, el_head)
set_bone("forearm.L", el_head, wr_head)

print("After posing:")
print("pb upper_arm.L head:", metarig.pose.bones["upper_arm.L"].head, "tail:", metarig.pose.bones["upper_arm.L"].tail)
print("pb forearm.L head:  ", metarig.pose.bones["forearm.L"].head, "tail:", metarig.pose.bones["forearm.L"].tail)

# Apply pose as rest pose
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode='OBJECT')

print("\nAfter armature_apply:")
bones = metarig.data.bones
print("upper_arm.L head:", bones["upper_arm.L"].head_local, "tail:", bones["upper_arm.L"].tail_local)
print("forearm.L head:  ", bones["forearm.L"].head_local, "tail:", bones["forearm.L"].tail_local)
