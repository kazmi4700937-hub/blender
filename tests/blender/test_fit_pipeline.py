import bpy
import json
import math
from typing import Tuple
from mathutils import Vector, Matrix, Quaternion
import os
import sys

def build_bone_matrix(head: Vector, tail: Vector, ref_matrix: Matrix, scale_cross: Tuple[float, float] = (1.0, 1.0)) -> Matrix:
    """
    Constructs a 4x4 matrix for a bone spanning from head to tail,
    preserving roll / orientation from ref_matrix, and applying non-uniform scale.
    """
    v_target = tail - head
    len_target = v_target.length
    if len_target < 1e-5:
        len_target = 0.01
        v_target = Vector((0, 1, 0)) * len_target
        
    y_axis = v_target.normalized()
    
    # Extract reference orientation
    ref_y = ref_matrix.to_3x3().col[1].normalized()
    ref_x = ref_matrix.to_3x3().col[0].normalized()
    ref_z = ref_matrix.to_3x3().col[2].normalized()
    
    # Compute rotation from ref_y to y_axis
    rot_q = ref_y.rotation_difference(y_axis)
    new_x = (rot_q @ ref_x).normalized()
    new_z = (rot_q @ ref_z).normalized()
    
    # Re-orthogonalize
    new_z = new_x.cross(y_axis).normalized()
    new_x = y_axis.cross(new_z).normalized()
    
    sx, sz = scale_cross
    sy = len_target
    
    mat = Matrix.Identity(4)
    mat.col[0] = new_x.to_4d() * sx
    mat.col[1] = y_axis.to_4d() * sy
    mat.col[2] = new_z.to_4d() * sz
    mat.col[3] = head.to_4d()
    mat[3][3] = 1.0
    return mat

print("--- Testing Full Template Fitting Pipeline ---")
blend_path = os.path.abspath("assets/base_character.blend")
spec_path = os.path.abspath("assets/test_images/expected_character_spec.json")

bpy.ops.wm.open_mainfile(filepath=blend_path)
bpy.ops.preferences.addon_enable(module="rigify")

metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]

with open(spec_path, "r", encoding="utf-8") as f:
    spec = json.load(f)

joints = spec["joints"]

# We will test widening shoulders by 20%
target_sh_L = Vector(joints["shoulder_L"])
target_sh_R = Vector(joints["shoulder_R"])
target_el_L = Vector(joints["elbow_L"])
target_el_R = Vector(joints["elbow_R"])
target_wr_L = Vector(joints["wrist_L"])
target_wr_R = Vector(joints["wrist_R"])

# Widen shoulders by 20%
target_sh_L.x *= 1.2
target_sh_R.x *= 1.2
target_el_L.x *= 1.2
target_el_R.x *= 1.2
target_wr_L.x *= 1.2
target_wr_R.x *= 1.2

bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')

# Helper to place a bone
def fit_bone(b_name, h, t):
    pb = metarig.pose.bones.get(b_name)
    if not pb:
        return
    ref = metarig.data.bones[b_name].matrix_local
    # In rest pose, rest length:
    rest_len = metarig.data.bones[b_name].length
    v = t - h
    target_len = v.length
    sy = target_len / rest_len if rest_len > 1e-5 else 1.0
    
    # We can also set location, rotation, scale
    # To place pb such that pb.head == h and pb.tail == t:
    # pb.matrix = build_bone_matrix(h, t, ref, scale_cross=(1.0, 1.0))
    # where scale along Y is sy * rest_len:
    mat = Matrix.Identity(4)
    y_dir = v.normalized()
    ref_y = ref.to_3x3().col[1].normalized()
    rot = ref_y.rotation_difference(y_dir)
    x_dir = (rot @ ref.to_3x3().col[0]).normalized()
    z_dir = (rot @ ref.to_3x3().col[2]).normalized()
    
    mat.col[0] = x_dir.to_4d()
    mat.col[1] = y_dir.to_4d() * sy
    mat.col[2] = z_dir.to_4d()
    mat.col[3] = h.to_4d()
    mat[3][3] = 1.0
    pb.matrix = mat
    bpy.context.view_layer.update()

# Fit Upper Arms & Forearms
sh_head_L = Vector(metarig.data.bones["shoulder.L"].head_local)
sh_head_R = Vector(metarig.data.bones["shoulder.R"].head_local)

fit_bone("shoulder.L", sh_head_L, target_sh_L)
fit_bone("shoulder.R", sh_head_R, target_sh_R)
fit_bone("upper_arm.L", target_sh_L, target_el_L)
fit_bone("upper_arm.R", target_sh_R, target_el_R)
fit_bone("forearm.L", target_el_L, target_wr_L)
fit_bone("forearm.R", target_el_R, target_wr_R)

bpy.context.view_layer.update()

# Freeze mesh shape by applying Armature modifier
bpy.context.view_layer.objects.active = body
bpy.ops.object.mode_set(mode='OBJECT')
for m in list(body.modifiers):
    if m.type == 'ARMATURE':
        bpy.ops.object.modifier_apply(modifier=m.name)
        print("Applied armature modifier on body.")

# Apply pose as rest pose on metarig
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode='OBJECT')
print("Applied pose as rest pose on metarig.")

# Rebind mesh with Armature modifier
arm_mod = body.modifiers.new(name="Armature", type='ARMATURE')
arm_mod.object = metarig

# Check vertex group count and unweighted vertices
unweighted = [v.index for v in body.data.vertices if len(v.groups) == 0]
print("Unweighted vertices count after fit:", len(unweighted))

# Check mesh symmetry and manifold
import bmesh
bm = bmesh.new()
bm.from_mesh(body.data)
non_manifold = [e for e in bm.edges if not e.is_manifold]
print("Non-manifold edges count:", len(non_manifold))
bm.free()

# Check bone positions
ebones = metarig.data.bones
print("New upper_arm.L head:", ebones["upper_arm.L"].head_local)
print("Target shoulder_L:", target_sh_L)
diff = (ebones["upper_arm.L"].head_local - target_sh_L).length
print(f"Difference between bone head and target: {diff*100:.2f} cm")
assert diff < 0.01, f"Difference {diff}m exceeds 1cm!"

print("Fit pipeline test passed successfully!")
